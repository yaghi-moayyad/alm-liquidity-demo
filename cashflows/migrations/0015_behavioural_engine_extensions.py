from django.db import migrations, models


def seed_behavioural_framework(apps, schema_editor):
    Entity = apps.get_model('cashflows', 'Entity')
    AssumptionSet = apps.get_model('cashflows', 'LiquidityAssumptionSet')
    Assumption = apps.get_model('cashflows', 'LiquidityAssumption')
    entity = Entity.objects.filter(slug='jordan-mock').first()
    if not entity:
        return
    assumption_set = AssumptionSet.objects.filter(entity=entity, status='active').first()
    if not assumption_set:
        return

    def add(category, title, group, product, scope, value, enabled, order):
        Assumption.objects.get_or_create(
            assumption_set=assumption_set, category=category, title=title,
            defaults={'product_group': group, 'product_type': product,
                      'currency_scope': scope, 'value': value, 'enabled': enabled,
                      'sort_order': order},
        )

    # The workbook time-deposit runoff figures become dated early-withdrawal
    # curves. Other templates are disabled because the supplied workbook does
    # not approve their parameters yet.
    for old in Assumption.objects.filter(assumption_set=assumption_set, category='deposit_runoff', product_group__in=['Retail Time', 'Corporate Time']):
        add('term_deposit_early_withdrawal', f'{old.title} early withdrawal', old.product_group,
            old.product_type, old.currency_scope, old.value, True, old.sort_order + 1)

    template_curve = {'curve': [{'days': 30, 'cumulative': '0.00'}, {'days': 90, 'cumulative': '0.00'}, {'days': 365, 'cumulative': '0.00'}], 'curve_type': 'cumulative'}
    for title, group, product in [
        ('Mortgage loan prepayment · template', 'Retail Time', 'MortgageLoan'),
        ('Personal loan prepayment · template', 'Retail Time', 'PersonalLoan'),
        ('Corporate loan prepayment · template', 'Corporate Time', 'CorporateLoan'),
        ('Syndicated loan prepayment · template', 'Corporate Time', 'SyndicatedLoan'),
    ]:
        add('loan_prepayment', title, group, product, 'ALL', template_curve, False, 800)
    for title, group, product in [
        ('Undrawn commitment drawdown · template', 'UndrawnCommitment', 'UndrawnCommitment'),
        ('Uncommitted facility drawdown · template', 'UndrawnUncommitted', 'UndrawnUncommitted'),
        ('Trade-finance drawdown · template', 'TradeFinance', 'ALL'),
    ]:
        add('facility_drawdown', title, group, product, 'ALL', template_curve, False, 810)
    add('rollover', 'Bank time rollover · template', 'Bank Time', 'ALL', 'ALL',
        {'rollover_rate': '0.00', 'rollover_days': 30}, False, 820)


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0014_lcr_stress_testing')]

    operations = [
        migrations.AlterField(
            model_name='liquidityassumption', name='category',
            field=models.CharField(choices=[
                ('deposit_runoff', 'Deposit runoff'),
                ('term_deposit_early_withdrawal', 'Term-deposit early withdrawal'),
                ('loan_prepayment', 'Loan prepayment'),
                ('facility_drawdown', 'Approved facility drawdown'),
                ('rollover', 'Rollover / renewal'),
                ('security_liquidation', 'Security liquidation'),
                ('security_haircut', 'Security haircut'),
            ], max_length=32),
        ),
        migrations.RunPython(seed_behavioural_framework, migrations.RunPython.noop),
    ]
