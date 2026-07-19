#!/usr/bin/env python3
"""
Tesla Controller - Program do kontrolowania pojazdu Tesla
Umożliwia sprawdzanie podstawowych parametrów pojazdu oraz zarządzanie harmonogramem ładowania.
Używa wyłącznie Tesla Fleet API zgodnie z oficjalną dokumentacją.
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Import Fleet API - wymagany
try:
    from tesla_fleet_api_client import TeslaFleetAPIClient, TeslaAuthenticationError
    FLEET_API_AVAILABLE = True
except ImportError:
    FLEET_API_AVAILABLE = False
    raise ImportError("Tesla Fleet API Client jest wymagany. Sprawdź czy plik tesla_fleet_api_client.py istnieje.")

# Ładowanie zmiennych środowiskowych
load_dotenv()

console = Console()

@dataclass
class ChargeSchedule:
    """Klasa reprezentująca harmonogram ładowania"""
    id: Optional[int] = None
    enabled: bool = True
    start_time: Optional[int] = None  # minuty od północy
    end_time: Optional[int] = None    # minuty od północy
    start_enabled: bool = False
    end_enabled: bool = False
    days_of_week: str = "All"
    lat: float = 0.0
    lon: float = 0.0
    one_time: bool = False

class TeslaController:
    """Główna klasa kontrolera Tesla - używa wyłącznie Fleet API"""
    
    def __init__(self, email: str = None, cache_file: str = None):
        """
        Inicjalizacja kontrolera Tesla
        
        Args:
            email: Adres email konta Tesla (opcjonalne dla Fleet API)
            cache_file: Ścieżka do pliku cache z tokenami (opcjonalne)
        """
        self.email = email or os.getenv('TESLA_EMAIL')
        self.cache_file = cache_file or os.getenv('TESLA_CACHE_FILE', 'tesla_cache.json')
        self.timeout = int(os.getenv('TESLA_TIMEOUT', '30'))
        
        # Fleet API configuration - próba odczytu z Secret Manager
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
        # Próba odczytu sekretów (jeśli jest Google Cloud Project)
        if project_id:
            print(f"Wykryto Google Cloud Project: {project_id} - próbuję odczytać sekrety")
            try:
                from google.cloud import secretmanager
                client = secretmanager.SecretManagerServiceClient()
                
                # Funkcja pomocnicza do odczytu sekretów
                def get_secret(secret_name: str) -> str:
                    try:
                        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
                        response = client.access_secret_version(request={"name": name})
                        return response.payload.data.decode("UTF-8")
                    except Exception as e:
                        print(f"⚠ Błąd odczytu sekretu {secret_name}: {e}")
                        return None
                
                # Odczyt sekretów z fallback na zmienne środowiskowe
                secret_client_id = get_secret('tesla-client-id')
                secret_client_secret = get_secret('tesla-client-secret')
                
                if secret_client_id:
                    print("✓ Odczytano TESLA_CLIENT_ID z Secret Manager")
                    self.client_id = secret_client_id
                else:
                    print("⚠ Używam TESLA_CLIENT_ID ze zmiennej środowiskowej")
                    self.client_id = os.getenv('TESLA_CLIENT_ID')
                
                if secret_client_secret:
                    print("✓ Odczytano TESLA_CLIENT_SECRET z Secret Manager")
                    self.client_secret = secret_client_secret
                else:
                    print("⚠ Używam TESLA_CLIENT_SECRET ze zmiennej środowiskowej")
                    self.client_secret = os.getenv('TESLA_CLIENT_SECRET')
                
                # Odczyt TESLA_DOMAIN z Secret Manager
                secret_domain = get_secret('tesla-domain')
                secret_public_key_url = get_secret('tesla-public-key-url')
                
                if secret_domain:
                    print("✓ Odczytano TESLA_DOMAIN z Secret Manager")
                    self.domain = secret_domain
                else:
                    print("⚠ Używam TESLA_DOMAIN ze zmiennej środowiskowej")
                    self.domain = os.getenv('TESLA_DOMAIN')
                
                if secret_public_key_url:
                    print("✓ Odczytano TESLA_PUBLIC_KEY_URL z Secret Manager")
                    self.public_key_url = secret_public_key_url
                else:
                    print("⚠ Używam TESLA_PUBLIC_KEY_URL ze zmiennej środowiskowej")
                    self.public_key_url = os.getenv('TESLA_PUBLIC_KEY_URL')
                
                self.private_key_file = 'private-key.pem'  # Klucz z Secret Manager
                
                # Zapisz klucz prywatny lokalnie z Secret Manager
                private_key_content = get_secret('tesla-private-key')
                if private_key_content:
                    print("✓ Odczytano klucz prywatny z Secret Manager")
                    with open('private-key.pem', 'w') as f:
                        f.write(private_key_content)
                else:
                    print("⚠ Nie można odczytać klucza prywatnego z Secret Manager")
                
                # Odczyt danych lokalizacji z Secret Manager
                secret_home_latitude = get_secret('home-latitude')
                secret_home_longitude = get_secret('home-longitude')
                secret_home_radius = get_secret('home-radius')
                
                if secret_home_latitude:
                    print("✓ Odczytano HOME_LATITUDE z Secret Manager")
                    self.default_latitude = float(secret_home_latitude)
                else:
                    print("⚠ Używam HOME_LATITUDE ze zmiennej środowiskowej")
                    self.default_latitude = float(os.getenv('HOME_LATITUDE', '52.334215'))
                
                if secret_home_longitude:
                    print("✓ Odczytano HOME_LONGITUDE z Secret Manager")
                    self.default_longitude = float(secret_home_longitude)
                else:
                    print("⚠ Używam HOME_LONGITUDE ze zmiennej środowiskowej")
                    self.default_longitude = float(os.getenv('HOME_LONGITUDE', '20.937516'))
                
                if secret_home_radius:
                    print("✓ Odczytano HOME_RADIUS z Secret Manager")
                    self.home_radius = float(secret_home_radius)
                else:
                    print("⚠ Używam HOME_RADIUS ze zmiennej środowiskowej")
                    self.home_radius = float(os.getenv('HOME_RADIUS', '0.03'))
                
            except ImportError:
                # Fallback - użyj zmiennych środowiskowych
                self.client_id = os.getenv('TESLA_CLIENT_ID')
                self.client_secret = os.getenv('TESLA_CLIENT_SECRET')
                self.domain = os.getenv('TESLA_DOMAIN')
                self.private_key_file = os.getenv('TESLA_PRIVATE_KEY_FILE')
                self.public_key_url = os.getenv('TESLA_PUBLIC_KEY_URL')
        else:
            # Bez Google Cloud - użyj zmiennych środowiskowych
            self.client_id = os.getenv('TESLA_CLIENT_ID')
            self.client_secret = os.getenv('TESLA_CLIENT_SECRET')
            self.domain = os.getenv('TESLA_DOMAIN')
            self.private_key_file = os.getenv('TESLA_PRIVATE_KEY_FILE')
            self.public_key_url = os.getenv('TESLA_PUBLIC_KEY_URL')
        
        # Domyślna lokalizacja dla harmonogramów ładowania - fallback dla starych konfiguracji
        if not hasattr(self, 'default_latitude'):
            self.default_latitude = float(os.getenv('HOME_LATITUDE', '52.334215'))
        if not hasattr(self, 'default_longitude'):
            self.default_longitude = float(os.getenv('HOME_LONGITUDE', '20.937516'))
        if not hasattr(self, 'home_radius'):
            self.home_radius = float(os.getenv('HOME_RADIUS', '0.03'))
        

        # Sprawdzenie wymaganej konfiguracji Fleet API
        if not all([self.client_id, self.client_secret, self.domain, self.private_key_file, self.public_key_url]):
            raise ValueError(
                "Brak wymaganej konfiguracji Fleet API. Ustaw w pliku .env:\n"
                "TESLA_CLIENT_ID=twój_client_id\n"
                "TESLA_CLIENT_SECRET=twój_client_secret\n"
                "TESLA_DOMAIN=twoja_domena\n"
                "TESLA_PRIVATE_KEY_FILE=private-key.pem\n"
                "TESLA_PUBLIC_KEY_URL=https://twoja_domena/.well-known/appspecific/com.tesla.3p.public-key.pem"
            )
        
        # BEZPIECZEŃSTWO: Sprawdź czy nie używamy placeholder'ów
        self._validate_secrets_security()
        
        self.fleet_api = None
        self.vehicles = []
        self.current_vehicle = None
        self.private_key = None
        
        # Ładowanie klucza prywatnego
        self._load_private_key()
        
        # Inicjalizacja Fleet API
        self._init_fleet_api()
        
    def _validate_secrets_security(self):
        """
        BEZPIECZEŃSTWO: Sprawdza czy sekrety nie są placeholder'ami
        Zapobiega przypadkowemu użyciu placeholder'ów w produkcji
        """
        dangerous_placeholders = [
            "REPLACE_WITH_YOUR_CLIENT_SECRET",
            "REPLACE_WITH_YOUR_CLIENT_ID", 
            "REPLACE_WITH_YOUR_DOMAIN",
            "your_client_secret_from_tesla_developer_portal", 
            "twój_client_secret",
            "your_client_id_from_tesla_developer_portal",
            "twój_client_id",
            "your-domain.com",
            "twoja_domena",
            "twoja-domena.com",
            "managed-by-secret-manager"  # Nowy placeholder z Cloud Run
        ]
        
        # Sprawdź client_secret
        if self.client_secret in dangerous_placeholders:
            raise ValueError(
                "🚨 BŁĄD BEZPIECZEŃSTWA: Wykryto placeholder zamiast rzeczywistego TESLA_CLIENT_SECRET!\n"
                "Ustaw prawdziwy secret w Google Cloud Secret Manager lub .env"
            )
        
        # Sprawdź client_id
        if self.client_id in dangerous_placeholders:
            raise ValueError(
                "🚨 BŁĄD BEZPIECZEŃSTWA: Wykryto placeholder zamiast rzeczywistego TESLA_CLIENT_ID!\n"
                "Ustaw prawdziwy client ID w Google Cloud Secret Manager lub .env"
            )
        
        # Sprawdź domenę
        if self.domain in dangerous_placeholders:
            raise ValueError(
                "🚨 BŁĄD BEZPIECZEŃSTWA: Wykryto placeholder zamiast rzeczywistej TESLA_DOMAIN!\n"
                "Ustaw prawdziwą domenę w Google Cloud Secret Manager lub .env"
            )
        
        console.print("[green]✅ Walidacja bezpieczeństwa sekretów: PASSED[/green]")
        
    def _load_private_key(self):
        """Ładuje klucz prywatny do podpisywania komend"""
        try:
            if os.path.exists(self.private_key_file):
                with open(self.private_key_file, 'r') as f:
                    self.private_key = f.read()
                console.print("[green]✓ Klucz prywatny Fleet API załadowany[/green]")
            else:
                raise FileNotFoundError(f"Klucz prywatny nie znaleziony: {self.private_key_file}")
        except Exception as e:
            console.print(f"[red]✗ Błąd ładowania klucza prywatnego: {e}[/red]")
            raise
        
    def connect(self) -> bool:
        """
        Nawiązuje połączenie z Tesla Fleet API z obsługą błędów autoryzacji
        
        Returns:
            bool: True jeśli połączenie udane, False w przeciwnym razie
        """
        try:
            console.print("[yellow]🔗 Łączenie z Tesla Fleet API...[/yellow]")
            
            if not self.fleet_api:
                console.print("[red]❌ Fleet API nie jest zainicjalizowane.[/red]")
                return False
            
            # Sprawdzenie stanu autoryzacji
            auth_status = self.fleet_api.check_authorization_status()
            
            if auth_status.get('needs_reauthorization'):
                console.print("[red]🚫 Wymagana ponowna autoryzacja[/red]")
                console.print("[yellow]💡 Uruchom: python3 generate_token.py[/yellow]")
                console.print(f"[red]📄 Błąd: {auth_status.get('error', 'Nieznany błąd autoryzacji')}[/red]")
                return False
            
            # Pobieranie listy pojazdów przez Fleet API
            console.print("[yellow]📋 Pobieranie listy pojazdów...[/yellow]")
            self.vehicles = self.fleet_api.get_vehicles()
            
            if not self.vehicles:
                console.print("[red]❌ Nie znaleziono żadnych pojazdów na koncie.[/red]")
                console.print("[yellow]💡 Sprawdź czy aplikacja ma dostęp do pojazdów w Tesla App[/yellow]")
                return False
            
            # Ustawienie pierwszego pojazdu jako aktywny
            self.current_vehicle = self.vehicles[0]
            vehicle_name = self.current_vehicle.get('display_name', 'Nieznany')
            
            console.print(f"[green]✅ Połączono pomyślnie! Znaleziono {len(self.vehicles)} pojazd(ów).[/green]")
            console.print(f"[green]🚗 Aktywny pojazd: {vehicle_name}[/green]")
            
            return True
            
        except Exception as e:
            console.print(f"[red]💥 Błąd podczas łączenia z Tesla Fleet API: {e}[/red]")
            
            # Dodatkowe informacje diagnostyczne
            if "401" in str(e) or "unauthorized" in str(e).lower():
                console.print("[yellow]💡 Błąd autoryzacji - sprawdź tokeny:[/yellow]")
                console.print("[yellow]   1. Uruchom: python3 generate_token.py[/yellow]")
                console.print("[yellow]   2. Sprawdź konfigurację w .env[/yellow]")
            elif "403" in str(e) or "forbidden" in str(e).lower():
                console.print("[yellow]💡 Brak uprawnień - sprawdź scope'y aplikacji w Tesla Developer Portal[/yellow]")
            
            return False
    
    def _init_fleet_api(self):
        """Inicjalizuje Fleet API klienta"""
        try:
            self.fleet_api = TeslaFleetAPIClient(
                client_id=self.client_id,
                client_secret=self.client_secret,
                domain=self.domain,
                private_key_file=self.private_key_file,
                public_key_url=self.public_key_url
            )
            console.print("[green]✓ Fleet API klient zainicjalizowany[/green]")
        except Exception as e:
            console.print(f"[red]✗ Błąd inicjalizacji Fleet API: {e}[/red]")
            raise
    
    def check_authorization(self) -> bool:
        """
        Sprawdza stan autoryzacji Tesla API i wyświetla szczegółowe informacje
        
        Returns:
            bool: True jeśli autoryzacja jest prawidłowa
        """
        if not self.fleet_api:
            console.print("[red]❌ Fleet API nie jest zainicjalizowane[/red]")
            return False
        
        try:
            console.print("[yellow]🔍 Sprawdzanie stanu autoryzacji...[/yellow]")
            status = self.fleet_api.check_authorization_status()
            
            console.print("\n[bold]📊 Stan autoryzacji Tesla API:[/bold]")
            console.print(f"  Token dostępu: {'✅' if status['has_access_token'] else '❌'}")
            console.print(f"  Refresh token: {'✅' if status['has_refresh_token'] else '❌'}")
            
            if status.get('token_expires_at'):
                from datetime import datetime
                expires_at = datetime.fromisoformat(status['token_expires_at'])
                console.print(f"  Wygasa: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
                console.print(f"  Status: {'🔴 Wygasł' if status['token_expired'] else '🟢 Aktywny'}")
            
            if status['authorized']:
                console.print(f"  Pojazdy: {status.get('vehicle_count', 0)}")
                console.print("[green]✅ Autoryzacja prawidłowa[/green]")
                return True
            else:
                console.print(f"[red]❌ Błąd autoryzacji: {status.get('error', 'Nieznany błąd')}[/red]")
                
                if status['needs_reauthorization']:
                    console.print("\n[yellow]🔧 Wymagane działania:[/yellow]")
                    console.print("[yellow]  1. Uruchom: python3 generate_token.py[/yellow]")
                    console.print("[yellow]  2. Przejdź przez proces autoryzacji OAuth[/yellow]")
                    console.print("[yellow]  3. Sprawdź konfigurację w pliku .env[/yellow]")
                
                return False
                
        except Exception as e:
            console.print(f"[red]💥 Błąd sprawdzania autoryzacji: {e}[/red]")
            return False
    
    def list_vehicles(self) -> None:
        """Wyświetla listę dostępnych pojazdów"""
        if not self.vehicles:
            console.print("[red]Brak dostępnych pojazdów.[/red]")
            return
        
        table = Table(title="Dostępne pojazdy Tesla")
        table.add_column("Nr", style="cyan", no_wrap=True)
        table.add_column("Nazwa", style="magenta")
        table.add_column("Model", style="green")
        table.add_column("VIN", style="yellow")
        table.add_column("Status", style="blue")
        table.add_column("API", style="red")
        
        for i, vehicle in enumerate(self.vehicles):
            # Fleet API używa innych pól niż TeslaPy
            status = vehicle.get('state', 'unknown')
            api_type = "Fleet API"
            
            table.add_row(
                str(i + 1),
                vehicle.get('display_name', 'Nieznana'),
                vehicle.get('vehicle_config', {}).get('car_type', 'Nieznany'),
                vehicle.get('vin', 'Nieznany'),
                status.title(),
                api_type
            )
        
        console.print(table)
    
    def select_vehicle(self, index: int) -> bool:
        """
        Wybiera pojazd do kontrolowania
        
        Args:
            index: Indeks pojazdu (0-based)
            
        Returns:
            bool: True jeśli wybór udany
        """
        if 0 <= index < len(self.vehicles):
            self.current_vehicle = self.vehicles[index]
            console.print(f"[green]Wybrano pojazd: {self.current_vehicle.get('display_name', 'Nieznany')}[/green]")
            return True
        else:
            console.print(f"[red]Nieprawidłowy indeks pojazdu: {index}[/red]")
            return False
    
    def wake_up_vehicle(self, use_proxy: bool = False) -> bool:
        """
        Budzi pojazd jeśli jest uśpiony
        
        Args:
            use_proxy: Czy użyć Tesla HTTP Proxy dla komendy wake_up
        
        Returns:
            bool: True jeśli pojazd jest online
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać ID pojazdu.[/red]")
            return False
        
        # LOG DIAGNOSTYCZNY: Stan pojazdu w cache
        cached_state = self.current_vehicle.get('state', 'unknown')
        console.print(f"[yellow]🔍 Stan pojazdu w cache: {cached_state}[/yellow]")

        # UWAGA: Nie polegamy na cache - zawsze wywołujemy wake_up
        # Cache może być nieaktualny (pojazd zasnął od ostatniego sprawdzenia)
        # wake_up jest idempotentne - jeśli pojazd już nie śpi, natychmiast zwraca sukces

        try:
            proxy_info = "przez proxy" if use_proxy else "przez Fleet API"
            console.print(f"[yellow]🔄 Budzenie pojazdu {proxy_info}...[/yellow]")

            success = self.fleet_api.wake_vehicle(vehicle_id, use_proxy=use_proxy)

            if not success:
                # Komenda wake mogła zawieść (np. timeout proxy), choć pojazd JEST online —
                # zdecyduj na podstawie ŚWIEŻEGO odczytu, nigdy migawki z connect()
                console.print(f"[red]❌ Komenda wake_up nie powiodła się - sprawdzam świeży stan pojazdu[/red]")
                fresh_state = self._refresh_vehicle_state()
                if fresh_state == 'online':
                    console.print(f"[green]✅ Pojazd mimo to online (świeży odczyt)[/green]")
                    return True
                console.print(f"[red]❌ Pojazd nie jest online (świeży stan: {fresh_state or 'nieznany'})[/red]")
                return False

            # Polling z backoffem do ~90s — zimny pojazd potrafi wstawać 60-90s,
            # a 30 odpytań co 1s ryzykowało HTTP 429
            console.print(f"[yellow]⏳ Oczekiwanie na obudzenie pojazdu (max ~90s)...[/yellow]")
            waited = 0
            for delay in (2, 2, 3, 5, 5, 8, 10, 10, 15, 15, 15):
                time.sleep(delay)
                waited += delay
                fresh_state = self._refresh_vehicle_state()
                if fresh_state == 'online':
                    console.print(f"[green]✅ Pojazd obudzony po ~{waited}s[/green]")
                    return True
                if fresh_state is None:
                    # Błąd odczytu listy pojazdów — nie decyduj na stale cache, próbuj dalej
                    console.print(f"[yellow]⚠️ Błąd odczytu stanu (po {waited}s) - ponawiam[/yellow]")

            console.print(f"[red]⏰ Timeout wake_up - pojazd nie odpowiedział w ~{waited}s[/red]")
            return False
            
        except Exception as e:
            console.print(f"[red]Błąd podczas budzenia pojazdu: {e}[/red]")
            return False
    
    def _refresh_vehicle_state(self) -> Optional[str]:
        """
        Świeży odczyt stanu wybranego pojazdu z listy pojazdów.
        Aktualizuje current_vehicle przy trafieniu.

        Returns:
            str: stan pojazdu ('online'/'asleep'/'offline'...)
            None: błąd odczytu — NIE oznacza offline; wołający nie może
                  podejmować decyzji na podstawie starego cache
        """
        try:
            vehicles = self.fleet_api.get_vehicles()
            if not vehicles:
                return None
            for vehicle in vehicles:
                if vehicle.get('vin') == self.current_vehicle.get('vin'):
                    self.current_vehicle = vehicle
                    return vehicle.get('state')
            return None
        except Exception:
            return None

    def get_all_vehicles(self) -> List[Dict]:
        """
        Zwraca listę wszystkich pojazdów (kompatybilność z Worker Service)
        
        Returns:
            List[Dict]: Lista pojazdów
        """
        return self.vehicles if hasattr(self, 'vehicles') and self.vehicles else []
    
    def get_vehicle_status(self, vin: str = None) -> Optional[Dict[str, Any]]:
        """
        Pobiera podstawowe parametry pojazdu używając Fleet API z obsługą błędów autoryzacji
        BEZ BUDZENIA pojazdu gdy jest offline - sprawdza tylko stan taki jaki jest
        Gdy pojazd jest ONLINE - może "dotknąć" budzenia i pobrać pełne dane
        
        Returns:
            Dict zawierający status pojazdu
        """
        if not self.current_vehicle:
            console.print("[red]❌ Nie wybrano pojazdu.[/red]")
            return {}
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]❌ Nie można pobrać ID pojazdu.[/red]")
            return {}
        
        try:
            # ŚWIEŻY stan zamiast migawki z connect() — cache mógł się zdezaktualizować
            # (auto zasnęło/obudziło się od ostatniego odczytu), a decyzje online/offline
            # na stale cache pomijały wpięcie kabla albo raportowały fałszywy offline
            fresh_state = self._refresh_vehicle_state()
            vehicle_state = fresh_state if fresh_state is not None else self.current_vehicle.get('state', 'offline')

            if vehicle_state != 'online':
                # Pojazd offline/asleep - zwróć podstawowe informacje BEZ BUDZENIA.
                # UWAGA: wcześniejsze "dotknięcie budzenia" przy cache=online budziło
                # śpiący pojazd przy każdym odczycie statusu (vampire drain) — usunięte.
                return {
                    'vehicle_state': vehicle_state,
                    'display_name': self.current_vehicle.get('display_name', 'Nieznany'),
                    'vin': self.current_vehicle.get('vin', 'Nieznany'),
                    'online': False,
                    'timestamp': int(time.time() * 1000)
                }

            # Pojazd jest ONLINE - pobierz pełne dane pojazdu (bez komendy wake)
            
            # Pobierz standardowe dane pojazdu
            vehicle_data = self.fleet_api.get_vehicle_data(vehicle_id)
            
            # Pobierz dane lokalizacji (wymagają specjalnego parametru location_data)
            location_data = self.fleet_api.get_vehicle_data(vehicle_id, "location_data")
            
            # Użyj danych lokalizacji jeśli dostępne
            if location_data.get('drive_state', {}).get('latitude') is not None:
                # Połącz dane - użyj drive_state z location_data dla GPS
                vehicle_data['drive_state'] = location_data.get('drive_state', {})
            else:
                pass  # Brak danych GPS z API
            
            if not vehicle_data:
                console.print("[red]Nie udało się pobrać danych pojazdu.[/red]")
                return {}
            
            # Wyciągnięcie wszystkich potrzebnych informacji
            charge_state = vehicle_data.get('charge_state', {})
            drive_state = vehicle_data.get('drive_state', {})
            vehicle_state_data = vehicle_data.get('vehicle_state', {})
            
            # Sprawdź czy pojazd jest poprawnie wpięty do ładowania
            charging_state = charge_state.get('charging_state', 'Unknown')
            charge_port_latch = charge_state.get('charge_port_latch', 'Unknown')
            conn_charge_cable = charge_state.get('conn_charge_cable', 'Unknown')
            charge_port_door_open = charge_state.get('charge_port_door_open', False)
            
            # Określ czy jest gotowy do ładowania (POPRAWIONA LOGIKA)
            # Pojazd jest gotowy do ładowania TYLKO gdy:
            # 1. Jest faktycznie w trakcie ładowania (Charging) LUB
            # 2. Ładowanie zostało zakończone (Complete) LUB  
            # 3. Kabel jest prawidłowo podłączony (nie <invalid>)
            is_charging_ready = (
                charging_state in ['Charging', 'Complete'] or
                conn_charge_cable not in ['Unknown', None, '', '<invalid>']
            )
            
            # Określ lokalizację (HOME vs OUTSIDE)
            location_status = self._determine_location_status(drive_state)
            
            status = {
                'vehicle_state': vehicle_state,
                'online': True,
                'display_name': self.current_vehicle.get('display_name', 'Nieznany'),
                'vin': self.current_vehicle.get('vin', 'Nieznany'),
                
                # Status ładowania - pełne informacje
                'battery_level': charge_state.get('battery_level', 0),
                'battery_range': charge_state.get('battery_range', 0),
                'charging_state': charging_state,
                'charge_limit_soc': charge_state.get('charge_limit_soc', 0),
                'charge_current_request': charge_state.get('charge_current_request', 0),
                'charge_current_request_max': charge_state.get('charge_current_request_max', 0),
                'charge_port_latch': charge_port_latch,
                'conn_charge_cable': conn_charge_cable,
                'charge_port_door_open': charge_port_door_open,
                'is_charging_ready': is_charging_ready,
                'scheduled_charging_pending': charge_state.get('scheduled_charging_pending', False),
                'scheduled_charging_start_time': charge_state.get('scheduled_charging_start_time'),
                
                # Lokalizacja - HOME vs OUTSIDE
                'location_status': location_status,
                'latitude': drive_state.get('latitude'),
                'longitude': drive_state.get('longitude'),
                
                # Dodatkowe informacje o pojeździe (gdy online)
                'odometer': vehicle_state_data.get('odometer', 0),
                'locked': vehicle_state_data.get('locked', False),
                'sentry_mode': vehicle_state_data.get('sentry_mode', False),
                
                'timestamp': vehicle_data.get('timestamp', int(time.time() * 1000))
            }
            
            return status
            
        except Exception as e:
            console.print(f"[red]Błąd podczas pobierania statusu pojazdu: {e}[/red]")
            return {}

    def _determine_location_status(self, drive_state: Dict[str, Any]) -> str:
        """
        Określa czy pojazd znajduje się w domu (HOME) czy na zewnątrz (OUTSIDE)
        
        Args:
            drive_state: Dane o lokalizacji pojazdu
            
        Returns:
            str: 'HOME', 'OUTSIDE' lub 'UNKNOWN'
        """
        current_lat = drive_state.get('latitude')
        current_lon = drive_state.get('longitude')

        if not current_lat or not current_lon:
            # Brak danych GPS. Założenie "brak GPS = HOME" pozwalało zarządzać
            # harmonogramami auta wpiętego np. na publicznej ładowarce.
            # SHADOW MODE: domyślnie stare zachowanie z głośnym logiem;
            # LOCATION_UNKNOWN_ON_MISSING_GPS=true włącza UNKNOWN (warunek A
            # wymaga wtedy potwierdzonego HOME).
            if os.getenv('LOCATION_UNKNOWN_ON_MISSING_GPS', 'false').lower() == 'true':
                console.print("[yellow]📍 Brak GPS → UNKNOWN (enforce)[/yellow]")
                return 'UNKNOWN'
            console.print("[yellow]👻 [SHADOW] Brak GPS — zakładam HOME (docelowo UNKNOWN; "
                          "włącz LOCATION_UNKNOWN_ON_MISSING_GPS=true po weryfikacji)[/yellow]")
            return 'HOME'

        # Użyj promienia z Secret Manager lub zmiennej środowiskowej
        home_radius = self.home_radius

        # Oblicz odległość od punktu HOME
        home_lat = self.default_latitude
        home_lon = self.default_longitude

        # Odległość w stopniach z korektą cos(szerokości): bez niej strefa "dom"
        # była elipsą (na 52°N stopień długości ≈ 0.62 stopnia szerokości)
        import math
        lat_diff = abs(current_lat - home_lat)
        lon_diff = abs(current_lon - home_lon) * math.cos(math.radians(home_lat))
        distance = (lat_diff ** 2 + lon_diff ** 2) ** 0.5

        if distance <= home_radius:
            return 'HOME'
        else:
            return 'OUTSIDE'
    
    def display_vehicle_status(self) -> None:
        """Wyświetla status pojazdu w czytelnej formie"""
        status = self.get_vehicle_status()
        
        if not status:
            return
        
        # Sprawdź czy pojazd jest online
        if not status.get('online', False):
            # Pojazd offline - wyświetl podstawowe informacje
            offline_info = f"""
[bold]Nazwa pojazdu:[/bold] {status.get('display_name', 'Nieznany')}
[bold]VIN:[/bold] {status.get('vin', 'Nieznany')}
[bold]Stan pojazdu:[/bold] {status.get('vehicle_state', 'Nieznany').upper()}
[red]Pojazd jest offline - brak szczegółowych danych[/red]
"""
            console.print(Panel(offline_info, title="🚗 Status pojazdu (OFFLINE)", border_style="red"))
            
            # Timestamp
            timestamp = datetime.fromtimestamp(status['timestamp'] / 1000)
            console.print(f"[dim]Ostatnia aktualizacja: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            return
        
        # Pojazd online - wyświetl szczegółowe informacje
        # Panel z podstawowymi informacjami pojazdu
        basic_info = f"""
[bold]Nazwa pojazdu:[/bold] {status.get('display_name', 'Nieznany')}
[bold]VIN:[/bold] {status.get('vin', 'Nieznany')}
[bold]Stan pojazdu:[/bold] {status.get('vehicle_state', 'Nieznany').upper()}
"""
        console.print(Panel(basic_info, title="🚗 Informacje o pojeździe", border_style="blue"))
        
        # Panel z informacjami o ładowaniu
        charging_info = f"""
[bold]Poziom baterii:[/bold] {status['battery_level']}%
[bold]Status ładowania:[/bold] {status['charging_state']}
[bold]Limit ładowania:[/bold] {status['charge_limit_soc']}%
[bold]Prąd ładowania:[/bold] {status['charge_current_request']}A (max: {status['charge_current_request_max']}A)
[bold]Port ładowania:[/bold] {status.get('charge_port_latch', 'Unknown')}
[bold]Kabel podłączony:[/bold] {status.get('conn_charge_cable', 'Unknown')}
[bold]Drzwiczki portu:[/bold] {'🔓 Otwarte' if status.get('charge_port_door_open', False) else '🔒 Zamknięte'}
[bold]Gotowy do ładowania:[/bold] {'✅ TAK' if status.get('is_charging_ready', False) else '❌ NIE'}"""

        # Dodaj informację o zasięgu jeśli dostępna
        if status.get('battery_range'):
            charging_info += f"\n[bold]Zasięg:[/bold] {status['battery_range']:.1f} km"
        
        charging_info += "\n"
        
        # Kolor panelu zależny od statusu ładowania  
        if status.get('is_charging_ready', False):
            charging_border_color = "green"
        else:
            charging_border_color = "yellow"
            
        console.print(Panel(charging_info, title="🔋 Status ładowania", border_style=charging_border_color))
        
        # Panel z dodatkowymi informacjami o pojeździe (tylko gdy online)
        if status.get('odometer') or status.get('locked') is not None or status.get('sentry_mode') is not None:
            vehicle_details = f"""
[bold]Przebieg:[/bold] {status.get('odometer', 0):.1f} km
[bold]Zamknięty:[/bold] {'🔒 TAK' if status.get('locked', False) else '🔓 NIE'}
[bold]Tryb Sentry:[/bold] {'👁️ WŁĄCZONY' if status.get('sentry_mode', False) else '😴 WYŁĄCZONY'}
"""
            console.print(Panel(vehicle_details, title="🚗 Szczegóły pojazdu", border_style="blue"))
        
        # Panel z lokalizacją
        location_status = status.get('location_status', 'UNKNOWN')
        
        # Bezpieczne formatowanie współrzędnych
        lat = status.get('latitude')
        lon = status.get('longitude')
        if lat is not None and lon is not None:
            coordinates_text = f"{lat:.6f}, {lon:.6f}"
        else:
            coordinates_text = "Brak danych"
            
        location_info = f"""
[bold]Lokalizacja:[/bold] {location_status}
[bold]Współrzędne:[/bold] {coordinates_text}
"""
        
        # Kolor panelu zależny od lokalizacji
        if location_status == 'HOME':
            location_border_color = "green"
            location_icon = "🏠"
        elif location_status == 'OUTSIDE':
            location_border_color = "yellow"
            location_icon = "🌍"
        else:
            location_border_color = "red"
            location_icon = "❓"
            
        console.print(Panel(location_info, title=f"{location_icon} Lokalizacja", border_style=location_border_color))
        
        # Panel z harmonogramem ładowania (jeśli dostępny)
        if status.get('scheduled_charging_pending'):
            if status.get('scheduled_charging_start_time'):
                scheduled_time = datetime.fromtimestamp(status['scheduled_charging_start_time'])
                schedule_info = f"[bold]Zaplanowane ładowanie:[/bold] ⏰ {scheduled_time.strftime('%Y-%m-%d %H:%M')}"
            else:
                schedule_info = "[bold]Zaplanowane ładowanie:[/bold] ⏰ AKTYWNE (brak czasu)"
            console.print(Panel(schedule_info, title="⏰ Harmonogram ładowania", border_style="yellow"))
        elif 'scheduled_charging_pending' in status:
            # Tylko pokaż panel jeśli dane są dostępne (pojazd online)
            schedule_info = "[bold]Zaplanowane ładowanie:[/bold] ❌ NIEAKTYWNE"
            console.print(Panel(schedule_info, title="⏰ Harmonogram ładowania", border_style="cyan"))
        
        # Timestamp
        timestamp = datetime.fromtimestamp(status['timestamp'] / 1000)
        console.print(f"[dim]Ostatnia aktualizacja: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
        
        # Podsumowanie statusu
        summary = []
        if status.get('online'):
            summary.append("[green]✅ ONLINE[/green]")
        else:
            summary.append("[red]❌ OFFLINE[/red]")
            
        if status.get('is_charging_ready'):
            summary.append("[green]✅ GOTOWY DO ŁADOWANIA[/green]")
        else:
            summary.append("[yellow]⚠️ NIE GOTOWY DO ŁADOWANIA[/yellow]")
            
        if location_status == 'HOME':
            summary.append("[green]✅ W DOMU[/green]")
        elif location_status == 'OUTSIDE':
            summary.append("[blue]ℹ️ POZA DOMEM[/blue]")
        else:
            summary.append("[red]❓ LOKALIZACJA NIEZNANA[/red]")
            
        console.print(f"\n[bold]Podsumowanie:[/bold] {' | '.join(summary)}")
    
    def set_charge_limit(self, limit: int, use_proxy: bool = False) -> bool:
        """
        Ustawia limit ładowania baterii używając Fleet API
        
        Args:
            limit: Limit ładowania w procentach (50-100)
            use_proxy: Czy wymusić użycie Tesla HTTP Proxy (wymagane dla podpisanych komend)
            
        Returns:
            bool: True jeśli komenda została wykonana pomyślnie
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        if not 50 <= limit <= 100:
            console.print("[red]Limit ładowania musi być między 50% a 100%.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać ID pojazdu.[/red]")
            return False
        
        try:
            if not self.wake_up_vehicle(use_proxy=use_proxy):
                return False
            
            console.print(f"[yellow]Ustawianie limitu ładowania na {limit}%{'przez Tesla HTTP Proxy' if use_proxy else ''}...[/yellow]")
            result = self.fleet_api.set_charge_limit(vehicle_id, limit, use_proxy=use_proxy)
            
            if result:
                console.print(f"[green]Limit ładowania ustawiony na {limit}% ({'Tesla HTTP Proxy' if use_proxy else 'Fleet API'}).[/green]")
                return True
            else:
                console.print(f"[red]Błąd podczas ustawiania limitu ładowania.[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Błąd podczas ustawiania limitu ładowania: {e}[/red]")
            return False
    
    def set_charging_amps(self, amps: int) -> bool:
        """
        Ustawia prąd ładowania używając Fleet API
        
        Args:
            amps: Prąd ładowania w amperach
            
        Returns:
            bool: True jeśli komenda została wykonana pomyślnie
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać ID pojazdu.[/red]")
            return False
        
        try:
            # Sprawdź czy proxy jest dostępny
            use_proxy = bool(hasattr(self.fleet_api, 'proxy_url') and self.fleet_api.proxy_url)

            if not self.wake_up_vehicle(use_proxy=use_proxy):
                return False

            console.print(f"[yellow]Ustawianie prądu ładowania na {amps}A...[/yellow]")
            result = self.fleet_api.set_charging_amps(vehicle_id, amps)

            if result:
                console.print(f"[green]Prąd ładowania ustawiony na {amps}A (Fleet API).[/green]")
                return True
            else:
                console.print(f"[red]Błąd podczas ustawiania prądu ładowania.[/red]")
                return False

        except Exception as e:
            console.print(f"[red]Błąd podczas ustawiania prądu ładowania: {e}[/red]")
            return False

    def time_to_minutes(self, time_str: str) -> int:
        """
        Konwertuje czas w formacie HH:MM na minuty od północy
        
        Args:
            time_str: Czas w formacie "HH:MM"
            
        Returns:
            int: Minuty od północy
        """
        try:
            hours, minutes = map(int, time_str.split(':'))
            return hours * 60 + minutes
        except ValueError:
            raise ValueError(f"Nieprawidłowy format czasu: {time_str}. Użyj formatu HH:MM")
    
    def minutes_to_time(self, minutes: int) -> str:
        """
        Konwertuje minuty od północy na format HH:MM
        
        Args:
            minutes: Minuty od północy
            
        Returns:
            str: Czas w formacie HH:MM
        """
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"
    
    def get_vehicle_location(self) -> tuple[float, float]:
        """
        Pobiera lokalizację pojazdu lub zwraca domyślną lokalizację z .env
        
        Returns:
            tuple: (latitude, longitude)
        """
        if not self.current_vehicle:
            console.print("[yellow]Nie wybrano pojazdu - używam domyślnej lokalizacji[/yellow]")
            return self.default_latitude, self.default_longitude
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[yellow]Nie można pobrać ID pojazdu - używam domyślnej lokalizacji[/yellow]")
            return self.default_latitude, self.default_longitude
        
        try:
            # Próba pobrania obecnej lokalizacji pojazdu.
            # NAPRAWKA: GPS przychodzi TYLKO z endpoints="location_data" —
            # bez tego parametru lokalizacja zawsze spadała na domyślną z .env
            vehicle_data = self.fleet_api.get_vehicle_data(vehicle_id, endpoints="location_data")
            drive_state = vehicle_data.get('drive_state', {})
            
            current_lat = drive_state.get('latitude')
            current_lon = drive_state.get('longitude')
            
            if current_lat and current_lon and current_lat != 0.0 and current_lon != 0.0:
                console.print(f"[green]✓ Używam obecnej lokalizacji pojazdu: {current_lat:.6f}, {current_lon:.6f}[/green]")
                return current_lat, current_lon
            else:
                console.print(f"[yellow]Brak prawidłowej lokalizacji pojazdu - używam domyślnej z .env: {self.default_latitude:.6f}, {self.default_longitude:.6f}[/yellow]")
                return self.default_latitude, self.default_longitude
                
        except Exception as e:
            console.print(f"[yellow]Błąd pobierania lokalizacji pojazdu ({e}) - używam domyślnej z .env: {self.default_latitude:.6f}, {self.default_longitude:.6f}[/yellow]")
            return self.default_latitude, self.default_longitude

    def add_charge_schedule(self, schedule: ChargeSchedule, skip_wake: bool = False) -> bool:
        """
        Dodaje harmonogram ładowania używając Fleet API

        Args:
            schedule: Obiekt ChargeSchedule z parametrami harmonogramu
            skip_wake: Jeśli True, pomija wake_up (użyj gdy pojazd już obudzony)

        Returns:
            bool: True jeśli harmonogram został dodany pomyślnie
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać VIN pojazdu.[/red]")
            return False
        
        try:
            # Sprawdź czy proxy jest dostępny (używamy dla wake_up i komendy)
            use_proxy = bool(hasattr(self.fleet_api, 'proxy_url') and self.fleet_api.proxy_url)

            # Wybudź pojazd z tym samym ustawieniem proxy co komenda (chyba że skip_wake=True)
            if not skip_wake:
                if not self.wake_up_vehicle(use_proxy=use_proxy):
                    return False

            # Ustaw lokalizację jeśli nie została podana
            if schedule.lat == 0.0 and schedule.lon == 0.0:
                schedule.lat, schedule.lon = self.get_vehicle_location()
                console.print(f"[blue]Ustawiono lokalizację harmonogramu: {schedule.lat:.6f}, {schedule.lon:.6f}[/blue]")

            # Log informacyjny
            if use_proxy:
                console.print("[yellow]Dodawanie harmonogramu ładowania przez Tesla HTTP Proxy...[/yellow]")
            else:
                console.print("[yellow]Dodawanie harmonogramu ładowania przez Fleet API (brak proxy)...[/yellow]")
            
            # Wywołanie Fleet API
            result = self.fleet_api.add_charge_schedule(
                vehicle_id=vehicle_id,
                days_of_week=schedule.days_of_week,
                enabled=schedule.enabled,
                lat=schedule.lat,
                lon=schedule.lon,
                start_enabled=schedule.start_enabled,
                start_time=schedule.start_time,
                end_enabled=schedule.end_enabled,
                end_time=schedule.end_time,
                one_time=schedule.one_time,
                use_proxy=use_proxy
            )
            
            if result:
                console.print("[green]Harmonogram ładowania dodany pomyślnie.[/green]")
                return True
            else:
                console.print("[red]Błąd podczas dodawania harmonogramu.[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Błąd podczas dodawania harmonogramu: {e}[/red]")
            return False
    
    def set_scheduled_charging(self, time_str: str, enable: bool = True) -> bool:
        """
        Ustawia zaplanowane ładowanie używając Fleet API (starsza metoda)
        
        Args:
            time_str: Czas w formacie "HH:MM"
            enable: Czy włączyć zaplanowane ładowanie
            
        Returns:
            bool: True jeśli komenda została wykonana pomyślnie
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać ID pojazdu.[/red]")
            return False
        
        try:
            # Sprawdź czy proxy jest dostępny
            use_proxy = bool(hasattr(self.fleet_api, 'proxy_url') and self.fleet_api.proxy_url)

            if not self.wake_up_vehicle(use_proxy=use_proxy):
                return False

            time_minutes = self.time_to_minutes(time_str)

            console.print(f"[yellow]Ustawianie zaplanowanego ładowania na {time_str}...[/yellow]")
            result = self.fleet_api.set_scheduled_charging(vehicle_id, enable, time_minutes)
            
            if result:
                if enable:
                    console.print(f"[green]Zaplanowane ładowanie ustawione na {time_str} (Fleet API).[/green]")
                else:
                    console.print("[green]Zaplanowane ładowanie wyłączone (Fleet API).[/green]")
                return True
            else:
                console.print(f"[red]Błąd podczas ustawiania zaplanowanego ładowania.[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Błąd podczas ustawiania zaplanowanego ładowania: {e}[/red]")
            return False
    
    def get_charge_schedules(self) -> Optional[List[Dict]]:
        """
        Pobiera istniejące harmonogramy ładowania używając Fleet API

        Returns:
            List[Dict]: Lista harmonogramów ładowania ([] gdy potwierdzono brak)
            None: Błąd odczytu — nie oznacza braku harmonogramów
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return None

        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać VIN pojazdu.[/red]")
            return None

        try:
            # Sprawdź czy proxy jest dostępny
            use_proxy = bool(hasattr(self.fleet_api, 'proxy_url') and self.fleet_api.proxy_url)

            if not self.wake_up_vehicle(use_proxy=use_proxy):
                # Błąd odczytu (None), nie "brak harmonogramów" ([])
                return None

            console.print("[yellow]Pobieranie harmonogramów ładowania...[/yellow]")
            schedules = self.fleet_api.get_charge_schedules(vehicle_id)
            return schedules

        except Exception as e:
            console.print(f"[red]Błąd podczas pobierania harmonogramów: {e}[/red]")
            return None

    def days_of_week_to_string(self, days_of_week: int) -> str:
        """
        Konwertuje days_of_week z formatu bitowego na czytelny string
        
        Args:
            days_of_week: Liczba reprezentująca dni tygodnia w formacie bitowym
            
        Returns:
            str: Czytelny opis dni tygodnia
        """
        if days_of_week == 127:  # 1111111 - wszystkie dni
            return "Wszystkie dni"
        elif days_of_week == 62:  # 0111110 - dni robocze (pon-pią)
            return "Dni robocze"
        elif days_of_week == 65:  # 1000001 - weekend (sob-nie)
            return "Weekend"
        else:
            # Mapowanie bitów na dni tygodnia
            days = []
            day_names = ["Niedziela", "Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota"]
            for i in range(7):
                if days_of_week & (1 << i):
                    days.append(day_names[i])
            return ", ".join(days) if days else "Brak"

    def display_charge_schedules(self) -> None:
        """Wyświetla istniejące harmonogramy ładowania"""
        schedules = self.get_charge_schedules()
        
        if not schedules:
            console.print("[yellow]Brak harmonogramów ładowania.[/yellow]")
            return
        
        table = Table(title="Harmonogramy ładowania")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Włączony", style="green")
        table.add_column("Dni tygodnia", style="magenta")
        table.add_column("Czas rozpoczęcia", style="yellow")
        table.add_column("Czas zakończenia", style="yellow")
        table.add_column("Jednorazowy", style="blue")
        
        for schedule in schedules:
            start_time = ""
            if schedule.get('start_enabled') and schedule.get('start_time') is not None:
                start_time = self.minutes_to_time(schedule['start_time'])
            
            end_time = ""
            if schedule.get('end_enabled') and schedule.get('end_time') is not None:
                end_time = self.minutes_to_time(schedule['end_time'])
            
            # Konwertuj days_of_week z liczby na string
            days_of_week = schedule.get('days_of_week', 0)
            if isinstance(days_of_week, int):
                days_str = self.days_of_week_to_string(days_of_week)
            else:
                days_str = str(days_of_week)
            
            table.add_row(
                str(schedule.get('id', 'N/A')),
                "Tak" if schedule.get('enabled') else "Nie",
                days_str,
                start_time,
                end_time,
                "Tak" if schedule.get('one_time') else "Nie"
            )
        
        console.print(table)

    def remove_charge_schedule(self, schedule_id: int, skip_wake: bool = False) -> bool:
        """
        Usuwa harmonogram ładowania używając Fleet API

        Args:
            schedule_id: ID harmonogramu ładowania
            skip_wake: Jeśli True, pomija wake_up (użyj gdy pojazd już obudzony)

        Returns:
            bool: True jeśli harmonogram został usunięty pomyślnie
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać VIN pojazdu.[/red]")
            return False
        
        try:
            # Komenda wymaga proxy - użyj go też dla wake_up (chyba że skip_wake=True)
            if not skip_wake:
                if not self.wake_up_vehicle(use_proxy=True):
                    return False

            # WAŻNE: Komendy modyfikujące harmonogram wymagają użycia proxy
            console.print(f"[yellow]Usuwanie harmonogramu ładowania (ID: {schedule_id}) przez Tesla HTTP Proxy...[/yellow]")
            result = self.fleet_api.remove_charge_schedule(vehicle_id, schedule_id, use_proxy=True)
            
            if result:
                console.print("[green]Harmonogram ładowania usunięty pomyślnie.[/green]")
                return True
            else:
                console.print("[red]Błąd podczas usuwania harmonogramu.[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Błąd podczas usuwania harmonogramu: {e}[/red]")
            return False

    def remove_all_charge_schedules(self) -> bool:
        """
        Usuwa wszystkie harmonogramy ładowania używając Fleet API
        
        Returns:
            bool: True jeśli wszystkie harmonogramy zostały usunięte pomyślnie
        """
        if not self.current_vehicle:
            console.print("[red]Nie wybrano pojazdu.[/red]")
            return False
        
        vehicle_id = self.current_vehicle.get('vin') or self.current_vehicle.get('id_s')
        if not vehicle_id:
            console.print("[red]Nie można pobrać VIN pojazdu.[/red]")
            return False
        
        try:
            # Komenda wymaga proxy - użyj go też dla wake_up
            if not self.wake_up_vehicle(use_proxy=True):
                return False

            # WAŻNE: Komendy modyfikujące harmonogram wymagają użycia proxy
            console.print("[yellow]Usuwanie wszystkich harmonogramów ładowania przez Tesla HTTP Proxy...[/yellow]")
            result = self.fleet_api.remove_all_charge_schedules(vehicle_id, use_proxy=True)
            
            if result:
                console.print("[green]Wszystkie harmonogramy ładowania usunięte pomyślnie.[/green]")
                return True
            else:
                console.print("[red]Błąd podczas usuwania wszystkich harmonogramów.[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Błąd podczas usuwania wszystkich harmonogramów: {e}[/red]")
            return False

    def get_quick_status(self) -> str:
        """
        Pobiera szybkie podsumowanie statusu pojazdu bez budzenia
        
        Returns:
            str: Krótkie podsumowanie statusu w formacie: "STATUS | BATTERY | CHARGING | LOCATION"
        """
        status = self.get_vehicle_status()
        
        if not status:
            return "ERROR: Nie można pobrać statusu pojazdu"
        
        # Sprawdź czy pojazd jest online
        if not status.get('online', False):
            vehicle_state = status.get('vehicle_state', 'UNKNOWN').upper()
            return f"OFFLINE ({vehicle_state}) | Brak danych | Brak danych | Brak danych"
        
        # Pojazd online - przygotuj podsumowanie
        battery_level = status.get('battery_level', 0)
        charging_state = status.get('charging_state', 'Unknown')
        is_charging_ready = status.get('is_charging_ready', False)
        location_status = status.get('location_status', 'UNKNOWN')
        
        # Format: STATUS | BATTERY | CHARGING | LOCATION
        charging_ready_text = "READY" if is_charging_ready else "NOT_READY"
        
        return f"ONLINE | {battery_level}% | {charging_state} ({charging_ready_text}) | {location_status}"


if __name__ == "__main__":
    # Przykład użycia
    controller = TeslaController()
    
    if controller.connect():
        controller.list_vehicles()
        controller.display_vehicle_status() 