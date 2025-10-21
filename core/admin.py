from django.contrib import admin
from .models import Bundle, Purchase

@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ('name', 'bundle_code', 'price', 'datadash_code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'bundle_code', 'datadash_code')

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'paid', 'api_transaction_id', 'created_at')
    list_filter = ('paid',)
