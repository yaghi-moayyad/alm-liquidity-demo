import copy
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from cashflows.models import CalculationRun,CashFlow,Entity
from cashflows.sample import sample
from cashflows.services import execute_run,dispatch_run
from cashflows.tasks import calculate_run

class DjangoApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=get_user_model().objects.create_user('analyst',password='test-only-password-123')
        cls.other=get_user_model().objects.create_user('other',password='test-only-password-456')
    def setUp(self):
        self.client=APIClient()
        self.client.force_authenticate(self.user)
    def submit(self,key=None,payload=None):
        kwargs={'HTTP_IDEMPOTENCY_KEY':key} if key else {}
        return self.client.post('/api/v1/runs',payload or sample(),format='json',**kwargs)
    def completed(self):
        response=self.submit()
        self.assertEqual(response.status_code,202,response.data)
        run=CalculationRun.objects.get(pk=response.data['id'])
        call_command('runworker',once=True,verbosity=0)
        run.refresh_from_db()
        self.assertEqual(run.status,'completed')
        return run
    def test_worker_pipeline_and_orm_persistence(self):
        run=self.completed()
        self.assertEqual(run.owner,self.user)
        expected=sample();expected.update({'interest_projection':'constant','forward_curve':Entity.objects.get(slug='jordan-mock').configuration.forward_curve})
        self.assertEqual(run.input_payload,expected)
        self.assertEqual(run.result_summary['accepted_count'],11)
        self.assertGreater(run.cashflows.count(),0)
        self.assertNotIn('cashflows',run.result_summary)
        self.assertNotIn('contracts',run.result_summary)
        self.assertEqual(run.contract_index.count(),11)
        self.assertIsNotNone(run.finished)
    def test_authentication_required(self):
        client=APIClient()
        self.assertIn(client.get('/api/v1/runs').status_code,(401,403))
        self.assertEqual(client.get('/api/v1/health').status_code,200)
        self.assertEqual(client.get('/').status_code,302)
    def test_owner_isolation(self):
        run=self.completed()
        self.client.force_authenticate(self.other)
        for suffix in ('','/input','/cashflows','/summary.csv','/result.json'):
            self.assertEqual(self.client.get(f'/api/v1/runs/{run.pk}{suffix}').status_code,404)
        self.assertEqual(self.client.get('/api/v1/runs').data['runs'],[])
    def test_idempotency_and_conflict(self):
        first=self.submit('same-key')
        again=self.submit('same-key')
        self.assertEqual(again.status_code,200)
        self.assertTrue(again.data['reused'])
        self.assertEqual(first.data['id'],again.data['id'])
        self.assertEqual(CalculationRun.objects.count(),1)
        changed=sample();changed['bucket_days']=[1,7]
        self.assertEqual(self.submit('same-key',changed).status_code,409)
    def test_idempotency_scoped_to_user(self):
        self.submit('same-key')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.submit('same-key').status_code,202)
        self.assertEqual(CalculationRun.objects.count(),2)
    def test_duplicate_task_does_not_duplicate_flows(self):
        run=self.completed();n=run.cashflows.count()
        self.assertFalse(execute_run(run.id))
        self.assertEqual(run.cashflows.count(),n)
    def test_partial_result_exceptions(self):
        payload=sample();payload['contracts'][0]['rate_type']='floating'
        response=self.submit(payload=payload)
        execute_run(response.data['id'])
        data=self.client.get(response.data['status_url']).data
        self.assertEqual(data['status'],'completed')
        self.assertEqual(data['result']['rejected_count'],0)
    def test_validation(self):
        for change in ({'bucket_days':[7,1]},{'bucket_days':[True,7]},{'bucket_days':[1.1,7]},
                       {'entity':'Other'},{'unknown':'x'},{'contracts':[]}):
            payload=sample();payload.update(change)
            with self.subTest(change=change):
                self.assertEqual(self.submit(payload=payload).status_code,400)
        self.assertEqual(CalculationRun.objects.count(),0)
    def test_pagination_and_decimals(self):
        run=self.completed()
        response=self.client.get(f'/api/v1/runs/{run.pk}/cashflows',{'currency':'USD','limit':2})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.data['cashflows']),2)
        self.assertGreater(response.data['total'],2)
        self.assertTrue(all(f['currency']=='USD' for f in response.data['cashflows']))
        self.assertEqual(len(response.data['cashflows'][0]['principal'].split('.')[1]),2)
        self.assertEqual(self.client.get(f'/api/v1/runs/{run.pk}/cashflows',{'limit':1001}).status_code,400)

    def test_contract_search_is_indexed_and_prefix_based(self):
        run=self.completed()
        response=self.client.get(f'/api/v1/runs/{run.pk}/contracts',{'q':'LN'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['query'],'LN')
        self.assertEqual([row['contract_id'] for row in response.data['contracts']],['LN-1001','LN-1002','LN-1003'])
        self.assertEqual(self.client.get(f'/api/v1/runs/{run.pk}/contracts',{'q':'L'}).status_code,400)
    def test_csv_and_snapshot(self):
        run=self.completed()
        for suffix in ('summary.csv','cashflows.csv'):
            response=self.client.get(f'/api/v1/runs/{run.pk}/{suffix}')
            self.assertEqual(response.status_code,200)
            content=b''.join(response.streaming_content).decode('utf-8-sig')
            self.assertIn('currency',content)
            self.assertIn('JOD',content)
        expected=sample();expected.update({'interest_projection':'constant','forward_curve':Entity.objects.get(slug='jordan-mock').configuration.forward_curve})
        self.assertEqual(self.client.get(f'/api/v1/runs/{run.pk}/input').data,expected)
        result=self.client.get(f'/api/v1/runs/{run.pk}/result.json').data
        self.assertEqual(len(result['cashflows']),run.cashflows.count())
    def test_token_authentication(self):
        client=APIClient()
        token=Token.objects.create(user=self.user)
        client.credentials(HTTP_AUTHORIZATION='Token '+token.key)
        self.assertEqual(client.get('/api/v1/sample').status_code,200)
    def test_session_csrf_and_ui(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username='analyst',password='test-only-password-123'))
        page=client.get('/')
        self.assertEqual(page.status_code,200)
        self.assertContains(page,'/static/app/assets/')
        self.assertContains(page,'ALM Workspace')
        self.assertEqual(client.post('/api/v1/runs',sample(),format='json').status_code,403)
        csrf=client.cookies['csrftoken'].value
        self.assertEqual(client.post('/api/v1/runs',sample(),format='json',HTTP_X_CSRFTOKEN=csrf).status_code,202)
        self.assertEqual(client.post('/api/v1/runs',sample(),format='json',HTTP_X_CSRFTOKEN=csrf,HTTP_ORIGIN='https://example.com').status_code,403)
    def test_schema_and_docs(self):
        response=self.client.get('/api/v1/schema',HTTP_ACCEPT='application/vnd.oai.openapi+json')
        self.assertEqual(response.status_code,200)
        self.assertIn('/api/v1/runs',response.data['paths'])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api-docs').status_code,200)
    def test_queued_results_not_ready(self):
        run=self.submit().data
        self.assertEqual(self.client.get(run['status_url']+'/cashflows').status_code,409)
    def test_real_celery_task_entrypoint(self):
        run=self.submit().data
        task=calculate_run.apply(args=[run['id']])
        self.assertTrue(task.successful())
        self.assertEqual(CalculationRun.objects.get(pk=run['id']).status,'completed')
    @override_settings(TASK_BACKEND='celery')
    @patch('cashflows.tasks.calculate_run.delay')
    def test_celery_dispatch_adapter(self,delay):
        with self.captureOnCommitCallbacks(execute=True): response=self.submit()
        delay.assert_called_once_with(str(response.data['id']))
