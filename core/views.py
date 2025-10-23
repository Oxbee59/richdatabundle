from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import requests
import json
from django.utils.timezone import now

from .forms import SignupForm, BuyForm
from .models import Bundle, Purchase


# -------------------------
# Authentication Views
# -------------------------
def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password1"])
            user.save()
            messages.success(request, "Account created successfully. You can now log in.")
            return redirect("login")
    else:
        form = SignupForm()
    return render(request, "core/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get("next") or "dashboard"
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, "core/login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# -------------------------
# Dashboard
# -------------------------
@login_required
def dashboard(request):
    bundles = Bundle.objects.all().order_by("price")
    # Preload default bundles if none exist
    if not bundles.exists():
        Bundle.objects.bulk_create([
            Bundle(name="MTN 1GB", price=Decimal("10.00"), code="MTN1GB"),
            Bundle(name="Telecel 2GB", price=Decimal("18.00"), code="TELECEL2GB"),
            Bundle(name="AirtelTigo 3GB", price=Decimal("25.00"), code="AIRTELTIGO3GB"),
        ])
        bundles = Bundle.objects.all().order_by("price")

    purchases = Purchase.objects.filter(user=request.user).order_by("-paid_at")[:5]

    return render(request, "core/dashboard.html", {
        "bundles": bundles,
        "purchases": purchases,
    })


# -------------------------
# Buy Bundle
# -------------------------
@login_required
def buy_bundle(request):
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

        # Create purchase record (pending)
        purchase = Purchase.objects.create(
            user=user, recipient=recipient, bundle=bundle, amount=amount, paid=False
        )

        # Initialize Paystack payment
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": user.email,
            "amount": int(amount * 100),  # in kobo
            "reference": str(purchase.id),
            "callback_url": request.build_absolute_uri("/paystack-webhook/"),
        }
        r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data)
        res = r.json()
        if res.get("status"):
            return redirect(res["data"]["authorization_url"])
        else:
            messages.error(request, "Payment initialization failed. Try again.")
            return redirect("buy_bundle")

    return render(request, "core/buy_bundle.html", {"bundles": bundles})


# -------------------------
# My Purchases
# -------------------------
@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-paid_at")
    return render(request, "core/my_purchases.html", {"purchases": purchases})


# -------------------------
# Paystack Webhook
# -------------------------
@csrf_exempt
def paystack_webhook(request):
    payload = json.loads(request.body.decode("utf-8"))
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference")
        try:
            purchase = Purchase.objects.get(id=reference, paid=False)
            purchase.paid = True
            purchase.paid_at = now()
            purchase.save()

            # Deliver bundle via DataDash
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

    return HttpResponse(status=200)
