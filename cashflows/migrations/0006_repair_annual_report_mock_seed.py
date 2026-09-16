from django.db import migrations


def repair(apps, schema_editor):
    Contract = apps.get_model('cashflows', 'PortfolioContract')
    for contract in Contract.objects.filter(entity__slug='jordan-mock', external_id__in=['JOD-TD-009', 'JOD-TD-010', 'JOD-TD-011', 'JOD-TD-012']):
        terms = contract.terms
        terms['next_payment'] = '2026-03-31'
        contract.terms = terms
        contract.save(update_fields=['terms'])
    contract = Contract.objects.get(entity__slug='jordan-mock', external_id='JOD-BOR-006')
    terms = contract.terms
    terms['principal'] = '13156300.000'
    contract.terms = terms
    contract.save(update_fields=['terms'])
    contract = Contract.objects.get(entity__slug='jordan-mock', external_id='JOD-TD-012')
    terms = contract.terms
    terms['principal'] = '7600000.000'
    contract.terms = terms
    contract.save(update_fields=['terms'])


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0005_annual_report_aligned_jordan_mock')]
    operations = [migrations.RunPython(repair, migrations.RunPython.noop)]
