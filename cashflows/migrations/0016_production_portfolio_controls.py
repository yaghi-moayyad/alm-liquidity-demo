from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0015_behavioural_engine_extensions')]

    operations = [
        migrations.AddField(
            model_name='entityconfiguration',
            name='proxy_maturity_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='entityconfiguration',
            name='proxy_maturity_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='entityconfiguration',
            name='proxy_maturity_scope',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='cashflow',
            name='maturity_source',
            field=models.CharField(default='bank', max_length=24),
        ),
    ]
