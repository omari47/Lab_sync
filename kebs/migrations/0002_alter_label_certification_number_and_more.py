# Generated by Django 5.2 on 2025-04-10 16:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kebs', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='label',
            name='certification_number',
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name='label',
            name='label_data',
            field=models.JSONField(default=dict),
        ),
    ]
