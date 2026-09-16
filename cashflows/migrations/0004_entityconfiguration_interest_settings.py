# Generated manually for the contractual interest projection settings.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cashflows', '0003_seed_jordan_mock')]

    operations = [
        migrations.AddField(model_name='entityconfiguration', name='forward_curve', field=models.JSONField(default=list)),
        migrations.AddField(model_name='entityconfiguration', name='interest_projection', field=models.CharField(default='constant', max_length=24)),
    ]
