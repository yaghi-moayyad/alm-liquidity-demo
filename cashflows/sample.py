"""Synthetic data only, in original currencies."""
from .engine import DEFAULT_BUCKETS

def sample():
    def c(cid,product,principal,rate,maturity,method='bullet',currency='JOD',frequency=3,next_payment='2026-10-01'):
        return dict(contract_id=cid,product=product,currency=currency,principal=str(principal),annual_rate=str(rate),
                    rate_type='fixed',repayment=method,day_count='ACT/365F',frequency_months=frequency,
                    accrual_start='2026-07-01',next_payment=next_payment,maturity=maturity,end_of_month=False)
    return {'entity':'jordan-mock','as_of_date':'2026-09-16','bucket_days':DEFAULT_BUCKETS,
        'contracts':[
        c('LN-1001','loan',120000,.072,'2028-07-01','equal_principal'),
        c('LN-1002','loan',85000,.065,'2029-07-01','level_payment'),
        c('LN-1003','loan',240000,.081,'2027-07-01'),
        c('TD-2001','term_deposit',300000,.041,'2026-10-01'),
        c('TD-2002','term_deposit',150000,.038,'2027-01-01'),
        c('BOND-3001','bond',500000,.055,'2031-07-01',frequency=6,next_payment='2027-01-01'),
        c('IB-4001','interbank_asset',175000,.045,'2026-09-23',next_payment='2026-09-23'),
        c('BOR-5001','borrowing',90000,.043,'2027-07-01'),
        c('USD-LN-01','loan',220000,.06,'2028-07-01','equal_principal','USD'),
        c('USD-TD-01','term_deposit',180000,.035,'2027-01-01',currency='USD'),
        {'contract_id':'CASA-6001','product':'demand_deposit','currency':'JOD','principal':'425000.000'}]}
