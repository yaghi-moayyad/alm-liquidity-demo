from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient
from cashflows.models import Entity,PortfolioContract,CalculationRun
from cashflows.sample import sample
from cashflows.services import execute_run

class EntityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff=get_user_model().objects.create_user('entity-admin',password='test-only-123',is_staff=True)
        cls.analyst=get_user_model().objects.create_user('reader',password='test-only-456')
    def setUp(self):
        self.client=APIClient();self.client.force_authenticate(self.staff)
    def test_seed_persisted(self):
        entity=Entity.objects.get(slug='jordan-mock')
        self.assertEqual(entity.name,'Jordan-Mock')
        self.assertTrue(entity.is_mock)
        self.assertEqual(entity.portfolio_contracts.count(),86)
        self.assertTrue(entity.configuration.bucket_days)
        rows=self.client.get('/api/v1/entities').data
        self.assertEqual(rows[0]['contract_count'],86)
    def test_create_and_isolate_portfolios(self):
        response=self.client.post('/api/v1/entities',{'slug':'egypt-test','name':'Egypt-Test','country':'Egypt','base_currency':'USD','is_mock':True},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(Entity.objects.get(slug='egypt-test').portfolio_contracts.count(),0)
        p=sample();p.update(entity='egypt-test',expected_revision=1)
        response=self.client.put('/api/v1/entities/egypt-test/portfolio',p,format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['revision'],2)
        self.assertEqual(PortfolioContract.objects.filter(entity__slug='jordan-mock').count(),86)
        run=self.client.post('/api/v1/runs',{k:v for k,v in p.items() if k!='expected_revision'},format='json')
        self.assertEqual(run.status_code,202,run.data)
        execute_run(run.data['id'])
        self.assertEqual(len(self.client.get('/api/v1/runs?entity=egypt-test').data['runs']),1)
        self.assertEqual(self.client.get('/api/v1/runs?entity=jordan-mock').data['runs'],[])
        self.assertEqual(CalculationRun.objects.get(pk=run.data['id']).entity_ref.slug,'egypt-test')
    def test_stale_revision_blocked(self):
        p=sample();p['expected_revision']=1
        self.assertEqual(self.client.put('/api/v1/entities/jordan-mock/portfolio',p,format='json').status_code,200)
        self.assertEqual(self.client.put('/api/v1/entities/jordan-mock/portfolio',p,format='json').status_code,409)
    def test_entity_mismatch_blocked(self):
        p=sample();p.update(entity='missing',expected_revision=1)
        self.assertEqual(self.client.put('/api/v1/entities/jordan-mock/portfolio',p,format='json').status_code,400)
    def test_staff_write_permissions(self):
        self.client.force_authenticate(self.analyst)
        self.assertEqual(self.client.get('/api/v1/entities/jordan-mock/portfolio').status_code,200)
        self.assertEqual(self.client.post('/api/v1/entities',{},format='json').status_code,403)
        self.assertEqual(self.client.put('/api/v1/entities/jordan-mock/portfolio',{},format='json').status_code,403)
    def test_saved_runs_keep_snapshot_after_edit(self):
        payload=sample();job=self.client.post('/api/v1/runs',payload,format='json')
        changed=sample();changed['contracts'][0]['principal']='95000';changed['expected_revision']=1
        self.client.put('/api/v1/entities/jordan-mock/portfolio',changed,format='json')
        self.assertEqual(CalculationRun.objects.get(pk=job.data['id']).input_payload['contracts'][0]['principal'],'120000')
    def test_validation_does_not_persist_run(self):
        r=self.client.post('/api/v1/validate',sample(),format='json')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.data['accepted_count'],11)
        self.assertEqual(CalculationRun.objects.count(),0)
    def test_baseline_seed_is_idempotent(self):
        call_command('seed_demo',username=self.staff.username,verbosity=0)
        call_command('seed_demo',username=self.staff.username,verbosity=0)
        self.assertEqual(CalculationRun.objects.count(),1)
        self.assertEqual(CalculationRun.objects.first().result_summary['accepted_count'],86)
