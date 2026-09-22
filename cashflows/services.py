"""Application service shared by database and Celery workers."""
import hashlib
import json
import logging
from decimal import Decimal
from datetime import date
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .engine import calculate, schedule, VERSION, MAX_SAVED_PORTFOLIO_CONTRACTS, PRODUCTS, PRECISION, add_months
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


DATED_PRODUCTS={'loan','bond','interbank_asset','term_deposit','borrowing'}


def _safe_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def readiness_issue(contract, as_of_date):
    """Return the one actionable contract-term issue, if any.

    This deliberately works on canonical terms, not raw files. A resolution is
    scoped to source table + product + issue and is applied only to a run
    snapshot, exactly like a governed Fusion-style data adjustment.
    """
    # DRF submits ISO strings while persisted Django runs provide date objects.
    # Treat both representations identically at this service boundary.
    as_of_date=_safe_date(as_of_date)
    if not as_of_date:
        return 'invalid_reporting_date'
    if str(contract.get('product')) not in DATED_PRODUCTS:
        return None
    maturity=_safe_date(contract.get('maturity'))
    if not maturity:
        return 'missing_maturity'
    start=_safe_date(contract.get('accrual_start'))
    nxt=_safe_date(contract.get('next_payment'))
    if not start or not nxt:
        return 'missing_schedule_date'
    if not start <= as_of_date < nxt <= maturity:
        return 'invalid_schedule_dates'
    if (nxt-start).days>370:
        return 'long_first_accrual'
    return None


def readiness_group_key(contract, issue):
    return '|'.join((str(contract.get('source_table') or 'canonical'),str(contract.get('product') or 'unknown'),issue))


def _resolution_index(resolutions):
    return {str(item.get('group_key')):item for item in (resolutions or []) if isinstance(item,dict)}


def _candidate_fields(contract):
    values=contract.get('source_date_candidates') or (contract.get('data_quality') or {}).get('source_date_candidates') or {}
    return values if isinstance(values,dict) else {}


def _apply_readiness_resolution(contract, as_of_date, resolutions):
    """Apply one approved, run-only exception rule. Returns (terms, audit).

    ``None`` terms means the user explicitly excluded this exception group.
    Invalid or incomplete decisions are left unresolved so the run cannot start.
    """
    issue=readiness_issue(contract,as_of_date)
    if not issue:
        return contract,None
    resolution=_resolution_index(resolutions).get(readiness_group_key(contract,issue))
    if not resolution:
        return contract,{'issue':issue,'status':'unresolved'}
    action=resolution.get('action')
    if action=='exclude':
        return None,{'issue':issue,'action':'exclude','status':'excluded'}
    adjusted=dict(contract)
    maturity=_safe_date(adjusted.get('maturity'))
    if action=='proxy_maturity' and issue=='missing_maturity':
        proxy=_safe_date(resolution.get('date'))
        if not proxy or proxy<=as_of_date:
            return contract,{'issue':issue,'status':'unresolved','reason':'Proxy maturity must be after reporting date'}
        adjusted['maturity']=proxy.isoformat(); adjusted['maturity_source']='proxy'
        # A dated product still needs a valid schedule; derive a first period
        # from the reporting date when no source payment date exists.
        maturity=proxy; issue=readiness_issue(adjusted,as_of_date)
        if issue=='missing_schedule_date': action='derive_from_reporting_date'
    if action=='use_candidate_date':
        candidate=_safe_date(_candidate_fields(adjusted).get(str(resolution.get('candidate_field'))))
        if not candidate:
            return contract,{'issue':issue,'status':'unresolved','reason':'Selected source date is blank or invalid'}
        nxt=candidate
    elif action=='set_next_payment_date':
        nxt=_safe_date(resolution.get('date'))
    elif action=='derive_from_reporting_date':
        frequency=adjusted.get('frequency_months')
        if frequency not in (1,3,6,12) or not maturity:
            return contract,{'issue':issue,'status':'unresolved','reason':'A supported frequency and maturity are required to derive a schedule'}
        nxt=min(add_months(as_of_date,frequency,bool(adjusted.get('end_of_month',False))),maturity)
    else:
        return contract,{'issue':issue,'status':'unresolved','reason':'This action cannot resolve the exception'}
    frequency=adjusted.get('frequency_months')
    if frequency not in (1,3,6,12) or not nxt or not maturity or not as_of_date<nxt<=maturity:
        return contract,{'issue':issue,'status':'unresolved','reason':'Chosen next payment date must be after reporting date and not after maturity'}
    start=add_months(nxt,-frequency,bool(adjusted.get('end_of_month',False)))
    if start>as_of_date:
        # A next date more than one full period away cannot be made contractual
        # by a simple rule; require a different source date or explicit flows.
        return contract,{'issue':issue,'status':'unresolved','reason':'The selected date is more than one payment period after reporting date'}
    adjusted.update({'accrual_start':start.isoformat(),'next_payment':nxt.isoformat(),
        'readiness_resolution':{'group_key':resolution['group_key'],'action':resolution['action'],
            'date':resolution.get('date'),'candidate_field':resolution.get('candidate_field')}})
    remaining=readiness_issue(adjusted,as_of_date)
    if remaining:
        return contract,{'issue':issue,'status':'unresolved','reason':'The rule does not produce a valid contractual schedule'}
    return adjusted,{'issue':issue,'action':resolution['action'],'status':'applied'}


def _snapshot_terms(terms, policy, as_of_date=None, readiness_resolutions=None):
    """Copy one canonical contract and apply run-only data policies."""
    contract = dict(terms)
    maturity = str(contract.get('maturity') or '').strip()
    if maturity:
        contract.setdefault('maturity_source', 'bank')
    elif policy['enabled']:
        contract['maturity'] = policy['date']
        contract['maturity_source'] = 'proxy'
    else:
        contract.setdefault('maturity_source', 'open')
    if as_of_date is None:
        return contract, False, None
    contract,audit=_apply_readiness_resolution(contract,as_of_date,readiness_resolutions)
    return contract, bool(contract and contract.get('maturity_source')=='proxy'), audit


def _persist_saved_portfolio_snapshot(run, entity, config, as_of_date, readiness_resolutions=None):
    """Persist immutable run terms in batches before the worker is queued.

    A run is therefore reproducible even after the next daily ETL refresh. The
    browser never receives these terms and ``CalculationRun.input_payload``
    keeps only settings and snapshot metadata.
    """
    snapshot, policy = _saved_portfolio_metadata(entity, config, as_of_date)
    batch, proxy_count, excluded, unresolved = [], 0, 0, []
    source = PortfolioContract.objects.filter(entity=entity).order_by('external_id').values_list('external_id', 'terms').iterator(chunk_size=5_000)
    for external_id, terms in source:
        contract, proxy_applied, audit = _snapshot_terms(terms, policy, as_of_date, readiness_resolutions)
        if audit and audit.get('status')=='unresolved':
            unresolved.append({'contract_id':str(external_id),'issue':audit['issue'],'reason':audit.get('reason','Choose a data readiness treatment')})
            if len(unresolved)>=10: break
        if contract is None:
            excluded += 1
            continue
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
    if unresolved:
        raise ValidationError({'data_readiness':{'message':'Resolve data-readiness exceptions before running the calculation.','examples':unresolved}})
    snapshot['proxy_maturity_contract_count'] = proxy_count
    snapshot['data_readiness']={'resolutions':readiness_resolutions or [],'excluded_contract_count':excluded}
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


def _readiness_groups(entity, as_of_date, resolutions, max_examples=5):
    """Aggregate only unresolved exceptions; never send raw rows to React."""
    grouped={}
    source=PortfolioContract.objects.filter(entity=entity).order_by('external_id').values_list('external_id','terms').iterator(chunk_size=5_000)
    for external_id,terms in source:
        issue=readiness_issue(terms,as_of_date)
        if not issue: continue
        _,audit=_apply_readiness_resolution(dict(terms),as_of_date,resolutions)
        if audit and audit.get('status') in {'applied','excluded'}: continue
        key=readiness_group_key(terms,issue)
        item=grouped.setdefault(key,{'key':key,'source_table':str(terms.get('source_table') or 'Canonical portfolio'),
            'product':str(terms.get('product') or 'unknown'),'issue':issue,'contract_count':0,
            'balances':{},'candidate_fields':set(),'examples':[]})
        item['contract_count']+=1
        currency=str(terms.get('currency') or 'UNK')
        try: amount=Decimal(str(terms.get('principal') or 0))
        except Exception: amount=Decimal(0)
        item['balances'][currency]=str(Decimal(item['balances'].get(currency,'0'))+amount)
        item['candidate_fields'].update(_candidate_fields(terms).keys())
        if len(item['examples'])<max_examples: item['examples'].append(str(external_id))
    result=[]
    labels={'missing_maturity':'Missing maturity date','missing_schedule_date':'Missing contractual payment date',
        'invalid_schedule_dates':'Invalid contractual date sequence','long_first_accrual':'First accrual period exceeds 370 days'}
    for item in grouped.values():
        issue=item['issue']; actions=['exclude']
        if issue=='missing_maturity': actions=['proxy_maturity','exclude']
        elif issue in {'missing_schedule_date','invalid_schedule_dates','long_first_accrual'}:
            actions=['use_candidate_date','set_next_payment_date','derive_from_reporting_date','exclude']
        result.append({**item,'issue_label':labels[issue],'candidate_fields':sorted(item['candidate_fields']),
            'allowed_actions':actions})
    return sorted(result,key=lambda item:(item['source_table'],item['product'],item['issue']))


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
    resolutions=payload.get('data_readiness_resolutions') or []
    readiness_groups=_readiness_groups(entity,as_of_date,resolutions)
    accepted=rejected=cashflow_count=0
    exceptions=[]; undated=[]; seen=set()
    scheduled_by_currency={}; generated_by_currency={}; open_by_currency={}
    source=PortfolioContract.objects.filter(entity=entity).order_by('external_id').values_list('external_id','terms').iterator(chunk_size=5_000)
    for index, (external_id, terms) in enumerate(source, start=1):
        contract,_,audit=_snapshot_terms(terms,policy,as_of_date,resolutions)
        if contract is None:
            rejected += 1
            if len(exceptions)<max_examples: exceptions.append({'row':index,'contract_id':str(external_id),'error':'Excluded by approved data readiness rule'})
            continue
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
        'exceptions':exceptions,'undated':undated,'controls':controls,'examples_truncated':rejected>len(exceptions),
        'readiness_groups':readiness_groups}


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
                snapshot, policy = _persist_saved_portfolio_snapshot(run, run.entity_ref, config, run.as_of_date, payload.get('data_readiness_resolutions'))
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
