# Generated by Django 5.0.1 on 2025-03-04 18:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clienteshtmls', '0003_alter_clienteshtml_token_uuid'),
    ]

    operations = [
        migrations.AddField(
            model_name='clienteshtml',
            name='EXPIRES_AT',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
