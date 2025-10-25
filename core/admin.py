from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from .models import Bundle, Purchase


# Restrict admin login to staff/superusers only
class CustomAdminLoginView(auth_views.LoginView):
    def form_valid(self, form):
        user = form.get_user()
        if not user.is_staff:  # Prevent normal user login
            return redirect('/')  # Redirect to home
        return super().form_valid(form)


# Override the default Django admin login view
admin.site.login = CustomAdminLoginView.as_view()


# Bundle admin configuration
@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price')
    search_fields = ('name', 'code')


# Purchase admin configuration
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'bundle', 'recipient', 'amount', 'paid', 'api_transaction_id', 'created_at')
    list_filter = ('paid',)
    search_fields = ('recipient', 'api_transaction_id')
