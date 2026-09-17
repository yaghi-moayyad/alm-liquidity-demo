from django.db import migrations, models
import django.db.models.deletion


# Product Mapping worksheet. K+ is retained exactly as the source workbook's
# GL pattern. Temporary 99xxx values exist only for the six missing corporate
# liability mappings and are marked as such in Django administration.
CATALOGUE = [
 ('Asset','Cash','CashInBranches','10999',False),('Asset','Cash','MandatoryCash_Interest','11002',False),('Asset','Cash','MandatoryCash_NoninterestBearing','11001',False),
 *[('Asset',"Marketable Securities & CDs",p,gl,False) for p,gl in [('Tbill','K+'),('Tbond','K+'),('PSEBond','K+'),('BankFIBond','K+'),('CorporateBond','K+'),('BankFICommercialPaper','K+'),('CorporateCommercialPaper','K+'),('Shares','12399; 12814; 13814; 13399; 18309'),('CD_with_CB','11039'),('CD_with_BFI','11129; 11229'),('Sukuk','15009; 15019; 15029; 15039; 15049')]],
 *[('Asset',"Non-marketable Securities & CDs",p,gl,False) for p,gl in [('Tbill','K+'),('Tbond','K+'),('PSEBond','K+'),('BankFIBond','K+'),('CorporateBond','K+'),('BankFICommercialPaper','K+'),('CorporateCommercialPaper','K+'),('Shares','12399; 12814; 13814; 13399; 18309'),('CD_with_CB','11039'),('CD_with_BFI','11129; 11229'),('Sukuk','15009; 15019; 15029; 15039; 15049')]],
 ('Asset','Retail Call','RetailOverdraft','14103; 14113; 14143; 14702',False),('Asset','Retail Call','CreditCard','14121; 14122; 14129; 14133',False),('Asset','Retail Call','RetailOverdrawn','14702',False),
 ('Asset','Retail Time','MortgageLoan','14259; 14707',False),('Asset','Retail Time','PersonalLoan','14249; 14703',False),
 ('Asset','Intergroup Call','Account_with_AB','11309; 11409',False),('Asset','Intergroup Time','TimeDeposit_with_AB','11319; 11419',False),
 ('Asset','Bank Call','Account_with_BFI','11109; 11209; 11599',False),('Asset','Bank Time','TimeDeposit_with_BFI','11119; 11219',False),('Asset','ReverseRepo','ReverseRepo','K+',False),
 ('Asset','Corporate Call','CorporateOverdrawn','14132; 14709',False),('Asset','Corporate Call','CorporateOverdraft','14102; 14112; 14142; 14159; 14709',False),
 ('Asset','Corporate Time','CorporateLoan','14239; 14269; 14709',False),('Asset','Corporate Time','SyndicatedLoan','14339; 14709; 14309; 14329; 14319',False),('Asset','Corporate Time','DiscountedBill_Acceptance','14019; 14029; 14009; 14709',False),
 ('Asset','Other Loans','OtherLoans_Overdraft','14101; 14111; 14131; 14141',False),('Asset','Other Loans','OtherLoans_Term','14209; 14219; 14229; 14709',False),('Asset','Government','TimeDeposit_with_CB','11029',False),('Asset','NPL','NPL','11019',False),
 ('Liability','Repo','Repo','61101; 61001; 61201; 61003; 61103; 61203',False),
 ('Liability','Retail Call','CurrentAccount','61309; 61409; 61002; 61004; 61102; 61104; 61202; 61204',False),('Liability','Retail Call','SavingsAccount','61219; 61419',False),('Liability','Retail Call','CashMarginAccount','62009; 62019; 62199',False),
 ('Liability','Retail Time','TimeDeposit','61119; 61229; 61329; 61429',False),('Liability','Retail Time','CashMarginTD','62029; 62039',False),('Liability','Retail Time','CD','61029; 61129; 61239',False),
 ('Liability','Intergroup Call','Account_due_to_AB','61309; 60409',False),('Liability','Intergroup Time','TimeDeposit_due_to_AB','60319; 60419',False),('Liability','Bank Call','Account_due_to_BFI','60109; 60209',False),('Liability','Bank Time','TimeDeposit_due_to_BFI','60119; 60219',False),
 ('Liability','Corporate Call','CurrentAccount','99001',True),('Liability','Corporate Call','SavingsAccount','99002',True),('Liability','Corporate Call','CashMarginAccount','99003',True),('Liability','Corporate Time','TimeDeposit','99004',True),('Liability','Corporate Time','CashMarginTD','99005',True),('Liability','Corporate Time','CD','99006',True),
 *[('OffBalanceSheet','Derivatives',p,'K+',False) for p in ['IRS','Future','FRA','Option','FXSpot','FXForward','FXSwap','CCS']],
 ('OffBalanceSheet','UndrawnCommitment','UndrawnCommitment','50393',False),('OffBalanceSheet','UndrawnUncommitted','UndrawnUncommitted','50393',False),('OffBalanceSheet','TradeFinance','LC','50099',False),('OffBalanceSheet','TradeFinance','LG','50199',False),('OffBalanceSheet','TradeFinance','Acceptances','50299',False),
]


def seed_catalogue(apps, schema_editor):
    Entity=apps.get_model('cashflows','Entity'); Item=apps.get_model('cashflows','ProductCatalogueItem')
    entity=Entity.objects.filter(slug='jordan-mock').first()
    if not entity: return
    for classification, group, product, gl, temporary in CATALOGUE:
        Item.objects.get_or_create(entity=entity,classification=classification,product_group=group,product_type=product,
            defaults={'general_ledger':gl,'is_temporary_gl':temporary,'source':'Jordan Product mapping workbook' if not temporary else 'Temporary demo mapping pending bank GL confirmation'})


class Migration(migrations.Migration):
    dependencies=[('cashflows','0010_behavioural_assumptions')]
    operations=[
        migrations.CreateModel(name='ProductCatalogueItem',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('classification',models.CharField(max_length=32)),('product_group',models.CharField(max_length=96)),('product_type',models.CharField(max_length=96)),
            ('general_ledger',models.TextField()),('is_temporary_gl',models.BooleanField(default=False)),('source',models.CharField(default='Jordan Product mapping workbook',max_length=160)),
            ('active',models.BooleanField(default=True)),('created',models.DateTimeField(auto_now_add=True)),('updated',models.DateTimeField(auto_now=True)),
            ('entity',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='product_catalogue',to='cashflows.entity')),
        ],options={'ordering':['classification','product_group','product_type']}),
        migrations.AddConstraint(model_name='productcatalogueitem',constraint=models.UniqueConstraint(fields=('entity','classification','product_group','product_type'),name='unique_entity_catalogue_item')),
        migrations.RunPython(seed_catalogue,migrations.RunPython.noop),
    ]
