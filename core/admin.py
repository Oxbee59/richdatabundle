from django.contrib import admin
from .models import Bundle, Purchase, Profile

@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price', 'description')
    search_fields = ('name', 'code')

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'bundle', 'recipient', 'amount', 'paid', 'api_transaction_id', 'created_at')
    list_filter = ('paid',)
    search_fields = ('user__username', 'recipient', 'bundle__name')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_agent', 'phone')
    search_fields = ('user__username', 'phone')
