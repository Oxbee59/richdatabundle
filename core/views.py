import json
import hmac
import hashlib
import requests
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
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
        messages.success(request, "Account created successfully! You can now log in.")
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
            messages.error(request, "Invalid credentials.")
            return redirect("login")

    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------------------
# SYNC DATADASH PLANS
# ---------------------------

def sync_datadash_plans():
    """Fetch /v1/plans from DataDash and sync with local Bundle model."""
    base_url = getattr(settings, "DATADASH_BASE_URL", "https://datadashgh.com/agents/api")
    url = f"{base_url}/v1/plans"
    headers = {"Authorization": f"Bearer {settings.DATADASH_API_KEY}"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print("Failed to fetch DataDash plans:", resp.status_code, resp.text)
            return None

        # ✅ FIX: Handle when response is string or nested JSON
        try:
            plans = resp.json()
            if isinstance(plans, str):
                import json
                plans = json.loads(plans)
        except Exception as e:
            print("Error parsing DataDash JSON:", e)
            return None

        # ✅ Validate format
        if not isinstance(plans, list):
            print("Unexpected DataDash response format:", plans)
            return None

        from .models import Bundle

        for plan in plans:
            if not isinstance(plan, dict):
                print("Skipping invalid plan record:", plan)
                continue

            plan_id = (
                plan.get("id")
                or plan.get("plan_id")
                or plan.get("planId")
                or plan.get("code")
            )
            if not plan_id:
                continue

            price = (
                plan.get("price")
                or plan.get("selling_price")
                or plan.get("amount")
                or 0
            )
            name = plan.get("name") or plan.get("title") or f"Plan {plan_id}"
            description = plan.get("description", "")

            Bundle.objects.update_or_create(
                code=plan_id,
                defaults={
                    "name": name,
                    "price": float(price),
                    "description": description,
                },
            )

        print("✅ DataDash plans synced successfully.")
        return plans

    except Exception as e:
        print("Error syncing DataDash plans:", e)
        return None

# ---------------------------
# DASHBOARD VIEW
# ---------------------------

@login_required
def dashboard(request):
    sync_datadash_plans()  # keep plans fresh
    bundles = Bundle.objects.all().order_by("price")
    return render(request, "core/dashboard.html", {"bundles": bundles})


# ---------------------------
# BUY BUNDLE PAGE
# ---------------------------

@login_required
def buy_bundle(request):
    bundles = Bundle.objects.all().order_by("price")

    if request.method == "POST":
        recipient = request.POST.get("recipient")
        bundle_id = request.POST.get("bundle_id")
        bundle = Bundle.objects.get(id=bundle_id)

        # Initialize Paystack payment
        paystack_url = "https://api.paystack.co/transaction/initialize"
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        amount = int(float(bundle.price) * 100)

        data = {
            "email": request.user.email or "noemail@example.com",
            "amount": amount,
            "metadata": {
                "bundle_code": bundle.code,
                "bundle_name": bundle.name,
                "recipient": recipient,
                "username": request.user.username,
            },
            "callback_url": request.build_absolute_uri("/payment-success/"),
        }

        try:
            res = requests.post(paystack_url, headers=headers, json=data, timeout=15)
            res.raise_for_status()
            auth_url = res.json()["data"]["authorization_url"]

            # Save pending purchase
            Purchase.objects.create(
                user=request.user,
                bundle=bundle,
                recipient=recipient,
                amount=bundle.price,
                paid=False,
            )

            return redirect(auth_url)
        except Exception as e:
            print("Paystack init error:", e)
            messages.error(request, "Payment initialization failed.")
            return redirect("buy_bundle")

    return render(request, "core/buy_bundle.html", {"bundles": bundles})


# ---------------------------
# PAYMENT SUCCESS (user redirected after Paystack)
# ---------------------------

@login_required
def payment_success(request):
    reference = request.GET.get("reference")
    if not reference:
        messages.error(request, "No payment reference found.")
        return redirect("dashboard")

    # Verify Paystack payment
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"

    try:
        res = requests.get(verify_url, headers=headers)
        data = res.json()
        if data.get("data", {}).get("status") == "success":
            metadata = data["data"]["metadata"]
            bundle_code = metadata.get("bundle_code")
            recipient = metadata.get("recipient")
            bundle = Bundle.objects.filter(code=bundle_code).first()

            purchase = Purchase.objects.filter(
                user=request.user, bundle=bundle, recipient=recipient, paid=False
            ).last()
            if purchase:
                purchase.paid = True
                purchase.transaction_id = reference
                purchase.save()

            # Deliver via DataDash
            order_payload = {
                "plan_id": bundle_code,
                "recipient": recipient,
                "price": float(bundle.price),
            }
            dd_headers = {
                "Authorization": f"Bearer {settings.DATADASH_API_KEY}",
                "Content-Type": "application/json",
            }

            r = requests.post(f"{settings.DATADASH_BASE_URL}/v1/orders", headers=dd_headers, json=order_payload)
            if r.status_code in (200, 201):
                messages.success(request, f"Bundle successfully sent to {recipient}!")
            else:
                messages.warning(request, "Payment succeeded but bundle delivery pending.")
        else:
            messages.error(request, "Payment verification failed.")
    except Exception as e:
        print("Payment verification error:", e)
        messages.error(request, "Payment verification failed. Please contact support.")

    return redirect("my_purchases")


# ---------------------------
# MY PURCHASES + PROFILE
# ---------------------------

@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "core/my_purchases.html", {"purchases": purchases})


@login_required
def profile(request):
    return render(request, "core/profile.html", {"user": request.user})


# ---------------------------
# PAYSTACK WEBHOOK
# ---------------------------

@csrf_exempt
def paystack_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    signature = request.headers.get("X-Paystack-Signature", "")
    secret = settings.PAYSTACK_SECRET_KEY.encode()
    computed = hmac.new(secret, request.body, hashlib.sha512).hexdigest()

    if not hmac.compare_digest(computed, signature):
        print("Webhook signature mismatch")
        return HttpResponse(status=400)

    try:
        event = json.loads(request.body)
    except Exception as e:
        print("Invalid webhook JSON:", e)
        return HttpResponse(status=400)

    if event.get("event") == "charge.success":
        data = event.get("data", {})
        metadata = data.get("metadata", {})
        bundle_code = metadata.get("bundle_code")
        recipient = metadata.get("recipient")
        amount = float(data.get("amount", 0)) / 100.0

        purchase = Purchase.objects.filter(bundle__code=bundle_code, recipient=recipient, amount=amount, paid=False).last()
        if purchase:
            purchase.paid = True
            purchase.transaction_id = data.get("reference")
            purchase.save()

        # Deliver via DataDash
        try:
            headers = {
                "Authorization": f"Bearer {settings.DATADASH_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "plan_id": bundle_code,
                "recipient": recipient,
                "price": amount,
            }
            r = requests.post(f"{settings.DATADASH_BASE_URL}/v1/orders", headers=headers, json=payload)
            if r.status_code not in (200, 201):
                print("DataDash delivery failed:", r.text)
        except Exception as e:
            print("Webhook DataDash error:", e)

    return HttpResponse(status=200)
