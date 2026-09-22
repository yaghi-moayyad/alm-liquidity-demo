from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cashflows', '0016_production_portfolio_controls'),
    ]

    operations = [
        migrations.AddField(
            model_name='runcontract',
            name='terms',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
