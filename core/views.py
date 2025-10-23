from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
import requests
from .models import Bundle, Purchase
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt

@login_required
def buy_bundle(request):
    bundles = Bundle.objects.all().order_by("price")

    # --- if no bundles exist, preload 3 defaults for display ---
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
            messages.error(request, "Please provide a valid recipient and select a bundle.")
            return redirect("buy_bundle")

        try:
            bundle = Bundle.objects.get(id=bundle_id)
        except Bundle.DoesNotExist:
            messages.error(request, "Invalid bundle selected.")
            return redirect("buy_bundle")

        amount = bundle.price
        user = request.user

        # Create a purchase record (unpaid for now)
        purchase = Purchase.objects.create(
            user=user, recipient=recipient, bundle=bundle, amount=amount, status="pending"
        )

        # Redirect to Paystack payment page
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
        data = {
            "email": user.email,
            "amount": int(amount * 100),  # in kobo
            "reference": str(purchase.id),
            "callback_url": request.build_absolute_uri("/webhook/"),
        }

        r = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data)
        res = r.json()

        if res.get("status"):
            return redirect(res["data"]["authorization_url"])
        else:
            messages.error(request, "Payment initialization failed. Try again.")
            return redirect("buy_bundle")

    return render(request, "core/buy_bundle.html", {"bundles": bundles})


@csrf_exempt
def webhook(request):
    """Paystack webhook to verify payment and deliver data via DataDash"""
    import json
    from django.utils.timezone import now

    payload = json.loads(request.body.decode("utf-8"))
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference")
        amount = Decimal(data.get("amount", 0)) / 100

        try:
            purchase = Purchase.objects.get(id=reference, status="pending")
            purchase.status = "paid"
            purchase.paid_at = now()
            purchase.save()

            # --- Deliver via DataDash ---
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
