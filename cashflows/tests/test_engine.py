import unittest
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal as D
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cashflows.engine import calculate, schedule, year_fraction, add_months, validate_config
from cashflows.sample import sample


def contract(**kwargs):
    c=dict(contract_id='A1',product='loan',currency='JOD',principal='1200.000',annual_rate='0.12',
           repayment='equal_principal',day_count='30E/360',frequency_months=1,
           accrual_start='2026-01-01',next_payment='2026-02-01',maturity='2026-04-01')
    c.update(kwargs)
    return c

class EngineTests(unittest.TestCase):
    def test_equal_principal_hand_calculation(self):
        _,f,_=schedule(contract(),date(2026,1,1))
        self.assertEqual([x['principal'] for x in f],['400.000']*3)
        self.assertEqual([x['interest'] for x in f],['12.000','8.000','4.000'])
        self.assertEqual(f[-1]['remaining_principal'],'0.000')

    def test_bullet_actual_360_leap_year(self):
        c=contract(principal='100000',annual_rate='.036',repayment='bullet',day_count='ACT/360',
                   accrual_start='2024-01-01',next_payment='2024-07-01',maturity='2024-07-01')
        _,f,_=schedule(c,date(2024,1,1))
        self.assertEqual(f[0]['interest'],'1820.000')
        self.assertEqual(f[0]['principal'],'100000.000')

    def test_level_payment_matches_independent_annuity_formula(self):
        _,f,_=schedule(contract(repayment='level_payment'),date(2026,1,1))
        expected=(D(1200)*D('.01')/(1-(1+D('.01'))**-3)).quantize(D('.001'))
        self.assertEqual(D(f[0]['total']),expected)
        self.assertEqual(D(f[1]['total']),expected)
        self.assertEqual(sum(D(x['principal']) for x in f),D(1200))
        self.assertLess(abs(D(f[-1]['total'])-expected),D('.003'))

    def test_zero_rate_level_payment(self):
        _,f,_=schedule(contract(annual_rate='0',repayment='level_payment'),date(2026,1,1))
        self.assertEqual([x['total'] for x in f],['400.000']*3)

    def test_stub_and_end_of_month(self):
        c=contract(accrual_start='2026-01-31',next_payment='2026-02-28',maturity='2026-05-15',end_of_month=True)
        _,f,_=schedule(c,date(2026,1,31))
        self.assertEqual([x['payment_date'] for x in f],['2026-02-28','2026-03-31','2026-04-30','2026-05-15'])
        self.assertEqual(sum(D(x['principal']) for x in f),D(1200))

    def test_day_count_conventions(self):
        self.assertEqual(year_fraction(date(2024,2,28),date(2024,3,1),'ACT/365F'),D(2)/D(365))
        self.assertEqual(year_fraction(date(2026,1,31),date(2026,2,28),'30E/360'),D(28)/D(360))
        self.assertEqual(add_months(date(2026,1,31),2),date(2026,3,31))

    def test_buckets_boundaries_and_currency_separation(self):
        a=contract(repayment='bullet',next_payment='2026-01-08',maturity='2026-01-08')
        b=contract(contract_id='B',product='term_deposit',currency='USD',repayment='bullet',next_payment='2026-01-09',maturity='2026-01-09')
        r=calculate(dict(as_of_date='2026-01-01',bucket_days=[1,7],contracts=[a,b]))
        self.assertEqual(r['summary']['JOD'][1]['inflow_principal'],'1200.000')
        self.assertEqual(r['summary']['USD'][2]['outflow_principal'],'1200.00')
        self.assertEqual(r['cashflows'][0]['days_from_asof'],7)

    def test_demo_control_totals(self):
        r=calculate(sample())
        self.assertEqual(r['status'],'completed')
        self.assertEqual(r['accepted_count'],11)
        self.assertTrue(all(c['passed'] for c in r['controls']))
        self.assertEqual(len(r['undated']),1)
        self.assertNotIn('CASA-6001',{x['contract_id'] for x in r['cashflows']})
        for cur,rows in r['summary'].items():
            net=sum((D(f['total'])*(1 if f['direction']=='inflow' else -1) for f in r['cashflows'] if f['currency']==cur),D(0))
            self.assertEqual(D(rows[-1]['cumulative_gap']),net)

    def test_bank_ladder_asof_balance_is_principal_only(self):
        r = calculate(sample())
        ladder = r['bank_ladder']['JOD']
        rows = {row['key']: row for row in ladder['rows']}
        retail_time = rows['retail_time_out']
        self.assertEqual(D(retail_time['balance']), sum(D(v) for v in retail_time['principal']))
        self.assertNotEqual(D(retail_time['balance']), sum(D(v) for v in retail_time['total']))
        self.assertEqual(
            D(rows['total_outflows']['balance']),
            sum(D(rows[key]['balance']) for key in ('repo', 'retail_call_out', 'retail_time_out', 'intergroup_call_out', 'intergroup_time_out', 'other_bank_call_out', 'other_bank_time_out', 'corporate_call_out', 'corporate_time_out', 'government', 'borrowed_funds', 'other_liabilities_illiquid')),
        )

    def test_behavioural_deposit_curve_moves_open_maturity(self):
        p=sample()
        casa=next(c for c in p['contracts'] if c['product']=='demand_deposit')
        casa.update({'liquidity_group':'Retail Call','liquidity_product':'CurrentAccount'})
        p['behavioral_assumption_set']={'name':'Test Jordan defaults','base_currency':'JOD','rules':[
            {'category':'deposit_runoff','product_group':'Retail Call','product_type':'ALL','currency_scope':'LCY','enabled':True,
             'value':{'curve':[{'days':1,'cumulative':'0.01'},{'days':30,'cumulative':'0.10'}]}},
        ]}
        r=calculate(p)
        contractual={row['key']:row for row in r['bank_ladder']['JOD']['rows']}['retail_call_out']
        behavioural={row['key']:row for row in r['behavioral_bank_ladder']['JOD']['rows']}['retail_call_out']
        self.assertEqual(D(contractual['principal'][0]),D(casa['principal']))
        self.assertEqual(D(behavioural['principal'][1]),D(casa['principal'])*D('.01'))
        self.assertEqual(D(behavioural['principal'][5]),D(casa['principal'])*D('.09'))
        self.assertEqual(behavioural['children'][0]['label'],'CurrentAccount')

    def test_behavioural_prepayment_accelerates_principal_without_creating_cash(self):
        p={'as_of_date':'2026-01-01','entity':'Jordan','bucket_days':[30,60,90], 'contracts':[
            contract(liquidity_group='Retail Time', liquidity_product='MortgageLoan'),
        ], 'behavioral_assumption_set':{'base_currency':'JOD','rules':[
            {'category':'loan_prepayment','product_group':'Retail Time','product_type':'MortgageLoan','currency_scope':'LCY','enabled':True,
             'value':{'curve':[{'days':30,'cumulative':'0.50'}]}},
        ]}}
        result=calculate(p)
        contractual={row['key']:row for row in result['bank_ladder']['JOD']['rows']}['retail_time_in']
        behavioural={row['key']:row for row in result['behavioral_bank_ladder']['JOD']['rows']}['retail_time_in']
        self.assertGreater(D(behavioural['principal'][5]), D(contractual['principal'][5]))
        self.assertEqual(sum(map(D,behavioural['principal'])),sum(map(D,contractual['principal'])))
        self.assertEqual(sum(map(D,behavioural['interest'])),sum(map(D,contractual['interest'])))

    def test_facility_drawdown_curve_replaces_open_maturity(self):
        p={'as_of_date':'2026-01-01','entity':'Jordan','bucket_days':[1,30], 'contracts':[
            {'contract_id':'FAC-1','product':'undrawn_commitment','currency':'JOD','principal':'1000.000',
             'liquidity_group':'UndrawnCommitment','liquidity_product':'UndrawnCommitment'},
        ], 'behavioral_assumption_set':{'base_currency':'JOD','rules':[
            {'category':'facility_drawdown','product_group':'UndrawnCommitment','product_type':'UndrawnCommitment','currency_scope':'LCY','enabled':True,
             'value':{'curve':[{'days':1,'cumulative':'0.10'},{'days':30,'cumulative':'0.30'}]}},
        ]}}
        result=calculate(p)
        contractual={row['key']:row for row in result['bank_ladder']['JOD']['rows']}['undrawn_commitment']
        behavioural={row['key']:row for row in result['behavioral_bank_ladder']['JOD']['rows']}['undrawn_commitment']
        self.assertEqual(D(contractual['principal'][0]),D('1000.000'))
        self.assertEqual(D(behavioural['principal'][1]),D('100.000'))
        self.assertEqual(D(behavioural['principal'][5]),D('200.000'))

    def test_duplicates_excluded_entirely(self):
        p=sample();p['contracts']=[p['contracts'][0],p['contracts'][0]]
        r=calculate(p)
        self.assertEqual(r['rejected_count'],2)
        self.assertEqual(r['cashflow_count'],0)
        self.assertEqual(r['status'],'failed_validation')

    def test_unsupported_terms_rejected(self):
        for change in [dict(rate_type='floating'),dict(day_count='ACT/ACT'),dict(status='defaulted'),
                       dict(annual_rate='NaN'),dict(currency='XYZ'),dict(principal='-1'),
                       dict(early_withdrawal=True),dict(next_payment='2026-01-01')]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError): schedule(contract(**change),date(2026,1,1))

    def test_rounding_final_adjustment(self):
        _,f,_=schedule(contract(principal='100.00',currency='USD',annual_rate='0'),date(2026,1,1))
        self.assertEqual([x['principal'] for x in f],['33.33','33.33','33.34'])

    def test_configuration_validation(self):
        for buckets in [[7,1],[1,1],[0],[1.5],[]]:
            p=sample();p['bucket_days']=buckets
            with self.assertRaises(ValueError):validate_config(p)
        p=sample();p['entity']=''
        with self.assertRaises(ValueError):validate_config(p)

if __name__=='__main__':unittest.main()
