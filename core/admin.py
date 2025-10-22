from django.contrib import admin
from .models import Bundle, Purchase

@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price')
    search_fields = ('name', 'code')

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'bundle', 'recipient', 'amount', 'paid', 'api_transaction_id', 'created_at')
    list_filter = ('paid',)
    search_fields = ('recipient', 'api_transaction_id')
