# core/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from decimal import Decimal
import requests
import json
from django.utils.timezone import now
from .forms import SignupForm, BuyForm
from .models import Bundle, Purchase, AgentRegistration
from django.contrib.auth.models import User
from django.db.models import Sum
from typing import Optional
from .models import Bundle, ApiKey
from .models import AgentRegistration, AgentSettings



# -------------------------
# Authentication & Signup
# -------------------------
def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password1"])
            user.save()
            # set profile flags (profile signal creates profile on user creation)
            profile = user.profile
            profile.phone = form.cleaned_data.get("phone", "")
            profile.is_agent = form.cleaned_data.get("is_agent", False)
            profile.save()

            # If user requested agent registration, start agent registration payment
            if profile.is_agent:
                # create AgentRegistration record and redirect to payment start view
                amount = Decimal(getattr(settings, "AGENT_REG_FEE", "0.00"))
                reg = AgentRegistration.objects.create(user=user, amount=amount, paid=False)
                return redirect("agent_register", reg_id=reg.id)

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
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, "core/login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# -------------------------
# Agent registration helpers
# -------------------------
@login_required
def agent_register_start(request):
    """
    Called when a user clicks "Become an Agent".
    Creates an AgentRegistration record (if none pending) and redirects to agent_register view.
    """
    user = request.user
    # if there's an unpaid registration already, reuse it
    existing = user.agentregistration_set.filter(paid=False).first()
    if existing:
        return redirect("agent_register", reg_id=existing.id)

    amount = Decimal(getattr(settings, "AGENT_REG_FEE", "0.00"))
    reg = AgentRegistration.objects.create(user=user, amount=amount, paid=False)
    return redirect("agent_register", reg_id=reg.id)

@login_required
def agent_register(request, reg_id=None):
    """
    Handle agent registration and Paystack checkout.
    If reg_id is provided, continue payment for existing registration.
    Otherwise, create a new registration using the admin-set fee.
    """
    user = request.user

    # Get the registration fee from admin-controlled AgentSettings
    try:
        settings_obj = AgentSettings.objects.first()
        registration_fee = settings_obj.registration_fee if settings_obj else Decimal("0.00")
    except Exception:
        registration_fee = Decimal("0.00")

    # If user POSTs registration form, create a new AgentRegistration record
    if request.method == "POST":
        # Prevent duplicate unpaid registrations
        existing_reg = AgentRegistration.objects.filter(user=user, paid=False).first()
        if existing_reg:
            reg = existing_reg
        else:
            reg = AgentRegistration.objects.create(
                user=user,
                amount=registration_fee,
                paid=False
            )

        return redirect("agent_register", reg_id=reg.id)

    # If reg_id is provided, fetch existing unpaid registration
    reg = None
    if reg_id:
        try:
            reg = AgentRegistration.objects.get(id=reg_id, user=user, paid=False)
        except AgentRegistration.DoesNotExist:
            messages.error(request, "Agent registration not found or already completed.")
            return redirect("dashboard")

        # Initialize Paystack payment
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": user.email or f"{user.username}@example.com",
            "amount": int(reg.amount * 100),
            "reference": f"agent-{reg.id}",
            "callback_url": request.build_absolute_uri("/paystack-webhook/"),
            "metadata": {"purpose": "agent_registration", "user_id": user.id},
        }

        try:
            r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data, timeout=15)
            res = r.json()
            if res.get("status"):
                reg.paystack_reference = res["data"].get("reference")
                reg.save()
                return redirect(res["data"]["authorization_url"])
            else:
                messages.error(request, f"Payment initialization failed: {res.get('message')}")
        except Exception as e:
            messages.error(request, f"Error initializing payment: {e}")

        return redirect("dashboard")

    # No POST and no reg_id: show registration page with current fee
    context = {
        "registration_fee": registration_fee,
        "registration": reg
    }
    return render(request, "core/agent_register.html", context)


@login_required
def agent_wallet_topup(request):
    """
    Initialize a wallet top-up for an agent. This only starts the Paystack flow.
    Webhook must credit the profile.wallet_balance (if the field exists).
    """
    if request.method != "POST":
        return redirect("agent_dashboard")

    amount_raw = request.POST.get("amount")
    try:
        amount = Decimal(amount_raw)
        if amount <= 0:
            raise ValueError("Invalid amount")
    except Exception:
        messages.error(request, "Please provide a valid top-up amount.")
        return redirect("agent_dashboard")

    user = request.user
    # create a reference using wallet-<user_id>-<timestamp>
    import time
    ref = f"wallet-{user.id}-{int(time.time())}"

    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    data = {
        "email": user.email or f"{user.username}@example.com",
        "amount": int(amount * 100),
        "reference": ref,
        "callback_url": request.build_absolute_uri("/paystack-webhook/"),
        "metadata": {"purpose": "wallet_topup", "user_id": user.id},
    }

    try:
        r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data, timeout=15)
        res = r.json()
        if res.get("status"):
            return redirect(res["data"]["authorization_url"])
        else:
            messages.error(request, f"Top-up initialization failed: {res.get('message')}")
    except Exception as e:
        messages.error(request, f"Error initializing top-up: {e}")

    return redirect("agent_dashboard")


# -------------------------
# Dashboard
# -------------------------
@login_required
def dashboard(request):
    user = request.user
    context = {}

    # bundles for quick-sell widget
    context["bundles"] = Bundle.objects.all().order_by("price")[:12]

    # dashboard metadata counts
    context["bundles_count"] = Bundle.objects.count()
    context["purchase_count"] = Purchase.objects.filter(user=user).count()
    # recent purchases (for showing on dashboard)
    context["recent_purchases"] = Purchase.objects.filter(user=user).order_by("-created_at")[:6]

    try:
        profile = user.profile
    except Exception:
        profile = None

    # pending agent registration (template-safe)
    pending_registration: Optional[AgentRegistration] = None
    if hasattr(user, "agentregistration_set"):
        pending_registration = user.agentregistration_set.filter(paid=False).first()
    context["pending_registration"] = pending_registration

    # agent dashboard data (only if active agent)
    if profile and profile.is_agent and profile.is_agent_active:
        total_sales = Purchase.objects.filter(user=user, paid=True).count()
        recent_sales = Purchase.objects.filter(user=user).order_by("-created_at")[:8]
        total_volume = Purchase.objects.filter(user=user, paid=True).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        # wallet balance (best-effort: show 0.00 if profile has no field)
        wallet_balance = getattr(profile, "wallet_balance", Decimal("0.00"))

        context.update({
            "is_agent": True,
            "total_sales": total_sales,
            "recent_sales": recent_sales,
            "total_volume": total_volume,
            "wallet_balance": wallet_balance,
        })
    else:
        context["is_agent"] = False
        # present a preview wallet_balance so template can display something
        context["wallet_balance"] = getattr(profile, "wallet_balance", Decimal("0.00")) if profile else Decimal("0.00")

    # convenience counts for templates
    context["purchase_count"] = Purchase.objects.filter(user=user).count()
    context["bundles_count"] = Bundle.objects.count()

    return render(request, "core/dashboard.html", context)

# -------------------------
# Agent Dashboard & Agent-Specific Views
# -------------------------
@login_required
def agent_dashboard(request):
    """
    Shows agent-specific metrics: wallet balance, commission, total sales, total volume,
    recent transactions, and bundles for quick sell.
    """
    user = request.user
    profile = getattr(user, "profile", None)

    if not profile or not profile.is_agent or not profile.is_agent_active:
        # Redirect non-agents or inactive agents back to main dashboard
        return redirect("dashboard")

    # Wallet balance (assumes you have a field or calculation method in profile)
    wallet_balance = getattr(profile, "wallet_balance", 0)  # default to 0 if not yet implemented

    # Commission earned (example: 5% of paid purchases)
    paid_purchases = Purchase.objects.filter(user=user, paid=True)
    commission_earned = sum(p.amount * Decimal("0.05") for p in paid_purchases)  # 5% commission

    # Total sales (number of purchases)
    total_sales = paid_purchases.count()

    # Total sales volume
    total_volume = paid_purchases.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    # Recent sales (latest 8)
    recent_sales = Purchase.objects.filter(user=user).order_by("-created_at")[:8]

    # Bundles for Quick Sell form
    bundles = Bundle.objects.all().order_by("price")

    context = {
        "wallet_balance": wallet_balance,
        "commission_earned": commission_earned,
        "total_sales": total_sales,
        "total_volume": total_volume,
        "recent_sales": recent_sales,
        "bundles": bundles,
    }

    return render(request, "core/agent_dashboard.html", context)


@login_required
def load_wallet(request):
    """
    Example view to let agent top up wallet. You can integrate Paystack or other payment provider.
    """
    user = request.user
    profile = getattr(user, "profile", None)

    if not profile or not profile.is_agent or not profile.is_agent_active:
        return redirect("dashboard")

    if request.method == "POST":
        amount = request.POST.get("amount")
        if amount:
            # Integrate payment logic here, e.g., initialize Paystack transaction
            messages.success(request, f"Wallet top-up of ₵{amount} initialized successfully!")
            return redirect("agent_dashboard")

    return render(request, "core/load_wallet.html")


# -------------------------
# Buy Bundle (sales) - works for customer or agent acting as seller
# -------------------------
@login_required
def buy_bundle(request):
    bundles = Bundle.objects.all().order_by("price")

    if request.method == "POST":
        recipient = request.POST.get("recipient")
        bundle_id = request.POST.get("bundle_id")

        if not recipient or not bundle_id:
            messages.error(request, "Please provide recipient number and select a bundle.")
            return redirect("buy_bundle")

        try:
            bundle = Bundle.objects.get(id=bundle_id)
        except Bundle.DoesNotExist:
            messages.error(request, "Invalid bundle selected.")
            return redirect("buy_bundle")

        user = request.user
        amount = bundle.price

        # Create purchase record (actor is the user — agent or customer)
        purchase = Purchase.objects.create(
            user=user, recipient=recipient, bundle=bundle, amount=amount, paid=False
        )

        # Initialize Paystack payment
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": user.email or f"{user.username}@example.com",
            "amount": int(amount * 100),
            "reference": str(purchase.id),  # pure numeric reference for purchases
            "callback_url": request.build_absolute_uri("/paystack-webhook/"),
            "metadata": {"custom_fields": [{"display_name": "Recipient", "variable_name": "recipient", "value": recipient}]}
        }

        try:
            r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data, timeout=15)
            res = r.json()
            if res.get("status"):
                auth_url = res["data"]["authorization_url"]
                return redirect(auth_url)
            else:
                messages.error(request, f"Payment initialization failed: {res.get('message')}")
        except Exception as e:
            messages.error(request, f"Error initializing payment: {e}")

        return redirect("buy_bundle")

    return render(request, "core/buy_bundle.html", {"bundles": bundles})


# -------------------------
# My Purchases
# -------------------------
@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "core/my_purchases.html", {"purchases": purchases})


# -------------------------
# Paystack Webhook (handles purchase payments AND agent registrations AND wallet topups)
# Accepts both /paystack-webhook/ and /paystack/webhook/ paths (we add both in urls)
# -------------------------
@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference")
        # Try to be defensive: reference may be None or unexpected format
        try:
            if reference and str(reference).startswith("agent-"):
                # agent registration flow
                reg_id = int(str(reference).split("agent-")[1])
                try:
                    reg = AgentRegistration.objects.get(id=reg_id, paid=False)
                    reg.paid = True
                    reg.paid_at = now()
                    reg.paystack_reference = data.get("reference")
                    reg.save()

                    # activate the user's profile as an agent
                    profile = reg.user.profile
                    profile.is_agent_active = True
                    profile.save()
                except AgentRegistration.DoesNotExist:
                    pass

            elif reference and str(reference).startswith("wallet-"):
                # wallet top-up flow. reference format: wallet-<user_id>-<ts>
                try:
                    parts = str(reference).split("-")
                    # parts[1] is user id in our prefix
                    uid = int(parts[1])
                    amt = data.get("amount")  # in kobo
                    credited = (Decimal(amt) / Decimal(100)) if amt is not None else None
                    user = User.objects.filter(id=uid).first()
                    if user:
                        profile = getattr(user, "profile", None)
                        # only credit if profile has a writable wallet_balance attribute
                        if profile and hasattr(profile, "wallet_balance"):
                            # read existing safely
                            try:
                                current = Decimal(getattr(profile, "wallet_balance", "0.00"))
                            except Exception:
                                current = Decimal("0.00")
                            try:
                                profile.wallet_balance = current + (credited or Decimal("0.00"))
                                profile.save()
                            except Exception:
                                # if saving fails, do nothing (admin will reconcile)
                                pass
                except Exception:
                    pass

            else:
                # treat as Purchase id (numeric)
                try:
                    purchase_id = int(reference)
                except Exception:
                    purchase_id = None

                if purchase_id:
                    try:
                        purchase = Purchase.objects.get(id=purchase_id, paid=False)
                        purchase.paid = True
                        purchase.paid_at = now()
                        purchase.api_transaction_id = data.get("transaction_id") or data.get("id") or ""
                        purchase.save()

                        # Deliver bundle via DataDash (best effort)
                        headers = {
                            "Authorization": f"Bearer {settings.DATADASH_API_KEY}",
                            "Content-Type": "application/json",
                        }
                        payload = {
                            "plan_id": purchase.bundle.code,
                            "recipient": purchase.recipient,
                            "price": float(purchase.amount),
                        }
                        try:
                            requests.post(f"{settings.DATADASH_BASE_URL}/v1/orders", headers=headers, json=payload, timeout=10)
                        except Exception:
                            pass

                    except Purchase.DoesNotExist:
                        pass

        except Exception:
            # swallow to avoid webhook failing — log in real app
            pass

    return HttpResponse(status=200)


# -------------------------
# Simple API (API key protected)
# - GET /api/bundles/          -> returns bundles JSON (public)
# - POST /api/sell/            -> create sale (requires X-API-KEY)
# - GET  /api/agent/<id>/tx/   -> agent transactions (requires X-API-KEY)
# -------------------------
def _check_api_key(request):
    """Return True if valid api key provided in header X-API-KEY or ?api_key=."""
    api_key_env = getattr(settings, "API_KEY", "") or ""
    if not api_key_env:
        return False
    header = request.headers.get("X-API-KEY") or request.GET.get("api_key")
    if not header:
        return False
    # support multiple keys separated by comma
    keys = [k.strip() for k in api_key_env.split(",") if k.strip()]
    return header in keys


@require_http_methods(["GET"])
def api_bundles(request):
    bundles = Bundle.objects.all().order_by("price")
    data = []
    for b in bundles:
        data.append({
            "id": b.id,
            "name": b.name,
            "code": b.code,
            "price": str(b.price),
            "network": b.network,
            "description": b.description or "",
            "logo": b.logo or "",
            "color": b.color or "",
        })
    return JsonResponse({"status": "ok", "data": data})


@csrf_exempt
@require_http_methods(["POST"])
def api_sell(request):
    if not _check_api_key(request):
        return JsonResponse({"status": "error", "message": "Invalid or missing API key"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    bundle_id = payload.get("bundle_id")
    recipient = payload.get("recipient")
    agent_username = payload.get("agent_username")  # optional: which agent is making the sale

    if not bundle_id or not recipient:
        return JsonResponse({"status": "error", "message": "bundle_id and recipient required"}, status=400)

    try:
        bundle = Bundle.objects.get(id=bundle_id)
    except Bundle.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Invalid bundle_id"}, status=404)

    # determine user (agent) performing the sale
    user = None
    if agent_username:
        try:
            user = User.objects.get(username=agent_username)
        except User.DoesNotExist:
            user = None

    # fallback to API key owner if you store mapping — for now use anonymous system user if none
    if user is None:
        # pick a generic system user if exists
        try:
            user = User.objects.filter(is_superuser=True).first()
        except Exception:
            user = None

    purchase = Purchase.objects.create(
        user=user or User.objects.first(),
        recipient=recipient,
        bundle=bundle,
        amount=bundle.price,
        paid=False
    )

    # initialize paystack and return authorization_url for client to complete payment
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    data = {
        "email": (user.email if user and user.email else f"{user.username if user else 'anon'}@example.com"),
        "amount": int(bundle.price * 100),
        "reference": str(purchase.id),
        "callback_url": request.build_absolute_uri("/paystack-webhook/"),
        "metadata": {"custom_fields": [{"display_name": "Recipient", "variable_name": "recipient", "value": recipient}]}
    }
    try:
        r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data, timeout=15)
        res = r.json()
        if res.get("status"):
            return JsonResponse({"status": "ok", "authorization_url": res["data"]["authorization_url"], "purchase_id": purchase.id})
        else:
            return JsonResponse({"status": "error", "message": res.get("message")}, status=500)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_http_methods(["GET"])
def api_agent_transactions(request, user_id):
    if not _check_api_key(request):
        return JsonResponse({"status": "error", "message": "Invalid or missing API key"}, status=401)

    try:
        u = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"status": "error", "message": "User not found"}, status=404)

    txs = Purchase.objects.filter(user=u).order_by("-created_at")[:200]
    data = []
    for t in txs:
        data.append({
            "id": t.id,
            "bundle": t.bundle.name,
            "amount": str(t.amount),
            "recipient": t.recipient,
            "paid": t.paid,
            "created_at": t.created_at.isoformat(),
            "paid_at": t.paid_at.isoformat() if t.paid_at else None,
        })
    return JsonResponse({"status": "ok", "user": u.username, "data": data})


# -------------------------
# Simple UI helpers
# -------------------------
def payment_success(request):
    return render(request, "payment_success.html")


def profile(request):
    return render(request, "core/profile.html")


@login_required
def api_docs(request):
    return render(request, "core/api_docs.html")


@login_required
def agent_dashboard(request):
    """
    Shows agent-specific metrics: total sales, total volume, recent transactions
    """
    user = request.user
    profile = getattr(user, 'profile', None)
    if not profile or not profile.is_agent or not profile.is_agent_active:
        # non-agent users redirected to main dashboard (they can preview)
        return redirect('dashboard')

    total_sales = Purchase.objects.filter(user=user, paid=True).count()
    total_volume = Purchase.objects.filter(user=user, paid=True).aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
    recent_sales = Purchase.objects.filter(user=user).order_by('-created_at')[:12]

    # wallet & commission (best-effort: rely on profile fields if they exist)
    wallet = getattr(profile, "wallet_balance", Decimal("0.00"))
    commission = getattr(profile, "commission_balance", Decimal("0.00"))

    context = {
        'total_sales': total_sales,
        'total_volume': total_volume,
        'recent_sales': recent_sales,
        'wallet': wallet,
        'commission': commission,
        'bundles': Bundle.objects.all().order_by("price")[:20],
    }
    return render(request, 'core/agent_dashboard.html', context)

@login_required
def api_docs(request):
    # Show all bundles dynamically
    bundles = Bundle.objects.all().order_by("price")

    # Get the first API key for the user (if any)
    api_key = ApiKey.objects.filter(user=request.user, active=True).first()

    context = {
        "bundles": bundles,
        "api_key": api_key,
    }
    return render(request, "core/api_docs.html", context)