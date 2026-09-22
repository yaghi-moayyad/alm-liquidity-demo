"""Application service shared by database and Celery workers."""
import hashlib
import json
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .engine import calculate, schedule, VERSION, MAX_SAVED_PORTFOLIO_CONTRACTS, PRODUCTS, PRECISION
from .models import CalculationRun, CashFlow, Entity, EntityConfiguration, PortfolioContract, RunContract, LiquidityAssumptionSet, ProductCatalogueItem

logger=logging.getLogger(__name__)

class IdempotencyConflict(APIException):
    status_code=409
    default_detail='This Idempotency-Key was already used with a different request.'


def input_fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def _saved_portfolio_metadata(entity, config, as_of_date):
    """Return controlled saved-portfolio metadata without loading its terms."""
    policy = {
        'enabled': bool(config.proxy_maturity_enabled),
        'date': config.proxy_maturity_date.isoformat() if config.proxy_maturity_date else None,
        'scope': config.proxy_maturity_scope or {'mode': 'all_missing_maturity'},
        'version': config.revision,
    }
    if policy['enabled']:
        if not config.proxy_maturity_date:
            raise ValidationError({'proxy_maturity_date': 'Set a proxy maturity date before enabling the policy.'})
        if config.proxy_maturity_date <= as_of_date:
            raise ValidationError({'proxy_maturity_date': 'Proxy maturity must be after the reporting date.'})

    total = PortfolioContract.objects.filter(entity=entity).count()
    if not total:
        raise ValidationError({'portfolio': 'The saved portfolio is empty.'})
    if total > MAX_SAVED_PORTFOLIO_CONTRACTS:
        raise ValidationError({'portfolio': f'Saved portfolio exceeds the governed limit of {MAX_SAVED_PORTFOLIO_CONTRACTS:,} contracts.'})

    return {
        'source': 'saved_portfolio', 'portfolio_revision': config.revision,
        'contract_count': total,
    }, policy


def _snapshot_terms(terms, policy):
    """Copy one canonical contract and apply a run-only proxy maturity policy."""
    contract = dict(terms)
    maturity = str(contract.get('maturity') or '').strip()
    if maturity:
        contract.setdefault('maturity_source', 'bank')
        return contract, False
    if policy['enabled']:
        contract['maturity'] = policy['date']
        contract['maturity_source'] = 'proxy'
        return contract, True
    contract.setdefault('maturity_source', 'open')
    return contract, False


def _persist_saved_portfolio_snapshot(run, entity, config, as_of_date):
    """Persist immutable run terms in batches before the worker is queued.

    A run is therefore reproducible even after the next daily ETL refresh. The
    browser never receives these terms and ``CalculationRun.input_payload``
    keeps only settings and snapshot metadata.
    """
    snapshot, policy = _saved_portfolio_metadata(entity, config, as_of_date)
    batch, proxy_count = [], 0
    source = PortfolioContract.objects.filter(entity=entity).order_by('external_id').values_list('external_id', 'terms').iterator(chunk_size=5_000)
    for external_id, terms in source:
        contract, proxy_applied = _snapshot_terms(terms, policy)
        proxy_count += int(proxy_applied)
        # ``external_id`` is the entity's unique canonical identifier.  Do
        # not let a stale JSON value turn a source refresh into a duplicate
        # run-snapshot key.
        contract_id = str(external_id)
        contract['contract_id'] = contract_id
        product = str(contract.get('product') or 'unknown')
        currency = str(contract.get('currency') or 'UNK').upper()[:3]
        batch.append(RunContract(
            run=run, contract_id=contract_id, contract_id_key=contract_id.upper(),
            product=product, currency=currency, direction=PRODUCTS.get(product, 'unknown'), terms=contract,
        ))
        if len(batch) >= 5_000:
            RunContract.objects.bulk_create(batch, batch_size=5_000)
            batch = []
    if batch:
        RunContract.objects.bulk_create(batch, batch_size=5_000)
    snapshot['proxy_maturity_contract_count'] = proxy_count
    return snapshot, policy


def hydrate_run_payload(payload):
    """Attach server-side portfolio, settings and behavioural rules to a reproducible run."""
    hydrated=dict(payload)
    entity=Entity.objects.get(slug=payload['entity'])
    config=EntityConfiguration.objects.get(entity=entity)
    as_of_date=payload['as_of_date']
    if isinstance(as_of_date, str):
        from datetime import date
        as_of_date=date.fromisoformat(as_of_date)
    if payload.get('use_saved_portfolio'):
        snapshot, policy = _saved_portfolio_metadata(entity, config, as_of_date)
        hydrated['calculation_source'] = 'saved_portfolio'
        hydrated['portfolio_snapshot'] = snapshot
        hydrated['proxy_maturity_policy'] = policy
    hydrated['interest_projection']=config.interest_projection
    hydrated['forward_curve']=config.forward_curve
    assumption_set = (LiquidityAssumptionSet.objects.filter(entity__slug=payload['entity'], status='active')
                      .prefetch_related('rules').first())
    if assumption_set:
        hydrated['behavioral_assumption_set']={
            'id': assumption_set.pk, 'name': assumption_set.name, 'version': assumption_set.version,
            'effective_date': assumption_set.effective_date.isoformat(), 'source': assumption_set.source,
            'base_currency': config.entity.base_currency,
            'rules': [{'id':rule.pk, 'category':rule.category, 'title':rule.title, 'product_group':rule.product_group,
                'product_type':rule.product_type, 'currency_scope':rule.currency_scope,
                'maturity_breakdown':rule.maturity_breakdown, 'value':rule.value, 'enabled':rule.enabled}
                for rule in assumption_set.rules.all()],
            'product_treatments': [{'product_group':item.product_group,'product_type':item.product_type,
                'treatment':item.cash_flow_treatment} for item in ProductCatalogueItem.objects.filter(entity=config.entity,active=True)],
        }
    return hydrated


def preflight_saved_portfolio(payload, max_examples=100):
    """Validate a saved portfolio without constructing a full report in HTTP.

    This is a readiness check for the guided New Calculation screen. It scans
    all canonical terms server-side, retains only a bounded set of examples,
    and leaves the full cash-flow result to the queued calculation worker.
    """
    entity=Entity.objects.get(slug=payload['entity'])
    config=EntityConfiguration.objects.get(entity=entity)
    as_of_date=payload['as_of_date']
    if isinstance(as_of_date,str):
        from datetime import date
        as_of_date=date.fromisoformat(as_of_date)
    _, policy=_saved_portfolio_metadata(entity,config,as_of_date)
    accepted=rejected=cashflow_count=0
    exceptions=[]; undated=[]; seen=set()
    scheduled_by_currency={}; generated_by_currency={}; open_by_currency={}
    source=PortfolioContract.objects.filter(entity=entity).order_by('external_id').values_list('external_id','terms').iterator(chunk_size=5_000)
    for index, (external_id, terms) in enumerate(source, start=1):
        contract,_=_snapshot_terms(terms,policy)
        contract['contract_id']=str(external_id)
        cid=str(contract.get('contract_id','?')) if isinstance(contract,dict) else '?'
        try:
            if cid in seen:
                raise ValueError('Duplicate contract_id in the saved portfolio; correct the source mapping before calculation')
            seen.add(cid)
            base, flows, open_item=schedule(contract,as_of_date,{**payload,'interest_projection':config.interest_projection,'forward_curve':config.forward_curve})
            accepted += 1
            cashflow_count += len(flows)
            currency=base['currency']; quantum=PRECISION[currency]
            scheduled_by_currency.setdefault(currency,Decimal(0)); generated_by_currency.setdefault(currency,Decimal(0)); open_by_currency.setdefault(currency,Decimal(0))
            if base['product'] not in ('demand_deposit','cash_central_bank') or base.get('maturity_source') == 'proxy':
                scheduled_by_currency[currency] += Decimal(base['principal'])
            generated_by_currency[currency] += sum((Decimal(flow['principal']) for flow in flows),Decimal(0))
            if open_item and open_item.get('product') == 'demand_deposit':
                open_by_currency[currency] += Decimal(open_item['balance'])
                if len(undated)<max_examples: undated.append(open_item)
        except (ValueError,TypeError,OverflowError,ArithmeticError) as error:
            rejected += 1
            if len(exceptions)<max_examples:
                exceptions.append({'row':index,'contract_id':cid,'error':str(error) or 'Invalid contract terms'})
    controls=[]
    for currency in sorted(set(scheduled_by_currency)|set(generated_by_currency)|set(open_by_currency)):
        quantum=PRECISION[currency]; scheduled=scheduled_by_currency.get(currency,Decimal(0)); generated=generated_by_currency.get(currency,Decimal(0)); opened=open_by_currency.get(currency,Decimal(0))
        controls.append({'currency':currency,'scheduled_balance':str(scheduled.quantize(quantum)),
            'generated_principal':str(generated.quantize(quantum)),'difference':str((scheduled-generated).quantize(quantum)),
            'undated_balance':str(opened.quantize(quantum)),'passed':scheduled==generated})
    return {'accepted_count':accepted,'rejected_count':rejected,'cashflow_count':cashflow_count,
        'exceptions':exceptions,'undated':undated,'controls':controls,'examples_truncated':rejected>len(exceptions)}


def submit_run(owner,payload,key=None):
    payload=hydrate_run_payload(payload)
    fingerprint=input_fingerprint(payload)
    if key:
        existing=CalculationRun.objects.filter(owner=owner,idempotency_key=key).first()
        if existing:
            if existing.input_hash != fingerprint: raise IdempotencyConflict()
            return existing,True
    try:
        with transaction.atomic():
            run=CalculationRun.objects.create(owner=owner,entity=payload['entity'],entity_ref=Entity.objects.get(slug=payload['entity']),as_of_date=payload['as_of_date'],
                input_payload=payload,input_hash=fingerprint,engine_version=VERSION,idempotency_key=key)
            if payload.get('calculation_source') == 'saved_portfolio':
                config=EntityConfiguration.objects.select_for_update().get(entity=run.entity_ref)
                snapshot, policy = _persist_saved_portfolio_snapshot(run, run.entity_ref, config, run.as_of_date)
                payload['portfolio_snapshot'] = snapshot
                payload['proxy_maturity_policy'] = policy
                run.input_payload = payload
                # Keep the idempotency fingerprint based on the submitted
                # request/configuration. Snapshot counts are operational
                # metadata, not a second user request.
                run.save(update_fields=['input_payload'])
            transaction.on_commit(lambda:dispatch_run(run.pk))
    except IntegrityError:
        if not key: raise
        run=CalculationRun.objects.get(owner=owner,idempotency_key=key)
        if run.input_hash != fingerprint: raise IdempotencyConflict()
        return run,True
    return run,False


def dispatch_run(run_id):
    if settings.TASK_BACKEND == 'inline':
        # Small public-demo deployments have no separate worker.  This keeps the
        # API-first flow functional while preserving the normal Celery path for
        # production-scale deployments.
        execute_run(run_id)
        return
    if settings.TASK_BACKEND == 'celery':
        from .tasks import calculate_run
        try:
            calculate_run.delay(str(run_id))
        except Exception:
            # Durable queued row remains recoverable if the broker cannot accept the message.
            CalculationRun.objects.filter(pk=run_id,status='queued').update(error='Broker unavailable; run remains queued. Restore broker and use dispatch_runs.')
            logger.exception('Could not dispatch run %s',run_id)


def execute_run(run_id):
    now=timezone.now()
    claimed=CalculationRun.objects.filter(pk=run_id,status='queued').update(status='running',started=now,heartbeat=now,error='')
    if not claimed: return False
    try:
        run=CalculationRun.objects.get(pk=run_id)
        def progress(done,total):
            CalculationRun.objects.filter(pk=run_id,status='running').update(progress=int(100*done/total),heartbeat=timezone.now())
        input_payload = dict(run.input_payload)
        saved_snapshot = input_payload.get('calculation_source') == 'saved_portfolio'
        if saved_snapshot:
            input_payload['contracts'] = list(
                run.contract_index.exclude(terms__isnull=True).order_by('contract_id').values_list('terms', flat=True).iterator(chunk_size=5_000)
            )
        result=calculate(input_payload,progress)
        flows=result.pop('cashflows')
        contracts=result.pop('contracts')
        with transaction.atomic():
            # Mark-interrupted recovery is only used once the old worker has stopped.
            current=CalculationRun.objects.select_for_update().get(pk=run_id)
            if current.status != 'running': return False
            for start in range(0,len(flows),1000):
                CashFlow.objects.bulk_create([CashFlow(run_id=run_id,sequence=i,**flow)
                    for i,flow in enumerate(flows[start:start+1000],start)],batch_size=1000)
            if not saved_snapshot:
                for start in range(0,len(contracts),1000):
                    RunContract.objects.bulk_create([RunContract(run_id=run_id, contract_id=item['contract_id'],
                        contract_id_key=item['contract_id'].upper(), product=item['product'], currency=item['currency'],
                        direction=item['direction']) for item in contracts[start:start+1000]], batch_size=1000)
            current.result_summary=result
            current.status=result['status']
            current.progress=100
            current.finished=timezone.now()
            current.heartbeat=current.finished
            current.error=''
            current.save(update_fields=['result_summary','status','progress','finished','heartbeat','error'])
        return True
    except Exception:
        logger.exception('Calculation failed for run %s',run_id)
        CalculationRun.objects.filter(pk=run_id,status='running').update(status='failed',finished=timezone.now(),error='Calculation failed. Consult the worker log for the error.')
        return False
