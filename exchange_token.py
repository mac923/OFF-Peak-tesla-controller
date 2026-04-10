#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# Pobierz konfigurację
client_id = os.getenv('TESLA_CLIENT_ID')
client_secret = os.getenv('TESLA_CLIENT_SECRET')
domain = os.getenv('TESLA_DOMAIN')
auth_code = "EU_e3ef53aed41c044c51588131816e9ff6c0044c3bda34e0bc01355912c8c4"

print("🔄 Wymiana kodu na tokeny...")

# Wymień kod na token
data = {
    'grant_type': 'authorization_code',
    'client_id': client_id,
    'client_secret': client_secret,
    'code': auth_code,
    'audience': 'https://fleet-api.prd.eu.vn.cloud.tesla.com',
    'redirect_uri': f'{domain}/api/auth/callback'
}

try:
    response = requests.post(
        'https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token',
        json=data,
        timeout=30
    )
    response.raise_for_status()
    token_response = response.json()

    # Przygotuj dane tokenów
    expires_in = token_response.get('expires_in', 28800)  # domyślnie 8h
    token_data = {
        'access_token': token_response['access_token'],
        'refresh_token': token_response['refresh_token'],
        'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        'refresh_token_created_at': datetime.now(timezone.utc).isoformat()
    }

    # Zapisz lokalnie
    with open('fleet_tokens.json', 'w') as f:
        json.dump(token_data, f, indent=2)

    print("✅ Tokeny otrzymane pomyślnie")
    print(f"   Access token: {token_response['access_token'][:50]}...")
    print(f"   Refresh token: {token_response['refresh_token']}")
    print(f"   Wygasa za: {expires_in // 3600}h")
    print()
    print("✅ Zapisano lokalnie do: fleet_tokens.json")

    # Wyświetl dane do zapisania w Secret Manager
    print("\n" + "="*80)
    print("Dane tokenów gotowe do zapisania w Secret Manager")
    print("="*80)

except requests.exceptions.RequestException as e:
    print(f"❌ Błąd podczas wymiany kodu: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"   Odpowiedź: {e.response.text}")
    exit(1)
