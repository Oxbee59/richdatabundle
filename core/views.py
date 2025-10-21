import requests
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

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

    return render(request, "signup.html")


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

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------------------
# DASHBOARD (Bundles)
# ---------------------------
@login_required
def dashboard(request):
    base_url = settings.DATADASH_BASE_URL
    bundles = []

    try:
        response = requests.get(f"{base_url}/bundles/")
        if response.status_code == 200:
            bundles = response.json()
    except Exception as e:
        print("Error fetching bundles:", e)

    return render(request, "dashboard.html", {"bundles": bundles})


# ---------------------------
# BUY BUNDLE
# ---------------------------
@login_required
def buy_bundle(request):
    code = request.GET.get("code")

    if request.method == "POST":
        phone = request.POST.get("phone")
        amount = request.POST.get("amount")

        # Create Paystack payment session
        paystack_url = "https://api.paystack.co/transaction/initialize"
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": request.user.email or "customer@example.com",
            "amount": int(float(amount) * 100),  # kobo
            "metadata": {"phone": phone, "bundle_code": code, "user": request.user.username},
            "callback_url": request.build_absolute_uri("/payment-success/"),
        }

        response = requests.post(paystack_url, headers=headers, json=data)
        if response.status_code == 200:
            checkout_url = response.json()["data"]["authorization_url"]
            return redirect(checkout_url)
        else:
            messages.error(request, "Error initializing payment. Try again.")
            return redirect("dashboard")

    return render(request, "buy_bundle.html", {"bundle_code": code})


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
@csrf_exempt
def paystack_webhook(request):
    try:
        event = request.body.decode("utf-8")
        print("Webhook Event:", event)
    except Exception as e:
        print("Webhook Error:", e)
    return JsonResponse({"status": "ok"})
