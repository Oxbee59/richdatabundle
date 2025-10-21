from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Purchase
from django.conf import settings
from decouple import config
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
import requests
import uuid
import json
import hmac
import hashlib
from bs4 import BeautifulSoup


# ------------------------------
# ENVIRONMENT VARIABLES
# ------------------------------
PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY')
DATADASH_API_KEY = config('DATADASH_API_KEY')
DATADASH_BASE_URL = config('DATADASH_BASE_URL', default="https://datadashgh.com")
PAYSTACK_BASE_URL = "https://api.paystack.co"


# ------------------------------
# SIGNUP
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
# LOGIN
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
# LOGOUT
# ------------------------------
def logout_view(request):
    logout(request)
    return redirect('login')


# ------------------------------
# DASHBOARD
# ------------------------------
@login_required
def dashboard(request):
    return render(request, 'core/dashboard.html')


# ------------------------------
# BUY BUNDLE
# ------------------------------
@login_required
def buy_bundle(request):
    """
    Scrapes live bundle prices directly from DataDash.
    """
    network = request.GET.get('network', 'MTN')
    cat_ids = {
        "MTN": "f9a5ef5854f97ee36c6b82853ea5080c",
        "AIRTELTIGO": "b517322fd097b20c3d9ff92f39e1e3fa",
        "VODAFONE": "38cc8710df7bba96870f8f4bb1aafc77",
    }

    bundles = []
    try:
        url = f"https://datadashgh.com/agents/buy_data_subcategories?cat_id={cat_ids[network.upper()]}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table tr')[1:]  # skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    plan = cols[0].get_text(strip=True)
                    price = cols[1].get_text(strip=True).replace("GHS", "").strip()
                    bundles.append({"name": plan, "price": price})
        else:
            messages.error(request, f"Failed to fetch {network} bundles from DataDash.")
    except Exception as e:
        print(f"🚨 Error fetching bundles: {e}")
        messages.error(request, f"Unable to connect to DataDash for {network} bundles.")

    if request.method == "POST":
        bundle_name = request.POST.get("bundle_name")
        phone_number = request.POST.get("phone_number")
        amount = request.POST.get("amount")

        if not phone_number or not bundle_name or not amount:
            messages.error(request, "Please select a bundle and enter phone number.")
            return redirect(f"/buy-bundle/?network={network}")

        # Initialize Paystack
        reference = str(uuid.uuid4()).replace("-", "")[:16]
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
        data = {
            "email": request.user.email,
            "amount": int(float(amount) * 100),
            "reference": reference,
            "callback_url": request.build_absolute_uri('/paystack/callback/'),
            "metadata": {
                "phone": phone_number,
                "bundle": bundle_name,
                "network": network
            },
        }

        try:
            res = requests.post(f"{PAYSTACK_BASE_URL}/transaction/initialize", headers=headers, json=data)
            if res.status_code == 200:
                return redirect(res.json()['data']['authorization_url'])
            else:
                messages.error(request, "Payment initialization failed. Please try again.")
        except Exception as e:
            print(f"🚨 Paystack init error: {e}")
            messages.error(request, "Error connecting to Paystack. Please try again.")

    return render(request, "core/buy_bundle.html", {
        "bundles": bundles,
        "network": network,
    })


# ------------------------------
# PAYSTACK CALLBACK
# ------------------------------
@login_required
def paystack_callback(request):
    reference = request.GET.get('reference')
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}

    try:
        res = requests.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}", headers=headers)
        if res.status_code == 200:
            result = res.json()
            if result['data']['status'] == 'success':
                messages.success(request, "Payment successful! Your data bundle will be processed shortly.")
                return redirect('my_purchases')
            else:
                messages.error(request, "Payment verification failed.")
        else:
            messages.error(request, "Unable to verify payment at this time.")
    except Exception as e:
        print(f"🚨 Paystack verify error: {e}")
        messages.error(request, "An error occurred verifying your payment.")

    return redirect('buy_bundle')


# ------------------------------
# MY PURCHASES
# ------------------------------
@login_required
def my_purchases(request):
    purchases = Purchase.objects.filter(user=request.user).order_by('-id')
    return render(request, 'core/my_purchases.html', {'purchases': purchases})


# ------------------------------
# PROFILE
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
    Handles Paystack webhook after successful payment and triggers DataDash top-up.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

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
        network = metadata.get('network')

        headers = {"Authorization": f"Token {DATADASH_API_KEY}"}
        payload = {
            "mobile_number": phone,
            "plan": bundle_type,
            "amount": amount,
            "network": network,
        }

        try:
            datadash_response = requests.post(
                f"{DATADASH_BASE_URL}/api/vend-data/",
                json=payload,
                headers=headers,
                timeout=15
            )
            if datadash_response.status_code == 200:
                print(f"✅ Bundle delivered successfully to {phone}")
            else:
                print(f"⚠️ DataDash API failed: {datadash_response.text}")
        except Exception as e:
            print(f"🚨 DataDash Error: {e}")

    return JsonResponse({"status": "success"}, status=200)
