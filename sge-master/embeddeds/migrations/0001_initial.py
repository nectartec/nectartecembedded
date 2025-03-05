from django.db import migrations, models

class Migration(migrations.Migration):  # Essa classe precisa existir
    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Embedded',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]