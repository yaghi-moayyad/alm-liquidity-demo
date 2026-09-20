from django.db import migrations, models
import django.db.models.deletion


def seed_treatments(apps, schema_editor):
    Item = apps.get_model('cashflows', 'ProductCatalogueItem')
    Assumption = apps.get_model('cashflows', 'LiquidityAssumption')
    Item.objects.filter(classification='Liability', product_group__in=['Retail Call', 'Corporate Call']).update(cashflow_treatment='behavioral')
    Item.objects.filter(product_group__in=['Retail Time', 'Corporate Time']).update(cashflow_treatment='hybrid')
    Item.objects.filter(product_group='Marketable Securities & CDs').update(cashflow_treatment='hybrid')
    # The reconstructed workbook already contains 30-day behavioural percentages
    # for Retail/Corporate Time.  In the explicit engine those are early-withdrawal
    # assumptions rather than NMD runoff rules.
    Assumption.objects.filter(category='deposit_runoff', product_group__in=['Retail Time','Corporate Time']).update(category='term_deposit_early_withdrawal')


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0011_product_catalogue')]
    operations = [
        migrations.AddField(
            model_name='productcatalogueitem', name='cashflow_treatment',
            field=models.CharField(choices=[('contractual','Contractual'),('behavioral','Behavioural'),('hybrid','Hybrid')], default='contractual', max_length=16),
        ),
        migrations.AlterField(
            model_name='liquidityassumption', name='category',
            field=models.CharField(choices=[
                ('deposit_runoff','Deposit runoff'),('security_liquidation','Security liquidation'),('security_haircut','Security haircut'),
                ('loan_prepayment','Loan prepayment'),('term_deposit_early_withdrawal','Term-deposit early withdrawal'),('term_deposit_rollover','Term-deposit rollover')
            ], max_length=32),
        ),
        migrations.CreateModel(
            name='BehavioralCashFlow', fields=[
                ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
                ('sequence',models.PositiveIntegerField()),('contract_id',models.CharField(max_length=64)),('product',models.CharField(max_length=32)),
                ('liquidity_product',models.CharField(blank=True,max_length=96)),('liquidity_group',models.CharField(blank=True,max_length=96)),
                ('currency',models.CharField(max_length=3)),('direction',models.CharField(max_length=8)),('payment_date',models.DateField()),
                ('accrual_start',models.DateField()),('accrual_end',models.DateField()),('days_from_asof',models.PositiveIntegerField()),
                ('principal',models.DecimalField(decimal_places=3,max_digits=24)),('interest',models.DecimalField(decimal_places=3,max_digits=24)),
                ('total',models.DecimalField(decimal_places=3,max_digits=24)),('remaining_principal',models.DecimalField(decimal_places=3,max_digits=24)),
                ('bucket',models.CharField(blank=True,max_length=64)),('behavioral_source',models.CharField(blank=True,max_length=48)),
                ('behavioral_rule_id',models.PositiveIntegerField(blank=True,null=True)),('behavioral_rule_title',models.CharField(blank=True,max_length=160)),
                ('run',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='behavioral_cashflows',to='cashflows.calculationrun')),
            ], options={'ordering':['sequence']},
        ),
        migrations.AddConstraint(model_name='behavioralcashflow',constraint=models.UniqueConstraint(fields=('run','sequence'),name='unique_run_behavioral_flow_sequence')),
        migrations.AddIndex(model_name='behavioralcashflow',index=models.Index(fields=['run','contract_id'],name='bflow_run_contract_idx')),
        migrations.AddIndex(model_name='behavioralcashflow',index=models.Index(fields=['run','currency','payment_date'],name='bflow_run_currency_date_idx')),
        migrations.RunPython(seed_treatments, migrations.RunPython.noop),
    ]
