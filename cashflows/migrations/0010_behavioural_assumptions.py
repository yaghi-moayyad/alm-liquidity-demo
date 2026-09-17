from datetime import date
from django.db import migrations, models
import django.db.models.deletion


DEPOSIT_CURVES = [
    ('Corporate Call · LCY', 'Corporate Call', 'ALL', 'LCY', [(1, .20), (2, .20), (7, .25), (14, .25), (30, .40), (60, .40), (90, .40), (180, .40), (365, .45)]),
    ('Corporate Call · FCY', 'Corporate Call', 'ALL', 'FCY', [(1, .10), (2, .10), (7, .15), (14, .15), (30, .20), (60, .20), (90, .30), (180, .35), (365, .35)]),
    ('Retail Call · LCY', 'Retail Call', 'ALL', 'LCY', [(1, .01), (2, .01), (7, .03), (14, .03), (30, .10), (60, .10), (90, .12), (180, .12), (365, .15)]),
    ('Retail Call · FCY', 'Retail Call', 'ALL', 'FCY', [(1, .01), (2, .01), (7, .02), (14, .02), (30, .02), (60, .03), (90, .03), (180, .03), (365, .05)]),
    ('Corporate Time · LCY', 'Corporate Time', 'ALL', 'LCY', [(30, .20)]),
    ('Corporate Time · FCY', 'Corporate Time', 'ALL', 'FCY', [(30, .30)]),
    ('Retail Time · LCY', 'Retail Time', 'ALL', 'LCY', [(30, .15)]),
    ('Retail Time · FCY', 'Retail Time', 'ALL', 'FCY', [(30, .25)]),
]

SECURITY_TIMING = [
    ('Tbill', '1d'), ('Tbond', '1d'), ('PSEBond', '1d'), ('BankFIBond', '1d'),
    ('CorporateBond', '1w2w'), ('BankFICommercialPaper', '1d'),
    ('CorporateCommercialPaper', '1y'), ('Shares', '1w'), ('CD_with_CB', '1d'),
    ('CD_with_BFI', '1d'), ('Sukuk', '1d'),
]
NON_MARKETABLE_PRODUCTS = ['Tbill', 'Tbond', 'PSEBond', 'BankFIBond', 'CorporateBond',
    'BankFICommercialPaper', 'CorporateCommercialPaper', 'CD_with_CB', 'CD_with_BFI', 'Sukuk']


def seed_defaults(apps, schema_editor):
    Entity = apps.get_model('cashflows', 'Entity')
    AssumptionSet = apps.get_model('cashflows', 'LiquidityAssumptionSet')
    Assumption = apps.get_model('cashflows', 'LiquidityAssumption')
    Contract = apps.get_model('cashflows', 'PortfolioContract')
    entity = Entity.objects.filter(slug='jordan-mock').first()
    if not entity:
        return
    assumption_set, _ = AssumptionSet.objects.get_or_create(
        entity=entity, name='Jordan default behavioural assumptions',
        defaults={'version': 1, 'effective_date': date(2025, 7, 1), 'status': 'active',
                  'source': 'Liquidity_Assumptions_Reconstructed workbook', 'is_system': True},
    )
    if not Assumption.objects.filter(assumption_set=assumption_set).exists():
        order = 10
        rules = []
        for title, group, product, scope, curve in DEPOSIT_CURVES:
            rules.append(Assumption(assumption_set=assumption_set, category='deposit_runoff', title=title,
                product_group=group, product_type=product, currency_scope=scope,
                value={'curve': [{'days': days, 'cumulative': str(rate)} for days, rate in curve], 'curve_type': 'cumulative'}, sort_order=order))
            order += 10
        for product, timing in SECURITY_TIMING:
            rules.append(Assumption(assumption_set=assumption_set, category='security_liquidation',
                title=f'Marketable Securities · {product}', product_group='Marketable Securities & CDs', product_type=product,
                maturity_breakdown='All maturities', value={'timing': timing}, sort_order=order))
            order += 10
            haircut = '0.20' if product == 'CD_with_BFI' else '0.10'
            rules.append(Assumption(assumption_set=assumption_set, category='security_haircut',
                title=f'Marketable Securities · {product} haircut', product_group='Marketable Securities & CDs', product_type=product,
                maturity_breakdown='All maturities', value={'haircut': haircut}, sort_order=order))
            order += 10
        # The workbook records these as contractual (not liquidated) and zero
        # haircut. Keeping them in the editable register makes that treatment
        # visible instead of silently omitting the product family.
        for product in NON_MARKETABLE_PRODUCTS:
            rules.append(Assumption(assumption_set=assumption_set, category='security_liquidation',
                title=f'Non-marketable Securities · {product}', product_group='Non-marketable Securities & CDs', product_type=product,
                maturity_breakdown='All maturities', value={'timing': 'contractual'}, sort_order=order))
            order += 10
            rules.append(Assumption(assumption_set=assumption_set, category='security_haircut',
                title=f'Non-marketable Securities · {product} haircut', product_group='Non-marketable Securities & CDs', product_type=product,
                maturity_breakdown='All maturities', value={'haircut': '0.00'}, sort_order=order))
            order += 10
        rules.append(Assumption(assumption_set=assumption_set, category='security_liquidation',
            title='Non-marketable Securities · Shares', product_group='Non-marketable Securities & CDs', product_type='Shares',
            maturity_breakdown='All maturities', value={'timing': '1w'}, sort_order=order))
        Assumption.objects.bulk_create(rules)
    # Give the synthetic portfolio transparent product labels so the demo can
    # show the same hierarchy as the bank format without changing raw products.
    for contract in Contract.objects.filter(entity=entity):
        terms = contract.terms
        cid = contract.external_id
        changed = False
        if cid.startswith('JOD-CASA-') or cid.startswith('USD-CASA-'):
            number = int(cid.rsplit('-', 1)[1])
            terms['liquidity_group'] = 'Retail Call'
            terms['liquidity_product'] = 'CurrentAccount' if number % 2 else 'SavingsAccount'
            changed = True
        elif cid.startswith(('JOD-TD-', 'USD-TD-')):
            terms['liquidity_group'] = 'Retail Time'; terms['liquidity_product'] = 'TimeDeposit'; changed = True
        elif cid.startswith(('JOD-BOND-', 'USD-BOND-')):
            terms['liquidity_group'] = 'Marketable Securities & CDs'
            terms['liquidity_product'] = 'Tbond' if cid.endswith(('001', '003', '005')) else 'CorporateBond'
            changed = True
        if changed:
            contract.terms = terms
            contract.save(update_fields=['terms'])


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0009_runcontract')]

    operations = [
        migrations.CreateModel(
            name='LiquidityAssumptionSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)), ('version', models.PositiveIntegerField(default=1)),
                ('effective_date', models.DateField()), ('status', models.CharField(choices=[('active', 'Active'), ('draft', 'Draft'), ('retired', 'Retired')], default='active', max_length=16)),
                ('source', models.CharField(default='Jordan liquidity assumptions workbook', max_length=160)), ('is_system', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)), ('updated', models.DateTimeField(auto_now=True)),
                ('entity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assumption_sets', to='cashflows.entity')),
            ], options={'ordering': ['-effective_date', '-version']},
        ),
        migrations.CreateModel(
            name='LiquidityAssumption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('deposit_runoff', 'Deposit runoff'), ('security_liquidation', 'Security liquidation'), ('security_haircut', 'Security haircut')], max_length=32)),
                ('title', models.CharField(max_length=160)), ('product_group', models.CharField(blank=True, max_length=96)), ('product_type', models.CharField(blank=True, max_length=96)),
                ('currency_scope', models.CharField(default='ALL', max_length=8)), ('maturity_breakdown', models.CharField(blank=True, max_length=32)),
                ('value', models.JSONField(default=dict)), ('enabled', models.BooleanField(default=True)), ('sort_order', models.PositiveIntegerField(default=0)),
                ('created', models.DateTimeField(auto_now_add=True)), ('updated', models.DateTimeField(auto_now=True)),
                ('assumption_set', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rules', to='cashflows.liquidityassumptionset')),
            ], options={'ordering': ['category', 'sort_order', 'title']},
        ),
        migrations.AddConstraint(model_name='liquidityassumptionset', constraint=models.UniqueConstraint(fields=('entity', 'name'), name='unique_entity_assumption_set_name')),
        migrations.AddField(model_name='cashflow', name='liquidity_group', field=models.CharField(blank=True, max_length=96)),
        migrations.AddField(model_name='cashflow', name='liquidity_product', field=models.CharField(blank=True, max_length=96)),
        migrations.RunPython(seed_defaults, migrations.RunPython.noop),
    ]
