from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import Bundle, Purchase
from .forms import SignupForm, BuyForm
from decimal import Decimal
import requests
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now

# ----------------------
# Auth Views
# ----------------------
def signup_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])
            user.save()
            messages.success(request, "Signup successful. Please login.")
            return redirect("login")
    else:
        form = SignupForm()
    return render(request, "core/signup.html", {"form": form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid credentials.")
    return render(request, "core/login.html")

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("login")

# ----------------------
# Dashboard
# ----------------------
@login_required
def dashboard(request):
    bundles = Bundle.objects.all().order_by("price")[:3]
    purchases = Purchase.objects.filter(user=request.user).order_by("-paid_at")[:5]
    return render(request, "core/dashboard.html", {
        "bundles": bundles,
        "purchases": purchases
    })

# ----------------------
# Buy Bundles
# ----------------------
@login_required
def buy_bundle(request):
    bundles = Bundle.objects.all().order_by("price")

    # preload defaults if empty
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
            messages.error(request, "Select bundle and recipient.")
            return redirect("buy_bundle")
        try:
            bundle = Bundle.objects.get(id=bundle_id)
        except Bundle.DoesNotExist:
            messages.error(request, "Invalid bundle.")
            return redirect("buy_bundle")

        amount = bundle.price
        purchase = Purchase.objects.create(
            user=request.user,
            recipient=recipient,
            bundle=bundle,
            amount=amount,
            status="pending"
        )

        # Paystack initialization
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": request.user.email,
            "amount": int(amount * 100),
            "reference": str(purchase.id),
            "callback_url": request.build_absolute_uri("/paystack-webhook/"),
        }
        r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data)
        res = r.json()
        if res.get("status"):
            return redirect(res["data"]["authorization_url"])
        messages.error(request, "Payment initialization failed.")
        return redirect("buy_bundle")

    return render(request, "core/buy_bundle.html", {"bundles": bundles})

# ----------------------
# Paystack Webhook
# ----------------------
@csrf_exempt
def paystack_webhook(request):
    import json
    payload = json.loads(request.body.decode("utf-8"))
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference")
        try:
            purchase = Purchase.objects.get(id=reference, status="pending")
            purchase.status = "paid"
            purchase.paid_at = now()
            purchase.save()
            # deliver via DataDash
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
                print("DataDash error:", e)
        except Purchase.DoesNotExist:
            pass
    return HttpResponse(status=200)

# ----------------------
# My Purchases
# ----------------------
@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-paid_at")
    return render(request, "core/my_purchases.html", {"purchases": purchases})

# ----------------------
# Profile
# ----------------------
@login_required
def profile(request):
    return render(request, "core/profile.html")
