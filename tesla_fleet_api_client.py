#!/usr/bin/env python3
"""
Tesla Fleet API Client - Obsługa Fleet API z podpisanymi komendami
"""

import os
import json
import time
import base64
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from requests_oauthlib import OAuth2Session
from rich.console import Console

# BEZPIECZEŃSTWO: Wyłączenie ostrzeżeń SSL dla Tesla HTTP Proxy
# Tesla HTTP Proxy (localhost) używa self-signed certyfikatów SSL
# To jest bezpieczne ponieważ:
# 1. Komunikacja odbywa się lokalnie (localhost/127.0.0.1)
# 2. Tesla HTTP Proxy jest zaufanym komponentem
# 3. Self-signed certyfikaty są standardem dla lokalnych proxy
# 4. Dane są już szyfrowane przez Tesla Fleet API na wyższym poziomie
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()

class TeslaAuthenticationError(Exception):
    """Wyjątek dla błędów autoryzacji Tesla API"""
    
    def __init__(self, message: str, status_code: int = None, error_data: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_data = error_data or {}
        
    def is_token_expired(self) -> bool:
        """Sprawdza czy błąd dotyczy wygasłego tokena"""
        return self.status_code == 401
    
    def is_forbidden(self) -> bool:
        """Sprawdza czy błąd dotyczy braku uprawnień"""
        return self.status_code == 403
    
    def needs_reauthorization(self) -> bool:
        """Sprawdza czy wymagana jest ponowna autoryzacja"""
        if self.status_code == 401:
            # Sprawdz czy to błąd refresh tokena
            error_msg = str(self).lower()
            return 'invalid_grant' in error_msg or 'unauthorized' in error_msg
        return self.status_code == 403

class TeslaFleetAPIClient:
    """Klient Tesla Fleet API z obsługą podpisanych komend"""
    
    def __init__(self, client_id: str, client_secret: str, domain: str, 
                 private_key_file: str, public_key_url: str):
        """
        Inicjalizacja klienta Fleet API
        
        Args:
            client_id: ID aplikacji z portalu Tesla Developer
            client_secret: Secret aplikacji
            domain: Domena aplikacji
            private_key_file: Ścieżka do klucza prywatnego
            public_key_url: URL klucza publicznego
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.domain = domain
        self.private_key_file = private_key_file
        self.public_key_url = public_key_url
        
        # Ustaw domyślny URL dla Fleet API
        self.base_url = "https://fleet-api.prd.eu.vn.cloud.tesla.com"
        
        # Sprawdzenie czy skonfigurowano lokalne proxy
        proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST')
        proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT')
        
        if proxy_host and proxy_port:
            self.proxy_url = f"https://{proxy_host}:{proxy_port}"
            console.print(f"[blue]Tesla HTTP Proxy jest skonfigurowane: {self.proxy_url}[/blue]")
        else:
            self.proxy_url = None
        
        # NAPRAWKA: Używaj nowych URL-i Tesla Fleet API zgodnie z dokumentacją
        self.auth_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/authorize"
        self.token_url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
        
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.private_key = None
        
        # Ładowanie klucza prywatnego
        self._load_private_key()
        
        # Automatyczne ładowanie istniejących tokenów
        self._load_tokens()
    
    def _load_private_key(self):
        """Ładuje klucz prywatny do podpisywania komend"""
        try:
            with open(self.private_key_file, 'rb') as f:
                self.private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            console.print(f"[green]✓ Załadowano klucz prywatny Fleet API[/green]")
        except Exception as e:
            console.print(f"[red]✗ Błąd ładowania klucza prywatnego: {e}[/red]")
            raise
    
    def get_authorization_url(self, use_localhost: bool = False) -> str:
        """
        Generuje URL autoryzacji OAuth
        
        Args:
            use_localhost: Czy użyć localhost jako redirect URI
        
        Returns:
            str: URL do autoryzacji
        """
        redirect_uri = "http://localhost:8080/auth/callback" if use_localhost else f"{self.domain}/api/auth/callback"
        
        oauth = OAuth2Session(
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            scope=[
                "openid", 
                "offline_access", 
                "vehicle_device_data", 
                "vehicle_cmds", 
                "vehicle_charging_cmds",
                "vehicle_location",
                "user_data"
            ]
        )
        
        authorization_url, state = oauth.authorization_url(
            self.auth_url,
            state="tesla_fleet_auth"
        )
        
        return authorization_url
    
    def exchange_code_for_token(self, authorization_code: str, use_localhost: bool = False) -> bool:
        """
        Wymienia kod autoryzacji na token dostępu z lepszą obsługą błędów
        
        Args:
            authorization_code: Kod autoryzacji z callback
            use_localhost: Czy użyto localhost jako redirect URI
            
        Returns:
            bool: True jeśli sukces
        """
        try:
            redirect_uri = "http://localhost:8080/auth/callback" if use_localhost else f"{self.domain}/api/auth/callback"
            
            data = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': authorization_code,
                'audience': 'https://fleet-api.prd.eu.vn.cloud.tesla.com',  # NAPRAWKA: audience dla regionu Europa
                'redirect_uri': redirect_uri
            }
            
            console.print("[yellow]🔄 Wymiana kodu autoryzacji na token...[/yellow]")
            response = requests.post(self.token_url, data=data, timeout=30)
            
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error_description', error_data.get('error', 'Nieprawidłowy kod autoryzacji'))
                    
                    if 'invalid_grant' in error_msg.lower() or 'authorization_code' in error_msg.lower():
                        console.print("[red]🚫 Kod autoryzacji jest nieprawidłowy lub wygasł[/red]")
                        console.print("[yellow]💡 Spróbuj ponownie procesu autoryzacji[/yellow]")
                    elif 'invalid_client' in error_msg.lower():
                        console.print("[red]🚫 Nieprawidłowy Client ID lub Client Secret[/red]")
                        console.print("[yellow]💡 Sprawdź konfigurację w pliku .env[/yellow]")
                    else:
                        console.print(f"[red]❌ Błąd wymiany kodu: {error_msg}[/red]")
                        
                    console.print(f"[red]📊 Szczegóły błędu: {error_data}[/red]")
                except:
                    console.print(f"[red]❌ HTTP 400: {response.reason}[/red]")
                return False
                
            elif response.status_code == 401:
                console.print("[red]🚫 Nieautoryzowane - sprawdź Client ID i Client Secret[/red]")
                return False
                
            elif response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error_description', error_data.get('error', 'Nieznany błąd'))
                    console.print(f"[red]❌ Błąd HTTP {response.status_code}: {error_msg}[/red]")
                except:
                    console.print(f"[red]❌ HTTP {response.status_code}: {response.reason}[/red]")
                return False
            
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            self.refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            # Zapisanie tokenów
            self._save_tokens()
            
            console.print("[green]✅ Token dostępu uzyskany pomyślnie[/green]")
            console.print(f"[green]⏱️  Token wygaśnie za {expires_in//3600} godzin[/green]")
            if self.refresh_token:
                console.print("[green]🔄 Refresh token zapisany - automatyczne odnawianie włączone[/green]")
            return True
            
        except requests.exceptions.ConnectionError as e:
            console.print(f"[red]🌐 Błąd połączenia z Tesla Auth: {e}[/red]")
            return False
        except requests.exceptions.Timeout as e:
            console.print(f"[red]⏰ Timeout podczas autoryzacji: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]💥 Nieoczekiwany błąd podczas wymiany kodu na token: {e}[/red]")
            return False
    
    def _save_tokens(self):
        """
        Zapisuje tokeny zgodnie z wymaganiami Tesla API.

        Auto-cleanup utrzymuje max 3 aktywne wersje w Secret Manager (kontrola kosztów).
        """
        token_data = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
            'refresh_token_created_at': datetime.now(timezone.utc).isoformat()
        }

        # Sprawdź czy refresh_token się zmienił (Tesla rotuje go przy każdym odświeżeniu)
        refresh_token_changed = (
            not hasattr(self, '_last_saved_refresh_token') or
            self._last_saved_refresh_token != self.refresh_token
        )

        # Zapisz lokalnie (zawsze)
        try:
            with open('fleet_tokens.json', 'w') as f:
                json.dump(token_data, f)
            console.print("[green]✓ Tokeny zapisane lokalnie[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Nie udało się zapisać tokenów lokalnie: {e}[/yellow]")

        # Zapisz do Secret Manager przy każdej zmianie refresh_token
        # Auto-cleanup utrzymuje max 3 aktywne wersje (kontrola kosztów)
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if project_id and refresh_token_changed:
            try:
                from google.cloud import secretmanager
                client = secretmanager.SecretManagerServiceClient()

                secret_name = f"projects/{project_id}/secrets/fleet-tokens"
                payload = json.dumps(token_data).encode("UTF-8")

                client.add_secret_version(
                    request={"parent": secret_name, "payload": {"data": payload}}
                )
                self._last_saved_refresh_token = self.refresh_token
                console.print("[green]🔐 Tokeny zapisane do Secret Manager[/green]")

                # AUTO-CLEANUP: Wyłącz stare wersje (max 3 aktywne)
                self._cleanup_old_secret_versions(client, project_id)

            except Exception as e:
                console.print(f"[yellow]⚠️ Nie udało się zapisać tokenów w Secret Manager: {e}[/yellow]")
        elif project_id:
            console.print("[dim]ℹ️ Refresh token bez zmian - pomijam zapis[/dim]")

    def _cleanup_old_secret_versions(self, client, project_id: str):
        """
        Usuwa (destroy) stare wersje sekretu fleet-tokens (zostaw ostatnie 3).
        Zniszczone wersje są permanentnie usunięte i nie zaśmiecają konsoli.
        """
        try:
            parent = f"projects/{project_id}/secrets/fleet-tokens"
            versions = list(client.list_secret_versions(request={"parent": parent}))

            # Filtruj tylko włączone wersje
            from google.cloud.secretmanager_v1.types import SecretVersion
            enabled = [v for v in versions if v.state == SecretVersion.State.ENABLED]

            # Sortuj od najnowszej do najstarszej
            enabled.sort(key=lambda v: v.create_time, reverse=True)

            # Usuń (destroy) wszystkie oprócz 3 najnowszych
            destroyed_count = 0
            for old_version in enabled[3:]:
                try:
                    client.destroy_secret_version(request={"name": old_version.name})
                    destroyed_count += 1
                except Exception:
                    pass  # Ignoruj błędy pojedynczych wersji

            if destroyed_count > 0:
                console.print(f"[dim]🗑️ Usunięto {destroyed_count} starych wersji sekretu[/dim]")

        except Exception as e:
            console.print(f"[yellow]⚠️ Cleanup wersji nie powiódł się: {e}[/yellow]")
    
    def _clear_tokens(self):
        """Czyści tokeny z pamięci i pliku"""
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        
        try:
            if os.path.exists('fleet_tokens.json'):
                os.remove('fleet_tokens.json')
                console.print("[yellow]🗑️  Wyczyszczono nieprawidłowe tokeny[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Nie udało się usunąć pliku tokenów: {e}[/yellow]")
    
    def _load_tokens(self) -> bool:
        """
        Ładuje tokeny z centralnego miejsca (fleet-tokens) z automatyczną migracją
        
        KROK 1: Spróbuj załadować z fleet-tokens
        KROK 2: Jeśli niewłaściwe -> migruj z legacy sekretów  
        KROK 3: Fallback do lokalnego pliku
        """
        # KROK 1: Spróbuj załadować z fleet-tokens (centralne miejsce)
        if self._load_from_secret_manager():
            if self._are_tokens_valid():
                console.print("[green]✓ Tokeny załadowane z centralnego miejsca (fleet-tokens)[/green]")
                return True
            else:
                console.print("[yellow]⚠️ Tokeny z fleet-tokens są nieważne lub wygasłe[/yellow]")
        
        # KROK 2: Migracja z legacy sekretów (Worker Service)
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if project_id:
            console.print("[yellow]⚠️ fleet-tokens niewłaściwe - próba migracji z legacy[/yellow]")
            if self._migrate_from_legacy_tokens():
                console.print("[green]✅ Migracja z legacy sekretów udana[/green]")
                return True
            else:
                console.print("[yellow]⚠️ Migracja z legacy sekretów nie udana[/yellow]")
        
        # KROK 3: Fallback do lokalnego pliku
        return self._load_from_local_file()
    
    def _load_from_secret_manager(self) -> bool:
        """Ładuje tokeny z fleet-tokens w Secret Manager"""
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            return False
        
        try:
            # Importuj Google Cloud Secret Manager
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            
            # Odczytaj fleet-tokens
            name = f"projects/{project_id}/secrets/fleet-tokens/versions/latest"
            response = client.access_secret_version(request={"name": name})
            token_data = json.loads(response.payload.data.decode("UTF-8"))
            
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')

            # Zapamiętaj aktualny refresh_token do wykrywania zmian (optymalizacja kosztów)
            self._last_saved_refresh_token = self.refresh_token

            if token_data.get('expires_at'):
                expires_str = token_data['expires_at']
                if expires_str.endswith('Z'):
                    expires_str = expires_str.replace('Z', '+00:00')
                self.token_expires_at = datetime.fromisoformat(expires_str)
                if self.token_expires_at.tzinfo is None:
                    self.token_expires_at = self.token_expires_at.replace(tzinfo=timezone.utc)

            return True

        except Exception as e:
            console.print(f"[yellow]⚠️ Nie udało się załadować tokenów z fleet-tokens: {e}[/yellow]")
            return False
    
    def _load_from_local_file(self) -> bool:
        """Fallback: ładuje tokeny z lokalnego pliku"""
        try:
            with open('fleet_tokens.json', 'r') as f:
                token_data = json.load(f)
            
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')

            # Zapamiętaj aktualny refresh_token do wykrywania zmian (optymalizacja kosztów)
            self._last_saved_refresh_token = self.refresh_token

            if token_data.get('expires_at'):
                expires_str = token_data['expires_at']
                # NAPRAWKA: Zapewnij timezone-aware datetime dla porównań
                if expires_str.endswith('Z'):
                    expires_str = expires_str.replace('Z', '+00:00')
                self.token_expires_at = datetime.fromisoformat(expires_str)
                if self.token_expires_at.tzinfo is None:
                    self.token_expires_at = self.token_expires_at.replace(tzinfo=timezone.utc)

            console.print("[green]✓ Tokeny załadowane z lokalnego pliku[/green]")
            return True
        except FileNotFoundError:
            console.print("[yellow]⚠️ Nie znaleziono pliku fleet_tokens.json[/yellow]")
            return False
        except Exception as e:
            console.print(f"[yellow]⚠️ Błąd ładowania tokenów z pliku: {e}[/yellow]")
            return False
    
    def _refresh_access_token(self) -> bool:
        """Odświeża token dostępu z lepszą obsługą błędów"""
        if not self.refresh_token:
            console.print("[yellow]⚠️  Brak refresh tokena - wymagana ponowna autoryzacja[/yellow]")
            return False
        
        try:
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': self.refresh_token,
                'audience': 'https://fleet-api.prd.eu.vn.cloud.tesla.com'  # NAPRAWKA: audience dla regionu Europa
            }
            
            console.print("[yellow]🔄 Odświeżanie tokena dostępu...[/yellow]")
            response = requests.post(self.token_url, data=data, timeout=30)
            
            if response.status_code == 401:
                console.print("[red]🚫 Refresh token jest nieważny - wymagana ponowna autoryzacja[/red]")
                console.print("[yellow]💡 Uruchom: python3 generate_token.py[/yellow]")
                # Wyczyść tokeny
                self._clear_tokens()
                return False
            elif response.status_code == 403:
                console.print("[red]🚫 Brak uprawnień do odświeżenia tokena[/red]")
                console.print("[yellow]💡 Sprawdź konfigurację aplikacji w Tesla Developer Portal[/yellow]")
                return False
            elif response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error_description', error_data.get('error', 'Nieznany błąd'))
                    console.print(f"[red]❌ Błąd odświeżania tokena: {error_msg}[/red]")
                    console.print(f"[red]📊 Status code: {response.status_code}[/red]")
                    
                    # Szczegółowe błędy OAuth
                    if 'invalid_grant' in error_msg.lower():
                        console.print("[yellow]💡 Refresh token wygasł - wymagana ponowna autoryzacja[/yellow]")
                        self._clear_tokens()
                except:
                    console.print(f"[red]❌ HTTP {response.status_code}: {response.reason}[/red]")
                return False
            
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            
            # Obsługa rotacji refresh tokenu
            old_refresh_token = self.refresh_token
            if 'refresh_token' in token_data:
                self.refresh_token = token_data['refresh_token']
                if old_refresh_token != self.refresh_token:
                    console.print("[green]🔄 Otrzymano nowy refresh token - poprzedni będzie ważny jeszcze przez 24h[/green]")
            
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            # Zapisz tokeny
            self._save_tokens()
            
            console.print("[green]✅ Token odświeżony pomyślnie[/green]")
            console.print(f"[green]⏱️  Token wygaśnie za {expires_in//3600}h {(expires_in%3600)//60}m[/green]")
            return True
            
        except requests.exceptions.ConnectionError as e:
            console.print(f"[red]🌐 Błąd połączenia podczas odświeżania tokena: {e}[/red]")
            return False
        except requests.exceptions.Timeout as e:
            console.print(f"[red]⏰ Timeout podczas odświeżania tokena: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]💥 Nieoczekiwany błąd odświeżania tokenu: {e}[/red]")
            return False
    
    def _ensure_valid_token(self) -> bool:
        """Zapewnia ważny token dostępu"""
        # Próba załadowania istniejących tokenów
        if not self.access_token:
            if not self._load_tokens():
                return False
        
        # Sprawdzenie czy token nie wygasł
        if self.token_expires_at and datetime.now(timezone.utc) >= self.token_expires_at:
            if not self._refresh_access_token():
                return False
        
        return bool(self.access_token)
    
    def check_authorization_status(self) -> Dict[str, any]:
        """
        Sprawdza stan autoryzacji i zwraca szczegółowe informacje
        
        Returns:
            Dict z informacjami o stanie autoryzacji
        """
        status = {
            'authorized': False,
            'has_access_token': bool(self.access_token),
            'has_refresh_token': bool(self.refresh_token),
            'token_expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
            'token_expired': False,
            'needs_reauthorization': False,
            'error': None
        }
        
        if not self.access_token:
            status['error'] = 'Brak tokena dostępu'
            status['needs_reauthorization'] = True
            return status
        
        if self.token_expires_at:
            now = datetime.now(timezone.utc)
            status['token_expired'] = now >= self.token_expires_at
            if status['token_expired']:
                if self.refresh_token:
                    status['error'] = 'Token wygasł - możliwe automatyczne odświeżenie'
                else:
                    status['error'] = 'Token wygasł - brak refresh tokena'
                    status['needs_reauthorization'] = True
        
        # Sprawdź wiek refresh tokenu
        try:
            with open('fleet_tokens.json', 'r') as f:
                token_data = json.load(f)
                if 'refresh_token_created_at' in token_data:
                    created_at = datetime.fromisoformat(token_data['refresh_token_created_at'])
                    days_old = (datetime.now(timezone.utc) - created_at).days
                    
                    # Ostrzeż gdy zostało mniej niż 2 tygodnie
                    if days_old > 75:  # 90 dni - 2 tygodnie = 76 dni
                        console.print(f"[yellow]⚠️ Refresh token wygaśnie za {90-days_old} dni![/yellow]")
                        console.print("[yellow]💡 Zalecana ponowna autoryzacja: python3 generate_token.py[/yellow]")
                        status['refresh_token_expires_in_days'] = 90 - days_old
        except:
            pass  # Ignoruj błędy - to tylko dodatkowa diagnostyka
        
        # Test podstawowego połączenia
        try:
            vehicles = self.get_vehicles()
            status['authorized'] = True
            status['vehicle_count'] = len(vehicles)
        except TeslaAuthenticationError as e:
            status['error'] = str(e)
            status['needs_reauthorization'] = e.needs_reauthorization()
        except Exception as e:
            status['error'] = f'Błąd połączenia: {e}'
        
        return status
    
    def _sign_command(self, method: str, path: str, body: str = "") -> str:
        """
        Podpisuje komendę kluczem prywatnym
        
        Args:
            method: Metoda HTTP (GET, POST, etc.)
            path: Ścieżka API
            body: Treść żądania
            
        Returns:
            str: Podpis w formacie base64
        """
        # Tworzenie wiadomości do podpisania
        timestamp = str(int(time.time()))
        message = f"{method}\n{path}\n{body}\n{timestamp}"
        
        # Podpisywanie wiadomości
        signature = self.private_key.sign(
            message.encode('utf-8'),
            ec.ECDSA(hashes.SHA256())
        )
        
        # Kodowanie podpisu w base64
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return f"{signature_b64}:{timestamp}"
    
    def _make_signed_request(self, method: str, path: str, data: Dict = None, retry_auth: bool = True, use_proxy: bool = False) -> Dict:
        """
        Tworzy i wysyła podpisane żądanie do Tesla Fleet API lub przez proxy
        
        Args:
            method: Metoda HTTP (POST, GET)
            path: Ścieżka API (np. /api/1/vehicles)
            data: Słownik z danymi żądania
            retry_auth: Czy ponowić autoryzację w przypadku błędu
            use_proxy: Czy użyć Tesla HTTP Proxy zamiast bezpośredniego połączenia
            
        Returns:
            Dict: Odpowiedź API jako słownik
        """
        if not self._ensure_valid_token():
            raise TeslaAuthenticationError("Brak ważnego tokena dostępu", status_code=401)
        
        # Wybierz URL docelowy
        if use_proxy:
            if not self.proxy_url:
                error_msg = "Próba użycia proxy, ale TESLA_HTTP_PROXY_HOST/PORT nie są skonfigurowane."
                console.print(f"[red] BŁĄD: {error_msg}[/red]")
                raise ValueError(error_msg)
            
            base_url = self.proxy_url
            verify_ssl = False # Wyłącz weryfikację SSL dla self-signed certyfikatów proxy
            url_info = f"przez PROXY {base_url}"
        else:
            base_url = self.base_url
            verify_ssl = True
            url_info = f"do Fleet API {base_url}"

        url = f"{base_url}{path}"
        body = json.dumps(data) if data else ""
        signature = self._sign_command(method, path, body)
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            console.print(f"Wysyłanie żądania {method} {path} {url_info}")
            
            response = requests.request(
                method,
                url,
                headers=headers,
                data=body,
                timeout=30,
                verify=verify_ssl
            )

            # Debugging: wyświetl odpowiedź
            # console.print(f"Odpowiedź ({response.status_code}): {response.text}")

            # Obsługa błędów autoryzacji
            if response.status_code == 401:
                error_data = {}
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', 'Token dostępu wygasł lub jest nieważny')
                except:
                    error_msg = "Token dostępu wygasł lub jest nieważny"
                
                console.print(f"[red]🚫 Błąd autoryzacji (401): {error_msg}[/red]")
                
                # Spróbuj odświeżyć token i ponowić żądanie
                if retry_auth and self.refresh_token:
                    console.print("[yellow]🔄 Próba odświeżenia tokena...[/yellow]")
                    if self._refresh_access_token():
                        console.print("[yellow]🔄 Ponowne wysłanie żądania...[/yellow]")
                        return self._make_signed_request(method, path, data, retry_auth=False, use_proxy=use_proxy)
                    else:
                        console.print("[red]❌ Nie udało się odświeżyć tokena[/red]")
                
                raise TeslaAuthenticationError(error_msg, status_code=401, error_data=error_data)
                
            elif response.status_code == 403:
                error_data = {}
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', 'Brak uprawnień do wykonania tej operacji')
                except:
                    error_msg = "Brak uprawnień do wykonania tej operacji"
                
                console.print(f"[red]🚫 Błąd uprawnień (403): {error_msg}[/red]")
                console.print("[yellow]💡 Sprawdź scope'y aplikacji w Tesla Developer Portal[/yellow]")
                console.print(f"[yellow]📍 Żądanie: {method} {path}[/yellow]")
                
                raise TeslaAuthenticationError(error_msg, status_code=403, error_data=error_data)
            
            elif response.status_code >= 400:
                # Inne błędy HTTP - szczegółowe logowanie
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', f'HTTP {response.status_code}: {response.reason}')
                    console.print(f"[red]❌ Błąd API ({response.status_code}): {error_msg}[/red]")
                    console.print(f"[red]📍 Żądanie: {method} {path}[/red]")
                    if error_data:
                        console.print(f"[red]📊 Dane błędu: {error_data}[/red]")
                except:
                    console.print(f"[red]❌ HTTP {response.status_code}: {response.reason}[/red]")
                    console.print(f"[red]📍 Żądanie: {method} {path}[/red]")
                    console.print(f"[red]📄 Odpowiedź: {response.text[:300]}[/red]")
            
            response.raise_for_status()
            return response.json()
            
        except TeslaAuthenticationError:
            # Przepuść błędy autoryzacji bez modyfikacji
            raise
        except requests.exceptions.SSLError as e:
            if use_proxy:
                console.print(f"[yellow]🔒 Błąd SSL z proxy - sprawdź czy tesla-http-proxy działa na {base_url}[/yellow]")
            raise Exception(f"Błąd SSL: {e}")
        except requests.exceptions.ConnectionError as e:
            if use_proxy:
                console.print(f"[yellow]🌐 Nie można połączyć z proxy {base_url} - sprawdź czy tesla-http-proxy jest uruchomiony[/yellow]")
            raise Exception(f"Błąd połączenia: {e}")
        except requests.exceptions.Timeout as e:
            console.print(f"[yellow]⏰ Timeout żądania do Tesla API[/yellow]")
            raise Exception(f"Timeout żądania: {e}")
        except Exception as e:
            console.print(f"[red]💥 Nieoczekiwany błąd żądania: {e}[/red]")
            raise Exception(f"Błąd żądania: {e}")
    
    # Wzorce "reason" przy result=false oznaczające stan już osiągnięty (idempotencja)
    _ALREADY_SATISFIED_REASONS = ('not_found', 'not found', 'does not exist', 'no such schedule')

    def _command_result(self, response: Dict, command_name: str) -> tuple:
        """
        Odczytuje faktyczny wynik komendy /command/* z odpowiedzi Fleet API.
        Tesla zwraca HTTP 200 z {"response": {"result": false, "reason": "..."}}
        gdy pojazd odrzuci komendę — sam status HTTP nie oznacza sukcesu.
        UWAGA: nie dotyczy wake_up, który nie zwraca pola result.

        Returns:
            (success: bool, reason: str)
        """
        inner = response.get('response') if isinstance(response, dict) else None
        if not isinstance(inner, dict) or 'result' not in inner:
            # Nieznany kształt odpowiedzi — nie blokuj, ale zostaw wyraźny ślad
            console.print(f"[yellow]⚠️ {command_name}: odpowiedź bez pola result — przyjmuję sukces: {str(response)[:200]}[/yellow]")
            return True, ''
        reason = str(inner.get('reason') or '')
        if inner.get('result') is True:
            return True, reason
        console.print(f"[red]❌ {command_name}: pojazd odrzucił komendę (result=false, reason='{reason}')[/red]")
        return False, reason

    # ========== PODSTAWOWE OPERACJE ==========

    def get_vehicles(self) -> List[Dict]:
        """Pobiera listę pojazdów z obsługą błędów autoryzacji"""
        try:
            response = self._make_signed_request('GET', '/api/1/vehicles')
            return response.get('response', [])
        except TeslaAuthenticationError as e:
            if e.needs_reauthorization():
                console.print("[yellow]💡 Wymagana ponowna autoryzacja - uruchom: python3 generate_token.py[/yellow]")
            console.print(f"[red]🚫 Błąd autoryzacji podczas pobierania pojazdów: {e}[/red]")
            return []
        except Exception as e:
            console.print(f"[red]❌ Błąd pobierania pojazdów: {e}[/red]")
            return []
    
    def wake_vehicle(self, vehicle_id: str, use_proxy: bool = False) -> bool:
        """Budzi pojazd"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/wake_up', use_proxy=use_proxy)
            return True
        except Exception as e:
            console.print(f"[red]Błąd budzenia pojazdu: {e}[/red]")
            return False
    
    def get_vehicle_data(self, vehicle_id: str, endpoints: str = None) -> Dict:
        """
        Pobiera dane pojazdu z obsługą błędów autoryzacji
        
        Args:
            vehicle_id: ID pojazdu
            endpoints: Opcjonalne - konkretne endpointy do pobrania (np. "charge_schedule_data")
        """
        try:
            path = f'/api/1/vehicles/{vehicle_id}/vehicle_data'
            if endpoints:
                path += f'?endpoints={endpoints}'
            response = self._make_signed_request('GET', path)
            return response.get('response', {})
        except TeslaAuthenticationError as e:
            if e.needs_reauthorization():
                console.print("[yellow]💡 Wymagana ponowna autoryzacja - uruchom: python3 generate_token.py[/yellow]")
            console.print(f"[red]🚫 Błąd autoryzacji podczas pobierania danych pojazdu: {e}[/red]")
            return {}
        except Exception as e:
            console.print(f"[red]❌ Błąd pobierania danych pojazdu: {e}[/red]")
            return {}
    
    # ========== KOMENDY ŁADOWANIA ==========
    
    def set_charge_limit(self, vehicle_id: str, percent: int, use_proxy: bool = None) -> bool:
        """
        Ustawia limit ładowania (50-100%) z obsługą błędów autoryzacji
        WYMAGANE: Komenda musi być podpisana - automatycznie używa proxy jeśli dostępny
        """
        try:
            data = {'percent': percent}
            
            # Auto-detect proxy usage jeśli nie podano explicit
            if use_proxy is None:
                use_proxy = bool(self.proxy_url)
            
            if use_proxy and self.proxy_url:
                console.print(f"[yellow]🔐 set_charge_limit przez Tesla HTTP Proxy: {self.proxy_url}[/yellow]")
            elif use_proxy:
                console.print(f"[red]⚠️ set_charge_limit wymaga proxy ale proxy_url nie jest skonfigurowany[/red]")
            else:
                console.print(f"[yellow]⚠️ set_charge_limit przez Fleet API (może być odrzucony bez podpisu)[/yellow]")
            
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_charge_limit', data, use_proxy=use_proxy)
            ok, _ = self._command_result(resp, 'set_charge_limit')
            return ok
        except TeslaAuthenticationError as e:
            if e.needs_reauthorization():
                console.print("[yellow]💡 Wymagana ponowna autoryzacja - uruchom: python3 generate_token.py[/yellow]")
            elif e.is_forbidden():
                console.print("[yellow]💡 Brak uprawnień vehicle_cmds - sprawdź scope'y w Tesla Developer Portal[/yellow]")
            console.print(f"[red]🚫 Błąd autoryzacji podczas ustawiania limitu ładowania: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]❌ Błąd ustawiania limitu ładowania: {e}[/red]")
            return False
    
    def set_charging_amps(self, vehicle_id: str, charging_amps: int, use_proxy: bool = None) -> bool:
        """Ustawia prąd ładowania"""
        try:
            data = {'charging_amps': charging_amps}
            # Auto-detect proxy usage jeśli nie podano explicit (jak w set_charge_limit)
            if use_proxy is None:
                use_proxy = bool(self.proxy_url)
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_charging_amps', data, use_proxy=use_proxy)
            ok, _ = self._command_result(resp, 'set_charging_amps')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd ustawiania prądu ładowania: {e}[/red]")
            return False
    

    
    def charge_start(self, vehicle_id: str, use_proxy: bool = None) -> bool:
        """
        Rozpoczyna ładowanie (gdy okno harmonogramu pokrywa "teraz",
        a pojazd czeka zamiast ładować).
        """
        try:
            if use_proxy is None:
                use_proxy = bool(self.proxy_url)
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/charge_start', use_proxy=use_proxy)
            ok, reason = self._command_result(resp, 'charge_start')
            if not ok and 'charging' in reason.lower():
                # np. reason="is_charging" — pojazd już ładuje = cel osiągnięty
                console.print(f"[yellow]ℹ️ charge_start: pojazd już ładuje ('{reason}') — traktuję jako sukces[/yellow]")
                return True
            return ok
        except Exception as e:
            console.print(f"[red]Błąd komendy charge_start: {e}[/red]")
            return False

    def charge_stop(self, vehicle_id: str, use_proxy: bool = None) -> bool:
        """
        Zatrzymuje ładowanie (gdy trwająca sesja wypadła poza okno taniej taryfy
        po przeliczeniu harmonogramu).
        """
        try:
            if use_proxy is None:
                use_proxy = bool(self.proxy_url)
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/charge_stop', use_proxy=use_proxy)
            ok, reason = self._command_result(resp, 'charge_stop')
            if not ok and 'not_charging' in reason.lower():
                # Pojazd nie ładuje = cel osiągnięty
                console.print(f"[yellow]ℹ️ charge_stop: pojazd nie ładuje ('{reason}') — traktuję jako sukces[/yellow]")
                return True
            return ok
        except Exception as e:
            console.print(f"[red]Błąd komendy charge_stop: {e}[/red]")
            return False

    def charge_max_range(self, vehicle_id: str) -> bool:
        """Ładuje do maksymalnego zasięgu"""
        try:
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/charge_max_range')
            ok, _ = self._command_result(resp, 'charge_max_range')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd ustawiania ładowania max range: {e}[/red]")
            return False
    
    def charge_standard(self, vehicle_id: str) -> bool:
        """Ładuje w trybie standardowym"""
        try:
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/charge_standard')
            ok, _ = self._command_result(resp, 'charge_standard')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd ustawiania ładowania standard: {e}[/red]")
            return False
    
    def charge_port_door_open(self, vehicle_id: str) -> bool:
        """Otwiera klapę portu ładowania"""
        try:
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/charge_port_door_open')
            ok, _ = self._command_result(resp, 'charge_port_door_open')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd otwierania klapy ładowania: {e}[/red]")
            return False
    
    def charge_port_door_close(self, vehicle_id: str) -> bool:
        """Zamyka klapę portu ładowania"""
        try:
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/charge_port_door_close')
            ok, _ = self._command_result(resp, 'charge_port_door_close')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd zamykania klapy ładowania: {e}[/red]")
            return False
    
    # ========== HARMONOGRAMY ŁADOWANIA ==========
    
    def set_scheduled_charging(self, vehicle_id: str, enable: bool, time: int = None) -> bool:
        """Ustawia zaplanowane ładowanie (DEPRECATED - użyj add_charge_schedule)"""
        try:
            data = {'enable': enable}
            if time is not None:
                data['time'] = time
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_scheduled_charging', data)
            ok, _ = self._command_result(resp, 'set_scheduled_charging')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd ustawiania zaplanowanego ładowania: {e}[/red]")
            return False
    
    def add_charge_schedule(self, vehicle_id: str, days_of_week: str, enabled: bool, 
                           lat: float, lon: float, start_enabled: bool = True, 
                           end_enabled: bool = False, start_time: int = None, 
                           end_time: int = None, one_time: bool = False, 
                           schedule_id: int = None, use_proxy: bool = None) -> bool:
        """
        Dodaje nowy lub modyfikuje istniejący harmonogram ładowania
        WYMAGANE: Komenda musi być podpisana - automatycznie używa proxy jeśli dostępny
        
        Args:
            vehicle_id: ID pojazdu
            days_of_week: Dni tygodnia ("All", "Weekdays", "Monday,Tuesday" itp.)
            enabled: Czy harmonogram jest aktywny
            lat: Szerokość geograficzna
            lon: Długość geograficzna
            start_enabled: Czy rozpoczynać ładowanie o określonej godzinie
            end_enabled: Czy kończyć ładowanie o określonej godzinie
            start_time: Czas rozpoczęcia (minuty od północy)
            end_time: Czas zakończenia (minuty od północy)
            one_time: Czy to jednorazowy harmonogram
            schedule_id: ID istniejącego harmonogramu do modyfikacji
            use_proxy: None=auto-detect, True=wymuszaj proxy, False=Fleet API
            
        Returns:
            bool: True jeśli operacja się powiodła
        """
        try:
            data = {
                'enabled': enabled,
                'start_enabled': start_enabled,
                'end_enabled': end_enabled,
                'days_of_week': days_of_week,
                'lat': lat,
                'lon': lon,
                'one_time': one_time
            }
            
            if start_time is not None:
                data['start_time'] = start_time
            
            if end_time is not None:
                data['end_time'] = end_time
            
            if schedule_id is not None:
                data['id'] = schedule_id
            
            # Auto-detect proxy usage jeśli nie podano explicit
            if use_proxy is None:
                use_proxy = bool(self.proxy_url)
            
            if use_proxy and self.proxy_url:
                console.print(f"[yellow]🔐 add_charge_schedule przez Tesla HTTP Proxy: {self.proxy_url}[/yellow]")
            elif use_proxy:
                console.print(f"[red]⚠️ add_charge_schedule wymaga proxy ale proxy_url nie jest skonfigurowany[/red]")
            else:
                console.print(f"[yellow]⚠️ add_charge_schedule przez Fleet API (może być odrzucony bez podpisu)[/yellow]")

            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/add_charge_schedule', data, use_proxy=use_proxy)
            ok, _ = self._command_result(resp, 'add_charge_schedule')
            return ok
        except Exception as e:
            console.print(f"[red]Błąd dodawania harmonogramu ładowania: {e}[/red]")
            return False
    
    def remove_charge_schedule(self, vehicle_id: str, schedule_id: int, use_proxy: bool = False) -> bool:
        """
        Usuwa harmonogram ładowania
        WAŻNE: Ta komenda musi być wysłana przez Tesla HTTP Proxy
        """
        try:
            data = {'id': schedule_id}
            
            # WAŻNE: Wymuszenie użycia proxy dla tej komendy
            if not use_proxy:
                console.print("[yellow]OSTRZEŻENIE: remove_charge_schedule wymaga proxy. Wymuszono użycie proxy.[/yellow]")
                use_proxy = True
                
            resp = self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/remove_charge_schedule', data, use_proxy=use_proxy)
            ok, reason = self._command_result(resp, 'remove_charge_schedule')
            if not ok and any(p in reason.lower() for p in self._ALREADY_SATISFIED_REASONS):
                # Harmonogram już nie istnieje (np. wykonany one_time) — cel osiągnięty
                console.print(f"[yellow]ℹ️ remove_charge_schedule: harmonogram {schedule_id} już nie istnieje — traktuję jako sukces[/yellow]")
                return True
            return ok
        except Exception as e:
            console.print(f"[red]Błąd usuwania harmonogramu ładowania: {e}[/red]")
            return False
    
    def get_charge_schedules(self, vehicle_id: str) -> Optional[List[Dict]]:
        """
        Pobiera istniejące harmonogramy ładowania z dużą odpornością na zmiany w API

        Returns:
            List[Dict]: Lista harmonogramów ładowania ([] gdy potwierdzono brak)
            None: Gdy odczyt się nie powiódł — NIE oznacza "brak harmonogramów"!
                  Wołający nie może na tej podstawie pomijać usuwania starych wpisów.
        """
        try:
            # Krok 1: Zgodnie z dokumentacją Tesla API, harmonogramy są w konkretnych endpointach
            # Dokumentacja mówi: "call vehicle_data endpoint and request charge_schedule_data"
            # i "request preconditioning_schedule_data"
            endpoints_to_query = ";".join([
                "charge_schedule_data",      # Główny endpoint dla harmonogramów ładowania
                "preconditioning_schedule_data",  # Endpoint dla harmonogramów preconditioning
                "charge_state",              # Dodatkowe dane o ładowaniu
                "vehicle_state"              # Ogólne dane pojazdu
            ])
            
            console.print(f"Pobieranie danych pojazdu z endpointami: {endpoints_to_query}...")
            vehicle_data = self.get_vehicle_data(vehicle_id, endpoints=endpoints_to_query) 
            
            if not vehicle_data:
                console.print("[yellow]Nie udało się pobrać danych pojazdu — błąd odczytu (None), nie pusta lista.[/yellow]")
                return None

            # Krok 2: Zgodnie z dokumentacją Tesla API, sprawdź dokładnie wskazane endpointy
            console.print(f"🔍 Sprawdzanie struktury odpowiedzi vehicle_data...")
            console.print(f"📋 Dostępne klucze główne: {list(vehicle_data.keys())}")
            
            # Krok 2a: Sprawdź główny endpoint dla harmonogramów ładowania
            charge_schedule_data = vehicle_data.get('charge_schedule_data')
            if charge_schedule_data is not None:
                console.print(f"✅ Znaleziono charge_schedule_data: {type(charge_schedule_data)}")
                console.print(f"📋 Klucze w charge_schedule_data: {list(charge_schedule_data.keys()) if isinstance(charge_schedule_data, dict) else 'nie jest dict'}")
                
                # Sprawdź czy zawiera harmonogramy
                if isinstance(charge_schedule_data, dict):
                    # Może być lista harmonogramów bezpośrednio
                    if 'charge_schedules' in charge_schedule_data:
                        schedules = charge_schedule_data['charge_schedules']
                        if isinstance(schedules, list) and schedules:
                            console.print(f"✅ Znaleziono {len(schedules)} harmonogramów w charge_schedule_data.charge_schedules")
                            return schedules
                    # Lub może być to po prostu lista na najwyższym poziomie
                    elif isinstance(charge_schedule_data, list) and charge_schedule_data:
                        console.print(f"✅ Znaleziono {len(charge_schedule_data)} harmonogramów w charge_schedule_data (lista)")
                        return charge_schedule_data
                elif isinstance(charge_schedule_data, list) and charge_schedule_data:
                    console.print(f"✅ Znaleziono {len(charge_schedule_data)} harmonogramów w charge_schedule_data (lista)")
                    return charge_schedule_data
            
            # UWAGA: preconditioning_schedule_data celowo NIE jest zwracane —
            # to harmonogramy podgrzewania, nie ładowania. Wcześniejszy fallback
            # zwracał je jako charge schedules, przez co remove_all mógł kasować
            # użytkownikowi preconditioning i nie usuwać realnych okien ładowania.
            if vehicle_data.get('preconditioning_schedule_data') is not None:
                console.print("[blue]ℹ️ Pominięto preconditioning_schedule_data (to nie są harmonogramy ładowania)[/blue]")

            # Krok 2c: Sprawdź czy harmonogramy nie są w charge_state (fallback)
            charge_state = vehicle_data.get('charge_state', {})
            if isinstance(charge_state, dict):
                console.print(f"📋 Klucze w charge_state: {list(charge_state.keys())}")
                for possible_field in ['charge_schedules', 'scheduled_charging', 'charging_schedules']:
                    if possible_field in charge_state:
                        schedules = charge_state[possible_field]
                        if isinstance(schedules, list) and schedules:
                            console.print(f"✅ Znaleziono {len(schedules)} harmonogramów w charge_state.{possible_field}")
                            return schedules

            console.print("[yellow]Nie znaleziono harmonogramów ładowania w żadnej ze znanych lokalizacji.[/yellow]")
            console.print("[blue]Uwaga: Harmonogramy mogą być widoczne tylko w aplikacji mobilnej Tesla.[/blue]")
            console.print("[blue]Tesla Fleet API może nie zwracać wszystkich typów harmonogramów.[/blue]")
            return []
            
        except Exception as e:
            console.print(f"[red]Błąd pobierania harmonogramów ładowania: {e}[/red]")
            return None

    def remove_all_charge_schedules(self, vehicle_id: str, use_proxy: bool = False) -> bool:
        """
        Usuwa wszystkie harmonogramy ładowania
        WAŻNE: Ta komenda musi być wysłana przez Tesla HTTP Proxy
        
        Returns:
            bool: True jeśli wszystkie harmonogramy zostały usunięte pomyślnie
        """
        try:
            schedules = self.get_charge_schedules(vehicle_id)
            if schedules is None:
                # Błąd odczytu — NIE wolno uznać "brak harmonogramów = sukces",
                # bo wołający doda nowe okna obok osieroconych starych.
                console.print("[red]❌ Nie udało się odczytać harmonogramów — przerwano usuwanie (stare wpisy mogą istnieć).[/red]")
                return False
            if not schedules:
                console.print("[yellow]Brak harmonogramów do usunięcia.[/yellow]")
                return True
            
            success_count = 0
            total_count = len(schedules)
            
            for schedule in schedules:
                schedule_id = schedule.get('id')
                if schedule_id is not None:
                    if self.remove_charge_schedule(vehicle_id, schedule_id, use_proxy=use_proxy):
                        success_count += 1
                        console.print(f"[green]Usunięto harmonogram ID: {schedule_id}[/green]")
                    else:
                        console.print(f"[red]Nie udało się usunąć harmonogramu ID: {schedule_id}[/red]")
                else:
                    console.print(f"[yellow]Harmonogram bez ID - pomijam[/yellow]")
            
            if success_count == total_count:
                console.print(f"[green]Pomyślnie usunięto wszystkie {total_count} harmonogramów ładowania.[/green]")
                return True
            else:
                console.print(f"[yellow]Usunięto {success_count} z {total_count} harmonogramów.[/yellow]")
                return False
                
        except Exception as e:
            console.print(f"[red]Błąd usuwania wszystkich harmonogramów: {e}[/red]")
            return False
    
    # ========== KOMENDY KLIMATYZACJI ==========
    
    def auto_conditioning_start(self, vehicle_id: str) -> bool:
        """Włącza klimatyzację"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/auto_conditioning_start')
            return True
        except Exception as e:
            console.print(f"[red]Błąd włączania klimatyzacji: {e}[/red]")
            return False
    
    def auto_conditioning_stop(self, vehicle_id: str) -> bool:
        """Wyłącza klimatyzację"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/auto_conditioning_stop')
            return True
        except Exception as e:
            console.print(f"[red]Błąd wyłączania klimatyzacji: {e}[/red]")
            return False
    
    def set_temps(self, vehicle_id: str, driver_temp: float, passenger_temp: float) -> bool:
        """Ustawia temperaturę kabiny"""
        try:
            data = {
                'driver_temp': driver_temp,
                'passenger_temp': passenger_temp
            }
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_temps', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania temperatury: {e}[/red]")
            return False
    
    def set_climate_keeper_mode(self, vehicle_id: str, mode: int) -> bool:
        """
        Ustawia tryb Climate Keeper
        0: Off, 1: Keep Mode, 2: Dog Mode, 3: Camp Mode
        """
        try:
            data = {'climate_keeper_mode': mode}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_climate_keeper_mode', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania Climate Keeper: {e}[/red]")
            return False
    
    def set_cabin_overheat_protection(self, vehicle_id: str, on: bool, fan_only: bool = False) -> bool:
        """Ustawia ochronę przed przegrzaniem kabiny"""
        try:
            data = {
                'on': on,
                'fan_only': fan_only
            }
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_cabin_overheat_protection', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania ochrony przed przegrzaniem: {e}[/red]")
            return False
    
    # ========== KOMENDY ZAMKÓW I BEZPIECZEŃSTWA ==========
    
    def door_lock(self, vehicle_id: str) -> bool:
        """Zamyka pojazd"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/door_lock')
            return True
        except Exception as e:
            console.print(f"[red]Błąd zamykania pojazdu: {e}[/red]")
            return False
    
    def door_unlock(self, vehicle_id: str) -> bool:
        """Otwiera pojazd"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/door_unlock')
            return True
        except Exception as e:
            console.print(f"[red]Błąd otwierania pojazdu: {e}[/red]")
            return False
    
    def set_sentry_mode(self, vehicle_id: str, on: bool) -> bool:
        """Włącza/wyłącza tryb Sentry"""
        try:
            data = {'on': on}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_sentry_mode', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania trybu Sentry: {e}[/red]")
            return False
    
    def flash_lights(self, vehicle_id: str) -> bool:
        """Miga światłami"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/flash_lights')
            return True
        except Exception as e:
            console.print(f"[red]Błąd migania światłami: {e}[/red]")
            return False
    
    def honk_horn(self, vehicle_id: str) -> bool:
        """Trąbi klaksonem"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/honk_horn')
            return True
        except Exception as e:
            console.print(f"[red]Błąd trąbienia: {e}[/red]")
            return False
    
    # ========== KOMENDY BAGAŻNIKA I OKIEN ==========
    
    def actuate_trunk(self, vehicle_id: str, which_trunk: str) -> bool:
        """
        Otwiera/zamyka bagażnik
        which_trunk: "front" lub "rear"
        """
        try:
            data = {'which_trunk': which_trunk}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/actuate_trunk', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd obsługi bagażnika: {e}[/red]")
            return False
    
    def window_control(self, vehicle_id: str, command: str, lat: float = None, lon: float = None) -> bool:
        """
        Kontroluje okna
        command: "vent" lub "close"
        """
        try:
            data = {'command': command}
            if lat is not None:
                data['lat'] = lat
            if lon is not None:
                data['lon'] = lon
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/window_control', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd kontroli okien: {e}[/red]")
            return False
    
    def sun_roof_control(self, vehicle_id: str, state: str) -> bool:
        """
        Kontroluje szyberdach
        state: "stop", "close", "vent"
        """
        try:
            data = {'state': state}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/sun_roof_control', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd kontroli szyberdachu: {e}[/red]")
            return False
    
    # ========== KOMENDY MEDIÓW ==========
    
    def media_toggle_playback(self, vehicle_id: str) -> bool:
        """Przełącza odtwarzanie/pauzę"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/media_toggle_playback')
            return True
        except Exception as e:
            console.print(f"[red]Błąd przełączania odtwarzania: {e}[/red]")
            return False
    
    def media_next_track(self, vehicle_id: str) -> bool:
        """Następny utwór"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/media_next_track')
            return True
        except Exception as e:
            console.print(f"[red]Błąd przełączania na następny utwór: {e}[/red]")
            return False
    
    def media_prev_track(self, vehicle_id: str) -> bool:
        """Poprzedni utwór"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/media_prev_track')
            return True
        except Exception as e:
            console.print(f"[red]Błąd przełączania na poprzedni utwór: {e}[/red]")
            return False
    
    def adjust_volume(self, vehicle_id: str, volume: float) -> bool:
        """
        Ustawia głośność (0.0 - 11.0)
        Wymaga obecności użytkownika i włączonego dostępu mobilnego
        """
        try:
            data = {'volume': volume}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/adjust_volume', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania głośności: {e}[/red]")
            return False
    
    # ========== KOMENDY NAWIGACJI ==========
    
    def navigation_gps_request(self, vehicle_id: str, lat: float, lon: float, order: int = 1) -> bool:
        """Rozpoczyna nawigację do współrzędnych GPS"""
        try:
            data = {
                'lat': lat,
                'lon': lon,
                'order': order
            }
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/navigation_gps_request', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd nawigacji GPS: {e}[/red]")
            return False
    
    def navigation_request(self, vehicle_id: str, locale: str, timestamp_ms: int, 
                          nav_type: str, value: str) -> bool:
        """Wysyła lokalizację do systemu nawigacji"""
        try:
            data = {
                'locale': locale,
                'timestamp_ms': timestamp_ms,
                'type': nav_type,
                'value': value
            }
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/navigation_request', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd żądania nawigacji: {e}[/red]")
            return False
    
    # ========== KOMENDY ZDALNEGO STARTU ==========
    
    def remote_start_drive(self, vehicle_id: str) -> bool:
        """
        Zdalny start pojazdu
        Wymaga włączonej jazdy bez kluczyka
        """
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/remote_start_drive')
            return True
        except Exception as e:
            console.print(f"[red]Błąd zdalnego startu: {e}[/red]")
            return False
    
    # ========== KOMENDY AKTUALIZACJI ==========
    
    def schedule_software_update(self, vehicle_id: str, offset_sec: int) -> bool:
        """Planuje aktualizację oprogramowania"""
        try:
            data = {'offset_sec': offset_sec}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/schedule_software_update', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd planowania aktualizacji: {e}[/red]")
            return False
    
    def cancel_software_update(self, vehicle_id: str) -> bool:
        """Anuluje aktualizację oprogramowania"""
        try:
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/cancel_software_update')
            return True
        except Exception as e:
            console.print(f"[red]Błąd anulowania aktualizacji: {e}[/red]")
            return False
    
    # ========== KOMENDY OGRZEWANIA FOTELI I KIEROWNICY ==========
    
    def remote_seat_heater_request(self, vehicle_id: str, seat_position: int, level: int) -> bool:
        """
        Ustawia ogrzewanie fotela
        seat_position: 0-8 (pozycje foteli)
        level: 0-3 (poziom ogrzewania)
        """
        try:
            data = {
                'seat_position': seat_position,
                'level': level
            }
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/remote_seat_heater_request', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania ogrzewania fotela: {e}[/red]")
            return False
    
    def remote_steering_wheel_heater_request(self, vehicle_id: str, on: bool) -> bool:
        """Włącza/wyłącza ogrzewanie kierownicy"""
        try:
            data = {'on': on}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/remote_steering_wheel_heater_request', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd ustawiania ogrzewania kierownicy: {e}[/red]")
            return False
    
    # ========== INNE KOMENDY ==========
    
    def remote_boombox(self, vehicle_id: str, sound: int) -> bool:
        """
        Odtwarza dźwięk przez zewnętrzny głośnik
        sound: 0 (random fart), 2000 (locate ping)
        """
        try:
            data = {'sound': sound}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/remote_boombox', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd odtwarzania dźwięku: {e}[/red]")
            return False
    
    def set_vehicle_name(self, vehicle_id: str, vehicle_name: str) -> bool:
        """Zmienia nazwę pojazdu"""
        try:
            data = {'vehicle_name': vehicle_name}
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/set_vehicle_name', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd zmiany nazwy pojazdu: {e}[/red]")
            return False
    
    def trigger_homelink(self, vehicle_id: str, lat: float, lon: float, token: str) -> bool:
        """Aktywuje HomeLink (otwieranie garażu)"""
        try:
            data = {
                'lat': lat,
                'lon': lon,
                'token': token
            }
            self._make_signed_request('POST', f'/api/1/vehicles/{vehicle_id}/command/trigger_homelink', data)
            return True
        except Exception as e:
            console.print(f"[red]Błąd aktywacji HomeLink: {e}[/red]")
            return False 

    def _migrate_from_legacy_tokens(self) -> bool:
        """
        Migruje tokeny z legacy sekretów do fleet-tokens (centralne zarządzanie)
        
        1. Pobierz legacy sekrety (tesla-refresh-token, tesla-client-id, tesla-client-secret)
        2. Użyj refresh tokenu do wygenerowania nowego access tokenu
        3. Zapisz oba do fleet-tokens
        4. Zwróć True jeśli sukces
        
        Returns:
            bool: True jeśli migracja udana
        """
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            console.print("[yellow]⚠️ Brak GOOGLE_CLOUD_PROJECT - pomijam migrację legacy[/yellow]")
            return False
        
        try:
            console.print("[yellow]🔄 [MIGRACJA] Próba migracji tokenów z legacy sekretów...[/yellow]")
            
            # Importuj Google Cloud Secret Manager
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            
            # Funkcja pomocnicza do odczytu legacy sekretów
            def get_legacy_secret(secret_name: str) -> Optional[str]:
                try:
                    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
                    response = client.access_secret_version(request={"name": name})
                    return response.payload.data.decode("UTF-8")
                except Exception as e:
                    console.print(f"[yellow]⚠️ Nie można odczytać {secret_name}: {e}[/yellow]")
                    return None
            
            # Pobierz legacy sekrety
            legacy_client_id = get_legacy_secret('tesla-client-id')
            legacy_client_secret = get_legacy_secret('tesla-client-secret')
            legacy_refresh_token = get_legacy_secret('tesla-refresh-token')
            
            if not all([legacy_client_id, legacy_client_secret, legacy_refresh_token]):
                console.print("[red]❌ [MIGRACJA] Brak wymaganych legacy sekretów[/red]")
                return False
            
            console.print("[yellow]✓ [MIGRACJA] Legacy sekrety odczytane pomyślnie[/yellow]")
            
            # Użyj legacy refresh tokenu do wygenerowania nowego access tokenu
            try:
                data = {
                    'grant_type': 'refresh_token',
                    'client_id': legacy_client_id,
                    'client_secret': legacy_client_secret,
                    'refresh_token': legacy_refresh_token,
                    'audience': 'https://fleet-api.prd.eu.vn.cloud.tesla.com'
                }
                
                console.print("[yellow]🔄 [MIGRACJA] Generowanie nowego access tokenu z legacy refresh...[/yellow]")
                response = requests.post(self.token_url, data=data, timeout=30)
                
                if response.status_code == 401:
                    console.print("[red]❌ [MIGRACJA] Legacy refresh token nieważny[/red]")
                    return False
                elif response.status_code >= 400:
                    console.print(f"[red]❌ [MIGRACJA] Błąd HTTP {response.status_code}: {response.reason}[/red]")
                    return False
                
                response.raise_for_status()
                token_data = response.json()
                
                # Aktualizuj tokeny w pamięci
                self.access_token = token_data['access_token']
                if 'refresh_token' in token_data:
                    self.refresh_token = token_data['refresh_token']
                else:
                    self.refresh_token = legacy_refresh_token  # Zachowaj legacy jeśli nie ma nowego
                
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                
                console.print("[green]✅ [MIGRACJA] Nowy access token wygenerowany pomyślnie[/green]")
                console.print(f"[green]⏱️ [MIGRACJA] Token wygaśnie za {expires_in//3600}h {(expires_in%3600)//60}m[/green]")
                
                # Zapisz zmigrowane tokeny do fleet-tokens
                self._save_tokens()
                
                console.print("[green]✅ [MIGRACJA] Tokeny zapisane do centralnego miejsca (fleet-tokens)[/green]")
                return True
                
            except requests.exceptions.RequestException as e:
                console.print(f"[red]❌ [MIGRACJA] Błąd sieci podczas odświeżania tokenu: {e}[/red]")
                return False
            except Exception as e:
                console.print(f"[red]❌ [MIGRACJA] Nieoczekiwany błąd: {e}[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]❌ [MIGRACJA] Błąd migracji tokenów: {e}[/red]")
            return False
    
    def _are_tokens_valid(self) -> bool:
        """Sprawdza czy tokeny są ważne i nie wygasłe"""
        if not self.access_token or not self.refresh_token:
            return False
        
        # Sprawdź czy access token nie wygasł (z 5 min buforem)
        if self.token_expires_at:
            buffer_minutes = 5  # 5 min buffer przed wygaśnięciem
            expires_with_buffer = self.token_expires_at - timedelta(minutes=buffer_minutes)
            if datetime.now(timezone.utc) >= expires_with_buffer:
                return False
        
        return True 