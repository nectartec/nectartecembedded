# Generated by Django 5.0.1 on 2025-03-04 18:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clienteshtmls', '0002_clienteshtml_embed_token_clienteshtml_embed_url_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clienteshtml',
            name='TOKEN_UUID',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
