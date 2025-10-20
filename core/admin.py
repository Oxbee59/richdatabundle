from django.contrib import admin
from .models import Bundle,Purchase,Profile
@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display=('network','size_label','price','bundle_code','created_at');list_filter=('network',);search_fields=('size_label','bundle_code')
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display=('user','bundle','recipient','amount','paid','created_at');search_fields=('recipient','user__username')
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display=('user','is_agent','phone')
