#!/usr/bin/env python3
"""
Tesla Scout Function - Lekka funkcja sprawdzająca tylko lokalizację pojazdu
Część architektury "Scout & Worker" dla agresywnej optymalizacji kosztów

ZADANIE:
- Sprawdza co 15 minut czy pojazd wrócił do domu
- Koszt wykonania: setne części grosza
- Jeśli wykryje powrót do domu -> wywołuje Worker (Cloud Run)
- Przechowuje stan w Firestore dla minimalnego kosztu

ARCHITEKTURA (POPRAWIONA):
Scout Function (tania, częsta) -> Worker Service (droga, rzadka)

NOWA ARCHITEKTURA TOKENÓW (v2):
❌ PROBLEM: Scout i Worker miały niezależne systemy zarządzania tokenami Tesla
✅ ROZWIĄZANIE: Worker centralnie zarządza tokenami, Scout pobiera tokeny z Worker

KORZYŚCI:
- Brak konfliktów refresh tokenów między Scout i Worker
- Stabilne zarządzanie tokenami 24h przez Worker
- Scout tylko pobiera gotowe tokeny z Worker via /get-token
- Jednolita architektura zgodna z dokumentacją Tesla API
"""

import json
import os
import logging
import requests
import pytz
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from google.cloud import firestore
from google.cloud import secretmanager
import functions_framework
import time

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _log_scout_status(status_data: Dict[str, Any], action: str = "check") -> None:
    """
    Loguje szczegółowy status Scout w formacie: [HH:MM] 🔍 SCOUT - akcja - dane
    
    Args:
        status_data: Dane o stanie pojazdu 
        action: Opis akcji (np. "check", "location_change")
    """
    try:
        print(f"🔧 [DEBUG] _log_scout_status wywołane z action='{action}', vehicle_state='{status_data.get('state', 'unknown')}'")
        
        # Czas warszawski w formacie [HH:MM]
        from datetime import datetime
        import pytz
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        now = datetime.now(warsaw_tz)
        time_str = now.strftime("[%H:%M]")
        
        # Podstawowe dane
        vin = status_data.get('vin', 'Unknown')
        vin_short = vin[-4:] if len(vin) > 4 else vin
        vehicle_state = status_data.get('state', 'unknown')
        
        if vehicle_state == 'online':
            # Pojazd online - szczegółowe informacje
            battery = status_data.get('battery_level', 0)
            charging = status_data.get('charging_state', 'Unknown')
            lat = status_data.get('latitude')
            lon = status_data.get('longitude')
            
            # Określ lokalizację
            if lat and lon:
                at_home = is_at_home(lat, lon)
                location = "HOME" if at_home else "OUTSIDE"
            else:
                location = "UNKNOWN"
            
            log_msg = f"{time_str} 🔍 SCOUT {action} - VIN={vin_short}, state={vehicle_state}, bateria={battery}%, ładowanie={charging}, lokalizacja={location}"
        else:
            # Pojazd offline/asleep - podstawowe informacje
            log_msg = f"{time_str} 🔍 SCOUT {action} - VIN={vin_short}, state={vehicle_state}, brak aktualnych danych"
        
        logger.info(log_msg)
        
        # DODATKOWO: print() dla pewności że logi będą widoczne w Cloud Functions
        print(log_msg)
        
    except Exception as e:
        logger.error(f"Błąd logowania Scout status: {e}")

# Konfiguracja
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GCP_PROJECT') or 'off-peak-tesla-controller'

# Fallback ze zmiennych środowiskowych 
HOME_LATITUDE_FALLBACK = float(os.environ.get('HOME_LATITUDE', '52.334215'))
HOME_LONGITUDE_FALLBACK = float(os.environ.get('HOME_LONGITUDE', '20.937516'))
HOME_RADIUS_FALLBACK = float(os.environ.get('HOME_RADIUS', '0.03'))

# Globalne zmienne dla współrzędnych domu (pobierane z Secret Manager przy inicjalizacji)
HOME_LATITUDE = None
HOME_LONGITUDE = None
HOME_RADIUS = None

WORKER_SERVICE_URL = os.environ.get('WORKER_SERVICE_URL')

# Globalne zmienne dla cachowania
_cached_secrets = {}
_cached_access_token = None
_token_expires_at = None

def get_secret(secret_name: str) -> Optional[str]:
    """Pobiera sekret z Google Secret Manager z cachowaniem"""
    global _cached_secrets
    
    # Sprawdź cache
    if secret_name in _cached_secrets:
        return _cached_secrets[secret_name]
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret = response.payload.data.decode("UTF-8")
        
        # Cache sekret
        _cached_secrets[secret_name] = secret
        return secret
    except Exception as e:
        logger.error(f"❌ Błąd pobierania sekretu {secret_name}: {e}")
        return None

def get_token_from_worker() -> Optional[str]:
    """
    NOWA ARCHITEKTURA: Pobiera token Tesla API z Worker Service (centralne zarządzanie tokenami)
    
    Rozwiązuje problem konfliktów między Scout i Worker przy refresh tokenów.
    Worker centralnie zarządza tokenami Tesla API (24h ważność).
    """
    global _cached_access_token, _token_expires_at
    
    # Sprawdź czy mamy ważny cached token
    if _cached_access_token and _token_expires_at:
        now = datetime.now(timezone.utc)
        if now < _token_expires_at:
            logger.info("🔄 [SCOUT] Używam cached token Tesla z Worker")
            return _cached_access_token
    
    try:
        if not WORKER_SERVICE_URL:
            logger.error("❌ [SCOUT] WORKER_SERVICE_URL nie jest skonfigurowany")
            logger.error("💡 Scout wymaga URL do Worker Service dla tokenów Tesla")
            return None
        
        # Pobierz token z Worker Service
        token_url = f"{WORKER_SERVICE_URL.rstrip('/')}/get-token"
        logger.info(f"📡 [SCOUT] Pobieram token Tesla z Worker: {token_url}")
        
        response = requests.get(token_url, timeout=30)
        
        if response.status_code == 200:
            token_data = response.json()
            
            if token_data.get('status') == 'success':
                _cached_access_token = token_data.get('access_token')
                
                # Ustaw czas wygaśnięcia na podstawie informacji z Worker
                remaining_minutes = token_data.get('remaining_minutes')
                if remaining_minutes and remaining_minutes > 0:
                    # Dodaj 5% marginesu bezpieczeństwa
                    safe_minutes = int(remaining_minutes * 0.95)
                    _token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=safe_minutes)
                    logger.info(f"✅ [SCOUT] Token Tesla otrzymany z Worker (ważny przez {safe_minutes} min)")
                else:
                    # Fallback - załóż 30 minut ważności
                    _token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
                    logger.warning("⚠️ [SCOUT] Brak informacji o czasie wygaśnięcia - używam 30min fallback")
                
                logger.info(f"🏗️ [SCOUT] Centralne zarządzanie tokenami przez Worker (architektura poprawiona)")
                return _cached_access_token
            else:
                error_msg = token_data.get('error', 'Unknown error')
                logger.error(f"❌ [SCOUT] Worker nie może udostępnić tokenu: {error_msg}")
                return None
                
        elif response.status_code == 500:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', 'Internal server error')
                logger.error(f"❌ [SCOUT] Worker ma problem z tokenami Tesla: {error_msg}")
            except:
                logger.error(f"❌ [SCOUT] Worker ma problem z tokenami Tesla (HTTP 500)")
        else:
            logger.error(f"❌ [SCOUT] Błąd HTTP {response.status_code} z Worker Service")
            
    except requests.exceptions.Timeout:
        logger.error("❌ [SCOUT] Timeout podczas pobierania tokenu z Worker")
    except requests.exceptions.ConnectionError:
        logger.error("❌ [SCOUT] Nie można połączyć się z Worker Service")
        logger.error(f"💡 Sprawdź czy Worker działa na: {WORKER_SERVICE_URL}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ [SCOUT] Błąd sieci podczas pobierania tokenu z Worker: {e}")
    except Exception as e:
        logger.error(f"❌ [SCOUT] Nieoczekiwany błąd podczas pobierania tokenu z Worker: {e}")
    
    # Wyczyść cache w przypadku błędu
    _cached_access_token = None
    _token_expires_at = None
    return None


def get_tesla_access_token_fallback() -> Optional[str]:
    """
    FALLBACK: Stary system tokenów - używany tylko gdy Worker Service jest niedostępny
    
    To jest fallback mechanism na wypadek problemów z Worker Service.
    Normalnie Scout powinien używać get_token_from_worker().
    """
    global _cached_access_token, _token_expires_at
    
    logger.warning("⚠️ [SCOUT FALLBACK] Używam fallback mechanizmu tokenów - Worker niedostępny")
    
    # Sprawdź czy token jest ważny
    if _cached_access_token and _token_expires_at:
        now = datetime.now(timezone.utc)
        if now < _token_expires_at:
            return _cached_access_token
    
    try:
        client_id = get_secret('tesla-client-id')
        client_secret = get_secret('tesla-client-secret')
        refresh_token = get_secret('tesla-refresh-token')
        
        if not all([client_id, client_secret, refresh_token]):
            logger.error("❌ [SCOUT FALLBACK] Brak wymaganych sekretów Tesla")
            return None
        
        # Odśwież token bezpośrednio (fallback)
        # NAPRAWKA: Używaj nowego URL Tesla Fleet API zgodnie z dokumentacją
        url = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "audience": "https://fleet-api.prd.eu.vn.cloud.tesla.com"  # NAPRAWKA: audience dla regionu Europa
        }
        
        logger.warning("🔄 [SCOUT FALLBACK] Próba bezpośredniego odświeżenia tokenu Tesla")
        response = requests.post(url, data=data, timeout=30)
        
        if response.status_code == 200:
            token_data = response.json()
            _cached_access_token = token_data['access_token']
            
            # Ustaw krótszy czas wygaśnięcia (fallback jest mniej stabilny)
            expires_in = token_data.get('expires_in', 900)  # Domyślnie 15 min
            safe_seconds = int(expires_in * 0.8)  # 20% marginesu bezpieczeństwa
            _token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=safe_seconds)
            
            logger.warning(f"✅ [SCOUT FALLBACK] Token otrzymany bezpośrednio (ważny przez {safe_seconds//60} min)")
            logger.warning("💡 [SCOUT FALLBACK] Sprawdź dlaczego Worker Service jest niedostępny")
            
            return _cached_access_token
        else:
            logger.error(f"❌ [SCOUT FALLBACK] Błąd odświeżania tokenu: {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ [SCOUT FALLBACK] Błąd fallback mechanizmu: {e}")
    
    # Wyczyść cache w przypadku błędu
    _cached_access_token = None
    _token_expires_at = None
    return None


def get_tesla_access_token_smart() -> Optional[str]:
    """
    SMART WRAPPER: Próbuje Worker Service, fallback na bezpośredni dostęp
    
    1. Próbuje pobrać token z Worker Service (preferowane)
    2. Jeśli Worker niedostępny -> fallback na bezpośredni dostęp
    3. Loguje wybraną strategię dla debugowania
    """
    
    # KROK 1: Próbuj Worker Service (preferowane)
    logger.info("🔄 [SCOUT] Próbuje centralne zarządzanie tokenami przez Worker")
    token = get_token_from_worker()
    
    if token:
        logger.info("✅ [SCOUT] Używam tokens z Worker Service (architektura docelowa)")
        return token
    
    # KROK 2: Fallback na bezpośredni dostęp
    logger.warning("⚠️ [SCOUT] Worker Service niedostępny - przechodzę na fallback")
    logger.warning("💡 [SCOUT] To może wskazywać na problem z Worker Service")
    
    token = get_tesla_access_token_fallback()
    
    if token:
        logger.warning("✅ [SCOUT] Używam fallback tokens (tymczasowo)")
        return token
    else:
        logger.error("❌ [SCOUT] Zarówno Worker jak i fallback nie działają")
        return None

def get_vehicle_location(access_token: str) -> Optional[Dict[str, Any]]:
    """Pobiera lokalizację pojazdu z Tesla API zgodnie z best practices"""
    try:
        # KROK 1: Pobierz listę pojazdów (nie budzi pojazdu)
        headers = {"Authorization": f"Bearer {access_token}"}
        vehicles_response = requests.get(
            "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles",
            headers=headers,
            timeout=30
        )
        
        if vehicles_response.status_code != 200:
            logger.error(f"❌ Błąd pobierania listy pojazdów: {vehicles_response.status_code}")
            return None
        
        vehicles = vehicles_response.json().get('response', [])
        if not vehicles:
            logger.error("❌ Brak pojazdów na koncie")
            return None
        
        vehicle = vehicles[0]  # Pierwszy pojazd
        vehicle_id = vehicle['id']
        vin = vehicle['vin']
        vehicle_state = vehicle.get('state', 'unknown')
        
        logger.info(f"🔍 Stan pojazdu {vin[-4:]}: {vehicle_state}")
        
        # KROK 2: Sprawdź stan pojazdu PRZED próbą pobrania danych
        if vehicle_state == 'online':
            # Pojazd online - pobierz pełne dane (lokalizacja + bateria + szczegółowe dane ładowania)
            logger.info("✅ Pojazd online - pobieram dane z location_data endpoint")
            
            # FIX: Użyj poprawnego formatu endpoints dla Tesla Fleet API
            # Zgodnie z testami: endpoints=location_data działa, kombinacje nie
            location_response = requests.get(
                f"https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles/{vehicle_id}/vehicle_data?endpoints=location_data",
                headers=headers,
                timeout=30
            )
            
            if location_response.status_code != 200:
                logger.error(f"❌ Błąd pobierania danych pojazdu: {location_response.status_code}")
                return None
            
            data = location_response.json().get('response', {})

            # Pobierz dane lokalizacji z drive_state (po użyciu location_data endpoint)
            location_info = data.get('drive_state', {})
            
            # Osobne zapytanie dla charge_state jeśli potrzebne
            if not location_info or 'latitude' not in location_info or 'longitude' not in location_info:
                logger.error("❌ Brak danych lokalizacyjnych pomimo użycia location_data endpoint")
                return None
            
            # NOWE: Pobierz szczegółowe dane ładowania dla obliczenia is_charging_ready
            charge_response = requests.get(
                f"https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles/{vehicle_id}/vehicle_data?endpoints=charge_state",
                headers=headers,
                timeout=30
            )
            
            charge_state = {}
            detailed_charge_data = {}
            if charge_response.status_code == 200:
                charge_data = charge_response.json().get('response', {})
                charge_state = charge_data.get('charge_state', {})
                # Wyciągnij szczegółowe dane ładowania potrzebne do is_charging_ready
                detailed_charge_data = {
                    'conn_charge_cable': charge_state.get('conn_charge_cable', 'Unknown'),
                    'charge_port_latch': charge_state.get('charge_port_latch', 'Unknown'),
                    'charge_port_door_open': charge_state.get('charge_port_door_open', False),
                    'charging_state': charge_state.get('charging_state', 'Unknown')
                }
            
            # Wyciągnij poziom baterii i stan ładowania
            battery_level = charge_state.get('battery_level', 0)
            charging_state = charge_state.get('charging_state', 'Unknown')
            
            # NOWE: Oblicz is_charging_ready zgodnie z logiką z TeslaController
            conn_charge_cable = detailed_charge_data.get('conn_charge_cable', 'Unknown')
            is_charging_ready = (
                charging_state in ['Charging', 'Complete'] or
                conn_charge_cable not in ['Unknown', None, '', '<invalid>']
            )
            
            logger.info(f"🔌 [SCOUT] Szczegóły ładowania: charging_state={charging_state}, conn_charge_cable={conn_charge_cable}, is_charging_ready={is_charging_ready}")
            
            return {
                'vehicle_id': vehicle_id,
                'vin': vin,
                'state': vehicle_state,
                'latitude': location_info.get('latitude'),
                'longitude': location_info.get('longitude'),
                'battery_level': battery_level,
                'charging_state': charging_state,
                'is_charging_ready': is_charging_ready,  # NOWE: Dodane pole
                'detailed_charge_data': detailed_charge_data,  # NOWE: Szczegółowe dane
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        elif vehicle_state == 'asleep':
            # Pojazd śpi - zwróć ostatnią znaną lokalizację lub błąd
            logger.warning(f"⚠️ Pojazd {vin[-4:]} śpi - brak dostępu do aktualnej lokalizacji")
            logger.info("💡 Scout nie budzi pojazdu - to zadanie Worker Service")
            
            # Zwróć podstawowe informacje bez lokalizacji
            return {
                'vehicle_id': vehicle_id,
                'vin': vin,
                'state': vehicle_state,
                'latitude': None,
                'longitude': None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': 'vehicle_asleep'
            }
            
        elif vehicle_state == 'offline':
            # Pojazd offline - brak połączenia
            logger.warning(f"⚠️ Pojazd {vin[-4:]} offline - brak połączenia")
            
            return {
                'vehicle_id': vehicle_id,
                'vin': vin,
                'state': vehicle_state,
                'latitude': None,
                'longitude': None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': 'vehicle_offline'
            }
            
        else:
            # Nieznany stan pojazdu
            logger.error(f"❌ Nieznany stan pojazdu: {vehicle_state}")
            return None
        
    except Exception as e:
        logger.error(f"❌ Błąd pobierania lokalizacji pojazdu: {e}")
        return None

def get_home_coordinates():
    """Pobiera współrzędne domu z Secret Manager z cachowaniem"""
    try:
        latitude = get_secret('home-latitude')
        longitude = get_secret('home-longitude') 
        radius = get_secret('home-radius')
        
        if not latitude or not longitude or not radius:
            logger.warning("⚠️ Brak sekretów lokalizacji - używam zmiennych środowiskowych jako fallback")
            return HOME_LATITUDE_FALLBACK, HOME_LONGITUDE_FALLBACK, HOME_RADIUS_FALLBACK
            
        return float(latitude), float(longitude), float(radius)
        
    except Exception as e:
        logger.error(f"❌ Błąd pobierania współrzędnych domu: {e} - fallback do zmiennych środowiskowych")
        return HOME_LATITUDE_FALLBACK, HOME_LONGITUDE_FALLBACK, HOME_RADIUS_FALLBACK

def initialize_home_coordinates():
    """Inicjalizuje współrzędne domu z Secret Manager - wywoływane raz przy starcie Scout"""
    global HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS
    
    # Jeśli już zainicjalizowane, nie rób nic
    if HOME_LATITUDE is not None:
        return
    
    try:
        logger.info("🏠 Inicjalizuję współrzędne domu z Secret Manager...")
        
        latitude = get_secret('home-latitude')
        longitude = get_secret('home-longitude') 
        radius = get_secret('home-radius')
        
        if not latitude or not longitude or not radius:
            logger.warning("⚠️ Brak sekretów lokalizacji - używam zmiennych środowiskowych jako fallback")
            HOME_LATITUDE = HOME_LATITUDE_FALLBACK
            HOME_LONGITUDE = HOME_LONGITUDE_FALLBACK
            HOME_RADIUS = HOME_RADIUS_FALLBACK
        else:
            HOME_LATITUDE = float(latitude)
            HOME_LONGITUDE = float(longitude)
            HOME_RADIUS = float(radius)
            logger.info(f"✅ Współrzędne domu: lat={HOME_LATITUDE:.6f}, lon={HOME_LONGITUDE:.6f}, radius={HOME_RADIUS}")
        
    except Exception as e:
        logger.error(f"❌ Błąd inicjalizacji współrzędnych domu: {e} - fallback do zmiennych środowiskowych")
        HOME_LATITUDE = HOME_LATITUDE_FALLBACK
        HOME_LONGITUDE = HOME_LONGITUDE_FALLBACK
        HOME_RADIUS = HOME_RADIUS_FALLBACK

def is_at_home(latitude: float, longitude: float) -> bool:
    """Sprawdza czy pojazd jest w domu - używa współrzędnych z Secret Manager"""
    if latitude is None or longitude is None:
        return False
    
    # Używaj globalnych zmiennych (zainicjalizowanych przy starcie)
    global HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS
    
    # Oblicz odległość (uproszczona formuła dla małych odległości)
    lat_diff = abs(latitude - HOME_LATITUDE)
    lon_diff = abs(longitude - HOME_LONGITUDE)
    distance = (lat_diff ** 2 + lon_diff ** 2) ** 0.5
    
    return distance <= HOME_RADIUS

def get_last_known_state(db: firestore.Client, vin: str) -> Optional[Dict[str, Any]]:
    """Pobiera ostatni znany stan pojazdu z Firestore"""
    try:
        doc_ref = db.collection('tesla_scout_state').document(vin)
        doc = doc_ref.get()
        
        if doc.exists:
            return doc.to_dict()
        return None
        
    except Exception as e:
        logger.error(f"❌ Błąd pobierania stanu z Firestore: {e}")
        return None

def check_conditions_a_b(location_data: Dict[str, Any], last_state: Optional[Dict[str, Any]], vin: str) -> tuple[bool, str]:
    """
    Sprawdza Warunki A i B dla pojazdu ONLINE w lokalizacji HOME
    
    Args:
        location_data: Aktualne dane pojazdu
        last_state: Ostatni znany stan z Firestore
        vin: VIN pojazdu
        
    Returns:
        tuple: (trigger_worker: bool, reason: str)
    """
    
    is_charging_ready = location_data.get('is_charging_ready', False)
    battery_level = location_data.get('battery_level', 0)
    charging_state = location_data.get('charging_state', 'Unknown')
    
    # Pobierz ostatni stan ładowania
    was_charging_ready = last_state.get('is_charging_ready', False) if last_state else False
    was_online = last_state.get('online', False) if last_state else False
    was_at_home = last_state.get('at_home', False) if last_state else False
    
    logger.info(f"🔍 [SCOUT] Sprawdzam Warunki A/B dla {vin[-4:]}: is_charging_ready={is_charging_ready}, charging_state={charging_state}, battery={battery_level}%")
    
    if is_charging_ready:
        # 🔋 WARUNEK A: Pojazd ONLINE + HOME + is_charging_ready=true
        logger.info(f"🔋 [SCOUT] WARUNEK A - pojazd gotowy do ładowania w domu")
        logger.info(f"📊 [SCOUT] Dane: bateria={battery_level}%, ładowanie={charging_state}")
        
        # Sprawdź czy to zmiana stanu (dla logowania)
        if not (was_charging_ready and was_at_home and was_online):
            logger.info(f"🔋 [SCOUT] Pierwsza detekcja Warunku A")
        else:
            logger.info(f"🔋 [SCOUT] Warunek A aktywny - sprawdzenie harmonogramów")
        
        # ZAWSZE wywołaj Worker dla Warunku A
        return True, "Warunek A - pojazd gotowy do ładowania w domu (OFF PEAK CHARGE API)"
    
    else:
        # ⏳ WARUNEK B: Pojazd ONLINE + HOME + is_charging_ready=false
        logger.info(f"⏳ [SCOUT] is_charging_ready=False - sprawdzam Warunek B")
        
        if was_charging_ready and was_at_home and was_online:
            # Zmiana z gotowego na niegotowy - rozpocznij monitoring
            logger.info(f"⏳ [SCOUT] WARUNEK B - zmiana z gotowego na niegotowy")
            logger.info(f"📊 [SCOUT] Rozpoczynam monitoring do stanu OFFLINE")
            return False, "Warunek B - zmiana na niegotowy, monitoring rozpoczęty"
        
        elif not was_charging_ready and was_at_home and was_online:
            # Pojazd nadal niegotowy - kontynuuj Warunek B (nie wywołuj Worker)
            logger.info(f"⏳ [SCOUT] Warunek B kontynuowany - pojazd nadal niegotowy")
            return False, "Warunek B - monitoring w toku"
        
        else:
            # Pierwsza detekcja niegotowego pojazdu w domu
            logger.info(f"⏳ [SCOUT] WARUNEK B - pierwsza detekcja niegotowego pojazdu w domu")
            return False, "Warunek B - pierwsza detekcja, monitoring rozpoczęty"
    
    return False, "Brak warunków A/B"

def save_current_state(db: firestore.Client, vin: str, location_data: Dict[str, Any], at_home: bool):
    """Zapisuje aktualny stan pojazdu do Firestore"""
    try:
        doc_ref = db.collection('tesla_scout_state').document(vin)
        
        # ROZSZERZONE: Zapisz dodatkowe dane o stanie ładowania
        state_data = {
            'vin': vin,
            'latitude': location_data.get('latitude'),
            'longitude': location_data.get('longitude'),
            'at_home': at_home,
            'last_check': location_data['timestamp'],
            'updated_at': firestore.SERVER_TIMESTAMP,
            # NOWE: Dodatkowe pola dla Warunków A/B
            'online': location_data.get('state') == 'online',
            'battery_level': location_data.get('battery_level', 0),
            'charging_state': location_data.get('charging_state', 'Unknown'),
            'is_charging_ready': location_data.get('is_charging_ready', False),
            'vehicle_state': location_data.get('state', 'unknown')
        }
        
        # Dodaj szczegółowe dane ładowania jeśli dostępne
        if 'detailed_charge_data' in location_data:
            state_data['detailed_charge_data'] = location_data['detailed_charge_data']
        
        doc_ref.set(state_data)
        
    except Exception as e:
        logger.error(f"❌ Błąd zapisywania stanu do Firestore: {e}")

def trigger_worker_service(reason: str, vehicle_data: Dict[str, Any]) -> bool:
    """Wywołuje Worker Service (Cloud Run) gdy potrzeba pełnej logiki"""
    try:
        if not WORKER_SERVICE_URL:
            logger.error("❌ Brak URL Worker Service")
            return False
        
        payload = {
            "trigger": "scout_detected_change",
            "reason": reason,
            "vehicle_data": vehicle_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        response = requests.post(
            f"{WORKER_SERVICE_URL}/run-cycle",
            json=payload,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Worker Service wywołany pomyślnie: {reason}")
            return True
        else:
            logger.error(f"❌ Błąd wywołania Worker Service: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Błąd wywołania Worker Service: {e}")
        return False

@functions_framework.http
def tesla_scout_main(request):
    """
    Główna funkcja Scout - sprawdza lokalizację pojazdu i wywołuje Worker w razie potrzeby
    """
    start_time = datetime.now(timezone.utc)
    logger.info(f"🔍 [SCOUT] Rozpoczynam sprawdzenie lokalizacji pojazdu")
    
    # Diagnostyka konfiguracji
    logger.info(f"�� [SCOUT] PROJECT_ID: {PROJECT_ID}")
    logger.info(f"🔧 [SCOUT] GOOGLE_CLOUD_PROJECT: {os.environ.get('GOOGLE_CLOUD_PROJECT', 'BRAK')}")
    logger.info(f"🔧 [SCOUT] GCP_PROJECT: {os.environ.get('GCP_PROJECT', 'BRAK')}")
    
    try:
        # Inicjalizacja Firestore
        db = firestore.Client(project=PROJECT_ID)
        
        # Inicjalizacja współrzędnych domu
        initialize_home_coordinates()
        
        # Pobierz access token - Smart wrapper (Worker + fallback)
        access_token = get_tesla_access_token_smart()
        if not access_token:
            return {"error": "Nie można uzyskać access token (Worker Service i fallback nie działają)"}, 401
        
        # Pobierz lokalizację pojazdu
        location_data = get_vehicle_location(access_token)
        if not location_data:
            return {"error": "Nie można pobrać danych pojazdu"}, 500
        
        vin = location_data['vin']
        vehicle_state = location_data.get('state', 'unknown')
        
        # Sprawdź czy pojazd jest online i ma lokalizację
        if location_data.get('error') in ['vehicle_asleep', 'vehicle_offline']:
            # Pojazd śpi lub jest offline - to normalna sytuacja
            logger.info(f"ℹ️ Pojazd {vin[-4:]} w stanie {vehicle_state} - brak aktualnej lokalizacji")
            
            # Logowanie Scout dla pojazdu offline
            _log_scout_status(location_data, "offline_check")
            
            # Pobierz ostatni znany stan z Firestore
            db = firestore.Client(project=PROJECT_ID)
            last_state = get_last_known_state(db, vin)
            
            if last_state:
                current_at_home = last_state.get('at_home', False)
                logger.info(f"📍 Używam ostatniej znanej lokalizacji: {'w domu' if current_at_home else 'poza domem'}")
                
                # NOWE: Sprawdź czy to przejście OFFLINE w trakcie Warunku B
                was_at_home = last_state.get('at_home', False)
                was_charging_ready = last_state.get('is_charging_ready', False)
                was_online = last_state.get('online', False)
                
                if was_at_home and not was_charging_ready and was_online and vehicle_state == 'offline':
                    # Warunek B: pojazd był niegotowy w domu i przeszedł OFFLINE
                    trigger_worker = True
                    reason = "Warunek B - pojazd OFFLINE, wybudzenie i sprawdzenie stanu"
                    logger.info(f"😴 [SCOUT] WARUNEK B OFFLINE - wywołuję Worker dla wybudzenia")
                    print(f"😴 [SCOUT] WARUNEK B OFFLINE - trigger_worker=True, reason='{reason}'")
                    
                    # Loguj szczegóły przejścia
                    _log_scout_status(location_data, "CONDITION_B_OFFLINE_DETECTED")
                
            else:
                # Brak danych historycznych - załóż że poza domem
                current_at_home = False
                logger.info("📍 Brak danych historycznych - zakładam lokalizację poza domem")
                
                # Zapisz stan jako unknown
                save_current_state(db, vin, {
                    'latitude': None,
                    'longitude': None,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }, False)
        else:
            # Pojazd online - sprawdź aktualną lokalizację
            current_at_home = is_at_home(location_data['latitude'], location_data['longitude'])
            logger.info(f"📍 Aktualna lokalizacja: {'w domu' if current_at_home else 'poza domem'}")
            
            # JEDYNE logowanie Scout dla pojazdu online (usunięto duplikat)
            _log_scout_status(location_data, "online_check")
            
            # Zapisz aktualny stan
            db = firestore.Client(project=PROJECT_ID)
            save_current_state(db, vin, location_data, current_at_home)
        
        # Pobierz ostatni znany stan do porównania
        last_state = get_last_known_state(db, vin)
        

        
        # ===== NOWA LOGIKA: Sprawdź Warunki A i B =====
        # NAPRAWKA: Nie resetuj trigger_worker jeśli został już ustawiony w sekcji offline
        if 'trigger_worker' not in locals():
            trigger_worker = False
        if 'reason' not in locals() or not reason:
            reason = ""
        
        # DEBUG: Loguj stan zmiennych po inicjalizacji
        if trigger_worker:
            logger.info(f"🔍 [DEBUG] Po inicjalizacji zmiennych: trigger_worker=True, reason='{reason}'")
            print(f"🔍 [DEBUG] Po inicjalizacji: trigger_worker zachowany jako True")
        
        if last_state is None:
            # Pierwsza inicjalizacja - wywołaj Worker dla inicjalizacji
            trigger_worker = True
            reason = "Pierwsza inicjalizacja Scout"
            logger.info(f"🔍 [SCOUT] {reason} - wywołuję Worker")
            print(f"🔍 [SCOUT] {reason}")
            
        elif vehicle_state == 'online' and current_at_home:
            # NOWE: Pojazd ONLINE i w domu - sprawdź Warunki A i B
            conditions_trigger, conditions_reason = check_conditions_a_b(location_data, last_state, vin)
            if conditions_trigger:
                trigger_worker = True
                reason = conditions_reason
                
                # Specjalne logowanie dla wykrytych warunków
                if "Warunek A" in reason:
                    _log_scout_status(location_data, "CONDITION_A_DETECTED")
                elif "Warunek B" in reason:
                    _log_scout_status(location_data, "CONDITION_B_DETECTED")
            else:
                logger.info(f"🔄 [SCOUT] {conditions_reason}")
                
        elif last_state.get('at_home') != current_at_home:
            # Zmiana stanu domu (poprzednia logika)
            if current_at_home:
                trigger_worker = True
                reason = "Pojazd wrócił do domu"
                logger.info(f"🏠 [SCOUT] WYKRYTO POWRÓT DO DOMU - wywołuję Worker")
                # Loguj szczegóły zmiany
                _log_scout_status(location_data, "HOME_RETURN_DETECTED")
            else:
                # Wyjazd z domu - nie wywołujemy Worker, tylko logujemy
                logger.info(f"🚗 [SCOUT] Pojazd wyjechał z domu - tylko logowanie")
                reason = "Pojazd wyjechał z domu (tylko logowanie)"
                # Loguj szczegóły wyjazdu
                _log_scout_status(location_data, "home_departure")
        
        # Wywołaj Worker jeśli potrzeba
        worker_called = False
        if trigger_worker:
            worker_called = trigger_worker_service(reason, location_data)
        
        # NAPRAWKA: Zapisz aktualny stan NA KOŃCU (po sprawdzeniu logiki Scout)
        # To zapewnia że last_state zawiera rzeczywiście poprzedni stan, nie aktualny
        if vehicle_state == 'online':
            save_current_state(db, vin, location_data, current_at_home)
            logger.info(f"💾 [SCOUT] Stan pojazdu online zapisany")
        elif vehicle_state == 'offline' and last_state and last_state.get('online', False):
            # NAPRAWKA: Zapisz stan offline TYLKO gdy pojazd przechodzi z online na offline
            # Unikamy marnowania zasobów przy każdym sprawdzeniu offline co 15 min
            offline_state_data = {
                'vin': vin,
                'latitude': None,
                'longitude': None,
                'at_home': current_at_home,  # Używamy ostatniej znanej lokalizacji
                'last_check': location_data['timestamp'],
                'updated_at': firestore.SERVER_TIMESTAMP,
                'online': False,  # KLUCZOWE: Zapisz że pojazd jest offline
                'battery_level': 0,  # Brak danych dla offline
                'charging_state': 'Unknown',
                'is_charging_ready': False,  # Offline = nie gotowy
                'vehicle_state': 'offline'
            }
            
            doc_ref = db.collection('tesla_scout_state').document(vin)
            doc_ref.set(offline_state_data)
            logger.info(f"💾 [SCOUT] Stan offline zapisany po przejściu online→offline")
            print(f"💾 [SCOUT] Przejście online→offline zapisane dla {vin[-4:]}")
        
        # Przygotuj odpowiedź
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        response = {
            "status": "success",
            "scout_execution_time_seconds": round(execution_time, 3),
            "vehicle": {
                "vin": vin,
                "state": vehicle_state,
                "at_home": current_at_home,
                "latitude": location_data.get('latitude'),
                "longitude": location_data.get('longitude'),
                "location_source": "current" if not location_data.get('error') else "last_known"
            },
            "state_change": {
                "detected": trigger_worker,
                "reason": reason,
                "worker_triggered": worker_called
            },
            "cost_optimization": {
                "scout_cost": "~0.01 groszy",
                "worker_avoided": not trigger_worker,
                "vehicle_wake_avoided": location_data.get('error') in ['vehicle_asleep', 'vehicle_offline']
            },
            "tesla_api_compliance": {
                "checked_vehicle_state": True,
                "avoided_wake_on_sleep": location_data.get('error') == 'vehicle_asleep',
                "best_practices": "Scout respects vehicle sleep state"
            },
            "timestamp": start_time.isoformat()
        }
        
        logger.info(f"✅ [SCOUT] Zakończono w {execution_time:.3f}s - Worker {'wywołany' if worker_called else 'nie wywołany'}")
        
        return response, 200
        
    except Exception as e:
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error(f"❌ [SCOUT] Błąd: {e}")
        
        return {
            "status": "error",
            "error": str(e),
            "scout_execution_time_seconds": round(execution_time, 3),
            "timestamp": start_time.isoformat()
        }, 500

if __name__ == "__main__":
    # Test lokalny
    class MockRequest:
        pass
    
    result, status = tesla_scout_main(MockRequest())
    print(f"Status: {status}")
    print(f"Response: {json.dumps(result, indent=2)}") 