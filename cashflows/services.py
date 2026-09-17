"""Application service shared by database and Celery workers."""
import hashlib
import json
import logging
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import APIException
from .engine import calculate, VERSION
from .models import CalculationRun, CashFlow, Entity, EntityConfiguration, RunContract, LiquidityAssumptionSet

logger=logging.getLogger(__name__)

class IdempotencyConflict(APIException):
    status_code=409
    default_detail='This Idempotency-Key was already used with a different request.'


def input_fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def hydrate_run_payload(payload):
    """Attach saved settings and behavioural rules so each run is reproducible."""
    hydrated=dict(payload)
    config=EntityConfiguration.objects.get(entity__slug=payload['entity'])
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
        }
    return hydrated


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
        result=calculate(run.input_payload,progress)
        flows=result.pop('cashflows')
        contracts=result.pop('contracts')
        with transaction.atomic():
            # Mark-interrupted recovery is only used once the old worker has stopped.
            current=CalculationRun.objects.select_for_update().get(pk=run_id)
            if current.status != 'running': return False
            for start in range(0,len(flows),1000):
                CashFlow.objects.bulk_create([CashFlow(run_id=run_id,sequence=i,**flow)
                    for i,flow in enumerate(flows[start:start+1000],start)],batch_size=1000)
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
