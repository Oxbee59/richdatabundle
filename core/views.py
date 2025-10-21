from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Bundle, Purchase
from django.conf import settings
from decouple import config
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
import requests
import uuid
import json
import hmac
import hashlib

# Load API Keys
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY')
DATADASH_BASE_URL = config('DATADASH_BASE_URL')
DATADASH_API_KEY = config('DATADASH_API_KEY')

# ------------------------------
# SIGNUP VIEW
# ------------------------------
def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('signup')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return redirect('signup')

        try:
            user = User.objects.create_user(username=username, email=email, password=password)
            user.save()
            messages.success(request, "Account created successfully! You can now log in.")
            return redirect('login')
        except Exception as e:
            print(f"🚨 SIGNUP ERROR: {e}")
            messages.error(request, "Something went wrong. Please try again.")
            return redirect('signup')

    return render(request, 'core/signup.html')


# ------------------------------
# LOGIN VIEW
# ------------------------------
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password")
    return render(request, 'core/login.html')


# ------------------------------
# LOGOUT VIEW
# ------------------------------
def logout_view(request):
    logout(request)
    return redirect('login')


# ------------------------------
# DASHBOARD VIEW
# ------------------------------
@login_required
def dashboard(request):
    return render(request, 'core/dashboard.html')


# ------------------------------
# BUY BUNDLE VIEW
# ------------------------------
@login_required
def buy_bundle(request):
    """
    Fetch bundles live from Datadash and handle purchases
    """
    headers = {"Authorization": f"Token {DATADASH_API_KEY}"}
    bundles = []

    try:
        res = requests.get(f"{DATADASH_BASE_URL}/data-plans/", headers=headers, timeout=10)
        if res.status_code == 200:
            bundles = res.json()
        else:
            messages.error(request, "Failed to fetch bundles from Datadash.")
    except Exception as e:
        print(f"🚨 Error fetching bundles: {e}")
        messages.error(request, "Unable to connect to Datadash API.")

    if request.method == "POST":
        bundle_code = request.POST.get("bundle_code")
        phone_number = request.POST.get("phone_number")

        if not bundle_code:
            messages.error(request, "Please select a bundle.")
            return redirect("buy_bundle")

        if not phone_number:
            messages.error(request, "Please enter recipient phone number.")
            return redirect("buy_bundle")

        # Find the selected bundle from Datadash
        selected_bundle = next((b for b in bundles if str(b["plan"]) == str(bundle_code)), None)
        if not selected_bundle:
            messages.error(request, "Invalid bundle selected.")
            return redirect("buy_bundle")

        reference = str(uuid.uuid4()).replace("-", "")[:16]

        # Initialize Paystack payment
        paystack_key = PAYSTACK_SECRET_KEY
        headers = {"Authorization": f"Bearer {paystack_key}"}
        data = {
            "email": request.user.email,
            "amount": int(float(selected_bundle["price"]) * 100),
            "reference": reference,
            "callback_url": request.build_absolute_uri('/paystack/callback/'),
            "metadata": {
                "phone": phone_number,
                "bundle": bundle_code,
            },
        }

        res = requests.post('https://api.paystack.co/transaction/initialize', headers=headers, json=data)
        if res.status_code == 200:
            return redirect(res.json()['data']['authorization_url'])
        else:
            print(res.text)
            messages.error(request, "Payment initialization failed.")
            return redirect('buy_bundle')

    return render(request, "core/buy_bundle.html", {"bundles": bundles})


# ------------------------------
# PAYSTACK CALLBACK VIEW
# ------------------------------
@login_required
def paystack_callback(request):
    reference = request.GET.get('reference')
    paystack_key = PAYSTACK_SECRET_KEY
    headers = {"Authorization": f"Bearer {paystack_key}"}
    res = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)

    if res.status_code == 200:
        result = res.json()
        if result['data']['status'] == 'success':
            messages.success(request, "Payment successful! Your data bundle will be processed shortly.")
            return redirect('my_purchases')
        else:
            messages.error(request, "Payment verification failed.")
    else:
        messages.error(request, "Unable to verify payment.")

    return redirect('buy_bundle')


# ------------------------------
# MY PURCHASES VIEW
# ------------------------------
@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by('-id')
    return render(request, 'core/my_purchases.html', {'purchases': purchases})


# ------------------------------
# PROFILE VIEW
# ------------------------------
@login_required
def profile(request):
    return render(request, 'core/profile.html', {
        'user': request.user,
        'profile': getattr(request.user, 'profile', None),
    })


# ------------------------------
# PAYSTACK WEBHOOK
# ------------------------------
@csrf_exempt
def paystack_webhook(request):
    """
    Handles Paystack Webhook events (especially successful payments)
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    paystack_signature = request.headers.get('x-paystack-signature')

    computed_signature = hmac.new(
        key=PAYSTACK_SECRET_KEY.encode('utf-8'),
        msg=request.body,
        digestmod=hashlib.sha512
    ).hexdigest()

    if paystack_signature != computed_signature:
        return HttpResponseForbidden("Invalid signature")

    event_data = json.loads(request.body.decode('utf-8'))
    event_type = event_data.get('event')
    print("🔔 Paystack Webhook Received:", event_type)

    if event_type == "charge.success":
        data = event_data.get('data', {})
        reference = data.get('reference')
        amount = int(data.get('amount', 0)) / 100
        metadata = data.get('metadata', {})
        phone = metadata.get('phone')
        bundle_type = metadata.get('bundle')

        headers = {"Authorization": f"Token {DATADASH_API_KEY}"}
        payload = {
            "mobile_number": phone,
            "plan": bundle_type,
            "amount": amount,
        }

        try:
            datadash_response = requests.post(
                f"{DATADASH_BASE_URL}/vend-data/",
                json=payload,
                headers=headers,
                timeout=10
            )
            if datadash_response.status_code == 200:
                print(f"✅ Bundle delivered to {phone}")
            else:
                print(f"⚠️ Datadash API failed: {datadash_response.text}")
        except Exception as e:
            print(f"🚨 Datadash error: {e}")

    return JsonResponse({"status": "success"}, status=200)
