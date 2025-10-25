from django.contrib import admin
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from .models import Bundle, Purchase


# Secure admin login: only staff/superusers allowed
def custom_admin_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user and user.is_staff:
            login(request, user)
            return redirect("/admin/")
        else:
            return render(request, "admin/login.html", {
                "error": "Invalid credentials or unauthorized user.",
            })

    return render(request, "admin/login.html")


# Bundle admin configuration
@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "price")
    search_fields = ("name", "code")


# Purchase admin configuration
@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("user", "bundle", "recipient", "amount", "paid", "api_transaction_id", "created_at")
    list_filter = ("paid",)
    search_fields = ("recipient", "api_transaction_id")
