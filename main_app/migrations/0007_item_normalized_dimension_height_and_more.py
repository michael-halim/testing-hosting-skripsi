# Generated by Django 4.1 on 2022-09-22 13:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0006_rename_distances_distance_rename_features_feature'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='normalized_dimension_height',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='item',
            name='normalized_dimension_length',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='item',
            name='normalized_dimension_width',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='item',
            name='normalized_weight',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=12),
        ),
    ]
