# Generated by Django 5.0.1 on 2025-03-06 18:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clienteshtmls', '0005_alter_clienteshtml_client_html_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clienteshtml',
            name='CLIENT_HTML',
            field=models.CharField(blank=True, max_length=4000, null=True),
        ),
    ]
