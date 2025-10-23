# core/utils.py
import requests
from django.conf import settings

def sync_datadash_plans():
    """
    Fetch available data plans from the DataDash API.
    """
    url = "https://datadashapi.com/api/plans"
    headers = {
        "Authorization": f"Token {settings.DATADASH_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        try:
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            else:
                print(f"Unexpected DataDash response format: {data}")
                return []
        except Exception as e:
            print(f"Error parsing DataDash response: {e}")
            return []
    else:
        print(f"Failed to fetch plans: {response.status_code} - {response.text}")
        return []
