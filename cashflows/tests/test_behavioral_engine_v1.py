import unittest
from decimal import Decimal as D
from cashflows.engine import calculate


class BehavioralEngineV1Tests(unittest.TestCase):
    def payload(self):
        return {
            'entity':'jordan-test','as_of_date':'2026-01-01','bucket_days':[1,7,14,30,60,90,180,365,730],
            'interest_projection':'constant','calculation_basis':'behavioral','forward_curve':[],
            'contracts':[
                {'contract_id':'LN1','product':'loan','currency':'JOD','principal':'1200.000','annual_rate':'0.12','repayment':'equal_principal','day_count':'30E/360','frequency_months':1,'accrual_start':'2026-01-01','next_payment':'2026-02-01','maturity':'2026-04-01','liquidity_group':'Retail Time','liquidity_product':'PersonalLoan'},
                {'contract_id':'TD1','product':'term_deposit','currency':'JOD','principal':'1000.000','annual_rate':'0.04','repayment':'bullet','day_count':'ACT/365F','frequency_months':3,'accrual_start':'2026-01-01','next_payment':'2026-04-01','maturity':'2026-07-01','liquidity_group':'Retail Time','liquidity_product':'TimeDeposit'},
                {'contract_id':'CASA1','product':'demand_deposit','currency':'JOD','principal':'1000.000','liquidity_group':'Retail Call','liquidity_product':'CurrentAccount'},
                {'contract_id':'SEC1','product':'bond','currency':'JOD','principal':'1000.000','annual_rate':'0.03','repayment':'bullet','day_count':'ACT/365F','frequency_months':6,'accrual_start':'2026-01-01','next_payment':'2026-07-01','maturity':'2026-07-01','liquidity_group':'Marketable Securities & CDs','liquidity_product':'Tbond'},
            ],
            'product_treatments':[
                {'product_group':'Retail Time','product_type':'PersonalLoan','cashflow_treatment':'hybrid'},
                {'product_group':'Retail Time','product_type':'TimeDeposit','cashflow_treatment':'hybrid'},
                {'product_group':'Retail Call','product_type':'CurrentAccount','cashflow_treatment':'behavioral'},
                {'product_group':'Marketable Securities & CDs','product_type':'Tbond','cashflow_treatment':'hybrid'},
            ],
            'behavioral_assumption_set':{'name':'Test','version':1,'base_currency':'JOD','rules':[
                {'id':1,'category':'loan_prepayment','title':'Loan prepay','product_group':'Retail Time','product_type':'PersonalLoan','currency_scope':'ALL','value':{'curve':[{'days':30,'cumulative':'0.25'}]},'enabled':True,'sort_order':1},
                {'id':2,'category':'term_deposit_early_withdrawal','title':'TD early withdrawal','product_group':'Retail Time','product_type':'TimeDeposit','currency_scope':'ALL','value':{'curve':[{'days':30,'cumulative':'0.20'}]},'enabled':True,'sort_order':1},
                {'id':3,'category':'term_deposit_rollover','title':'TD rollover','product_group':'Retail Time','product_type':'TimeDeposit','currency_scope':'ALL','value':{'rollover_rate':'0.50','tenor_days':90},'enabled':True,'sort_order':2},
                {'id':4,'category':'deposit_runoff','title':'CASA runoff','product_group':'Retail Call','product_type':'CurrentAccount','currency_scope':'ALL','value':{'curve':[{'days':1,'cumulative':'0.10'},{'days':30,'cumulative':'0.30'}]},'enabled':True,'sort_order':1},
                {'id':5,'category':'security_liquidation','title':'Tbond liquidation','product_group':'Marketable Securities & CDs','product_type':'Tbond','currency_scope':'ALL','value':{'timing':'1w'},'enabled':True,'sort_order':1},
                {'id':6,'category':'security_haircut','title':'Tbond haircut','product_group':'Marketable Securities & CDs','product_type':'Tbond','currency_scope':'ALL','value':{'haircut':'0.10'},'enabled':True,'sort_order':2},
            ]},
        }

    def test_behavioural_principal_is_conserved_for_dated_products(self):
        result=calculate(self.payload())
        for contract_id, expected in [('LN1',D('1200.000')),('TD1',D('1000.000'))]:
            actual=sum(D(flow['principal']) for flow in result['behavioral_cashflows'] if flow['contract_id']==contract_id)
            self.assertEqual(actual,expected)

    def test_nmd_runoff_creates_events_and_residual_balance(self):
        result=calculate(self.payload())
        casa=[flow for flow in result['behavioral_cashflows'] if flow['contract_id']=='CASA1']
        self.assertEqual([D(flow['principal']) for flow in casa],[D('100.000'),D('200.000')])
        adjustment=next(item for item in result['behavioral_adjustments'] if item['contract_id']=='CASA1')
        self.assertEqual(D(adjustment['residual']),D('700.000'))
        rows={row['key']:row for row in result['behavioral_bank_ladder']['JOD']['rows']}
        self.assertEqual(D(rows['retail_call_out']['balance']),D('1000.000'))

    def test_rollover_moves_remaining_maturity_principal(self):
        result=calculate(self.payload())
        td=[flow for flow in result['behavioral_cashflows'] if flow['contract_id']=='TD1']
        rollover=next(flow for flow in td if flow.get('behavioral_source')=='term_deposit_rollover')
        self.assertEqual(D(rollover['principal']),D('400.000'))
        self.assertEqual(rollover['payment_date'],'2026-09-29')

    def test_term_deposit_early_withdrawal_is_a_separate_auditable_event(self):
        result=calculate(self.payload())
        td=[flow for flow in result['behavioral_cashflows'] if flow['contract_id']=='TD1']
        early=next(flow for flow in td if flow.get('behavioral_source')=='term_deposit_early_withdrawal')
        self.assertEqual(D(early['principal']),D('200.000'))
        self.assertEqual(early['behavioral_rule_title'],'TD early withdrawal')

    def test_security_liquidation_haircut_moves_capacity_without_double_counting(self):
        result=calculate(self.payload())
        security=next(flow for flow in result['behavioral_cashflows'] if flow['contract_id']=='SEC1')
        self.assertEqual(security['behavioral_source'],'security_liquidation')
        self.assertEqual(D(security['principal']),D('900.000'))
        adjustment=next(item for item in result['behavioral_adjustments'] if item['contract_id']=='SEC1')
        self.assertEqual(adjustment['category'],'security_liquidation')
        self.assertEqual(D(adjustment['amount']),D('900.000'))
        rows={row['key']:row for row in result['behavioral_bank_ladder']['JOD']['rows']}
        self.assertEqual(D(rows['marketable_securities']['balance']),D('1000.000'))
        self.assertEqual(sum(D(v) for v in rows['marketable_securities']['principal']),D('900.000'))

    def test_contractual_treatment_ignores_behavioral_timing_rule(self):
        payload=self.payload()
        next(item for item in payload['product_treatments'] if item['product_type']=='PersonalLoan')['cashflow_treatment']='contractual'
        result=calculate(payload)
        loan=[flow for flow in result['behavioral_cashflows'] if flow['contract_id']=='LN1']
        self.assertFalse(any(flow.get('behavioral_source')=='loan_prepayment' for flow in loan))

    def test_contractual_basis_does_not_run_behavioural_engine(self):
        payload=self.payload();payload['calculation_basis']='contractual'
        result=calculate(payload)
        self.assertEqual(result['behavioral_cashflow_count'],0)
        self.assertFalse(result['behavioral_bank_ladder'])
        self.assertIsNone(result['behavioral_engine'])


if __name__=='__main__':
    unittest.main()
