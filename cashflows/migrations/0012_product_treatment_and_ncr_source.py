from django.db import migrations, models
import django.db.models.deletion


MOCK_POSITIONS=[
 ('NCR-001','10999','Cash','CashInBranches','JOD','197756.180','level1_coins','1.000000','hqla','1'),
 ('NCR-002','11002','Cash','MandatoryCash_Interest','JOD','5157487.540','level1_reserves','1.000000','hqla','1'),
 ('NCR-003','K+','Marketable Securities & CDs','Tbond','JOD','3407187.560','level1_sovereign','1.000000','hqla','1'),
 ('NCR-004','K+','Marketable Securities & CDs','PSEBond','JOD','410000.000','level2a_securities','0.850000','hqla','2A'),
 ('NCR-005','12399','Marketable Securities & CDs','Shares','JOD','120000.000','level2b_equities','0.500000','hqla','2B'),
 ('NCR-101','61309','Retail Call','CurrentAccount','JOD','1414962.870','retail_stable','0.150000','outflow',''),
 ('NCR-102','61219','Retail Call','SavingsAccount','JOD','644180.620','retail_less_stable','0.200000','outflow',''),
 ('NCR-103','61119','Retail Time','TimeDeposit','JOD','820588.800','retail_less_stable','0.250000','outflow',''),
 ('NCR-104','60109','Bank Call','Account_due_to_BFI','JOD','1141063.570','wholesale_operational','0.300000','outflow',''),
 ('NCR-105','60319','Intergroup Time','TimeDeposit_due_to_AB','JOD','1758245.100','wholesale_non_operational','0.350000','outflow',''),
 ('NCR-106','61101','Repo','Repo','JOD','581390.050','secured_funding','0.400000','outflow',''),
 ('NCR-107','50393','OffBalanceSheet','UndrawnCommitment','JOD','600000.000','other_outflows','0.100000','outflow',''),
 ('NCR-201','11109','Bank Call','Account_with_BFI','JOD','880000.000','inflow_financial','0.500000','inflow',''),
 ('NCR-202','14102','Corporate Call','CorporateOverdraft','JOD','640000.000','inflow_customer','0.500000','inflow',''),
]

BEHAVIOURAL_GROUPS={'Marketable Securities & CDs','Retail Call','Retail Time','Corporate Call','Corporate Time'}

def seed_treatment_and_positions(apps,schema_editor):
    Entity=apps.get_model('cashflows','Entity'); Catalogue=apps.get_model('cashflows','ProductCatalogueItem'); Position=apps.get_model('cashflows','RegulatorySourcePosition'); Assumption=apps.get_model('cashflows','LiquidityAssumption')
    entity=Entity.objects.filter(slug='jordan-mock').first()
    if not entity:return
    for item in Catalogue.objects.filter(entity=entity):
        treatment='behavioral' if item.product_group in BEHAVIOURAL_GROUPS else 'contractual'
        note='Approved Jordan workbook treatment'
        if item.product_group=='Non-marketable Securities & CDs' and item.product_type=='Shares': treatment='behavioral'
        elif item.product_group=='Non-marketable Securities & CDs': treatment='contractual'
        elif item.classification=='OffBalanceSheet' and item.product_group in {'UndrawnCommitment','UndrawnUncommitted','TradeFinance'}: treatment='behavioral'
        if item.product_group=='ReverseRepo': treatment='behavioral';note='Workbook detailed mapping: exclude cash inflows; verify against summary during bank sign-off.'
        item.cash_flow_treatment=treatment;item.treatment_note=note;item.save(update_fields=['cash_flow_treatment','treatment_note'])
    # Contractual non-marketable entries belong in the catalogue treatment map,
    # not in the behavioural-rule register.
    for rule in Assumption.objects.filter(assumption_set__entity=entity,product_group='Non-marketable Securities & CDs'):
        if rule.value.get('timing') == 'contractual':
            rule.delete()
    for external_id,gl,group,product,currency,balance,category,factor,direction,level in MOCK_POSITIONS:
        Position.objects.get_or_create(entity=entity,external_id=external_id,defaults={'gl_code':gl,'product_group':group,'product_type':product,'currency':currency,'balance':balance,'lcr_category':category,'lcr_factor':factor,'lcr_direction':direction,'hqla_level':level})


class Migration(migrations.Migration):
    dependencies=[('cashflows','0011_product_catalogue')]
    operations=[
        migrations.AddField(model_name='productcatalogueitem',name='cash_flow_treatment',field=models.CharField(choices=[('contractual','Contractual'),('behavioral','Behavioural'),('hybrid','Hybrid'),('excluded','Excluded')],default='contractual',max_length=16)),
        migrations.AddField(model_name='productcatalogueitem',name='treatment_note',field=models.CharField(blank=True,max_length=240)),
        migrations.CreateModel(name='RegulatorySourcePosition',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('external_id',models.CharField(max_length=64)),('gl_code',models.CharField(max_length=96)),('product_group',models.CharField(max_length=96)),('product_type',models.CharField(max_length=96)),('currency',models.CharField(max_length=3)),
            ('balance',models.DecimalField(decimal_places=3,max_digits=24)),('lcr_category',models.CharField(max_length=64)),('lcr_factor',models.DecimalField(decimal_places=6,max_digits=8)),('lcr_direction',models.CharField(max_length=12)),('hqla_level',models.CharField(blank=True,max_length=8)),('active',models.BooleanField(default=True)),('updated',models.DateTimeField(auto_now=True)),
            ('entity',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='regulatory_positions',to='cashflows.entity')),
        ],options={'ordering':['lcr_direction','lcr_category','external_id']}),
        migrations.AddConstraint(model_name='regulatorysourceposition',constraint=models.UniqueConstraint(fields=('entity','external_id'),name='unique_entity_regulatory_position')),
        migrations.RunPython(seed_treatment_and_positions,migrations.RunPython.noop),
    ]
