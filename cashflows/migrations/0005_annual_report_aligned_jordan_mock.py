"""Replace the tiny generic mock with a clearly synthetic, presentation-ready seed.

The aggregate JOD proportions are deliberately scaled from Arab Bank plc's public
2025 statement of financial position.  No customer, account, or transaction data
is represented here.
"""
from django.db import migrations


AS_OF = '2025-12-31'
BUCKETS = [1, 7, 14, 30, 60, 90, 180, 270, 365, 730, 1095, 1460, 1825]
CURVE = [
    {'currency': 'JOD', 'index': 'JOD-3M', 'tenor_days': 90, 'rate': '0.060000'},
    {'currency': 'JOD', 'index': 'JOD-3M', 'tenor_days': 365, 'rate': '0.057500'},
    {'currency': 'JOD', 'index': 'JOD-3M', 'tenor_days': 1825, 'rate': '0.055000'},
    {'currency': 'USD', 'index': 'USD-SOFR-3M', 'tenor_days': 90, 'rate': '0.043000'},
    {'currency': 'USD', 'index': 'USD-SOFR-3M', 'tenor_days': 365, 'rate': '0.040000'},
    {'currency': 'USD', 'index': 'USD-SOFR-3M', 'tenor_days': 1825, 'rate': '0.037500'},
]


def seed(apps, schema_editor):
    Entity = apps.get_model('cashflows', 'Entity')
    Config = apps.get_model('cashflows', 'EntityConfiguration')
    Contract = apps.get_model('cashflows', 'PortfolioContract')
    Run = apps.get_model('cashflows', 'CalculationRun')
    entity = Entity.objects.get(slug='jordan-mock')
    entity.name = 'Jordan-Mock'
    entity.country = 'Jordan'
    entity.base_currency = 'JOD'
    entity.is_mock = True
    entity.save(update_fields=['name', 'country', 'base_currency', 'is_mock'])
    Config.objects.update_or_create(entity=entity, defaults={
        'as_of_date': AS_OF, 'bucket_days': BUCKETS,
        'interest_projection': 'constant', 'forward_curve': CURVE, 'revision': 1,
    })
    # These are only mock records, so replace prior miniature seed and its old results.
    Run.objects.filter(entity_ref=entity).delete()
    Contract.objects.filter(entity=entity).delete()

    def dated(cid, product, principal, rate, maturity, method='bullet', currency='JOD',
              frequency=3, next_payment=None, floating=False):
        item = {
            'contract_id': cid, 'product': product, 'currency': currency,
            'principal': str(principal), 'annual_rate': str(rate),
            'rate_type': 'floating' if floating else 'fixed', 'repayment': method,
            'day_count': 'ACT/365F', 'frequency_months': frequency,
            'accrual_start': AS_OF, 'next_payment': next_payment or maturity,
            'maturity': maturity, 'end_of_month': False,
        }
        if floating:
            item.update({'interest_rate_index': 'JOD-3M' if currency == 'JOD' else 'USD-SOFR-3M',
                         'client_rate_spread': '0.012500' if currency == 'JOD' else '0.018000',
                         'rate_floor': '0.000000'})
        return item

    contracts = []
    # Direct credit facilities: JOD 1.336bn, approximately 10% of the publicly
    # disclosed JOD 13.358bn Arab Bank plc balance.  Maturities deliberately span
    # all bank reporting buckets and include fixed and floating instruments.
    loan_amounts = [168, 142, 126, 118, 105, 92, 86, 78, 70, 64, 55, 48, 41, 31, 18, 10]
    loan_maturities = ['2026-01-05', '2026-01-12', '2026-01-20', '2026-01-30', '2026-02-20', '2026-03-25', '2026-06-30', '2026-09-30', '2026-12-31', '2027-12-31', '2028-12-31', '2029-12-31', '2030-12-31', '2031-12-31', '2032-12-31', '2033-12-31']
    for index, (amount, maturity) in enumerate(zip(loan_amounts, loan_maturities), 1):
        contracts.append(dated(f'JOD-LN-{index:03}', 'loan', f'{amount * 1000000}.000',
            '0.071000' if index % 4 else '0.074500', maturity,
            'equal_principal' if index % 3 else 'level_payment',
            next_payment='2026-03-31' if maturity > '2026-03-31' else maturity,
            floating=index in (4, 8, 12, 16)))

    # Investment portfolio: JOD 613m. These are contractual bond cash flows,
    # separate from the later full counterbalancing-capacity mapping.
    bond_amounts = [110, 100, 90, 82, 75, 60, 45, 30, 21]
    bond_maturities = ['2026-01-07', '2026-01-28', '2026-03-31', '2026-06-30', '2026-12-31', '2027-12-31', '2028-12-31', '2030-12-31', '2032-12-31']
    for index, (amount, maturity) in enumerate(zip(bond_amounts, bond_maturities), 1):
        contracts.append(dated(f'JOD-BOND-{index:03}', 'bond', f'{amount * 1000000}.000', '0.056000', maturity,
            frequency=6, next_payment='2026-06-30' if maturity > '2026-06-30' else maturity))

    # Interbank placements: synthetic contractual subset of cash/due-from-banks.
    for index, (amount, maturity) in enumerate(zip([120, 100, 85, 70, 50, 35, 25, 15],
                                                     ['2026-01-01', '2026-01-08', '2026-01-21', '2026-02-15', '2026-03-31', '2026-06-30', '2026-09-30', '2026-12-31']), 1):
        contracts.append(dated(f'JOD-IB-{index:03}', 'interbank_asset', f'{amount * 1000000}.000', '0.053000', maturity,
            frequency=1, next_payment=maturity))

    # Customer deposits: JOD 2.378bn, approximately 10% of the published PLC
    # deposit balance. Open-maturity CASA is intentionally not behaviourally run off.
    for index, amount in enumerate([220, 180, 160, 130, 110, 90, 70, 45, 25], 1):
        contracts.append({'contract_id': f'JOD-CASA-{index:03}', 'product': 'demand_deposit', 'currency': 'JOD',
                          'principal': f'{amount * 1000000}.000'})
    term_amounts = [200, 170, 150, 140, 130, 120, 110, 100, 90, 70, 60, '7.6']
    term_maturities = ['2026-01-02', '2026-01-10', '2026-01-24', '2026-02-28', '2026-03-31', '2026-06-30', '2026-09-30', '2026-12-31', '2027-12-31', '2028-12-31', '2030-12-31', '2032-12-31']
    for index, (amount, maturity) in enumerate(zip(term_amounts, term_maturities), 1):
        principal = '7600000.000' if str(amount) == '7.6' else f'{amount}000000.000'
        contracts.append(dated(f'JOD-TD-{index:03}', 'term_deposit', principal, '0.047500', maturity,
            frequency=3, next_payment='2026-03-31' if maturity > '2026-03-31' else maturity))

    # Due to banks: JOD 228.156m, scaled from the published JOD 2.282bn balance.
    for index, (amount, maturity, is_float) in enumerate(zip([65, 50, 45, 35, 20, '13.1563'],
                                                               ['2026-03-31', '2026-12-31', '2027-12-31', '2028-12-31', '2030-12-31', '2032-12-31'],
                                                               [False, True, False, True, False, True]), 1):
        principal = '13156300.000' if str(amount) == '13.1563' else f'{amount}000000.000'
        contracts.append(dated(f'JOD-BOR-{index:03}', 'borrowing', principal, '0.054000', maturity,
            frequency=6, next_payment='2026-06-30' if maturity > '2026-06-30' else maturity, floating=is_float))

    # Small USD satellite portfolio makes the currency selector and USD forward curve
    # meaningful without claiming it is Arab Bank's actual Jordan currency split.
    for index, (product, amount, maturity, rate) in enumerate([
        ('loan', '85000000.00', '2027-12-31', '0.061000'), ('loan', '70000000.00', '2028-12-31', '0.063000'),
        ('loan', '55000000.00', '2030-12-31', '0.064000'), ('loan', '35000000.00', '2032-12-31', '0.066000'),
        ('bond', '60000000.00', '2026-06-30', '0.045000'), ('bond', '50000000.00', '2028-12-31', '0.046000'),
        ('bond', '40000000.00', '2031-12-31', '0.047000'), ('interbank_asset', '100000000.00', '2026-01-15', '0.042000'),
        ('interbank_asset', '80000000.00', '2026-03-31', '0.042000'), ('interbank_asset', '60000000.00', '2026-09-30', '0.043000'),
        ('term_deposit', '160000000.00', '2026-02-28', '0.039000'), ('term_deposit', '120000000.00', '2026-12-31', '0.040000'),
        ('term_deposit', '90000000.00', '2028-12-31', '0.041000'), ('borrowing', '95000000.00', '2027-12-31', '0.046000'),
    ], 1):
        contracts.append(dated(f'USD-{product[:2].upper()}-{index:03}', product, amount, rate, maturity,
            'equal_principal' if product == 'loan' else 'bullet', currency='USD', frequency=3,
            next_payment='2026-03-31' if maturity > '2026-03-31' else maturity,
            floating=product in ('loan', 'borrowing') and index % 2 == 0))
    for index, amount in enumerate(['120000000.00', '90000000.00', '60000000.00', '30000000.00'], 1):
        contracts.append({'contract_id': f'USD-CASA-{index:03}', 'product': 'demand_deposit', 'currency': 'USD', 'principal': amount})

    Contract.objects.bulk_create([Contract(entity=entity, external_id=item['contract_id'], terms=item) for item in contracts])


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0004_entityconfiguration_interest_settings')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
