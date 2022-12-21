from django.db import models
from datetime import datetime
from django.contrib.auth.models import User
from django_hashids import HashidsField

class Log(models.Model):
    user_id = models.IntegerField()
    event_type = models.CharField(max_length=10)
    product_id = models.IntegerField()
    timestamp_in = models.DateTimeField()
    timestamp_out = models.DateTimeField(null=True)
    timestamp_delta = models.DecimalField(null=True,max_digits = 12, decimal_places = 2)
    rank = models.IntegerField(null=True)

    def __str__(self):
        return str(self.timestamp_in) + ' | ' + str(self.timestamp_out) + ' | ' + str(self.timestamp_delta)

class Like(models.Model):
    user_id = models.IntegerField()
    product_id = models.IntegerField()

    def __str__(self):
        user = User.objects.get(id = self.user_id)
        item = Item.objects.get(id = self.product_id)
        return user.username + ' = LIKES => ' + item.name
        
class Item(models.Model):
    name = models.CharField(max_length = 150)
    slug = models.SlugField(max_length=420,db_index=True)
    pic = models.URLField(max_length = 430)
    address = models.CharField(max_length = 150)
    phone = models.CharField(max_length = 15)
    price = models.IntegerField()
    original_link = models.URLField(max_length = 460)
    description = models.TextField(max_length = 1500)
    additional_desc = models.TextField(max_length = 1500,default='')
    material = models.TextField(max_length = 440, default = '')
    weight = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0)
    weight_unit = models.CharField(max_length = 4, default = '')
    color = models.CharField(max_length = 450, default = '')
    dimension_length = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0)
    dimension_width = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0)
    dimension_height = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0)
    dimension_unit = models.CharField(max_length = 4, default='')
    isProduct = models.BooleanField(default = True)
    furniture_location = models.CharField(max_length = 100, default='')

    vect_name = models.TextField(max_length=4000, null=True)
    vect_color = models.TextField(max_length=500, null=True)
    vect_material = models.TextField(max_length=4000, null=True)
    vect_description = models.TextField(max_length=20000, null=True)
    vect_furniture_location = models.TextField(max_length=100, null=True)
    
    normalized_price = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0, null=True)
    normalized_weight = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0, null=True)
    normalized_dimension = models.DecimalField(max_digits = 12, decimal_places = 2, default = 0, null=True)
    
    def __str__(self):
        return self.name


class Feature(models.Model):
    name_feature = models.TextField(max_length=4000, null=True)
    color_feature = models.TextField(max_length=4000, null=True)
    material_feature = models.TextField(max_length=4000, null=True)
    description_feature = models.TextField(max_length=4000, null=True)
    
    furniture_location_feature = models.TextField(max_length=4000, null=True)

    def __str__(self):
        return 'All Feature Names'

class Distance(models.Model):
    product_id = models.IntegerField()
    other_product_id = models.IntegerField()

    name_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default = 0)
    description_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default = 0)
    material_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default = 0)
    weight_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default = 0)
    color_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default = 0)

    dimension_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default = 0)
    price_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default=0)
    furniture_location_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default=0)
    total_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default=0)
    temp_distance = models.DecimalField(max_digits = 4, decimal_places = 2, default=0)
    
    def __str__(self):
        item = Item.objects.get(id = self.product_id)
        other_item = Item.objects.get(id = self.other_product_id)
        return item.name + ' => ' + other_item.name

class Recommendation(models.Model):
    user_id = models.IntegerField()
    product_id = models.IntegerField()
    rank = models.IntegerField()
    created_at = models.DateTimeField()