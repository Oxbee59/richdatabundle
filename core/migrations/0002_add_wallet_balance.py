from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='wallet_balance',
            field=models.DecimalField(default=0.0, max_digits=12, decimal_places=2),
        ),
    ]
