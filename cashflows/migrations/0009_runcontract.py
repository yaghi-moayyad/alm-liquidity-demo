from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0008_add_mock_counterbalancing_capacity')]

    operations = [
        migrations.CreateModel(
            name='RunContract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contract_id', models.CharField(max_length=64)),
                ('contract_id_key', models.CharField(max_length=64)),
                ('product', models.CharField(max_length=32)),
                ('currency', models.CharField(max_length=3)),
                ('direction', models.CharField(max_length=8)),
                ('run', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='contract_index', to='cashflows.calculationrun')),
            ],
            options={'ordering': ['contract_id']},
        ),
        migrations.AddConstraint(
            model_name='runcontract',
            constraint=models.UniqueConstraint(fields=('run', 'contract_id'), name='unique_run_contract'),
        ),
        migrations.AddIndex(
            model_name='runcontract',
            index=models.Index(fields=['run', 'contract_id_key'], name='run_contract_search_idx'),
        ),
    ]
