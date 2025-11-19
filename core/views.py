from decimal import Decimal
import uuid
from typing import Optional
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect
from django.db.models import Sum
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

from .models import (
    Bundle,
    Profile,
    Purchase,
    AgentRegistration,
    AgentSettings,
    ApiKey,
    ApiAccessLog,
)

# =====================================================================
# DASHBOARD (NON-AGENTS)
# =====================================================================
@login_required
def dashboard(request):
    user = request.user
    profile = getattr(user, "profile", None)

    if profile and profile.is_agent and profile.is_agent_active:
        return redirect("agent_dashboard")

    context = {
        "bundles": Bundle.objects.all().order_by("price")[:12],
        "bundles_count": Bundle.objects.count(),
        "purchase_count": Purchase.objects.filter(user=user).count(),
        "recent_purchases": Purchase.objects.filter(user=user).order_by("-created_at")[:6],
        "wallet_balance": getattr(profile, "wallet_balance", 0) if profile else 0,
        "is_agent": False,
    }

    pending_registration = None
    if hasattr(user, "agentregistration_set"):
        pending_registration = user.agentregistration_set.filter(paid=False).first()
    context["pending_registration"] = pending_registration

    return render(request, "core/dashboard.html", context)

# =====================================================================
# AGENT DASHBOARD
# =====================================================================
@login_required
def agent_dashboard(request):
    user = request.user
    profile = getattr(user, "profile", None)

    if not profile or not profile.is_agent or not profile.is_agent_active:
        return redirect("dashboard")

    # Ensure agent has an API key
    api_key, created = ApiKey.objects.get_or_create(user=user)
    if created:
        api_key.key = uuid.uuid4().hex
        api_key.save()

    paid_purchases = Purchase.objects.filter(user=user, paid=True)
    commission_earned = sum(p.amount * Decimal("0.05") for p in paid_purchases)

    context = {
        "wallet_balance": getattr(profile, "wallet_balance", Decimal("0.00")),
        "commission_earned": commission_earned,
        "total_sales": paid_purchases.count(),
        "total_volume": paid_purchases.aggregate(total=Sum("amount"))["total"] or 0,
        "recent_sales": Purchase.objects.filter(user=user).order_by("-created_at")[:8],
        "bundles": Bundle.objects.all().order_by("price"),
        "is_agent": True,
        "api_key": api_key.key,
    }

    return render(request, "core/agent_dashboard.html", context)

# =====================================================================
# USER PROFILE
# =====================================================================
@login_required
def profile(request):
    profile = getattr(request.user, "profile", None)
    return render(request, "core/profile.html", {"profile": profile})

# =====================================================================
# LOGOUT
# =====================================================================
@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

# =====================================================================
# SIGNUP / LOGIN
# =====================================================================
def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        if User.objects.filter(username=username).exists():
            return render(request, "signup.html", {"error": "Username already exists"})
        User.objects.create_user(username=username, password=password)
        return HttpResponseRedirect("/login/")
    return render(request, "signup.html")

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return HttpResponseRedirect("/dashboard/")
        return render(request, "login.html", {"error": "Invalid credentials"})
    return render(request, "login.html")

# =====================================================================
# PURCHASES / BUNDLES
# =====================================================================
@login_required
def buy_bundle(request):
    if request.method == "POST":
        bundle_id = request.POST.get("bundle_id")
        recipient = request.POST.get("recipient")
        amount = request.POST.get("amount")
        try:
            bundle = Bundle.objects.get(id=bundle_id)
            Purchase.objects.create(
                user=request.user,
                bundle=bundle,
                recipient=recipient,
                amount=Decimal(amount),
                paid=False
            )
            messages.success(request, "Purchase created successfully!")
            return redirect("dashboard")
        except Bundle.DoesNotExist:
            messages.error(request, "Bundle does not exist")
            return redirect("dashboard")
    return render(request, "core/buy_bundle.html", {"bundles": Bundle.objects.all()})

@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "core/my_purchases.html", {"purchases": purchases})

@login_required
def payment_success(request):
    return render(request, "core/payment_success.html")

# =====================================================================
# AGENT REGISTRATION
# =====================================================================
@login_required
def agent_register_start(request):
    return render(request, "core/agent_register_start.html")

@login_required
def agent_register(request, reg_id: Optional[int] = None):
    profile = getattr(request.user, "profile", None)
    if profile and profile.is_agent:
        messages.info(request, "You are already an agent.")
        return redirect("dashboard")
    if request.method == "POST":
        AgentRegistration.objects.create(user=request.user)
        messages.success(request, "Registration created. Await payment.")
        return redirect("dashboard")
    return render(request, "core/agent_register.html")

@login_required
def agent_wallet_topup(request):
    return render(request, "core/agent_wallet_topup.html")

# =====================================================================
# API DOCS
# =====================================================================
@login_required
def api_docs(request):
    return render(request, "core/api_docs.html")

# =====================================================================
# PAYSTACK WEBHOOK
# =====================================================================
def paystack_webhook(request):
    # TODO: Add Paystack webhook handling logic here
    return JsonResponse({"status": "success"})

# =====================================================================
# SIMPLE API ENDPOINTS
# =====================================================================
def api_bundles(request):
    bundles = Bundle.objects.all().values("id", "name", "price", "network", "code")
    return JsonResponse({"status": True, "bundles": list(bundles)})

def api_sell(request):
    if request.method != "POST":
        return JsonResponse({"status": False, "error": "POST required"})
    user_id = request.POST.get("user_id")
    bundle_id = request.POST.get("bundle_id")
    recipient = request.POST.get("recipient")
    amount = request.POST.get("amount")
    try:
        user = Profile.objects.get(user__id=user_id).user
        bundle = Bundle.objects.get(id=bundle_id)
    except:
        return JsonResponse({"status": False, "error": "Invalid user or bundle"})
    purchase = Purchase.objects.create(
        user=user,
        bundle=bundle,
        recipient=recipient,
        amount=Decimal(amount),
        paid=False
    )
    return JsonResponse({"status": True, "message": "Purchase created", "tx_id": purchase.id})

def api_agent_transactions(request, user_id):
    purchases = Purchase.objects.filter(user__id=user_id, paid=True).values(
        "id", "recipient", "amount", "created_at", "bundle__name"
    )
    return JsonResponse({"status": True, "purchases": list(purchases)})
