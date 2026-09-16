from django.db import migrations


def seed_capacity(apps, schema_editor):
    Entity = apps.get_model('cashflows', 'Entity')
    Contract = apps.get_model('cashflows', 'PortfolioContract')
    entity = Entity.objects.get(slug='jordan-mock')
    Contract.objects.filter(entity=entity, external_id__startswith='JOD-CASH-').delete()
    Contract.objects.filter(entity=entity, external_id__startswith='USD-CASH-').delete()
    positions = [('JOD-CASH-001','JOD','380000000.000'),('JOD-CASH-002','JOD','250000000.000'),
                 ('JOD-CASH-003','JOD','180000000.000'),('JOD-CASH-004','JOD','120000000.000'),
                 ('JOD-CASH-005','JOD','80000000.000'),('JOD-CASH-006','JOD','38504400.000'),
                 ('USD-CASH-001','USD','180000000.00'),('USD-CASH-002','USD','120000000.00')]
    Contract.objects.bulk_create([Contract(entity=entity,external_id=cid,terms={'contract_id':cid,'product':'cash_central_bank','currency':currency,'principal':principal}) for cid,currency,principal in positions])


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0007_fix_final_mock_term_deposit')]
    operations = [migrations.RunPython(seed_capacity, migrations.RunPython.noop)]
