from django.contrib import admin
from .models import Item, Log, Like,Feature, Distance, Recommendation
from django import forms
import pprint
from django.forms import TextInput, Textarea, URLInput
from django.db import models
# Register your models here.
from django.contrib.sessions.models import Session
class SessionAdmin(admin.ModelAdmin):
    def _session_data(self, obj):
        return pprint.pformat(obj.get_decoded()).replace('\n', '<br>\n')
    _session_data.allow_tags=True
    list_display = ['session_key', '_session_data', 'expire_date']
    readonly_fields = ['_session_data']
    exclude = ['session_data']
    date_hierarchy='expire_date'

class LogAdmin(admin.ModelAdmin):
    list_display = ('user_id','event_type', 'product_id','timestamp_in','timestamp_out','timestamp_delta', 'rank')
    list_per_page = 20
    list_display_links = ('event_type', 'product_id','timestamp_in','timestamp_out','timestamp_delta', 'rank')
    empty_value_display = 'Not Set'
    list_filter = ('event_type',)

class LikeAdmin(admin.ModelAdmin):
    # list_display = ('user_id', 'product_id',)
    list_per_page = 20
    # list_display_links = ('user_id', 'product_id')
    empty_value_display = 'Not Set'
    list_filter = ('user_id','product_id',)

class ItemAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug':('name',)}
    search_fields = ['name__icontains','material__icontains','furniture_location__icontains', 
                        'address__icontains', 'price__icontains', 'color__icontains']
    list_filter = ('furniture_location','color','material',)
    list_display = ('id','name','material', 'color','furniture_location','price',)
    list_display_links = ('id','name','material', 'color','furniture_location','price',)
    
    list_per_page = 100
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size':'100'})},
        models.TextField: {'widget': Textarea(attrs={'rows':20, 'cols':100})},
    }

class FeatureAdmin(admin.ModelAdmin):
    list_per_page = 20
    

class DistanceAdmin(admin.ModelAdmin):
    search_fields = ['product_id__exact', 'other_product_id__exact']
    ordering = ('product_id','other_product_id')
    list_display = ('product_id','other_product_id','name_distance','material_distance', 'color_distance','description_distance', 'weight_distance', 'price_distance', 'dimension_distance', 'furniture_location_distance','total_distance','temp_distance',)
    list_display_links = ('product_id','other_product_id','name_distance','material_distance', 'color_distance','description_distance', 'weight_distance', 'price_distance', 'dimension_distance', 'furniture_location_distance','total_distance','temp_distance',)
    list_per_page = 150
class RecommendationAdmin(admin.ModelAdmin):
    search_fields = ['user_id__exact']
    list_display = ('user_id','product_id','rank','created_at',)
    list_display_links = ('user_id','product_id','rank','created_at',)
    list_per_page = 150

admin.site.register(Item,ItemAdmin)
admin.site.register(Log,LogAdmin)
admin.site.register(Like,LikeAdmin)
admin.site.register(Session, SessionAdmin)
admin.site.register(Feature, FeatureAdmin)
admin.site.register(Distance, DistanceAdmin)
admin.site.register(Recommendation, RecommendationAdmin)


admin.site.site_header  =  'Website Skripsi Admin Panel' 
admin.site.site_title  =  'Website Skripsi'
admin.site.index_title  =  'Data Website Skripsi'