# core/utils.py
import requests
from django.conf import settings
from .models import Bundle
from decimal import Decimal

def sync_datadash_plans():
    """
    Fetch /v1/plans from DataDash and sync with local Bundle model.
    Returns True on success, False otherwise.
    """
    base_url = getattr(settings, "DATADASH_BASE_URL", "https://datadashgh.com/agents/api")
    url = f"{base_url}/v1/plans"
    headers = {"Authorization": f"Bearer {getattr(settings, 'DATADASH_API_KEY', '')}"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            # API may return object {success: True, data: [...]}
            try:
                payload = r.json()
            except Exception:
                return False

            # If a non-200 but contains data, fall through
            data = payload.get("data") if isinstance(payload, dict) else None
        else:
            payload = r.json()
            # Many APIs return { success: True, data: [...] } or just a list
            if isinstance(payload, dict) and "data" in payload:
                data = payload["data"]
            elif isinstance(payload, list):
                data = payload
            else:
                # Unexpected format
                return False

        if not data:
            return False

        for p in data:
            # Support several possible key names
            plan_id = p.get("plan_id") or p.get("id") or p.get("code")
            name = p.get("size") or p.get("name") or p.get("title") or f"Plan {plan_id}"
            # price may be float or string or min_price
            price = p.get("price") or p.get("min_price") or p.get("amount") or 0
            try:
                price = Decimal(str(price))
            except Exception:
                price = Decimal("0.00")

            # create a sensible code to store remote plan_id
            if not plan_id:
                continue

            # Upsert
            Bundle.objects.update_or_create(
                code=str(plan_id),
                defaults={
                    "name": str(name),
                    "price": price,
                    "description": p.get("description", "") or "",
                },
            )
        return True
    except Exception as e:
        print("sync_datadash_plans error:", e)
        return False
