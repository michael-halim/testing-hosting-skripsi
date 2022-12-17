# Generated by Django 4.1 on 2022-09-21 11:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0004_distances'),
    ]

    operations = [
        migrations.AddField(
            model_name='features',
            name='dimension_height_feature',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='features',
            name='dimension_length_feature',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='features',
            name='dimension_width_feature',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='features',
            name='weight_feature',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
    ]
