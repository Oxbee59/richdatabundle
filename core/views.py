from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .models import Bundle, Purchase
from django.conf import settings
from decouple import config
import requests
import uuid


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
            messages.error(request, "Passwords do not match")
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken")
            return redirect('signup')

        user = User.objects.create_user(username=username, email=email, password=password)
        user.save()
        messages.success(request, "Account created successfully! You can now log in.")
        return redirect('login')

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
    bundles = Bundle.objects.filter(is_active=True)

    if request.method == "POST":
        bundle_code = request.POST.get("bundle_code")
        try:
            bundle = Bundle.objects.get(bundle_code=bundle_code, is_active=True)
        except Bundle.DoesNotExist:
            messages.error(request, "Invalid bundle selected.")
            return redirect("buy_bundle")

        # Generate unique reference for Paystack
        reference = str(uuid.uuid4()).replace("-", "")[:16]

        # Create a pending Purchase record
        purchase = Purchase.objects.create(
            user=request.user,
            bundle=bundle,
            amount=bundle.price,
            api_transaction_id=reference,
            paid=False,
        )

        # Initialize Paystack payment
        paystack_key = config('PAYSTACK_SECRET_KEY')
        headers = {"Authorization": f"Bearer {paystack_key}"}
        data = {
            "email": request.user.email,
            "amount": int(bundle.price * 100),  # convert to kobo
            "reference": reference,
            "callback_url": request.build_absolute_uri('/paystack/callback/'),
        }
        res = requests.post('https://api.paystack.co/transaction/initialize', headers=headers, data=data)

        if res.status_code == 200:
            result = res.json()
            return redirect(result['data']['authorization_url'])
        else:
            messages.error(request, "Error initializing payment. Please try again.")
            return redirect('buy_bundle')

    # GET request
    return render(request, "core/buy_bundle.html", {"bundles": bundles})

# ------------------------------
# PAYSTACK CALLBACK VIEW
# ------------------------------
@login_required
def paystack_callback(request):
    reference = request.GET.get('reference')
    paystack_key = config('PAYSTACK_SECRET_KEY')
    headers = {"Authorization": f"Bearer {paystack_key}"}
    res = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)

    if res.status_code == 200:
        result = res.json()
        if result['data']['status'] == 'success':
            purchase = get_object_or_404(Purchase, api_transaction_id=reference)
            purchase.paid = True
            purchase.save()
            messages.success(request, "Payment successful! Your data bundle will be processed.")
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
    """
    Displays user profile info, e.g. name, email, phone, agent status.
    """
    return render(request, 'core/profile.html', {
        'user': request.user,
        'profile': getattr(request.user, 'profile', None),
    })
