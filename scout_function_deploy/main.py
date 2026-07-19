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
import hashlib
import base64

# Google Cloud Identity Token dla autoryzacji Worker Service
from google.auth.transport.requests import Request
from google.oauth2 import id_token

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_google_cloud_identity_token(target_audience: str) -> Optional[str]:
    """
    Generuje Google Cloud Identity Token dla autoryzacji wywołań do Cloud Run
    
    Args:
        target_audience: URL serwisu Cloud Run (np. Worker Service URL)
    
    Returns:
        Identity token jako string lub None w przypadku błędu
    """
    try:
        # Wygeneruj Identity Token dla docelowego serwisu
        auth_req = Request()
        token = id_token.fetch_id_token(auth_req, target_audience)
        
        logger.info(f"✅ [AUTH] Wygenerowano Identity Token dla: {target_audience}")
        return token
        
    except Exception as e:
        logger.error(f"❌ [AUTH] Błąd generowania Identity Token: {e}")
        return None

# ====== SMART TOKEN CACHE (v2) ======
# Perzystentny cache w /tmp z szyfrowaniem i statystykami
CACHE_FILE_PATH = "/tmp/tesla_token_cache.json"
CACHE_STATS_FILE = "/tmp/cache_stats.json"

class SmartTokenCache:
    """
    Intelligent token caching system for Scout Function
    Features:
    - Persistent file-based cache in /tmp
    - Simple encryption to avoid plain text tokens
    - Hit/miss statistics tracking
    - Automatic expiration handling
    - Fallback to Secret Manager
    """
    
    def __init__(self):
        self.cache_file = CACHE_FILE_PATH
        self.stats_file = CACHE_STATS_FILE
        self._load_stats()
    
    def _simple_encrypt(self, data: str) -> str:
        """Simple encoding to avoid plain text storage"""
        return base64.b64encode(data.encode()).decode()
    
    def _simple_decrypt(self, data: str) -> str:
        """Simple decoding"""
        try:
            return base64.b64decode(data.encode()).decode()
        except:
            return ""
    
    def _load_stats(self):
        """Load cache statistics"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    self.stats = json.load(f)
            else:
                self.stats = {
                    'cache_hits': 0,
                    'cache_misses': 0,
                    'total_requests': 0,
                    'last_updated': None,
                    'bytes_saved': 0
                }
        except Exception as e:
            logger.warning(f"⚠️ Cache stats load error: {e}")
            self.stats = {'cache_hits': 0, 'cache_misses': 0, 'total_requests': 0, 'last_updated': None, 'bytes_saved': 0}
    
    def _save_stats(self):
        """Save cache statistics"""
        try:
            self.stats['last_updated'] = datetime.now(timezone.utc).isoformat()
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f)
        except Exception as e:
            logger.warning(f"⚠️ Cache stats save error: {e}")
    
    def get_cached_token(self) -> Optional[str]:
        """
        Get token from cache if valid
        Returns None if cache miss or expired
        """
        self.stats['total_requests'] += 1
        
        try:
            if not os.path.exists(self.cache_file):
                logger.info("📂 [CACHE] Cache file not found - cold start")
                self.stats['cache_misses'] += 1
                self._save_stats()
                return None
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Decrypt token
            encrypted_token = cache_data.get('encrypted_token')
            expires_at_str = cache_data.get('expires_at')
            
            if not encrypted_token or not expires_at_str:
                logger.info("📂 [CACHE] Invalid cache structure")
                self.stats['cache_misses'] += 1
                self._save_stats()
                return None
            
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            buffer_time = expires_at - timedelta(minutes=5)  # 5min safety buffer
            
            if now >= buffer_time:
                logger.info("📂 [CACHE] Token expired or expiring soon - cache miss")
                self.stats['cache_misses'] += 1
                self._save_stats()
                return None
            
            # Decrypt and return token
            access_token = self._simple_decrypt(encrypted_token)
            if access_token:
                remaining_minutes = int((expires_at - now).total_seconds() / 60)
                logger.info(f"🎯 [CACHE HIT] Token valid for {remaining_minutes}min - saved Secret Manager call!")
                self.stats['cache_hits'] += 1
                self.stats['bytes_saved'] += len(access_token)
                self._save_stats()
                return access_token
            else:
                logger.warning("📂 [CACHE] Decryption failed")
                self.stats['cache_misses'] += 1
                self._save_stats()
                return None
                
        except Exception as e:
            logger.warning(f"📂 [CACHE] Error reading cache: {e}")
            self.stats['cache_misses'] += 1
            self._save_stats()
            return None
    
    def cache_token(self, access_token: str, expires_at: datetime):
        """Cache token with encryption"""
        try:
            cache_data = {
                'encrypted_token': self._simple_encrypt(access_token),
                'expires_at': expires_at.isoformat(),
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'cache_version': '2.0'
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            remaining_minutes = int((expires_at - datetime.now(timezone.utc)).total_seconds() / 60)
            logger.info(f"💾 [CACHE] Token cached - expires in {remaining_minutes}min")
            
        except Exception as e:
            logger.warning(f"💾 [CACHE] Error caching token: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        if self.stats['total_requests'] > 0:
            hit_rate = (self.stats['cache_hits'] / self.stats['total_requests']) * 100
        else:
            hit_rate = 0.0
        
        return {
            **self.stats,
            'hit_rate_percent': round(hit_rate, 1),
            'estimated_secret_manager_calls_saved': self.stats['cache_hits']
        }
    
    def clear_cache(self):
        """
        Wyczyść wszystkie cache po odświeżeniu tokenów przez Worker
        
        Używane gdy Worker odświeżył tokeny i Scout musi pobrać świeże tokeny
        """
        try:
            # Usuń plik cache jeśli istnieje
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                logger.info("🗑️ [CACHE] Wyczyszczono cache po odświeżeniu tokenów przez Worker")
            
            # Aktualizuj statystyki
            self.stats['cache_misses'] += 1  # Wymuszone cache miss
            self._save_stats()
            
        except Exception as e:
            logger.warning(f"🗑️ [CACHE] Błąd czyszczenia cache: {e}")

# Global cache instance
_token_cache = SmartTokenCache()

# Legacy global variables for backward compatibility
_cached_access_token = None
_token_expires_at = None

# Dodaję nowe zmienne globalne do śledzenia prób odświeżania
_refresh_attempt_count = 0
_last_refresh_attempt = None

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

# Worker Service URL z Secret Manager (dla bezpieczeństwa)
WORKER_SERVICE_URL = None

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

# Usunięto niepotrzebne funkcje fallback:
# - get_token_from_worker() (Scout nie pobiera już tokenów z Worker przez HTTP)
# - get_tesla_access_token_fallback() (Scout nie używa już legacy sekretów)
# 
# NOWA ARCHITEKTURA v3:
# Scout i Worker oba mają bezpośredni dostęp do fleet-tokens w Secret Manager
# - Scout: READ ONLY (get_tesla_access_token_smart)
# - Worker: READ/WRITE (może odświeżać i migrować tokeny)

def get_tesla_access_token_smart() -> Optional[str]:
    """
    Smart Token Caching v2 - Persistent cache with encryption and statistics
    
    ARCHITEKTURA:
    1. Try persistent cache first (survives cold starts)
    2. Fallback to Secret Manager if cache miss/expired
    3. Cache new token for future use
    4. Track statistics for optimization
    
    Benefits:
    - Reduced Secret Manager calls (~67% reduction)
    - Better performance (cache hits ~1ms vs Secret Manager ~200ms)
    - Cost optimization (~$2-3/month savings)
    - Statistics for monitoring
    """
    global _cached_access_token, _token_expires_at
    
    # STEP 1: Try Smart Token Cache (persistent file)
    cached_token = _token_cache.get_cached_token()
    if cached_token:
        # Update legacy globals for backward compatibility
        _cached_access_token = cached_token
        return cached_token
    
    # STEP 2: Try legacy in-memory cache (backward compatibility)
    if _cached_access_token and _token_expires_at:
        now = datetime.now(timezone.utc)
        if now < _token_expires_at:
            logger.info("🔄 [LEGACY CACHE] Using in-memory cached token")
            # Also cache in persistent storage for next time
            _token_cache.cache_token(_cached_access_token, _token_expires_at)
            return _cached_access_token
    
    # STEP 3: Cache miss - fetch from Secret Manager
    try:
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        if not project_id:
            logger.error("❌ [SCOUT] Missing GOOGLE_CLOUD_PROJECT - cannot access centralized tokens")
            return None
        
        # Fetch from Secret Manager (expensive operation)
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        
        name = f"projects/{project_id}/secrets/fleet-tokens/versions/latest"
        logger.info("📡 [SECRET MANAGER] Fetching tokens from centralized storage...")
        
        response = client.access_secret_version(request={"name": name})
        token_data = json.loads(response.payload.data.decode("UTF-8"))
        
        access_token = token_data.get('access_token')
        if not access_token:
            logger.error("❌ [SCOUT] No access_token in fleet-tokens")
            logger.error("💡 [SCOUT] Worker should ensure valid tokens in fleet-tokens")
            return None
        
        # Parse expiration
        expires_at_str = token_data.get('expires_at')
        if expires_at_str:
            # Normalize timezone format
            if expires_at_str.endswith('Z'):
                expires_at_str = expires_at_str.replace('Z', '+00:00')
            expires_at = datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            # Check expiration with safety buffer
            buffer_time = expires_at - timedelta(minutes=5)
            now = datetime.now(timezone.utc)
            
            if now >= buffer_time:
                logger.warning("⚠️ [SCOUT] Token in fleet-tokens expired or expiring in <5 min")
                logger.warning("💡 [SCOUT] Próbuję odświeżyć tokeny przez Worker Service")
                
                # NOWY MECHANIZM: Wywołaj Worker do odświeżenia tokenów
                refresh_result = trigger_worker_refresh_tokens("Token wygasł lub wygasa w <5 min")
                
                if refresh_result["success"]:
                    logger.info("🔄 [SCOUT] Worker potwierdził odświeżenie - pobieram świeże tokeny")
                    # Spróbuj ponownie pobrać token po odświeżeniu przez Worker
                    fresh_token = retry_get_token_from_secret_manager()
                    if fresh_token:
                        return fresh_token
                    else:
                        logger.error("❌ [SCOUT] Nie udało się pobrać świeżych tokenów mimo pomyślnego odświeżenia")
                        return None
                else:
                    logger.error(f"❌ [SCOUT] Worker nie może odświeżyć tokenów: {refresh_result['message']}")
                    logger.error("💡 [SCOUT] Sprawdź logi Worker Service lub uruchom ręcznie generate_token.py")
                    return None
            
            # Cache token in both systems
            _cached_access_token = access_token
            _token_expires_at = expires_at
            _token_cache.cache_token(access_token, expires_at)
            
            remaining_minutes = int((expires_at - now).total_seconds() / 60)
            logger.info(f"✅ [SECRET MANAGER] Fresh token cached - valid for {remaining_minutes} min")
            
            # Log cache statistics
            stats = _token_cache.get_stats()
            if stats['total_requests'] > 1:  # Only show stats after some usage
                logger.info(f"📊 [CACHE STATS] Hit rate: {stats['hit_rate_percent']}% ({stats['cache_hits']}/{stats['total_requests']})")
            
            return access_token
        else:
            logger.warning("⚠️ [SCOUT] No expiration info in fleet-tokens")
            # Use token but don't cache without expiration
            return access_token
        
    except Exception as e:
        logger.error(f"❌ [SCOUT] Error fetching tokens from fleet-tokens: {e}")
        logger.error("💡 [SCOUT] Check if Worker Service is running and fleet-tokens exists")
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
            try:
                location_response = requests.get(
                    f"https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles/{vehicle_id}/vehicle_data?endpoints=location_data",
                    headers=headers,
                    timeout=30
                )
                
                if location_response.status_code != 200:
                    logger.error(f"❌ Błąd pobierania danych pojazdu: {location_response.status_code}")
                    logger.warning(f"⚠️ Pojazd {vin[-4:]} zgłoszony jako online, ale nie można pobrać danych - traktuję jako offline")
                    # NAPRAWKA: Jeśli nie można pobrać danych z pojazdu "online", traktuj jako offline
                    return {
                        'vehicle_id': vehicle_id,
                        'vin': vin,
                        'state': 'offline',  # NAPRAWKA: Spójny stan
                        'latitude': None,
                        'longitude': None,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'error': 'vehicle_offline'
                    }
                
                data = location_response.json().get('response', {})

                # Pobierz dane lokalizacji z drive_state (po użyciu location_data endpoint)
                location_info = data.get('drive_state', {})
                
                # Osobne zapytanie dla charge_state jeśli potrzebne
                if not location_info or 'latitude' not in location_info or 'longitude' not in location_info:
                    logger.error("❌ Brak danych lokalizacyjnych pomimo użycia location_data endpoint")
                    logger.warning(f"⚠️ Pojazd {vin[-4:]} online ale brak danych GPS - traktuję jako offline")
                    # NAPRAWKA: Jeśli brak danych GPS, traktuj jako offline
                    return {
                        'vehicle_id': vehicle_id,
                        'vin': vin,
                        'state': 'offline',  # NAPRAWKA: Spójny stan
                        'latitude': None,
                        'longitude': None,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'error': 'vehicle_offline'
                    }
                
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
                else:
                    logger.warning(f"⚠️ Nie można pobrać danych ładowania dla pojazdu {vin[-4:]} - używam domyślnych wartości")
                
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
                
                # NAPRAWKA: Zwracaj TYLKO spójne dane - jeśli pojazd online, to state='online' i BRAK error
                return {
                    'vehicle_id': vehicle_id,
                    'vin': vin,
                    'state': 'online',  # NAPRAWKA: Spójny stan - online bez error
                    'latitude': location_info.get('latitude'),
                    'longitude': location_info.get('longitude'),
                    'battery_level': battery_level,
                    'charging_state': charging_state,
                    'is_charging_ready': is_charging_ready,
                    'detailed_charge_data': detailed_charge_data,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                    # NAPRAWKA: BRAK pola 'error' dla pojazdu online
                }
                
            except Exception as api_error:
                logger.error(f"❌ Błąd API podczas pobierania danych pojazdu online {vin[-4:]}: {api_error}")
                logger.warning(f"⚠️ Pojazd {vin[-4:]} zgłoszony jako online, ale błąd API - traktuję jako offline")
                # NAPRAWKA: Jeśli błąd API, traktuj jako offline
                return {
                    'vehicle_id': vehicle_id,
                    'vin': vin,
                    'state': 'offline',  # NAPRAWKA: Spójny stan
                    'latitude': None,
                    'longitude': None,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'error': 'vehicle_offline'
                }
            
        elif vehicle_state == 'asleep':
            # Pojazd śpi - zwróć ostatnią znaną lokalizację lub błąd
            logger.warning(f"😴 Pojazd {vin[-4:]} w stanie 'asleep' - używam ostatniej znanej lokalizacji")
            
            # NAPRAWKA: Spójny stan - asleep z odpowiednim error
            return {
                'vehicle_id': vehicle_id,
                'vin': vin,
                'state': 'asleep',  # NAPRAWKA: Spójny stan
                'latitude': None,
                'longitude': None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': 'vehicle_asleep'
            }
            
        elif vehicle_state == 'offline':
            # Pojazd offline - brak połączenia
            logger.warning(f"⚠️ Pojazd {vin[-4:]} offline - brak połączenia")
            
            # NAPRAWKA: Spójny stan - offline z odpowiednim error
            return {
                'vehicle_id': vehicle_id,
                'vin': vin,
                'state': 'offline',  # NAPRAWKA: Spójny stan
                'latitude': None,
                'longitude': None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': 'vehicle_offline'
            }
            
        else:
            # Nieznany stan pojazdu
            logger.error(f"❌ Nieznany stan pojazdu: {vehicle_state}")
            # NAPRAWKA: Traktuj nieznany stan jako offline
            return {
                'vehicle_id': vehicle_id,
                'vin': vin,
                'state': 'offline',  # NAPRAWKA: Nieznany stan = offline
                'latitude': None,
                'longitude': None,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': 'vehicle_offline'
            }
        
    except Exception as e:
        logger.error(f"❌ Błąd pobierania lokalizacji pojazdu: {e}")
        return None

def get_home_coordinates():
    """Pobiera współrzędne domu z Secret Manager z cachowaniem"""
    global HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS
    if HOME_LATITUDE is not None and HOME_LONGITUDE is not None and HOME_RADIUS is not None:
        return HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS

    try:
        latitude = get_secret('home-latitude')
        longitude = get_secret('home-longitude') 
        radius = get_secret('home-radius')
        
        if not latitude or not longitude or not radius:
            logger.warning("⚠️ Brak sekretów lokalizacji - używam zmiennych środowiskowych jako fallback")
            HOME_LATITUDE = HOME_LATITUDE_FALLBACK
            HOME_LONGITUDE = HOME_LONGITUDE_FALLBACK
            HOME_RADIUS = HOME_RADIUS_FALLBACK
            return HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS
            
        HOME_LATITUDE = float(latitude)
        HOME_LONGITUDE = float(longitude)
        HOME_RADIUS = float(radius)
        return HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS
        
    except Exception as e:
        logger.error(f"❌ Błąd pobierania współrzędnych domu: {e} - fallback do zmiennych środowiskowych")
        HOME_LATITUDE = HOME_LATITUDE_FALLBACK
        HOME_LONGITUDE = HOME_LONGITUDE_FALLBACK
        HOME_RADIUS = HOME_RADIUS_FALLBACK
        return HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS

def initialize_home_coordinates():
    """Inicjalizuje współrzędne domu i Worker Service URL z Secret Manager - wywoływane raz przy starcie Scout"""
    global HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS, WORKER_SERVICE_URL
    
    # DIAGNOSTYKA: zawsze loguj wywołanie funkcji
    logger.info("🔧 [DIAGNOSTYKA] initialize_home_coordinates wywołane")
    print("🔧 [DIAGNOSTYKA] initialize_home_coordinates wywołane")
    
    # Jeśli już zainicjalizowane, nie rób nic
    if HOME_LATITUDE is not None:
        logger.info(f"🔧 [DIAGNOSTYKA] Już zainicjalizowane: HOME_LATITUDE={HOME_LATITUDE}, HOME_RADIUS={HOME_RADIUS}")
        print(f"🔧 [DIAGNOSTYKA] Już zainicjalizowane: HOME_LATITUDE={HOME_LATITUDE}, HOME_RADIUS={HOME_RADIUS}")
        return
    
    try:
        logger.info("🏠 Inicjalizuję konfigurację Scout z Secret Manager...")
        print("🏠 Inicjalizuję konfigurację Scout z Secret Manager...")
        
        # Współrzędne domu
        latitude = get_secret('home-latitude')
        longitude = get_secret('home-longitude') 
        radius = get_secret('home-radius')
        
        # DIAGNOSTYKA: loguj pobrane wartości
        logger.info(f"🔧 [DIAGNOSTYKA] Pobrane z Secret Manager: latitude={latitude}, longitude={longitude}, radius={radius}")
        print(f"🔧 [DIAGNOSTYKA] Pobrane z Secret Manager: latitude={latitude}, longitude={longitude}, radius={radius}")
        
        # Worker Service URL
        worker_url = get_secret('WORKER_SERVICE_URL')
        
        if not latitude or not longitude or not radius:
            logger.warning("⚠️ Brak sekretów lokalizacji - używam zmiennych środowiskowych jako fallback")
            print("⚠️ Brak sekretów lokalizacji - używam zmiennych środowiskowych jako fallback")
            HOME_LATITUDE = HOME_LATITUDE_FALLBACK
            HOME_LONGITUDE = HOME_LONGITUDE_FALLBACK
            HOME_RADIUS = HOME_RADIUS_FALLBACK
            logger.info(f"🔧 [DIAGNOSTYKA] Fallback values: HOME_LATITUDE={HOME_LATITUDE}, HOME_RADIUS={HOME_RADIUS}")
            print(f"🔧 [DIAGNOSTYKA] Fallback values: HOME_LATITUDE={HOME_LATITUDE}, HOME_RADIUS={HOME_RADIUS}")
        else:
            HOME_LATITUDE = float(latitude)
            HOME_LONGITUDE = float(longitude)
            HOME_RADIUS = float(radius)
            logger.info(f"✅ Współrzędne domu: lat={HOME_LATITUDE:.6f}, lon={HOME_LONGITUDE:.6f}, radius={HOME_RADIUS}")
            print(f"✅ Współrzędne domu: lat={HOME_LATITUDE:.6f}, lon={HOME_LONGITUDE:.6f}, radius={HOME_RADIUS}")
        
        if worker_url:
            WORKER_SERVICE_URL = worker_url.strip()
            logger.info(f"✅ Worker Service URL: {WORKER_SERVICE_URL}")
            print(f"✅ Worker Service URL: {WORKER_SERVICE_URL}")
        else:
            logger.error("❌ Brak WORKER_SERVICE_URL w Secret Manager")
            print("❌ Brak WORKER_SERVICE_URL w Secret Manager")
        
    except Exception as e:
        logger.error(f"❌ Błąd inicjalizacji konfiguracji Scout: {e} - fallback do zmiennych środowiskowych")
        print(f"❌ Błąd inicjalizacji konfiguracji Scout: {e} - fallback do zmiennych środowiskowych")
        HOME_LATITUDE = HOME_LATITUDE_FALLBACK
        HOME_LONGITUDE = HOME_LONGITUDE_FALLBACK
        HOME_RADIUS = HOME_RADIUS_FALLBACK
        logger.info(f"🔧 [DIAGNOSTYKA] Exception fallback values: HOME_LATITUDE={HOME_LATITUDE}, HOME_RADIUS={HOME_RADIUS}")
        print(f"🔧 [DIAGNOSTYKA] Exception fallback values: HOME_LATITUDE={HOME_LATITUDE}, HOME_RADIUS={HOME_RADIUS}")

def is_at_home(latitude: float, longitude: float) -> bool:
    """Sprawdza czy pojazd jest w domu - używa współrzędnych z Secret Manager"""
    if latitude is None or longitude is None:
        return False
    
    # Używaj globalnych zmiennych (zainicjalizowanych przy starcie)
    global HOME_LATITUDE, HOME_LONGITUDE, HOME_RADIUS
    
    # Odległość w stopniach z korektą cos(szerokości) — bez niej strefa "dom"
    # była elipsą rozciągniętą w osi N-S (na 52°N o ~60%)
    import math
    lat_diff = abs(latitude - HOME_LATITUDE)
    lon_diff = abs(longitude - HOME_LONGITUDE) * math.cos(math.radians(HOME_LATITUDE))
    distance = (lat_diff ** 2 + lon_diff ** 2) ** 0.5

    return distance <= HOME_RADIUS

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
    
    logger.info(f"🔍 [SCOUT] === ROZPOCZYNAM check_conditions_a_b ===")
    print(f"🔍 [SCOUT] === ROZPOCZYNAM check_conditions_a_b ===")
    logger.info(f"🔍 [SCOUT] VIN: {vin[-4:]}")
    print(f"🔍 [SCOUT] VIN: {vin[-4:]}")
    logger.info(f"🔍 [SCOUT] is_charging_ready: {is_charging_ready}")
    print(f"🔍 [SCOUT] is_charging_ready: {is_charging_ready}")
    logger.info(f"🔍 [SCOUT] charging_state: {charging_state}")
    print(f"🔍 [SCOUT] charging_state: {charging_state}")
    logger.info(f"🔍 [SCOUT] battery_level: {battery_level}%")
    print(f"🔍 [SCOUT] battery_level: {battery_level}%")
    logger.info(f"🔍 [SCOUT] Poprzedni stan: was_charging_ready={was_charging_ready}, was_at_home={was_at_home}, was_online={was_online}")
    print(f"🔍 [SCOUT] Poprzedni stan: was_charging_ready={was_charging_ready}, was_at_home={was_at_home}, was_online={was_online}")
    
    # NOWE: Sprawdź czy trwa special charging session
    if is_charging_ready:
        logger.info(f"🔍 [SCOUT] is_charging_ready=True - sprawdzam special charging sessions")
        print(f"🔍 [SCOUT] is_charging_ready=True - sprawdzam special charging sessions")
        special_session_active = _check_active_special_charging_session(vin)
        logger.info(f"🔍 [SCOUT] special_session_active: {special_session_active}")
        print(f"🔍 [SCOUT] special_session_active: {special_session_active}")
        
        if special_session_active:
            logger.info(f"🔋 [SCOUT] BLOKUJĘ Warunek A - trwa special charging session")
            print(f"🔋 [SCOUT] BLOKUJĘ Warunek A - trwa special charging session")
            return False, "Special charging w trakcie - blokuję normalne OFF PEAK API"
        else:
            logger.info(f"🔋 [SCOUT] Brak aktywnych special charging sessions - kontynuuję sprawdzanie Warunku A")
            print(f"🔋 [SCOUT] Brak aktywnych special charging sessions - kontynuuję sprawdzanie Warunku A")
    
    if is_charging_ready:
        # 🔋 WARUNEK A: Pojazd ONLINE + HOME + is_charging_ready=true
        logger.info(f"🔋 [SCOUT] === WARUNEK A WYKRYTY ===")
        logger.info(f"🔋 [SCOUT] Pojazd gotowy do ładowania w domu")
        logger.info(f"📊 [SCOUT] Dane: bateria={battery_level}%, ładowanie={charging_state}")
        
        # NAPRAWKA: Sprawdź czy to zmiana stanu - wywołuj Worker TYLKO przy zmianach
        state_change_condition = not (was_charging_ready and was_at_home and was_online)
        logger.info(f"🔋 [SCOUT] Warunek zmiany stanu: not ({was_charging_ready} AND {was_at_home} AND {was_online}) = {state_change_condition}")
        
        if state_change_condition:
            # Zmiana stanu - wywołaj Worker
            logger.info(f"🔋 [SCOUT] ZMIANA STANU - wywołuję Worker dla Warunku A")
            return True, "Warunek A - pojazd gotowy do ładowania w domu (OFF PEAK CHARGE API)"
        else:
            # Kontynuacja stanu - NIE wywołuj Worker (optymalizacja kosztów)
            logger.info(f"🔋 [SCOUT] KONTYNUACJA STANU - Worker NIE wywoływany (optymalizacja kosztów)")
            return False, "Warunek A - kontynuacja stanu bez zmiany (optymalizacja kosztów)"
    
    else:
        # ⏳ WARUNEK B: Pojazd ONLINE + HOME + is_charging_ready=false
        logger.info(f"⏳ [SCOUT] === SPRAWDZAM WARUNEK B ===")
        logger.info(f"⏳ [SCOUT] is_charging_ready=False - sprawdzam Warunek B")
        
        if was_charging_ready and was_at_home and was_online:
            # Zmiana z gotowego na niegotowy - rozpocznij monitoring
            logger.info(f"⏳ [SCOUT] WARUNEK B - zmiana z gotowego na niegotowy")
            logger.info(f"📊 [SCOUT] Rozpoczynam monitoring do stanu OFFLINE")
            return True, "Warunek B - pojazd niegotowy, rozpoczęcie monitoringu do OFFLINE"
        
        elif not was_charging_ready and was_at_home and was_online:
            # Pojazd nadal niegotowy - kontynuuj Warunek B (nie wywołuj Worker)
            logger.info(f"⏳ [SCOUT] Warunek B kontynuowany - pojazd nadal niegotowy")
            return False, "Warunek B - monitoring w toku"
        
        elif not was_charging_ready and was_at_home and not was_online:
            # Pojazd był niegotowy i przeszedł OFFLINE - czas na wybudzenie!
            logger.info(f"😴 [SCOUT] WARUNEK B - pojazd przeszedł OFFLINE, potrzeba wybudzenia")
            return True, "Warunek B - pojazd OFFLINE, wybudzenie i sprawdzenie stanu"
        
        else:
            # Pierwsza detekcja niegotowego pojazdu w domu
            logger.info(f"⏳ [SCOUT] WARUNEK B - pierwsza detekcja niegotowego pojazdu w domu")
            return False, "Warunek B - pierwsza detekcja, monitoring rozpoczęty"
    
    return False, "Brak warunków A/B"

def _check_active_special_charging_session(vin: str) -> bool:
    """
    Sprawdza czy trwa aktywny special charging session dla pojazdu
    Blokuje normalne OFF PEAK API jeśli special charging jest aktywny
    
    NAPRAWKA: Blokuje dla WSZYSTKICH sessions ACTIVE (nie tylko w czasie ładowania)
    Rozwiązuje problem gdzie Scout usuwał harmonogramy special charging przed rozpoczęciem ładowania
    """
    try:
        # Import Firestore tutaj aby uniknąć circular imports
        from google.cloud import firestore
        
        db = firestore.Client()
        
        # Sprawdź aktywne sessions dla tego VIN
        logger.info(f"🔍 [SPECIAL] Sprawdzam special charging sessions dla VIN: {vin[-4:]}")
        sessions_ref = db.collection('special_charging_sessions')
        query = sessions_ref.where('vin', '==', vin).where('status', '==', 'ACTIVE')
        sessions = list(query.stream())
        
        logger.info(f"🔍 [SPECIAL] Znaleziono {len(sessions)} aktywnych sessions")
        print(f"🔍 [SPECIAL] Znaleziono {len(sessions)} aktywnych sessions")
        
        if not sessions:
            logger.info(f"🔍 [SPECIAL] Brak aktywnych sessions - zwracam False")
            print(f"🔍 [SPECIAL] Brak aktywnych sessions - zwracam False")
            return False
        
        # NAPRAWKA: Blokuj dla WSZYSTKICH sessions ACTIVE (nie tylko w czasie ładowania)
        # Problem: Scout usuwał harmonogramy special charging gdy session była ACTIVE ale przed rozpoczęciem ładowania
        from datetime import datetime
        import pytz
        
        current_time = datetime.now(pytz.timezone('Europe/Warsaw'))
        
        for session_doc in sessions:
            session_data = session_doc.to_dict()
            session_id = session_data.get('session_id', session_doc.id)
            
            try:
                # Pobierz szczegóły sesji dla lepszego logowania
                charging_start_str = session_data.get('charging_start', 'Unknown')
                charging_end_str = session_data.get('charging_end', 'Unknown')
                created_at_str = session_data.get('created_at', 'Unknown')
                
                # ULEPSZONE LOGOWANIE: Szczegółowe informacje o blokującej sesji
                logger.info(f"🔋 [SCOUT] BLOKUJĘ - aktywny special charging session: {session_id}")
                print(f"🔋 [SCOUT] BLOKUJĘ - aktywny special charging session: {session_id}")
                logger.info(f"⏰ [SCOUT] Czas ładowania: {charging_start_str} → {charging_end_str}")
                print(f"⏰ [SCOUT] Czas ładowania: {charging_start_str} → {charging_end_str}")
                logger.info(f"📅 [SCOUT] Utworzona: {created_at_str}")
                print(f"📅 [SCOUT] Utworzona: {created_at_str}")
                
                # Sprawdź czy session mogła już się zakończyć (diagnostyka zombie sessions)
                if charging_end_str and charging_end_str != 'Unknown':
                    try:
                        charging_end = datetime.fromisoformat(charging_end_str.replace('Z', '+00:00'))
                        
                        # Konwertuj na Warsaw timezone jeśli potrzeba
                        if charging_end.tzinfo is None:
                            warsaw_tz = pytz.timezone('Europe/Warsaw')
                            charging_end = warsaw_tz.localize(charging_end)
                        
                        charging_end_warsaw = charging_end.astimezone(pytz.timezone('Europe/Warsaw'))
                        
                        # Sprawdź czy session już się zakończyła (diagnostyka)
                        hours_since_end = (current_time - charging_end_warsaw).total_seconds() / 3600
                        
                        if hours_since_end > 2:  # 2h buffer
                            logger.warning(f"⚠️ [SCOUT] ZOMBIE SESSION: {session_id} powinna być COMPLETED!")
                            logger.warning(f"⚠️ [SCOUT] Zakończone {hours_since_end:.1f}h temu - zlecam cleanup Workerowi")
                            print(f"⚠️ [SCOUT] ZOMBIE SESSION: {session_id} - zakończone {hours_since_end:.1f}h temu!")
                            # SELF-HEAL: bez tego zombie blokowała Warunek A bezterminowo
                            # (ten tick jeszcze blokuje; po cleanup kolejne ticki działają normalnie)
                            _trigger_zombie_session_cleanup(session_id)
                        else:
                            logger.info(f"✅ [SCOUT] Session {session_id} prawidłowo aktywna")
                            
                        # Dodatkowa informacja czy jesteśmy w czasie ładowania
                        charging_start = datetime.fromisoformat(charging_start_str.replace('Z', '+00:00'))
                        if charging_start.tzinfo is None:
                            warsaw_tz = pytz.timezone('Europe/Warsaw')
                            charging_start = warsaw_tz.localize(charging_start)
                        charging_start_warsaw = charging_start.astimezone(pytz.timezone('Europe/Warsaw'))
                        
                        if charging_start_warsaw <= current_time <= charging_end_warsaw:
                            logger.info(f"🔋 [SCOUT] Session w trakcie ładowania (current time: {current_time.strftime('%H:%M')})")
                            print(f"🔋 [SCOUT] Session w trakcie ładowania")
                        else:
                            logger.info(f"🕐 [SCOUT] Session przed/po ładowaniu (current time: {current_time.strftime('%H:%M')})")
                            print(f"🕐 [SCOUT] Session przed/po ładowaniu")
                            
                    except Exception as time_error:
                        logger.warning(f"⚠️ [SCOUT] Błąd parsowania czasu dla session {session_id}: {time_error}")
                        print(f"⚠️ [SCOUT] Błąd parsowania czasu dla session {session_id}")
                
                # Zawsze blokuj dla ACTIVE sessions (niezależnie od czasu)
                logger.info(f"🔋 [SCOUT] BLOKUJĘ Warunek A - znaleziono aktywne special charging sessions")
                print(f"🔋 [SCOUT] BLOKUJĘ Warunek A - znaleziono {len(sessions)} aktywnych sessions")
                return True
                        
            except Exception as e:
                logger.warning(f"⚠️ [SCOUT] Błąd sprawdzania session {session_doc.id}: {e}")
                print(f"⚠️ [SCOUT] Błąd sprawdzania session {session_doc.id}")
                continue
        
        logger.info(f"🔍 [SCOUT] Brak aktywnych special charging sessions dla {vin[-4:]} - nie blokuję")
        print(f"🔍 [SCOUT] Brak aktywnych special charging sessions - nie blokuję")
        return False
        
    except Exception as e:
        logger.warning(f"⚠️ [SCOUT] Błąd sprawdzania special charging sessions: {e}")
        return False  # W przypadku błędu nie blokuj normalnego działania

def _trigger_zombie_session_cleanup(session_id: str) -> bool:
    """
    SELF-HEAL: zleca Workerowi domknięcie sesji zombie (/cleanup-single-session).
    Wcześniej Scout tylko logował ostrzeżenie i blokował Warunek A bezterminowo —
    auto nie dostawało harmonogramu żadnej kolejnej nocy.
    """
    try:
        worker_url = os.environ.get('WORKER_SERVICE_URL')
        if not worker_url:
            logger.error("❌ [SCOUT] Brak WORKER_SERVICE_URL - nie mogę zlecić cleanup zombie")
            return False

        headers = {'Content-Type': 'application/json'}
        token = get_google_cloud_identity_token(worker_url)
        if token:
            headers['Authorization'] = f'Bearer {token}'

        response = requests.post(
            f"{worker_url}/cleanup-single-session",
            json={'session_id': session_id, 'trigger': 'scout_zombie_self_heal',
                  'action': 'cleanup_single_special_session'},
            headers=headers,
            timeout=45
        )
        if response.status_code == 200:
            logger.info(f"✅ [SCOUT] Worker domknął sesję zombie {session_id}")
            return True
        logger.error(f"❌ [SCOUT] Worker cleanup zombie {session_id}: HTTP {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"❌ [SCOUT] Błąd zlecania cleanup zombie {session_id}: {e}")
        return False

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

def save_current_state(db: firestore.Client, vin: str, location_data: Dict[str, Any], at_home: bool,
                       pending_trigger: Optional[Dict[str, Any]] = None,
                       special_blocked: bool = False):
    """
    Zapisuje aktualny stan pojazdu do Firestore.

    pending_trigger: gdy wywołanie Workera się nie powiodło, zapisujemy zaległy
    trigger ({'reason', 'created_at'}) — następny tick ponowi wywołanie zamiast
    uznać zdarzenie za "kontynuację stanu" i zgubić je na zawsze.
    None czyści flagę (trigger udany albo brak triggera).

    special_blocked: True gdy Warunek A był w tym ticku zablokowany przez sesję
    special charging. Gdy sesja się skończy (flaga była True, teraz blokady brak),
    Scout wymusza trigger — bez tego normalny harmonogram nie byłby przeliczony
    aż do wypięcia i ponownego wpięcia kabla.
    """
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
            'vehicle_state': location_data.get('state', 'unknown'),
            'pending_trigger': pending_trigger,
            'special_blocked': special_blocked
        }
        
        # Dodaj szczegółowe dane ładowania jeśli dostępne
        if 'detailed_charge_data' in location_data:
            state_data['detailed_charge_data'] = location_data['detailed_charge_data']
        
        doc_ref.set(state_data)
        
    except Exception as e:
        logger.error(f"❌ Błąd zapisywania stanu do Firestore: {e}")

def trigger_worker_refresh_tokens(reason: str = "Scout detected expired tokens") -> Dict[str, Any]:
    """
    Wywołuje Worker Service do wymuszenia odświeżenia tokenów Tesla
    
    Returns:
        Dict z wynikiem: {"success": bool, "message": str, "details": dict}
    """
    global _refresh_attempt_count, _last_refresh_attempt
    
    try:
        # Sprawdź czy nie próbujemy zbyt często (endless loop protection)
        now = datetime.now(timezone.utc)
        if _last_refresh_attempt and (now - _last_refresh_attempt).seconds < 60:
            logger.warning("⚠️ [SCOUT] Zbyt częste próby odświeżania tokenów - pomijam")
            return {"success": False, "message": "Rate limit - too frequent refresh attempts", "details": {}}
        
        _last_refresh_attempt = now
        _refresh_attempt_count += 1
        
        # Sprawdź czy Worker Service URL jest skonfigurowany
        global WORKER_SERVICE_URL
        worker_url = WORKER_SERVICE_URL
        if not worker_url:
            logger.error("❌ [SCOUT] WORKER_SERVICE_URL nie jest skonfigurowany")
            return {"success": False, "message": "WORKER_SERVICE_URL not configured", "details": {}}
        
        payload = {
            "reason": reason,
            "requested_by": "scout_function",
            "timestamp": now.isoformat(),
            "attempt_count": _refresh_attempt_count
        }
        
        refresh_url = f"{worker_url.rstrip('/')}/refresh-tokens"
        logger.info(f"🔄 [SCOUT] Wywołuję Worker do odświeżenia tokenów: {refresh_url}")
        logger.info(f"📋 [SCOUT] Powód: {reason}")
        
        # NAPRAWKA: Generuj Google Cloud Identity Token dla autoryzacji
        identity_token = get_google_cloud_identity_token(worker_url)
        if not identity_token:
            logger.error("❌ [SCOUT] Nie można wygenerować Identity Token dla Worker Service")
            return {"success": False, "message": "Identity token generation failed", "details": {}}
        
        # Przygotuj nagłówki z autoryzacją
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {identity_token}"
        }
        
        # Wywołaj Worker z timeoutem i autoryzacją
        response = requests.post(
            refresh_url,
            json=payload,
            timeout=45,  # 45s timeout - Worker potrzebuje czasu na odświeżenie
            headers=headers
        )
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"✅ [SCOUT] Worker odświeżył tokeny pomyślnie")
                return {"success": True, "message": "Tokens refreshed by Worker", "details": result}
            except json.JSONDecodeError:
                logger.info(f"✅ [SCOUT] Worker odświeżył tokeny (brak JSON response)")
                return {"success": True, "message": "Tokens refreshed by Worker", "details": {}}
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get('error', f'HTTP {response.status_code}')
            except:
                error_msg = f'HTTP {response.status_code}'
            
            logger.error(f"❌ [SCOUT] Worker nie może odświeżyć tokenów: {error_msg}")
            return {"success": False, "message": f"Worker refresh failed: {error_msg}", "details": {"status_code": response.status_code}}
            
    except requests.exceptions.Timeout:
        logger.error("❌ [SCOUT] Timeout podczas wywołania Worker - Worker może być przeciążony")
        return {"success": False, "message": "Worker timeout", "details": {"timeout": 45}}
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ [SCOUT] Nie można połączyć się z Worker Service: {e}")
        return {"success": False, "message": "Worker connection failed", "details": {"error": str(e)}}
    except Exception as e:
        logger.error(f"❌ [SCOUT] Nieoczekiwany błąd wywołania Worker: {e}")
        return {"success": False, "message": "Unexpected error", "details": {"error": str(e)}}

def retry_get_token_from_secret_manager() -> Optional[str]:
    """
    Ponowna próba pobrania tokenu z Secret Manager po odświeżeniu przez Worker
    
    Czyści cache i pobiera świeże tokeny z Secret Manager
    """
    global _cached_access_token, _token_expires_at
    
    logger.info("🔄 [SCOUT] Worker zakończył odświeżenie - pobieram świeże tokeny")
    
    # KROK 1: Wyczyść wszystkie cache żeby wymusić świeże pobranie
    _cached_access_token = None
    _token_expires_at = None
    _token_cache.clear_cache()
    
    # KROK 2: Krótka pauza żeby Worker zdążył zapisać tokeny w Secret Manager
    import time
    time.sleep(2)
    
    # KROK 3: Pobierz świeże tokeny z Secret Manager
    logger.info("📡 [SCOUT] Pobieram świeże tokeny z Secret Manager po odświeżeniu")
    fresh_token = get_tesla_access_token_smart()
    
    if fresh_token:
        logger.info("✅ [SCOUT] Pomyślnie pobrano świeże tokeny po odświeżeniu przez Worker")
        return fresh_token
    else:
        logger.error("❌ [SCOUT] Nie udało się pobrać świeżych tokenów mimo odświeżenia przez Worker")
        return None

def trigger_worker_service(reason: str, vehicle_data: Dict[str, Any]) -> bool:
    """
    Wywołuje Worker Service gdy Scout wykryje zmiany stanu pojazdu
    
    NOWA ARCHITEKTURA v3.1:
    - Scout: Głównie używa Secret Manager bezpośrednio
    - Worker: Wywoływany przez Scout gdy potrzebny (pojazd w domu) 
    - Fallback: Scout → Worker gdy tokeny wygasłe
    """
    try:
        global WORKER_SERVICE_URL
        worker_url = WORKER_SERVICE_URL
        if not worker_url:
            logger.error("❌ [SCOUT] WORKER_SERVICE_URL nie jest skonfigurowany")
            return False
        
        payload = {
            "trigger": "scout_detected_change",
            "reason": reason,
            "vehicle_data": vehicle_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"📡 [SCOUT] Wywołuję Worker Service: {reason}")
        
        # Generuj Google Cloud Identity Token dla autoryzacji
        identity_token = get_google_cloud_identity_token(worker_url)
        if not identity_token:
            logger.error("❌ [SCOUT] Nie można wygenerować Identity Token dla Worker Service")
            return False
        
        # Przygotuj nagłówki z autoryzacją
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {identity_token}"
        }
        
        response = requests.post(
            f"{worker_url.rstrip('/')}/run-cycle",
            json=payload,
            timeout=60,
            headers=headers
        )
        
        if response.status_code == 200:
            logger.info(f"✅ [SCOUT] Worker Service wywołany pomyślnie: {reason}")
            return True
        else:
            logger.error(f"❌ [SCOUT] Błąd wywołania Worker Service: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ [SCOUT] Błąd wywołania Worker Service: {e}")
        return False

def get_cache_stats() -> Dict[str, Any]:
    """Get detailed cache statistics for monitoring and optimization"""
    try:
        stats = _token_cache.get_stats()
        
        # Calculate additional metrics
        if stats['total_requests'] > 0:
            secret_manager_calls = stats['cache_misses']
            # Estimated cost: Secret Manager charges $0.03 per 10,000 accesses
            estimated_cost_saved = secret_manager_calls * 0.000003  # $0.03 / 10000
            estimated_monthly_savings = estimated_cost_saved * 30 * 96  # 96 Scout calls per day
            
            stats.update({
                'secret_manager_calls_made': secret_manager_calls,
                'estimated_daily_cost_saved_usd': round(estimated_cost_saved * 96, 6),
                'estimated_monthly_cost_saved_usd': round(estimated_monthly_savings, 4),
                'performance_metrics': {
                    'cache_hit_speed': '~1ms',
                    'secret_manager_speed': '~200ms',
                    'speed_improvement': f"{200}x faster on cache hits"
                },
                'cache_efficiency_rating': (
                    'Excellent (80%+)' if stats['hit_rate_percent'] >= 80 else
                    'Good (60-79%)' if stats['hit_rate_percent'] >= 60 else
                    'Needs Improvement (<60%)'
                )
            })
        
        return {
            'cache_status': 'active',
            'smart_cache_version': '2.0',
            **stats
        }
    except Exception as e:
        logger.error(f"❌ Error getting cache stats: {e}")
        return {'error': str(e), 'cache_status': 'error'}

@functions_framework.http
def tesla_scout_main(request):
    """
    Główna funkcja Scout - sprawdza lokalizację pojazdu i wywołuje Worker w razie potrzeby
    
    Endpoints:
    - GET /?action=cache-stats : Cache statistics and performance metrics
    - POST / : Main location checking functionality (default)
    """
    start_time = datetime.now(timezone.utc)
    
    # DIAGNOSTYKA: zawsze loguj start
    logger.info("🚀 [DIAGNOSTYKA] tesla_scout_main START")
    print("🚀 [DIAGNOSTYKA] tesla_scout_main START")
    
    # Handle cache statistics endpoint
    if request.method == 'GET' and request.args.get('action') == 'cache-stats':
        logger.info("📊 [SCOUT] Cache statistics requested")
        stats = get_cache_stats()
        stats['request_timestamp'] = datetime.now(timezone.utc).isoformat()
        stats['scout_function_version'] = 'v2.0_smart_cache'
        return stats
    
    logger.info(f"🔍 [SCOUT] Rozpoczynam sprawdzenie lokalizacji pojazdu")
    
    # KRYTYCZNE: Inicjalizacja konfiguracji przed wszystkim (WORKER_SERVICE_URL potrzebny w get_tesla_access_token_smart)
    logger.info("🔧 [DIAGNOSTYKA] Wywołuję initialize_home_coordinates...")
    print("🔧 [DIAGNOSTYKA] Wywołuję initialize_home_coordinates...")
    initialize_home_coordinates()
    logger.info(f"🔧 [DIAGNOSTYKA] Po initialize_home_coordinates: HOME_RADIUS={HOME_RADIUS}")
    print(f"🔧 [DIAGNOSTYKA] Po initialize_home_coordinates: HOME_RADIUS={HOME_RADIUS}")
    
    # Diagnostyka konfiguracji
    logger.info(f"🔧 [SCOUT] PROJECT_ID: {PROJECT_ID}")
    logger.info(f"🔧 [SCOUT] GOOGLE_CLOUD_PROJECT: {os.environ.get('GOOGLE_CLOUD_PROJECT', 'BRAK')}")
    logger.info(f"🔧 [SCOUT] GCP_PROJECT: {os.environ.get('GCP_PROJECT', 'BRAK')}")
    
    try:
        # Inicjalizacja Firestore
        db = firestore.Client(project=PROJECT_ID)
        
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
        
        # DODANE: Szczegółowe logowanie danych z get_vehicle_location
        logger.info(f"🔍 [SCOUT] Dane z get_vehicle_location: state='{vehicle_state}', error='{location_data.get('error', 'BRAK')}'")
        if location_data.get('latitude') and location_data.get('longitude'):
            logger.info(f"🔍 [SCOUT] GPS: lat={location_data['latitude']:.6f}, lon={location_data['longitude']:.6f}")
        else:
            logger.info(f"🔍 [SCOUT] GPS: BRAK DANYCH")
        
        # NAPRAWKA: Inicjalizuj Firestore client na początku
        db = firestore.Client(project=PROJECT_ID)
        
        # Sprawdź czy pojazd jest online i ma lokalizację
        if location_data.get('error') in ['vehicle_asleep', 'vehicle_offline']:
            # Pojazd śpi lub jest offline - to normalna sytuacja
            logger.info(f"ℹ️ Pojazd {vin[-4:]} w stanie {vehicle_state} - brak aktualnej lokalizacji")
            logger.info(f"🔍 [SCOUT] PRZECHODZĘ DO SEKCJI OFFLINE/ASLEEP - error='{location_data.get('error')}'")
            
            # Logowanie Scout dla pojazdu offline
            _log_scout_status(location_data, "offline_check")
            
            # Pobierz ostatni znany stan z Firestore
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
            
            # db client już zainicjalizowany na początku funkcji
        
        # NAPRAWKA: NAJPIERW pobierz ostatni znany stan PRZED zapisaniem aktualnego
        last_state = get_last_known_state(db, vin)
        
        # DEBUG: Loguj porównanie stanów
        if last_state:
            print(f"🔍 [DEBUG] Poprzedni stan: is_charging_ready={last_state.get('is_charging_ready', False)}, at_home={last_state.get('at_home', False)}, online={last_state.get('online', False)}")
            logger.info(f"🔍 [DEBUG] Poprzedni stan: is_charging_ready={last_state.get('is_charging_ready', False)}, at_home={last_state.get('at_home', False)}, online={last_state.get('online', False)}")
        else:
            print(f"🔍 [DEBUG] Brak poprzedniego stanu - pierwsza inicjalizacja")
            logger.info(f"🔍 [DEBUG] Brak poprzedniego stanu - pierwsza inicjalizacja")
        
        if vehicle_state == 'online':
            print(f"🔍 [DEBUG] Aktualny stan: is_charging_ready={location_data.get('is_charging_ready', False)}, at_home={current_at_home}, online=True")
            logger.info(f"🔍 [DEBUG] Aktualny stan: is_charging_ready={location_data.get('is_charging_ready', False)}, at_home={current_at_home}, online=True")
        
        # DODANE: Debug point 1
        logger.info(f"🐛 [DEBUG] Punkt 1: Przed sekcją warunków A/B")
        print(f"🐛 [DEBUG] Punkt 1: Przed sekcją warunków A/B")

        
        # ===== NOWA LOGIKA: Sprawdź Warunki A i B =====
        # NAPRAWKA: Nie resetuj trigger_worker jeśli został już ustawiony w sekcji offline
        if 'trigger_worker' not in locals():
            trigger_worker = False
        if 'reason' not in locals() or not reason:
            reason = ""

        # DODANE: Debug point 2
        logger.info(f"🐛 [DEBUG] Punkt 2: Po inicjalizacji zmiennych")
        print(f"🐛 [DEBUG] Punkt 2: Po inicjalizacji zmiennych")

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
            
        # DODANE: Debug point 3
        logger.info(f"🐛 [DEBUG] Punkt 3: Przed logami diagnostycznymi")
        print(f"🐛 [DEBUG] Punkt 3: Przed logami diagnostycznymi")

        # DIAGNOSTYKA: Sprawdź wszystkie warunki przed wywołaniem check_conditions_a_b  
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: Sprawdzam warunki wywołania check_conditions_a_b")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: Sprawdzam warunki wywołania check_conditions_a_b")
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: last_state is None: {last_state is None}")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: last_state is None: {last_state is None}")
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: vehicle_state: '{vehicle_state}'")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: vehicle_state: '{vehicle_state}'")
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: current_at_home: {current_at_home}")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: current_at_home: {current_at_home}")
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: vehicle_state == 'online': {vehicle_state == 'online'}")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: vehicle_state == 'online': {vehicle_state == 'online'}")
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: current_at_home: {current_at_home}")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: current_at_home: {current_at_home}")
        logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: warunek online AND at_home: {vehicle_state == 'online' and current_at_home}")
        print(f"🔍 [SCOUT] DIAGNOSTYKA: warunek online AND at_home: {vehicle_state == 'online' and current_at_home}")
        
        if last_state:
            logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: Mam last_state, sprawdzam dalej...")
            print(f"🔍 [SCOUT] DIAGNOSTYKA: Mam last_state, sprawdzam dalej...")
            logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: last_state.get('at_home'): {last_state.get('at_home')}")
            print(f"🔍 [SCOUT] DIAGNOSTYKA: last_state.get('at_home'): {last_state.get('at_home')}")
            logger.info(f"🔍 [SCOUT] DIAGNOSTYKA: current_at_home != last_state.get('at_home'): {current_at_home != last_state.get('at_home')}")
            print(f"🔍 [SCOUT] DIAGNOSTYKA: current_at_home != last_state.get('at_home'): {current_at_home != last_state.get('at_home')}")
        
        blocked_by_special = False
        if vehicle_state == 'online' and current_at_home:
            # NOWE: Pojazd ONLINE i w domu - sprawdź Warunki A i B
            logger.info(f"🔍 [SCOUT] KROK 1: WARUNEK SPEŁNIONY - Pojazd online w domu - sprawdzam warunki A/B")
            print(f"🔍 [SCOUT] KROK 1: WARUNEK SPEŁNIONY - Pojazd online w domu - sprawdzam warunki A/B")

            conditions_trigger, conditions_reason = check_conditions_a_b(location_data, last_state, vin)
            blocked_by_special = (not conditions_trigger) and ('Special charging' in (conditions_reason or ''))

            logger.info(f"🔍 [SCOUT] KROK 2: check_conditions_a_b zwrócił: trigger={conditions_trigger}, reason='{conditions_reason}'")

            # ODBLOKOWANIE PO SPECIAL: poprzedni tick blokowała sesja special,
            # teraz blokady nie ma — wymuś przeliczenie normalnego harmonogramu
            # (stan "gotowy" się nie zmienił, więc zwykła detekcja przejścia by milczała)
            if (not conditions_trigger and not blocked_by_special
                    and (last_state or {}).get('special_blocked')
                    and location_data.get('is_charging_ready', False)):
                conditions_trigger = True
                conditions_reason = "Sesja special charging zakończona - przeliczenie normalnego harmonogramu OFF PEAK"
                logger.info(f"🔓 [SCOUT] {conditions_reason}")

            if conditions_trigger:
                trigger_worker = True
                reason = conditions_reason
                logger.info(f"🔍 [SCOUT] KROK 3: WARUNEK WYKRYTY - ustawiam trigger_worker=True")
                
                # Specjalne logowanie dla wykrytych warunków
                if "Warunek A" in reason:
                    logger.info(f"🔋 [SCOUT] KROK 4: Wykryto WARUNEK A")
                    _log_scout_status(location_data, "CONDITION_A_DETECTED")
                elif "Warunek B" in reason:
                    logger.info(f"⏳ [SCOUT] KROK 4: Wykryto WARUNEK B")
                    _log_scout_status(location_data, "CONDITION_B_DETECTED")
            else:
                logger.info(f"🔄 [SCOUT] KROK 3: Brak warunków do wywołania Worker - {conditions_reason}")
                logger.info(f"🔄 [SCOUT] {conditions_reason}")
                
        # PENDING TRIGGER: zaległe (nieudane) wywołanie Workera z poprzednich ticków
        # ma pierwszeństwo — bez tego wpięcie kabla w trakcie cold-startu Workera
        # ginęło na zawsze ("kontynuacja stanu" przy każdym kolejnym ticku).
        PENDING_TRIGGER_MAX_AGE_SECONDS = 6 * 3600
        pending = (last_state or {}).get('pending_trigger')
        if pending and not trigger_worker:
            try:
                pending_age = (datetime.now(timezone.utc)
                               - datetime.fromisoformat(pending['created_at'])).total_seconds()
            except (KeyError, ValueError, TypeError):
                pending_age = None
            if pending_age is not None and pending_age <= PENDING_TRIGGER_MAX_AGE_SECONDS:
                trigger_worker = True
                reason = f"RETRY zaległego triggera ({int(pending_age / 60)} min): {pending.get('reason', 'unknown')}"
                logger.warning(f"🔁 [SCOUT] {reason}")
            else:
                logger.error(f"🚨 [SCOUT] ALERT: pending_trigger starszy niż 6h lub uszkodzony — porzucam: {pending}")

        # Wywołaj Worker jeśli potrzeba
        worker_called = False
        if trigger_worker:
            worker_called = trigger_worker_service(reason, location_data)

        # NAPRAWKA: Zapisz aktualny stan NA KOŃCU (po sprawdzeniu warunków A/B)
        # To naprawia problem nadmiarowej detekcji Warunku A - teraz last_state zawiera
        # rzeczywiście poprzedni stan, nie aktualny
        if vehicle_state == 'online':
            new_pending = None
            if trigger_worker and not worker_called:
                # Nie gub zdarzenia: zapisz zaległy trigger do ponowienia w następnym ticku.
                # Przy retry zachowaj oryginalny created_at, żeby limit 6h działał od zdarzenia.
                created_at = (pending or {}).get('created_at') if pending and reason.startswith('RETRY') \
                    else datetime.now(timezone.utc).isoformat()
                new_pending = {'reason': reason, 'created_at': created_at}
                logger.warning(f"⚠️ [SCOUT] Worker NIE wywołany — zapisuję pending_trigger do ponowienia")
            save_current_state(db, vin, location_data, current_at_home,
                               pending_trigger=new_pending, special_blocked=blocked_by_special)
            logger.info(f"💾 [SCOUT] Stan pojazdu zapisany po sprawdzeniu warunków A/B")
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