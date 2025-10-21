import os
import requests
from bs4 import BeautifulSoup
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment configs
DATADASH_BASE_URL = os.getenv("DATADASH_BASE_URL", "https://datadashgh.com/api")
DATADASH_API_KEY = os.getenv("DATADASH_API_KEY")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")

# Network category IDs from Datadash
NETWORKS = {
    "MTN": "f9a5ef5854f97ee36c6b82853ea5080c",
    "VODAFONE": "b9b30e8df23c3e163dfcfd99efca9d79",
    "AIRTELTIGO": "f79d28de77c8c41b198e682b07f9a9a1",
}


# -------------------------------
# DASHBOARD VIEW
# -------------------------------
@login_required
def dashboard(request):
    """
    Display all available bundles from all networks in one place.
    """
    all_bundles = []

    try:
        for network, cat_id in NETWORKS.items():
            url = f"{DATADASH_BASE_URL}/agents/buy_data_subcategories?cat_id={cat_id}"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                bundle_cards = soup.find_all("div", class_="bundle-card")

                for card in bundle_cards:
                    name = card.find("h6").get_text(strip=True) if card.find("h6") else "Unnamed Plan"
                    price = card.find("span", class_="price").get_text(strip=True) if card.find("span", class_="price") else ""
                    all_bundles.append({
                        "network": network,
                        "size_label": name,
                        "price": price,
                        "bundle_code": cat_id,
                    })
    except Exception as e:
        print("Error fetching bundles for dashboard:", e)

    return render(request, "core/dashboard.html", {"bundles": all_bundles})


# -------------------------------
# BUY BUNDLE VIEW
# -------------------------------
@login_required
def buy_bundle(request):
    """
    Handles bundle purchase UI and process.
    """
    selected_network = request.GET.get("network")
    bundles = []
    recipient = ""
    amount = ""

    if selected_network in NETWORKS:
        cat_id = NETWORKS[selected_network]
        url = f"{DATADASH_BASE_URL}/agents/buy_data_subcategories?cat_id={cat_id}"

        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                bundle_cards = soup.find_all("div", class_="bundle-card")

                for card in bundle_cards:
                    name = card.find("h6").get_text(strip=True) if card.find("h6") else "Unnamed Plan"
                    price = card.find("span", class_="price").get_text(strip=True) if card.find("span", class_="price") else ""
                    bundles.append({"name": name, "price": price})

        except Exception as e:
            print("Error fetching bundles:", e)

    if request.method == "POST":
        recipient = request.POST.get("recipient")
        amount = request.POST.get("amount")
        selected_network = request.POST.get("network")

        # TODO: Add Paystack integration here later
        messages.success(request, f"Bundle purchase request for {recipient} on {selected_network} processed.")
        return redirect("buy_bundle")

    context = {
        "bundles": bundles,
        "networks": NETWORKS.keys(),
        "selected_network": selected_network,
        "paystack_public_key": PAYSTACK_PUBLIC_KEY,
    }
    return render(request, "core/buy_bundle.html", context)
