from datetime import date
from django.db import migrations, models
import django.db.models.deletion


BASE_LCR = [
    ('coins','Coins and banknotes',197756.18,'level1_coins',1.00),
    ('reserves','Central Bank reserves drawable in stress',5157487.54,'level1_reserves',1.00),
    ('sovereign','Level 1 sovereign, central-bank and PSE securities',3407187.56,'level1_sovereign',1.00),
    ('level2a','Level 2A securities',410000.00,'level2a_securities',.85),
    ('equities','Level 2B qualifying equities',120000.00,'level2b_equities',.50),
    ('retail_stable','Stable retail deposits',1414962.87,'retail_stable',.15),
    ('retail_savings','Less stable retail deposits',644180.62,'retail_less_stable',.20),
    ('retail_time','Retail time deposits',820588.80,'retail_less_stable',.25),
    ('bank_operational','Operational bank deposits',1141063.57,'wholesale_operational',.30),
    ('intergroup','Non-operational wholesale deposits',1758245.10,'wholesale_non_operational',.35),
    ('wholesale','Wholesale funding from corporates and FIs',5000000.00,'wholesale_non_operational',.75),
    ('repo','Secured funding and repo transactions',581390.05,'secured_funding',.40),
    ('contingent','Other contractual and contingent outflows',2000000.00,'other_outflows',.40),
    ('financial_inflows','Inflows from financial institutions',880000.00,'inflow_financial',.50),
    ('customer_inflows','Inflows from customers and counterparties',640000.00,'inflow_customer',.50),
]

BASE_NSFR = [
    ('asf','002','Tier 1 capital',[0,0,450000],[0,0,0],[0,0,0],[0,0,1]),
    ('asf','003','Tier 2 capital',[0,0,3500],[0,0,0],[0,0,0],[0,0,1]),
    ('asf','004.1','Stable CASA',[1800000,0,0],[0,0,0],[0,0,0],[.95,.95,.95]),
    ('asf','005','Less stable term deposits',[540000,180000,0],[120000,30000,0],[350000,45000,0],[.90,.90,.90]),
    ('asf','009.3','Corporate uninsured non-operational deposits',[0,0,900000],[0,0,0],[0,0,0],[.50,.50,1]),
    ('asf','020','Bank non-operational deposits',[0,300000,700000],[0,0,0],[0,0,0],[0,.50,1]),
    ('rsf','034','Coins and banknotes',[197756,0,0],[0,0,0],[0,0,0],[.00,.00,.00]),
    ('rsf','035','Central bank reserves',[5157488,0,0],[0,0,0],[0,0,0],[.05,.05,.05]),
    ('rsf','040','Level 1 securities',[0,0,3407188],[0,0,0],[0,0,0],[.05,.05,.05]),
    ('rsf','041','Level 2A securities',[0,0,410000],[0,0,0],[0,0,0],[.15,.15,.15]),
    ('rsf','044','Corporate loans below one year',[1200000,0,0],[300000,0,0],[150000,0,0],[.50,.50,.50]),
    ('rsf','047','Residential mortgages',[0,0,2100000],[0,0,0],[0,0,0],[.65,.65,.65]),
    ('rsf','050','Other performing loans',[0,0,1800000],[0,0,0],[0,0,0],[.85,.85,.85]),
    ('rsf','057','Other assets',[0,0,220000],[0,0,0],[0,0,0],[1,1,1]),
    ('rsf','059','Committed facilities',[500000,0,0],[0,0,0],[0,0,0],[.05,.05,.05]),
]


def seed_snapshots(apps, schema_editor):
    Entity=apps.get_model('cashflows','Entity'); Snapshot=apps.get_model('cashflows','RegulatorySnapshot')
    entity=Entity.objects.filter(slug='jordan-mock').first()
    if not entity:return
    dates=[date(2026,4,30),date(2026,5,31),date(2026,6,30),date(2026,7,31),date(2026,8,31),date(2026,9,16)]
    hqla=[.93,.95,.97,.98,1,1.02]; funding=[.90,.92,.95,.97,1,1.03]; assets=[.94,.96,.98,1,1.01,1.03]
    for index,as_of in enumerate(dates):
        lcr=[]
        for key,label,balance,category,factor in BASE_LCR:
            multiplier=hqla[index] if category.startswith('level') else funding[index] if not category.startswith('inflow') else assets[index]
            lcr.append({'key':key,'label':label,'balance':round(balance*multiplier,3),'lcr_category':category,'lcr_factor':factor})
        nsfr=[]
        for direction,code,label,jod,usd,other,factors in BASE_NSFR:
            multiplier=funding[index] if direction=='asf' else assets[index]
            nsfr.append({'direction':direction,'code':code,'label':label,'jod':[round(v*multiplier,3) for v in jod],'usd':[round(v*multiplier,3) for v in usd],'other':[round(v*multiplier,3) for v in other],'factors':factors})
        Snapshot.objects.get_or_create(entity=entity,as_of_date=as_of,defaults={'source':'Jordan regulatory mock source data','is_mock':True,'source_data':{'lcr_positions':lcr,'nsfr_lines':nsfr}})


class Migration(migrations.Migration):
    dependencies=[('cashflows','0012_product_treatment_and_ncr_source')]
    operations=[
        migrations.CreateModel(name='RegulatorySnapshot',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('as_of_date',models.DateField()),('source',models.CharField(default='Mapped regulatory source positions',max_length=160)),('is_mock',models.BooleanField(default=False)),('source_data',models.JSONField(default=dict)),('created',models.DateTimeField(auto_now_add=True)),
            ('entity',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='regulatory_snapshots',to='cashflows.entity')),
        ],options={'ordering':['-as_of_date']}),
        migrations.AddConstraint(model_name='regulatorysnapshot',constraint=models.UniqueConstraint(fields=('entity','as_of_date'),name='unique_entity_regulatory_snapshot')),
        migrations.RunPython(seed_snapshots,migrations.RunPython.noop),
    ]
