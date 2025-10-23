# core/views.py
import json
import hmac
import hashlib
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import requests
from django.utils.timezone import now

from .forms import SignupForm, BuyForm
from .models import Bundle, Purchase
from .utils import sync_datadash_plans

# ---------------------------
# AUTH
# ---------------------------
def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password1"])
            user.save()
            messages.success(request, "Account created. Log in now.")
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
            nxt = request.GET.get("next") or "dashboard"
            return redirect(nxt)
        messages.error(request, "Invalid username or password.")
    return render(request, "core/login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------------------
# DASHBOARD - only welcome + trust message
# ---------------------------
@login_required
def dashboard(request):
    # Sync in background? We call sync only if admin triggers or no bundles yet
    bundles_exist = Bundle.objects.exists()
    trust_message = "Trusted, secure, and fast — buy your data bundles here. Go to Buy Bundles to proceed."
    return render(request, "core/dashboard.html", {
        "user": request.user,
        "bundles_exist": bundles_exist,
        "trust_message": trust_message,
    })


# ---------------------------
# BUY BUNDLE
# ---------------------------
@login_required
def buy_bundle(request):
    # show bundles from admin (DB). If none exist, create three sample bundles for display (admin can later edit/delete)
    bundles = Bundle.objects.all().order_by("price")
    if not bundles.exists():
        created = Bundle.objects.bulk_create([
            Bundle(name="MTN 1GB", price=Decimal("5.00"), code="MTN_1GB"),
            Bundle(name="Telecel 2GB", price=Decimal("18.00"), code="TELECEL_2GB"),
            Bundle(name="AirtelTigo 3GB", price=Decimal("25.00"), code="AIRTELTIGO_3GB"),
        ])
        bundles = Bundle.objects.all().order_by("price")

    if request.method == "POST":
        recipient = request.POST.get("recipient", "").strip()
        bundle_id = request.POST.get("bundle_id")
        if not recipient:
            messages.error(request, "Please enter recipient number.")
            return redirect("buy_bundle")
        if not bundle_id:
            messages.error(request, "Invalid bundle selection.")
            return redirect("buy_bundle")
        try:
            bundle = Bundle.objects.get(id=bundle_id)
        except Bundle.DoesNotExist:
            messages.error(request, "Bundle not found.")
            return redirect("buy_bundle")

        # create pending Purchase
        purchase = Purchase.objects.create(
            user=request.user,
            recipient=recipient,
            bundle=bundle,
            amount=bundle.price,
            paid=False,
        )

        # Initialize Paystack transaction
        paystack_headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        amount_kobo = int(bundle.price * 100)  # decimal -> kobo
        data = {
            "email": request.user.email or "noemail@example.com",
            "amount": amount_kobo,
            "metadata": {
                "purchase_id": str(purchase.id),
                "bundle_code": bundle.code,
                "recipient": recipient,
                "username": request.user.username,
            },
            # redirect the user after payment (we rely on webhook for processing)
            "callback_url": request.build_absolute_uri("/payment-success/"),
        }

        try:
            resp = requests.post("https://api.paystack.co/transaction/initialize", headers=paystack_headers, json=data, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            auth_url = payload["data"]["authorization_url"]
            return redirect(auth_url)
        except Exception as e:
            print("Paystack init error:", e)
            messages.error(request, "Payment initialization failed. Try again.")
            return redirect("buy_bundle")

    # Render buy page (cards layout)
    return render(request, "core/buy_bundle.html", {"bundles": bundles})


# ---------------------------
# PAYMENT REDIRECT (user returns here from Paystack)
# We keep it simple — rely on webhook to finalize delivery.
# ---------------------------
@login_required
def payment_success(request):
    messages.success(request, "Payment completed or in progress. Delivery will proceed once payment is confirmed.")
    return redirect("my_purchases")


# ---------------------------
# MY PURCHASES
# ---------------------------
@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-paid_at", "-created_at")
    return render(request, "core/my_purchases.html", {"purchases": purchases})


# ---------------------------
# PROFILE
# ---------------------------
@login_required
def profile(request):
    return render(request, "core/profile.html", {"user": request.user})


# ---------------------------
# PAYSTACK WEBHOOK
# ---------------------------
@csrf_exempt
def paystack_webhook(request):
    # Validate signature if PAYSTACK_SECRET_KEY_WEBHOOK provided, otherwise best-effort
    signature = request.headers.get("X-Paystack-Signature", "")
    raw = request.body or b""
    try:
        if getattr(settings, "PAYSTACK_SECRET_KEY", None):
            # Paystack webhook uses HMAC-SHA512 with your secret (the same secret)
            secret = settings.PAYSTACK_SECRET_KEY.encode()
            computed = hmac.new(secret, raw, hashlib.sha512).hexdigest()
            if signature and not hmac.compare_digest(computed, signature):
                print("Paystack webhook signature mismatch")
                return HttpResponse(status=400)
    except Exception:
        # fallback to not blocking webhook if verification setup differs
        pass

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print("Invalid webhook JSON:", e)
        return HttpResponse(status=400)

    event = payload.get("event")
    data = payload.get("data", {}) or {}

    # Only process successful charges
    if event in ("charge.success", "transaction.success"):
        metadata = data.get("metadata", {}) or {}
        purchase_id = metadata.get("purchase_id") or metadata.get("reference") or data.get("reference")
        amount_paid = Decimal(data.get("amount", 0)) / 100
        paystack_ref = data.get("reference")

        # Try to find Purchase
        purchase = None
        if purchase_id:
            try:
                purchase = Purchase.objects.filter(id=int(purchase_id)).first()
            except Exception:
                purchase = None

        # fallback: try to find by metadata bundle_code + recipient + amount (best-effort)
        if not purchase:
            plan_code = metadata.get("bundle_code")
            recipient = metadata.get("recipient")
            q = Purchase.objects.filter(bundle__code=plan_code, recipient=recipient, paid=False).order_by("-created_at")
            purchase = q.first() if q.exists() else None

        if purchase:
            purchase.paid = True
            purchase.paid_at = now()
            # store paystack ref and preserve datadash placeholder
            purchase.api_transaction_id = (purchase.api_transaction_id or "") + f" paystack:{paystack_ref}"
            purchase.save()

            # create DataDash order to deliver bundle (debits your DataDash wallet)
            try:
                dd_headers = {
                    "Authorization": f"Bearer {settings.DATADASH_API_KEY}",
                    "Content-Type": "application/json",
                }
                dd_payload = {
                    "plan_id": purchase.bundle.code,
                    "recipient": purchase.recipient,
                    "price": float(purchase.amount),
                }
                r = requests.post(f"{settings.DATADASH_BASE_URL.rstrip('/')}/v1/orders", headers=dd_headers, json=dd_payload, timeout=15)
                if r.status_code in (200, 201):
                    # optionally capture returned order id
                    try:
                        resp_json = r.json()
                        datadash_id = None
                        if isinstance(resp_json, dict):
                            datadash_id = resp_json.get("order_id") or resp_json.get("data", {}).get("order_id")
                        if datadash_id:
                            purchase.api_transaction_id = (purchase.api_transaction_id or "") + f" | datadash:{datadash_id}"
                            purchase.save()
                    except Exception:
                        pass
                else:
                    print("DataDash delivery failed:", r.status_code, r.text)
            except Exception as e:
                print("Webhook DataDash error:", e)
        else:
            # create a record if needed
            try:
                bundle = None
                bundle_code = metadata.get("bundle_code")
                if bundle_code:
                    bundle = Bundle.objects.filter(code=bundle_code).first()
                Purchase.objects.create(
                    user=None,
                    recipient=metadata.get("recipient", ""),
                    bundle=bundle,
                    amount=amount_paid,
                    paid=True,
                    api_transaction_id=f"paystack:{paystack_ref}"
                )
            except Exception as e:
                print("Could not create fallback purchase:", e)

    return HttpResponse(status=200)
