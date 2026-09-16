from django.db import migrations, models
import django.db.models.deletion

def seed(apps,schema_editor):
    Entity=apps.get_model('cashflows','Entity')
    Config=apps.get_model('cashflows','EntityConfiguration')
    Contract=apps.get_model('cashflows','PortfolioContract')
    Run=apps.get_model('cashflows','CalculationRun')
    entity,_=Entity.objects.get_or_create(slug='jordan-mock',defaults={'name':'Jordan-Mock','country':'Jordan','base_currency':'JOD','is_mock':True})
    buckets=[1,7,14,30,60,90,180,270,365,730,1095,1825]
    Config.objects.get_or_create(entity=entity,defaults={'as_of_date':'2026-09-16','bucket_days':buckets})
    def c(cid,product,principal,rate,maturity,method='bullet',currency='JOD',frequency=3,next_payment='2026-10-01'):
        return dict(contract_id=cid,product=product,currency=currency,principal=str(principal),annual_rate=str(rate),rate_type='fixed',repayment=method,day_count='ACT/365F',frequency_months=frequency,accrual_start='2026-07-01',next_payment=next_payment,maturity=maturity,end_of_month=False)
    contracts=[c('LN-1001','loan',120000,.072,'2028-07-01','equal_principal'),c('LN-1002','loan',85000,.065,'2029-07-01','level_payment'),c('LN-1003','loan',240000,.081,'2027-07-01'),c('TD-2001','term_deposit',300000,.041,'2026-10-01'),c('TD-2002','term_deposit',150000,.038,'2027-01-01'),c('BOND-3001','bond',500000,.055,'2031-07-01',frequency=6,next_payment='2027-01-01'),c('IB-4001','interbank_asset',175000,.045,'2026-09-23',next_payment='2026-09-23'),c('BOR-5001','borrowing',90000,.043,'2027-07-01'),c('USD-LN-01','loan',220000,.06,'2028-07-01','equal_principal','USD'),c('USD-TD-01','term_deposit',180000,.035,'2027-01-01',currency='USD'),{'contract_id':'CASA-6001','product':'demand_deposit','currency':'JOD','principal':'425000.000'}]
    for i in range(25):
        product='loan' if i%2==0 else 'term_deposit'
        contracts.append(c(f'MOCK-{i+1:03}',product,35000+i*7300,.06 if product=='loan' else .035,
            '2028-07-01' if product=='loan' else ('2027-01-01' if i%3 else '2026-10-01'),
            'equal_principal' if product=='loan' else 'bullet','USD' if i%5==0 else 'JOD'))
    for terms in contracts:
        Contract.objects.get_or_create(entity=entity,external_id=terms['contract_id'],defaults={'terms':terms})
    for run in Run.objects.filter(entity_ref__isnull=True).iterator():
        if run.entity in ('Jordan','jordan-mock'):
            run.entity_ref=entity
        else:
            from django.utils.text import slugify
            code=slugify(run.entity)[:64] or 'legacy-entity'
            item,_=Entity.objects.get_or_create(slug=code,defaults={'name':run.entity,'country':'Unspecified','base_currency':'JOD'})
            Config.objects.get_or_create(entity=item,defaults={'as_of_date':run.as_of_date,'bucket_days':buckets})
            run.entity_ref=item
        run.save(update_fields=['entity_ref'])

class Migration(migrations.Migration):
    dependencies=[('cashflows','0002_entity_alter_calculationrun_entity_and_more')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop),migrations.AlterField(model_name='calculationrun',name='entity_ref',field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='runs',to='cashflows.entity'))]
