from django.db import migrations


def fix(apps, schema_editor):
    Contract = apps.get_model('cashflows', 'PortfolioContract')
    contract = Contract.objects.get(entity__slug='jordan-mock', external_id='JOD-TD-012')
    terms = contract.terms
    terms['principal'] = '7600000.000'
    contract.terms = terms
    contract.save(update_fields=['terms'])


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0006_repair_annual_report_mock_seed')]
    operations = [migrations.RunPython(fix, migrations.RunPython.noop)]
