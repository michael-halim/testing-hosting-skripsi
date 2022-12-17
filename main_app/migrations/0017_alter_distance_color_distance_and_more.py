# Generated by Django 4.1.2 on 2022-12-01 15:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0016_recommendation'),
    ]

    operations = [
        migrations.AlterField(
            model_name='distance',
            name='color_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='description_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='dimension_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='furniture_location_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='material_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='name_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='price_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='temp_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='total_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='distance',
            name='weight_distance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='item',
            name='normalized_dimension',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=9, null=True),
        ),
        migrations.AlterField(
            model_name='item',
            name='normalized_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=9, null=True),
        ),
        migrations.AlterField(
            model_name='item',
            name='normalized_weight',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=9, null=True),
        ),
    ]
