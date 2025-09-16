#!/usr/bin/env python3
"""
Skrypt do generowania nowego tokenu Tesla Fleet API
"""

import os
import requests
from rich.console import Console
from rich.prompt import Prompt
from dotenv import load_dotenv

console = Console()
load_dotenv()

def generate_auth_url():
    """Generuje URL autoryzacji"""
    client_id = os.getenv('TESLA_CLIENT_ID')
    domain = os.getenv('TESLA_DOMAIN')
    
    # NAPRAWKA: Używaj nowego URL Tesla Fleet API zgodnie z dokumentacją
    auth_url = (
        f"https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/authorize?"
        f"client_id={client_id}&"
        f"locale=en-US&"
        f"prompt=login&"
        f"redirect_uri={domain}/api/auth/callback&"
        f"response_type=code&"
        f"scope=openid%20offline_access%20vehicle_device_data%20vehicle_cmds%20vehicle_charging_cmds%20vehicle_location%20user_data&"
        f"state=tesla_fleet_auth"
    )
    
    return auth_url

def exchange_code_for_token(auth_code):
    """Wymienia kod autoryzacji na token"""
    client_id = os.getenv('TESLA_CLIENT_ID')
    client_secret = os.getenv('TESLA_CLIENT_SECRET')
    domain = os.getenv('TESLA_DOMAIN')
    
    data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'audience': 'https://fleet-api.prd.eu.vn.cloud.tesla.com',  # NAPRAWKA: Dodano wymagany parametr audience
        'redirect_uri': f'{domain}/api/auth/callback'
    }
    
    try:
        # NAPRAWKA: Używaj nowego URL Tesla Fleet API
        response = requests.post('https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token', data=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        console.print(f"[red]Błąd wymiany kodu na token: {e}[/red]")
        if hasattr(e, 'response') and e.response is not None:
            console.print(f"[red]Status Code: {e.response.status_code}[/red]")
            console.print(f"[red]Response: {e.response.text}[/red]")
        return None

def save_token(token_data):
    """Zapisuje token do pliku i Secret Manager"""
    import json
    from datetime import datetime, timedelta, timezone
    
    # Oblicz czas wygaśnięcia
    expires_in = token_data.get('expires_in', 3600)
    expires_at = datetime.now() + timedelta(seconds=expires_in)
    
    fleet_token_data = {
        'access_token': token_data['access_token'],
        'refresh_token': token_data.get('refresh_token'),
        'expires_at': expires_at.isoformat(),
        'refresh_token_created_at': datetime.now(timezone.utc).isoformat()
    }
    
    # Zapisz lokalnie
    with open('fleet_tokens.json', 'w') as f:
        json.dump(fleet_token_data, f, indent=2)
    
    console.print(f"[green]✓ Token zapisany do fleet_tokens.json[/green]")
    
    # Zapisz w Google Cloud Secret Manager jeśli dostępne
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    if project_id:
        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            
            # Zapisz pełne dane tokenów
            secret_name = f"projects/{project_id}/secrets/fleet-tokens"
            payload = json.dumps(fleet_token_data).encode("UTF-8")
            
            client.add_secret_version(
                request={
                    "parent": secret_name,
                    "payload": {"data": payload}
                }
            )
            console.print("[green]✓ Tokeny zapisane w Google Cloud Secret Manager[/green]")
            
            # Zapisz osobno refresh token (dla kompatybilności z Worker)
            if token_data.get('refresh_token'):
                refresh_secret_name = f"projects/{project_id}/secrets/tesla-refresh-token"
                refresh_payload = token_data['refresh_token'].encode("UTF-8")
                
                client.add_secret_version(
                    request={
                        "parent": refresh_secret_name,
                        "payload": {"data": refresh_payload}
                    }
                )
                console.print("[green]✓ Refresh token zaktualizowany w Secret Manager[/green]")
                
        except Exception as e:
            console.print(f"[yellow]⚠️ Nie udało się zapisać do Secret Manager: {e}[/yellow]")
            console.print("[yellow]Worker Service może mieć problem z dostępem do tokenów[/yellow]")
    
    console.print(f"[green]✓ Token wygasa: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}[/green]")

def main():
    """Główna funkcja"""
    console.print("[bold blue]🔑 Generator tokenu Tesla Fleet API[/bold blue]")
    
    # Sprawdź konfigurację
    if not all([os.getenv('TESLA_CLIENT_ID'), os.getenv('TESLA_CLIENT_SECRET'), os.getenv('TESLA_DOMAIN')]):
        console.print("[red]Błąd: Brak konfiguracji w pliku .env[/red]")
        console.print("[yellow]Sprawdź czy masz ustawione: TESLA_CLIENT_ID, TESLA_CLIENT_SECRET, TESLA_DOMAIN[/yellow]")
        return
    
    # Generuj URL autoryzacji
    auth_url = generate_auth_url()
    
    console.print("\n[bold]Krok 1: Otwórz ten URL w przeglądarce:[/bold]")
    console.print(f"[blue]{auth_url}[/blue]")
    
    console.print("\n[bold]Krok 2:[/bold] Zaloguj się swoimi danymi Tesla")
    console.print("[bold]Krok 3:[/bold] Po przekierowaniu skopiuj kod z URL (parametr 'code=')")
    
    # Pobierz kod od użytkownika
    auth_code = Prompt.ask("\n[bold]Wklej kod autoryzacji")
    
    if not auth_code:
        console.print("[red]Nie podano kodu autoryzacji[/red]")
        return
    
    # Wymień kod na token
    console.print("[yellow]Wymieniam kod na token...[/yellow]")
    token_data = exchange_code_for_token(auth_code)
    
    if token_data:
        save_token(token_data)
        console.print("\n[green]🎉 Token wygenerowany pomyślnie![/green]")
        console.print("[green]Możesz teraz uruchomić program: python3 run.py[/green]")
    else:
        console.print("[red]Nie udało się wygenerować tokenu[/red]")

if __name__ == "__main__":
    main() 