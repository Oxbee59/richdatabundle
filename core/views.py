from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import requests
import json
from django.utils.timezone import now

from .models import Bundle, Purchase
from .forms import SignupForm, LoginForm


# ---------------------------
# AUTHENTICATION VIEWS
# ---------------------------
def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Signup successful!")
            return redirect("dashboard")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SignupForm()
    return render(request, "core/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user)
                return redirect("dashboard")
            else:
                messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()
    return render(request, "core/login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("login")


# ---------------------------
# DASHBOARD & PROFILE
# ---------------------------
@login_required
def dashboard(request):
    return render(request, "core/dashboard.html")


@login_required
def profile(request):
    return render(request, "core/profile.html", {"user": request.user})


@login_required
def purchases(request):
    user_purchases = Purchase.objects.filter(user=request.user).order_by("-paid_at")
    return render(request, "core/purchases.html", {"purchases": user_purchases})


# ---------------------------
# BUY BUNDLE
# ---------------------------
@login_required
def buy_bundle(request):
    bundles = Bundle.objects.all().order_by("price")

    # --- if no bundles exist, preload 3 defaults for display ---
    if not bundles.exists():
        Bundle.objects.bulk_create([
            Bundle(name="MTN 1GB", price=Decimal("10.00"), code="MTN1GB"),
            Bundle(name="Telecel 2GB", price=Decimal("18.00"), code="TELECEL2GB"),
            Bundle(name="AirtelTigo 3GB", price=Decimal("25.00"), code="AIRTELTIGO3GB"),
        ])
        bundles = Bundle.objects.all().order_by("price")

    if request.method == "POST":
        recipient = request.POST.get("recipient")
        bundle_id = request.POST.get("bundle_id")

        if not recipient or not bundle_id:
            messages.error(request, "Please provide a valid recipient and select a bundle.")
            return redirect("buy_bundle")

        try:
            bundle = Bundle.objects.get(id=bundle_id)
        except Bundle.DoesNotExist:
            messages.error(request, "Invalid bundle selected.")
            return redirect("buy_bundle")

        amount = bundle.price
        user = request.user

        # Create a purchase record (unpaid for now)
        purchase = Purchase.objects.create(
            user=user, recipient=recipient, bundle=bundle, amount=amount, status="pending"
        )

        # Redirect to Paystack payment page
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": user.email,
            "amount": int(amount * 100),  # in kobo
            "reference": str(purchase.id),
            "callback_url": request.build_absolute_uri("/webhook/"),
        }

        r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data)
        res = r.json()

        if res.get("status"):
            return redirect(res["data"]["authorization_url"])
        else:
            messages.error(request, "Payment initialization failed. Try again.")
            return redirect("buy_bundle")

    return render(request, "core/buy_bundle.html", {"bundles": bundles})


# ---------------------------
# PAYSTACK WEBHOOK
# ---------------------------
@csrf_exempt
def webhook(request):
    """Paystack webhook to verify payment and deliver data via DataDash"""
    try:
        payload = json.loads(request.body.decode("utf-8"))
        event = payload.get("event")
        data = payload.get("data", {})

        if event == "charge.success":
            reference = data.get("reference")
            amount = Decimal(data.get("amount", 0)) / 100

            try:
                purchase = Purchase.objects.get(id=reference, status="pending")
                purchase.status = "paid"
                purchase.paid_at = now()
                purchase.save()

                # --- Deliver via DataDash ---
                try:
                    headers = {
                        "Authorization": f"Bearer {settings.DATADASH_API_KEY}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "plan_id": purchase.bundle.code,
                        "recipient": purchase.recipient,
                        "price": float(purchase.amount),
                    }
                    r = requests.post(f"{settings.DATADASH_BASE_URL}/v1/orders", headers=headers, json=payload)
                    if r.status_code not in (200, 201):
                        print("DataDash delivery failed:", r.text)
                except Exception as e:
                    print("Webhook DataDash error:", e)

            except Purchase.DoesNotExist:
                pass

    except Exception as e:
        print("Webhook processing error:", e)

    return HttpResponse(status=200)
