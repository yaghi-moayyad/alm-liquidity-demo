from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[('cashflows','0013_regulatory_snapshots')]
    operations=[
        migrations.CreateModel(name='LcrStressConfiguration',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('configuration',models.JSONField(default=dict)),('top_depositor_amounts',models.JSONField(default=dict)),('updated',models.DateTimeField(auto_now=True)),
            ('entity',models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,related_name='lcr_stress_configuration',to='cashflows.entity')),
        ]),
        migrations.CreateModel(name='LcrStressRun',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('as_of_date',models.DateField()),('configuration',models.JSONField(default=dict)),('results',models.JSONField(default=dict)),('created',models.DateTimeField(auto_now_add=True)),
            ('entity',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='lcr_stress_runs',to='cashflows.entity')),
        ],options={'ordering':['-created']}),
    ]
