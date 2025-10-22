import hmac
import hashlib
import json
import requests

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse

from .models import Bundle, Purchase

# ---------------------------
# SIGNUP / LOGIN / LOGOUT
# ---------------------------
def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return redirect("signup")

        user = User.objects.create_user(username=username, email=email, password=password)
        user.save()
        messages.success(request, "Account created successfully! You can log in now.")
        return redirect("login")

    return render(request, "core/signup.html")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid credentials")
            return redirect("login")

    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------------------
# DASHBOARD (Show Bundles)
# ---------------------------
@login_required
def dashboard(request):
    bundles = Bundle.objects.all()
    return render(request, "core/dashboard.html", {"bundles": bundles})


# ---------------------------
# BUY BUNDLE
# ---------------------------
@login_required
def buy_bundle(request):
    bundle_code = request.GET.get("code")
    bundle = get_object_or_404(Bundle, code=bundle_code)

    if request.method == "POST":
        recipient = request.POST.get("recipient")
        amount = request.POST.get("amount")

        # Create a purchase record (unpaid)
        purchase = Purchase.objects.create(
            user=request.user,
            bundle=bundle,
            recipient=recipient,
            amount=amount,
            paid=False
        )

        # Initialize Paystack transaction
        paystack_url = "https://api.paystack.co/transaction/initialize"
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": request.user.email or "customer@example.com",
            "amount": int(float(amount) * 100),  # Convert to kobo
            "metadata": {"purchase_id": purchase.id, "recipient": recipient},
            "callback_url": request.build_absolute_uri("/payment-success/"),
        }

        response = requests.post(paystack_url, headers=headers, json=data)
        if response.status_code == 200:
            checkout_url = response.json()["data"]["authorization_url"]
            return redirect(checkout_url)
        else:
            messages.error(request, "Error initializing payment. Try again.")
            purchase.delete()  # Cleanup failed purchase
            return redirect("dashboard")

    return render(request, "core/buy_bundle.html", {"bundle": bundle})


# ---------------------------
# PAYMENT SUCCESS CALLBACK
# ---------------------------
@login_required
def payment_success(request):
    messages.success(request, "Payment successful! Your bundle will be processed shortly.")
    return redirect("dashboard")


# ---------------------------
# PAYSTACK WEBHOOK
# ---------------------------
@login_required
def paystack_webhook(request):
    """Handle Paystack webhook events"""
    if request.method != "POST":
        return HttpResponse(status=405)

    paystack_signature = request.headers.get("X-Paystack-Signature")
    payload = request.body
    secret = settings.PAYSTACK_SECRET_KEY.encode()
    hash_hmac = hmac.new(secret, payload, hashlib.sha512).hexdigest()

    if paystack_signature != hash_hmac:
        return HttpResponse(status=400)

    event = json.loads(payload)

    # Handle successful charges
    if event['event'] == 'charge.success':
        metadata = event['data']['metadata']
        purchase_id = metadata.get("purchase_id")

        try:
            purchase = Purchase.objects.get(id=purchase_id)
            purchase.paid = True
            purchase.api_transaction_id = event['data']['reference']
            purchase.save()
        except Purchase.DoesNotExist:
            print(f"Purchase ID {purchase_id} not found")

    return HttpResponse(status=200)
