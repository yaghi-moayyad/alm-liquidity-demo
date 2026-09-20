from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid

DEFAULT_MAPPINGS = [
    ('cash_central_bank','Cash & central bank',
     {'kind':'hqla','line_code':'LCR-HQLA-L1','line_label':'Level 1 HQLA · cash & central bank','factor':'1.00'},
     {'side':'RSF','line_code':'NSFR-RSF-CASH','line_label':'Cash / central-bank reserves','factor':'0.00'}),
    ('demand_deposit','Retail demand deposits',
     {'kind':'outflow','line_code':'LCR-OUT-RETAIL-DEMAND','line_label':'Retail demand deposits · configurable runoff','factor':'0.10'},
     {'side':'ASF','line_code':'NSFR-ASF-RETAIL-DEMAND','line_label':'Retail demand deposits','factor':'0.90'}),
    ('term_deposit','Retail term deposits',
     {'kind':'outflow','line_code':'LCR-OUT-RETAIL-TERM','line_label':'Retail term deposits maturing ≤30d','factor':'0.10','within_days':30},
     {'side':'ASF','line_code':'NSFR-ASF-RETAIL-TERM','line_label':'Retail term deposits','factors':{'<6m':'0.90','6-12m':'0.90','>=1y':'1.00','open':'0.90'}}),
    ('borrowing','Wholesale funding / borrowing',
     {'kind':'outflow','line_code':'LCR-OUT-WHOLESALE','line_label':'Wholesale funding maturing ≤30d','factor':'1.00','within_days':30},
     {'side':'ASF','line_code':'NSFR-ASF-WHOLESALE','line_label':'Wholesale funding','factors':{'<6m':'0.00','6-12m':'0.50','>=1y':'1.00','open':'0.00'}}),
    ('loan','Customer loans',
     {'kind':'inflow','line_code':'LCR-IN-LOANS','line_label':'Customer-loan inflows ≤30d','factor':'0.50','within_days':30},
     {'side':'RSF','line_code':'NSFR-RSF-LOANS','line_label':'Performing customer loans','factors':{'<6m':'0.50','6-12m':'0.50','>=1y':'0.85','open':'0.85'}}),
    ('interbank_asset','Interbank placements',
     {'kind':'inflow','line_code':'LCR-IN-FI','line_label':'Financial-institution inflows ≤30d','factor':'1.00','within_days':30},
     {'side':'RSF','line_code':'NSFR-RSF-FI','line_label':'Loans / placements to financial institutions','factors':{'<6m':'0.15','6-12m':'0.50','>=1y':'1.00','open':'1.00'}}),
    ('bond','Securities · classification required',
     {'kind':'excluded','line_code':'LCR-HQLA-SEC','line_label':'Securities pending HQLA classification','factor':'0.00'},
     {'side':'RSF','line_code':'NSFR-RSF-SEC','line_label':'Marketable securities · configurable factor','factor':'0.15'}),
]


def seed(apps, schema_editor):
    Entity=apps.get_model('cashflows','Entity')
    Config=apps.get_model('cashflows','RegulatoryConfiguration')
    Mapping=apps.get_model('cashflows','RegulatoryMapping')
    for entity in Entity.objects.all():
        fx={'JOD':'1.000000'}
        if entity.slug=='jordan-mock':
            # Demo-only reporting conversion used by the synthetic portfolio.
            # It is editable and not represented as a bank/regulator-approved rate.
            fx['USD']='0.709000'
        Config.objects.get_or_create(entity=entity, defaults={
            'reporting_currency':entity.base_currency,
            'fx_to_reporting':fx,
            'lcr_inflow_cap':'0.7500',
            'methodology_name':'Configurable LCR / NSFR source-data engine',
            'methodology_version':'draft-1',
        })
        for product,title,lcr,nsfr in DEFAULT_MAPPINGS:
            Mapping.objects.get_or_create(entity=entity,source_product=product,liquidity_group='',liquidity_product='',defaults={
                'title':title,'lcr_treatment':lcr,'nsfr_treatment':nsfr,
                'source':'Seed mapping from prior LCR/NSFR automation intelligence · requires bank/regulatory approval',
            })
        Mapping.objects.get_or_create(entity=entity,source_product='bond',liquidity_group='Marketable Securities & CDs',liquidity_product='Tbond',defaults={
            'title':'Treasury bonds · Level 1 HQLA demo classification',
            'lcr_treatment':{'kind':'hqla','line_code':'LCR-HQLA-L1-TBOND','line_label':'Level 1 HQLA · treasury bonds','factor':'1.00'},
            'nsfr_treatment':{'side':'RSF','line_code':'NSFR-RSF-L1','line_label':'Level 1 HQLA securities','factor':'0.05'},
            'source':'Detailed product mapping from liquidity catalogue · demo regulatory treatment pending approval',
        })


class Migration(migrations.Migration):
    dependencies=[('cashflows','0012_behavioral_cashflow_engine'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='RegulatoryConfiguration',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('reporting_currency',models.CharField(default='JOD',max_length=3)),('fx_to_reporting',models.JSONField(default=dict)),
            ('lcr_inflow_cap',models.DecimalField(decimal_places=4,default=0.75,max_digits=5)),
            ('methodology_name',models.CharField(default='Configurable LCR/NSFR methodology',max_length=160)),
            ('methodology_version',models.CharField(default='draft-1',max_length=32)),('updated',models.DateTimeField(auto_now=True)),
            ('entity',models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name='regulatory_configuration',to='cashflows.entity')),
        ]),
        migrations.CreateModel(name='RegulatoryMapping',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('source_product',models.CharField(max_length=64)),('liquidity_group',models.CharField(blank=True,max_length=96)),('liquidity_product',models.CharField(blank=True,max_length=96)),('title',models.CharField(max_length=160)),
            ('lcr_treatment',models.JSONField(default=dict)),('nsfr_treatment',models.JSONField(default=dict)),
            ('source',models.CharField(default='Regulatory mapping layer',max_length=180)),('active',models.BooleanField(default=True)),('updated',models.DateTimeField(auto_now=True)),
            ('entity',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='regulatory_mappings',to='cashflows.entity')),
        ],options={'ordering':['source_product']}),
        migrations.AddConstraint(model_name='regulatorymapping',constraint=models.UniqueConstraint(fields=('entity','source_product','liquidity_group','liquidity_product'),name='unique_entity_regulatory_product')),
        migrations.CreateModel(name='RegulatoryCalculation',fields=[
            ('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('as_of_date',models.DateField()),('created',models.DateTimeField(auto_now_add=True)),
            ('engine_version',models.CharField(max_length=32)),('methodology_version',models.CharField(blank=True,max_length=32)),('status',models.CharField(default='completed',max_length=24)),
            ('lcr_result',models.JSONField(default=dict)),('nsfr_result',models.JSONField(default=dict)),('controls',models.JSONField(default=dict)),('warnings',models.JSONField(default=list)),
            ('entity',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='regulatory_calculations',to='cashflows.entity')),
            ('owner',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
        ],options={'ordering':['-created']}),
        migrations.CreateModel(name='RegulatoryContribution',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('metric',models.CharField(max_length=8)),('contract_id',models.CharField(max_length=64)),('product',models.CharField(max_length=64)),('currency',models.CharField(max_length=3)),
            ('source_balance',models.DecimalField(decimal_places=3,max_digits=24)),('category_code',models.CharField(max_length=80)),('category_label',models.CharField(max_length=180)),
            ('factor',models.DecimalField(decimal_places=6,max_digits=10)),('weighted_amount',models.DecimalField(decimal_places=3,max_digits=24)),('maturity_band',models.CharField(blank=True,max_length=16)),
            ('treatment',models.JSONField(default=dict)),('calculation',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='contributions',to='cashflows.regulatorycalculation')),
        ],options={'ordering':['metric','category_code','contract_id']}),
        migrations.AddIndex(model_name='regulatorycontribution',index=models.Index(fields=['calculation','metric','category_code'],name='reg_calc_metric_line_idx')),
        migrations.RunPython(seed,migrations.RunPython.noop),
    ]
