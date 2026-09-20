from datetime import date
from types import SimpleNamespace
from decimal import Decimal
from django.test import TestCase
from cashflows.regulatory_engine import calculate_regulatory

class RegulatoryEngineTests(TestCase):
    def _mapping(self, product, lcr, nsfr):
        return SimpleNamespace(source_product=product,liquidity_group='',liquidity_product='',title=product,lcr_treatment=lcr,nsfr_treatment=nsfr,active=True)
    def _contract(self,cid,product,principal,maturity=None,currency='JOD'):
        terms={'contract_id':cid,'product':product,'principal':str(principal),'currency':currency}
        if maturity: terms['maturity']=maturity
        return SimpleNamespace(external_id=cid,terms=terms)
    def _config(self):
        return SimpleNamespace(reporting_currency='JOD',fx_to_reporting={'JOD':'1','USD':'0.70'},lcr_inflow_cap=Decimal('0.75'))

    def test_lcr_inflow_cap_and_ratio(self):
        entity=SimpleNamespace(base_currency='JOD')
        mappings=[
            self._mapping('cash',{'kind':'hqla','line_code':'H','factor':'1'},{'side':'RSF','line_code':'C','factor':'0'}),
            self._mapping('dep',{'kind':'outflow','line_code':'O','factor':'0.10'},{'side':'ASF','line_code':'D','factor':'0.90'}),
            self._mapping('loan',{'kind':'inflow','line_code':'I','factor':'1','within_days':30},{'side':'RSF','line_code':'L','factor':'0.50'}),
        ]
        contracts=[self._contract('cash1','cash',100),self._contract('dep1','dep',1000),self._contract('loan1','loan',500,'2026-01-15')]
        result=calculate_regulatory(entity,contracts,mappings,self._config(),date(2025,12,31))
        self.assertEqual(result['lcr']['gross_outflows'],'100.000')
        self.assertEqual(result['lcr']['gross_inflows'],'500.000')
        self.assertEqual(result['lcr']['eligible_inflows'],'75.000')
        self.assertEqual(result['lcr']['net_cash_outflows'],'25.000')
        self.assertEqual(result['lcr']['ratio'],'400.00')

    def test_nsfr_maturity_factor(self):
        entity=SimpleNamespace(base_currency='JOD')
        mapping=self._mapping('fund',{'kind':'excluded'},{'side':'ASF','line_code':'ASF','factors':{'<6m':'0','6-12m':'0.5','>=1y':'1','open':'0'}})
        contracts=[self._contract('a','fund',100,'2026-03-31'),self._contract('b','fund',100,'2026-09-30'),self._contract('c','fund',100,'2027-12-31')]
        result=calculate_regulatory(entity,contracts,[mapping],self._config(),date(2025,12,31))
        self.assertEqual(result['nsfr']['asf'],'150.000')

    def test_missing_mapping_is_flagged(self):
        entity=SimpleNamespace(base_currency='JOD')
        result=calculate_regulatory(entity,[self._contract('x','unknown',10)],[],self._config(),date(2025,12,31))
        self.assertFalse(result['controls']['complete_mapping'])
        self.assertEqual(result['warnings'][0]['type'],'unmapped_product')
