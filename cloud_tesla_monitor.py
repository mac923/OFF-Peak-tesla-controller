#!/usr/bin/env python3
"""
Cloud Tesla Monitor - Inteligentne monitorowanie pojazdu Tesla w Google Cloud
System ciągłego monitorowania z logowaniem tylko zmian stanu.

NOWA ARCHITEKTURA OPTYMALIZACJI KOSZTÓW:
- Domyślny tryb: Cloud Scheduler + Cloud Run "scale-to-zero" (optymalizacja kosztów)
- Tryb fallback: Ciągłe działanie (poprzednia implementacja)
- Zachowana pełna funkcjonalność Smart Proxy Mode

Harmonogram (UTC):
- 07:00-23:00: sprawdzaj co 15 minut
- 23:00-07:00: sprawdzaj co 60 minut
- 00:00: jednorazowe wybudzenie pojazdu i sprawdzenie stanu

NOWA Logika monitorowania (v2):
- System ZAWSZE monitoruje pojazd w regularnych interwałach
- Loguje tylko ZMIANY stanu, nie powtarzające się informacje
- WARUNEK A (gotowy do ładowania w domu): loguj pierwsze wykrycie + wywołaj OFF PEAK CHARGE API
- WARUNEK B (niegotowy w domu): loguj zmianę z gotowego na niegotowy
- Przyjazd/wyjazd z domu: zawsze loguj
- Przejście online/offline: zawsze loguj
- Inne stany: nie loguj, chyba że zmiana

NOWA Funkcjonalność - Automatyczne zarządzanie harmonogramami ładowania:
- Po pobraniu harmonogramu z OFF PEAK CHARGE API sprawdza czy jest różny od poprzedniego
- Jeśli jest różny: usuwa stare harmonogramy HOME i wysyła nowe z API OFF PEAK CHARGE
- Wymaga Tesla HTTP Proxy dla wysyłania komend do pojazdu

OPTYMALIZACJA KOSZTÓW:
- Cloud Scheduler wywołuje endpoint /run-cycle co 15/60 minut
- Cloud Run skaluje do zera między wywołaniami
- Tryb ciągły dostępny jako fallback (zmienna CONTINUOUS_MODE=true)

Korzyści:
✅ Ciągłe monitorowanie - nie gubi zmian stanu
✅ Minimalne logowanie - tylko istotne wydarzenia  
✅ Śledzenie historii zmian stanu pojazdu
✅ Lepsze debugowanie i diagnostyka
✅ Integracja z OFF PEAK CHARGE API dla optymalizacji ładowania
✅ Automatyczne zarządzanie harmonogramami ładowania
✅ Optymalizacja kosztów Cloud Run (scale-to-zero)

Wymagane sekrety w Google Cloud Secret Manager dla OFF PEAK CHARGE API:
- OFF_PEAK_CHARGE_API_URL: URL do API (opcjonalny, domyślnie: http://localhost:3000/api/external-calculate)
- OFF_PEAK_CHARGE_API_KEY: Klucz autoryzacyjny dla API (wymagany)
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta, timezone
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
import schedule
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytz
import requests
from google.cloud import logging as cloud_logging
from google.cloud import storage
from google.cloud import firestore
from dotenv import load_dotenv
from tesla_controller import TeslaController, ChargeSchedule
from tesla_fleet_api_client import TeslaAuthenticationError
from google.cloud import secretmanager
# BEZPIECZEŃSTWO: Wyłączenie ostrzeżeń SSL dla Tesla HTTP Proxy
# Tesla HTTP Proxy (localhost) używa self-signed certyfikatów SSL
# To jest bezpieczne ponieważ:
# 1. Komunikacja odbywa się lokalnie (localhost/127.0.0.1)
# 2. Tesla HTTP Proxy jest zaufanym komponentem
# 3. Self-signed certyfikaty są standardem dla lokalnych proxy
# 4. Dane są już szyfrowane przez Tesla Fleet API na wyższym poziomie
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Konfiguracja Google Cloud Logging
if os.getenv('GOOGLE_CLOUD_PROJECT'):
    client = cloud_logging.Client()
    client.setup_logging()

# Standardowe logowanie
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# BEZPIECZEŃSTWO: Informacje o konfiguracji SSL
logger.info("🔒 BEZPIECZEŃSTWO: Wyłączono ostrzeżenia SSL urllib3 dla Tesla HTTP Proxy")
logger.info("🔒 Dotyczy tylko localhost z self-signed certyfikatami - bezpieczeństwo zachowane")

def get_secret(secret_name: str, project_id: str) -> Optional[str]:
    """
    Odczytuje sekret z Google Secret Manager
    
    Args:
        secret_name: Nazwa sekretu
        project_id: ID projektu Google Cloud
        
    Returns:
        Wartość sekretu lub None jeśli błąd
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Nie można odczytać sekretu {secret_name}: {e}")
        return None

def _log_simple_status(status: Dict[str, Any], action: str = "") -> None:
    """
    Loguje prosty status pojazdu w formacie: [HH:MM] ✅ VIN=xxx, bateria=xx%, ładowanie=xxx, lokalizacja=xxx
    
    Args:
        status: Słownik ze statusem pojazdu
        action: Opcjonalny opis akcji (np. "wake-up", "check")
    """
    try:
        # Czas warszawski w formacie [HH:MM]
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        now = datetime.now(warsaw_tz)
        time_str = now.strftime("[%H:%M]")
        
        # Podstawowe dane pojazdu
        vin = status.get('vin', 'Unknown')
        vin_short = vin[-4:] if len(vin) > 4 else vin
        battery = status.get('battery_level', 0)
        is_charging_ready = status.get('is_charging_ready', False)
        location = status.get('location_status', 'UNKNOWN')
        is_online = status.get('online', False)
        
        # Formatowanie statusu ładowania
        charging_status = "gotowe" if is_charging_ready else "niegotowe"
        
        # Emoji w zależności od stanu online
        emoji = "✅" if is_online else "❌"
        
        # Formatowanie loga
        if action:
            log_msg = f"{time_str} {emoji} {action} - VIN={vin_short}, bateria={battery}%, ładowanie={charging_status}, lokalizacja={location}"
        else:
            log_msg = f"{time_str} {emoji} VIN={vin_short}, bateria={battery}%, ładowanie={charging_status}, lokalizacja={location}"
        
        logger.info(log_msg)
        
    except Exception as e:
        logger.error(f"Błąd logowania prostego statusu: {e}")

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Handler dla endpoint'ów aplikacji"""
    
    def __init__(self, monitor_instance, *args, **kwargs):
        self.monitor = monitor_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Obsługuje żądania GET"""
        if self.path == '/health':
            self._handle_health_check()
        elif self.path == '/reset':
            self._handle_reset()
        elif self.path == '/reset-tesla-schedules':
            self._handle_reset_tesla_schedules()
        elif self.path == '/debug-env':
            self._handle_debug_env()
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not found')
    
    def do_POST(self):
        """Obsługuje POST request"""
        if self.path == '/run-cycle':
            self._handle_run_cycle()
        elif self.path == '/run-midnight-wake':
            self._handle_midnight_wake()
        else:
            self.send_response(404)
            self.end_headers()
    
    def _handle_health_check(self):
        """Obsługuje sprawdzenie stanu aplikacji"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            
            # Sprawdź aktywne przypadki monitorowania
            active_cases_count = len(self.monitor.active_cases)
            
            response = {
                'status': 'healthy',
                'is_running': True,
                'active_cases': active_cases_count,
                'timestamp': warsaw_time.isoformat(),
                'timezone': 'Europe/Warsaw',
                'mode': 'scheduler'
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode('utf-8'))
            
        except Exception as e:
            logger.error(f"❌ Błąd health check: {e}")
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
            self.wfile.write(json.dumps(response).encode())

    def _handle_debug_env(self):
        """Obsługuje diagnostykę zmiennych środowiskowych Smart Proxy Mode"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            
            response = {
                'timestamp': warsaw_time.isoformat(),
                'timezone': 'Europe/Warsaw',
                'environment_variables': {
                    'TESLA_SMART_PROXY_MODE': os.getenv('TESLA_SMART_PROXY_MODE'),
                    'TESLA_PROXY_AVAILABLE': os.getenv('TESLA_PROXY_AVAILABLE'),
                    'TESLA_HTTP_PROXY_HOST': os.getenv('TESLA_HTTP_PROXY_HOST'),
                    'TESLA_HTTP_PROXY_PORT': os.getenv('TESLA_HTTP_PROXY_PORT')
                },
                'monitor_state': {
                    'smart_proxy_mode': self.monitor.smart_proxy_mode,
                    'proxy_available': self.monitor.proxy_available,
                    'proxy_running': self.monitor.proxy_running
                },
                'debug_info': {
                    'smart_proxy_check': os.getenv('TESLA_SMART_PROXY_MODE') == 'true',
                    'proxy_available_check': os.getenv('TESLA_PROXY_AVAILABLE') == 'true'
                }
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode('utf-8'))
            
        except Exception as e:
            logger.error(f"❌ Błąd debug env: {e}")
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'error',
                'error': str(e)
            }
            
            self.wfile.write(json.dumps(response).encode())
    
    def _handle_reset(self):
        """Obsługuje reset stanu monitorowania"""
        try:
            reset_result = self.monitor.reset_all_monitoring_state()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'reset_completed',
                'message': 'Monitoring state reset successfully - ready for testing from scratch',
                'reset_details': reset_result,
                'next_steps': [
                    'Application will now detect all vehicle states as new',
                    'First OFF PEAK CHARGE API call will be treated as initial',
                    'All harmonogram changes will be logged as first-time events'
                ]
            }
            
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'reset_failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                'timezone': 'Europe/Warsaw'
            }
            
            self.wfile.write(json.dumps(response).encode())
    
    def _handle_reset_tesla_schedules(self):
        """Obsługuje reset harmonogramów Tesla"""
        try:
            reset_result = self.monitor.reset_tesla_home_schedules()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'tesla_schedules_reset_completed' if reset_result.get('success') else 'tesla_schedules_reset_failed',
                'message': 'Tesla HOME schedules reset completed - all HOME schedules removed' if reset_result.get('success') else 'Tesla HOME schedules reset failed',
                'reset_details': reset_result,
                'next_steps': [
                    'All HOME schedules have been removed from Tesla',
                    'New schedules will be added based on OFF PEAK CHARGE API data',
                    'Monitor vehicle for new charging schedule events'
                ] if reset_result.get('success') else [
                    'Check Tesla HTTP Proxy availability',
                    'Verify Tesla API authorization',
                    'Try manual schedule removal through Tesla app'
                ]
            }
            
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'tesla_schedules_reset_error',
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                'timezone': 'Europe/Warsaw'
            }
            
            self.wfile.write(json.dumps(response).encode())
    
    def _handle_run_cycle(self):
        """Obsługuje wywołanie cyklu monitorowania przez Cloud Scheduler"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 📅 Cloud Scheduler: Rozpoczęcie cyklu monitorowania")
            
            # Wykonaj cykl monitorowania
            cycle_result = self.monitor.run_monitoring_cycle()

            if cycle_result == 'failed':
                raise RuntimeError("Monitoring cycle failed")

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'status': 'cycle_completed' if cycle_result == 'ok' else 'cycle_skipped_lock_busy',
                'message': 'Monitoring cycle completed successfully' if cycle_result == 'ok' else 'Another cycle in progress',
                'timestamp': warsaw_time.isoformat(),
                'timezone': 'Europe/Warsaw',
                'trigger': 'cloud_scheduler'
            }
            
            logger.info(f"{time_str} ✅ Cloud Scheduler: Cykl monitorowania zakończony")
            
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode('utf-8'))
            
        except Exception as e:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.error(f"{time_str} ❌ Cloud Scheduler: Błąd cyklu monitorowania: {e}")
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'cycle_failed',
                'error': str(e),
                'timestamp': warsaw_time.isoformat(),
                'timezone': 'Europe/Warsaw',
                'trigger': 'cloud_scheduler'
            }
            
            self.wfile.write(json.dumps(response).encode())
    
    def _handle_midnight_wake(self):
        """Obsługuje nocne wybudzenie pojazdu przez Cloud Scheduler"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 🌙 Cloud Scheduler: Rozpoczęcie nocnego wybudzenia")
            
            # Wykonaj nocne wybudzenie
            self.monitor.run_midnight_wake_check()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'midnight_wake_completed',
                'message': 'Midnight wake check completed successfully',
                'timestamp': warsaw_time.isoformat(),
                'timezone': 'Europe/Warsaw',
                'trigger': 'cloud_scheduler'
            }
            
            logger.info(f"{time_str} ✅ Cloud Scheduler: Nocne wybudzenie zakończone")
            
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode('utf-8'))
            
        except Exception as e:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.error(f"{time_str} ❌ Cloud Scheduler: Błąd nocnego wybudzenia: {e}")
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'midnight_wake_failed',
                'error': str(e),
                'timestamp': warsaw_time.isoformat(),
                'timezone': 'Europe/Warsaw',
                'trigger': 'cloud_scheduler'
            }
            
            self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        """Wyłącz standardowe logowanie HTTP serwera"""
        pass

class MonitoringState(Enum):
    """Stany monitorowania pojazdu"""
    IDLE = "idle"
    WAITING_FOR_OFFLINE = "waiting_for_offline"
    VEHICLE_AWOKEN = "vehicle_awoken"

@dataclass
class VehicleMonitoringCase:
    """Reprezentuje aktywny przypadek monitorowania pojazdu"""
    case_id: str
    vehicle_vin: str
    start_time: datetime
    state: MonitoringState
    last_battery_level: Optional[int] = None
    last_check_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """Konwertuje do słownika dla serializacji"""
        return {
            'case_id': self.case_id,
            'vehicle_vin': self.vehicle_vin,
            'start_time': self.start_time.isoformat(),
            'state': self.state.value,
            'last_battery_level': self.last_battery_level,
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'VehicleMonitoringCase':
        """Tworzy instancję z słownika"""
        return cls(
            case_id=data['case_id'],
            vehicle_vin=data['vehicle_vin'],
            start_time=datetime.fromisoformat(data['start_time']),
            state=MonitoringState(data['state']),
            last_battery_level=data.get('last_battery_level'),
            last_check_time=datetime.fromisoformat(data['last_check_time']) if data.get('last_check_time') else None
        )

class CloudTeslaMonitor:
    """Główna klasa monitorowania Tesla w Google Cloud"""
    
    def __init__(self):
        """Inicjalizacja monitora"""
        load_dotenv()
        
        # Konfiguracja strefy czasowej - CZAS WARSZAWSKI
        self.timezone = pytz.timezone('Europe/Warsaw')
        logger.info(f"Monitor skonfigurowany dla strefy czasowej: {self.timezone}")
        
        # Konfiguracja Tesla z diagnostyką połączenia
        logger.info("🔧 Inicjalizacja TeslaController...")
        
        # Sprawdź konfigurację Smart Tesla HTTP Proxy
        self.smart_proxy_mode = os.getenv('TESLA_SMART_PROXY_MODE') == 'true'
        self.proxy_available = os.getenv('TESLA_PROXY_AVAILABLE') == 'true'
        proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST')
        proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT')
        
        if self.smart_proxy_mode:
            logger.info("🔧 Smart Proxy Mode włączony")
            if self.proxy_available:
                logger.info(f"✅ Tesla HTTP Proxy dostępny: {proxy_host}:{proxy_port}")
                logger.info("🔧 Proxy uruchamiany on-demand dla komend")
            else:
                logger.warning("⚠️ Tesla HTTP Proxy niedostępny - tylko monitoring")
        elif proxy_host and proxy_port:
            logger.info(f"🔗 Tesla HTTP Proxy skonfigurowane: {proxy_host}:{proxy_port}")
        else:
            logger.warning("⚠️ Tesla HTTP Proxy NIE jest skonfigurowane - używam bezpośrednio Fleet API")
            logger.warning("⚠️ Usuwanie harmonogramów może nie działać bez Tesla HTTP Proxy")
        
        # Stan proxy
        self.proxy_process = None
        self.proxy_running = False
        
        self.tesla_controller = TeslaController()
        
        # NAPRAWKA: Test połączenia z Tesla HTTP Proxy TYLKO jeśli jest skonfigurowany i private key gotowy
        if proxy_host and proxy_port and not self.smart_proxy_mode:
            # Tylko dla non-smart proxy mode - test połączenia podczas startup
            private_key_ready = os.getenv('TESLA_PRIVATE_KEY_READY', 'false').lower() == 'true'
            if private_key_ready or os.path.exists('private-key.pem'):
                self._test_tesla_proxy_connection(proxy_host, proxy_port)
            else:
                logger.warning("⚠️ Private key niegotowy - pomijam test Tesla HTTP Proxy")
        elif self.smart_proxy_mode:
            logger.info("💡 Smart Proxy Mode - proxy będzie testowany on-demand")
        
        # Konfiguracja Google Cloud
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.bucket_name = os.getenv('GOOGLE_CLOUD_STORAGE_BUCKET', 'tesla-monitor-data')
        
        # Inicjalizacja klientów Google Cloud
        self.storage_client = storage.Client() if self.project_id else None
        self.firestore_client = firestore.Client() if self.project_id else None
        
        # Stan monitorowania
        self.active_cases: Dict[str, VehicleMonitoringCase] = {}
        self.is_running = False
        
        # Śledzenie poprzedniego stanu pojazdu dla logowania tylko zmian
        self.last_vehicle_state: Dict[str, Any] = {}
        
        # HTTP server dla health check
        self.http_server = None
        self.http_thread = None
        
        # NOWE: Cache dla harmonogramów OFF PEAK CHARGE
        # (inicjalizacja PRZED _load_monitoring_state, które może je wypełnić z Cloud Storage)
        self.last_off_peak_schedules: Dict[str, Dict] = {}  # VIN -> harmonogram hash
        self.last_tesla_schedules_home: Dict[str, List[Dict]] = {}  # VIN -> lista harmonogramów HOME

        # Ładowanie stanu z Cloud Storage
        self._load_monitoring_state()

        # Identyfikator instancji dla lease-locka cyklu (Firestore)
        self.instance_id = uuid.uuid4().hex

        # Retry-budget: licznik nieudanych prób zastosowania harmonogramu per VIN
        # (chroni przed spamem komend do pojazdu przy trwałym błędzie)
        self.schedule_apply_attempts: Dict[str, Dict[str, Any]] = {}
        
    def _load_monitoring_state(self):
        """Ładuje stan monitorowania z Cloud Storage"""
        try:
            if not self.storage_client:
                logger.info("Brak konfiguracji Google Cloud Storage - używam lokalnego stanu")
                return
                
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob('monitoring_state.json')
            
            if blob.exists():
                state_data = json.loads(blob.download_as_text())
                self.active_cases = {
                    case_id: VehicleMonitoringCase.from_dict(case_data)
                    for case_id, case_data in state_data.get('active_cases', {}).items()
                }

                # PERSYSTENCJA STANU DECYZYJNEGO (Faza 4): bez tego każdy cold start
                # (scale-to-zero!) widział pusty stan → pełny rewrite harmonogramów
                # przy każdym triggerze z wpiętym autem. TTL 24h: stan starszy niż doba
                # traktujemy jak pierwszy kontakt (bateria/plan mogły się zmienić).
                state_age_ok = False
                last_update_str = state_data.get('last_update')
                if last_update_str:
                    try:
                        last_update = datetime.fromisoformat(last_update_str)
                        state_age_ok = (self._get_warsaw_time() - last_update) <= timedelta(hours=24)
                    except (ValueError, TypeError):
                        state_age_ok = False

                if state_age_ok:
                    self.last_off_peak_schedules = state_data.get('last_off_peak_schedules', {})
                    self.last_vehicle_state = state_data.get('last_vehicle_state', {})
                    logger.info(f"Załadowano stan decyzyjny: {len(self.last_off_peak_schedules)} hashy planów, "
                                f"{len(self.last_vehicle_state)} stanów pojazdów")
                else:
                    logger.info("Stan decyzyjny starszy niż 24h lub bez znacznika czasu - ignoruję (pierwszy kontakt)")

                logger.info(f"Załadowano stan monitorowania: {len(self.active_cases)} aktywnych przypadków")
            else:
                logger.info("Brak zapisanego stanu monitorowania - rozpoczynam z pustym stanem")

        except Exception as e:
            logger.error(f"Błąd ładowania stanu monitorowania: {e}")
    
    def _save_monitoring_state(self):
        """Zapisuje stan monitorowania do Cloud Storage"""
        try:
            if not self.storage_client:
                logger.debug("Brak konfiguracji Google Cloud Storage - pomijam zapis stanu")
                return
                
            state_data = {
                'active_cases': {
                    case_id: case.to_dict()
                    for case_id, case in self.active_cases.items()
                },
                # Stan decyzyjny musi przeżyć scale-to-zero (patrz _load_monitoring_state)
                'last_off_peak_schedules': self.last_off_peak_schedules,
                'last_vehicle_state': self.last_vehicle_state,
                'last_update': self._get_warsaw_time().isoformat()
            }
            
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob('monitoring_state.json')
            blob.upload_from_string(json.dumps(state_data, indent=2))

            logger.debug("Stan monitorowania zapisany do Cloud Storage")

        except Exception as e:
            logger.error(f"Błąd zapisu stanu monitorowania: {e}")

    # ========== LEASE-LOCK CYKLU (Firestore) ==========

    CYCLE_LOCK_TTL_SECONDS = 300  # zgodne z timeoutSeconds Cloud Run — ubita instancja nie blokuje dłużej

    def _acquire_cycle_lock(self) -> bool:
        """
        Przejmuje lease-lock cyklu w Firestore (locks/monitoring_cycle).
        Chroni przed równoległymi cyklami (retry Cloud Schedulera, trigger Scout
        nakładający się na failsafe/midnight, druga instancja Cloud Run).

        Returns:
            bool: True gdy lock przejęty (lub tryb lokalny bez Firestore)
        """
        if not self.firestore_client:
            return True
        lock_ref = self.firestore_client.collection('locks').document('monitoring_cycle')
        now = datetime.now(timezone.utc)
        transaction = self.firestore_client.transaction()

        @firestore.transactional
        def _try_acquire(tx):
            snapshot = lock_ref.get(transaction=tx)
            if snapshot.exists:
                data = snapshot.to_dict() or {}
                expires_at = data.get('expires_at')
                if expires_at is not None and expires_at > now:
                    return False
            tx.set(lock_ref, {
                'owner': self.instance_id,
                'acquired_at': now,
                'expires_at': now + timedelta(seconds=self.CYCLE_LOCK_TTL_SECONDS)
            })
            return True

        try:
            acquired = _try_acquire(transaction)
            if not acquired:
                logger.info("🔒 Cykl monitorowania już trwa (lock zajęty) — pomijam ten trigger")
            return acquired
        except Exception as e:
            # Lock to zabezpieczenie, nie twarda zależność — awaria Firestore nie może zatrzymać systemu
            logger.warning(f"⚠️ Błąd akwizycji locka cyklu ({e}) — kontynuuję bez locka")
            return True

    def _release_cycle_lock(self):
        """Zwalnia lease-lock cyklu (tylko jeśli należy do tej instancji)."""
        if not self.firestore_client:
            return
        try:
            lock_ref = self.firestore_client.collection('locks').document('monitoring_cycle')
            snapshot = lock_ref.get()
            if snapshot.exists and (snapshot.to_dict() or {}).get('owner') == self.instance_id:
                lock_ref.delete()
        except Exception as e:
            logger.warning(f"⚠️ Błąd zwalniania locka cyklu: {e} (wygaśnie sam po TTL)")

    # ========== RETRY-BUDGET ZASTOSOWANIA HARMONOGRAMU ==========

    SCHEDULE_APPLY_MAX_ATTEMPTS = 3
    SCHEDULE_APPLY_COOLDOWN_SECONDS = 2 * 3600

    def _schedule_apply_blocked(self, vehicle_vin: str, schedule_hash: str) -> bool:
        """
        True gdy dla tego planu wyczerpano SCHEDULE_APPLY_MAX_ATTEMPTS prób
        i trwa cooldown. Chroni pojazd przed spamem wake/add/remove co 15 min
        przy trwałym błędzie (np. proxy padło na stałe).
        """
        entry = self.schedule_apply_attempts.get(vehicle_vin)
        if not entry or entry.get('hash') != schedule_hash:
            return False
        if entry.get('attempts', 0) < self.SCHEDULE_APPLY_MAX_ATTEMPTS:
            return False
        elapsed = time.time() - entry.get('last_attempt_ts', 0)
        if elapsed >= self.SCHEDULE_APPLY_COOLDOWN_SECONDS:
            self.schedule_apply_attempts.pop(vehicle_vin, None)
            return False
        remaining_min = int((self.SCHEDULE_APPLY_COOLDOWN_SECONDS - elapsed) / 60)
        logger.error(
            f"🚨 ALERT: {entry.get('attempts')} nieudanych prób zastosowania harmonogramu dla "
            f"{vehicle_vin[-4:]} — cooldown jeszcze {remaining_min} min (hash {schedule_hash[:8]})"
        )
        return True

    def _record_schedule_apply_failure(self, vehicle_vin: str, schedule_hash: str):
        entry = self.schedule_apply_attempts.get(vehicle_vin)
        if entry and entry.get('hash') == schedule_hash:
            entry['attempts'] = entry.get('attempts', 0) + 1
            entry['last_attempt_ts'] = time.time()
        else:
            entry = {'hash': schedule_hash, 'attempts': 1, 'last_attempt_ts': time.time()}
            self.schedule_apply_attempts[vehicle_vin] = entry
        logger.warning(
            f"⚠️ Nieudana próba {entry['attempts']}/{self.SCHEDULE_APPLY_MAX_ATTEMPTS} "
            f"zastosowania harmonogramu dla {vehicle_vin[-4:]}"
        )

    def _clear_schedule_apply_failures(self, vehicle_vin: str):
        self.schedule_apply_attempts.pop(vehicle_vin, None)

    # ========== WYRÓWNANIE STANU ŁADOWANIA Z PLANEM (Faza 2) ==========

    def _current_time_overlaps_schedules(self, schedules: List['ChargeSchedule']) -> bool:
        """Sprawdza, czy któreś włączone okno harmonogramu pokrywa obecną chwilę (czas warszawski)."""
        now = self._get_warsaw_time()
        now_min = now.hour * 60 + now.minute
        for s in schedules:
            if not s.enabled or s.start_time is None or s.end_time is None:
                continue
            start = s.start_time % 1440
            end = s.end_time % 1440
            if start <= end:
                if start <= now_min < end:
                    return True
            else:
                # Okno przez północ (np. 23:00-06:00)
                if now_min >= start or now_min < end:
                    return True
        return False

    def _get_protected_schedule_ids(self, vehicle_vin: str) -> Optional[set]:
        """
        ID harmonogramów należących do sesji special charging SCHEDULED/ACTIVE —
        zwykły cykl NIE może ich usuwać (wcześniej wymiatał je jako "stare okna HOME",
        po cichu kasując sesję special w trakcie jej trwania).

        Returns:
            set: chronione ID ([] gdy brak sesji),
            None: błąd odczytu — wołający musi przerwać usuwanie (nie wie, co chronić)
        """
        if not self.firestore_client:
            return set()
        try:
            sessions_ref = self.firestore_client.collection('special_charging_sessions')
            query = sessions_ref.where('vin', '==', vehicle_vin).where('status', 'in', ['ACTIVE', 'SCHEDULED'])
            protected = set()
            for doc in query.stream():
                for schedule_id in (doc.to_dict() or {}).get('tesla_schedule_ids') or []:
                    protected.add(schedule_id)
            if protected:
                logger.info(f"🔒 Chronione harmonogramy special dla {vehicle_vin[-4:]}: {sorted(protected)}")
            return protected
        except Exception as e:
            logger.error(f"❌ Błąd odczytu chronionych harmonogramów special: {e}")
            return None

    def _has_active_special_session(self, vehicle_vin: str) -> bool:
        """True gdy w Firestore istnieje sesja special charging SCHEDULED/ACTIVE dla pojazdu."""
        if not self.firestore_client:
            return False
        try:
            sessions_ref = self.firestore_client.collection('special_charging_sessions')
            query = sessions_ref.where('vin', '==', vehicle_vin).where('status', 'in', ['ACTIVE', 'SCHEDULED'])
            return len(list(query.stream())) > 0
        except Exception as e:
            # Przy błędzie odczytu załóż ostrożnie, że sesja może istnieć —
            # lepiej nie zatrzymać special charging niż zatrzymać go błędnie
            logger.warning(f"⚠️ Błąd sprawdzania sesji special charging: {e} — zakładam, że sesja istnieje")
            return True

    def _align_charging_with_plan(self, schedules: List['ChargeSchedule'], vehicle_vin: str,
                                  vehicle_status: Optional[Dict[str, Any]]):
        """
        Po zastosowaniu nowego planu wyrównuje faktyczny stan ładowania:
        - okno pokrywa "teraz", a pojazd nie ładuje → charge_start
          (Tesla po dodaniu okna w jego trakcie potrafi czekać do następnej granicy),
        - pojazd ładuje, a żadne okno nie pokrywa "teraz" → charge_stop
          (scenariusz: wpięcie w trakcie starego okna, które właśnie usunęliśmy).

        charge_stop jest gated:
        - CHARGE_STOP_ENFORCE=false (domyślnie) → tylko log (shadow mode),
        - bateria < MIN_SOC_FORCE_CHARGE (domyślnie 30%) → nie zatrzymuj
          (niski poziom baterii ma priorytet nad taryfą, także przy ładowaniu
          uruchomionym ręcznie przez użytkownika),
        - aktywna/zaplanowana sesja special charging → nie zatrzymuj.
        Błędy tej fazy nie unieważniają zastosowanego planu (best-effort, głośno logowane).
        """
        if not vehicle_status:
            return
        try:
            charging_state = vehicle_status.get('charging_state', 'Unknown')
            battery_level = vehicle_status.get('battery_level', 0)
            overlap = self._current_time_overlaps_schedules(schedules)
            use_proxy = bool(getattr(self.tesla_controller.fleet_api, 'proxy_url', None))

            if overlap and charging_state in ('Stopped', 'NoPower', 'Complete'):
                if charging_state == 'Complete':
                    return  # naładowany do limitu — nie ma czego startować
                logger.info(f"⚡ Okno harmonogramu pokrywa obecną godzinę, a pojazd nie ładuje — wysyłam charge_start")
                start_ok = self.tesla_controller.fleet_api.charge_start(vehicle_vin, use_proxy=use_proxy)
                self._log_event(
                    message="Auto charge_start (window overlaps now)",
                    vehicle_vin=vehicle_vin,
                    extra_data={'operation': 'align_charging', 'action': 'charge_start', 'success': start_ok}
                )
                if not start_ok:
                    logger.error(f"❌ charge_start nie powiódł się")

            elif not overlap and charging_state == 'Charging':
                enforce = os.getenv('CHARGE_STOP_ENFORCE', 'false').lower() == 'true'
                min_soc = int(os.getenv('MIN_SOC_FORCE_CHARGE', '30'))

                if battery_level < min_soc:
                    logger.info(f"🔋 Pojazd ładuje poza oknem, ale bateria {battery_level}% < {min_soc}% — NIE zatrzymuję")
                    return
                if self._has_active_special_session(vehicle_vin):
                    logger.info(f"🔋 Pojazd ładuje poza oknem, ale trwa sesja special charging — NIE zatrzymuję")
                    return

                if not enforce:
                    # SHADOW MODE: tylko log do porównania z rzeczywistością przed włączeniem enforce
                    logger.warning(f"👻 [SHADOW] Tu wysłałbym charge_stop: ładowanie {battery_level}% poza oknem taniej taryfy "
                                   f"(włącz CHARGE_STOP_ENFORCE=true po weryfikacji)")
                    self._log_event(
                        message="[SHADOW] charge_stop would be sent (charging outside plan window)",
                        vehicle_vin=vehicle_vin,
                        extra_data={'operation': 'align_charging', 'action': 'charge_stop_shadow',
                                    'battery_level': battery_level}
                    )
                    return

                logger.warning(f"🛑 Pojazd ładuje poza oknem taniej taryfy ({battery_level}%) — wysyłam charge_stop")
                stop_ok = self.tesla_controller.fleet_api.charge_stop(vehicle_vin, use_proxy=use_proxy)
                self._log_event(
                    message="Auto charge_stop (charging outside plan window)",
                    vehicle_vin=vehicle_vin,
                    extra_data={'operation': 'align_charging', 'action': 'charge_stop', 'success': stop_ok,
                                'battery_level': battery_level}
                )
                if not stop_ok:
                    logger.error(f"❌ charge_stop nie powiódł się — pojazd może ładować w drogiej taryfie")
        except Exception as e:
            logger.error(f"❌ Błąd wyrównania stanu ładowania z planem: {e}")
    
    def _get_warsaw_time(self) -> datetime:
        """
        Zwraca aktualny czas w strefie czasowej warszawskiej
        
        Returns:
            datetime: Czas w strefie Europe/Warsaw
        """
        return datetime.now(self.timezone)
    
    def _call_off_peak_charge_api(self, battery_level: int, vehicle_vin: str) -> Optional[Dict[str, Any]]:
        """
        Wywołuje OFF PEAK CHARGE API do obliczenia optymalnego harmonogramu ładowania
        
        Args:
            battery_level: Aktualny poziom baterii (%)
            vehicle_vin: VIN pojazdu
            
        Returns:
            Dict z odpowiedzią API lub fallback w przypadku błędu
        """
        
        def _create_fallback_response(reason: str) -> Dict[str, Any]:
            """
            Fallback przy awarii OFF PEAK API: domyślne okno nocne (env
            FALLBACK_CHARGE_START_HOUR/FALLBACK_CHARGE_END_HOUR, domyślnie 23-6).

            Czasy w pełnym ISO 8601 ze strefą — poprzedni format "13:00" nie
            przechodził przez fromisoformat() w konwerterze i slot po cichu
            znikał (pojazd zostawał z samym oknem-strażnikiem). Do tego 13:00-15:00
            wypadało w godzinach szczytu cenowego.
            """
            logger.warning(f"⚠️ Tworzę fallback harmonogram nocny (powód: {reason})")

            start_hour = int(os.getenv('FALLBACK_CHARGE_START_HOUR', '23'))
            end_hour = int(os.getenv('FALLBACK_CHARGE_END_HOUR', '6'))

            now = self._get_warsaw_time()
            end_today = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)

            if now < end_today:
                # Jesteśmy w trakcie okna nocnego (np. 01:30) — ładuj od teraz do końca okna
                start_dt = now.replace(second=0, microsecond=0)
                end_dt = end_today
            else:
                # Dzień — zaplanuj najbliższą noc: dziś start_hour → jutro end_hour
                start_dt = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                if start_dt <= now:
                    start_dt = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                end_dt = (now + timedelta(days=1)).replace(hour=end_hour, minute=0, second=0, microsecond=0)

            duration_h = max((end_dt - start_dt).total_seconds() / 3600, 0)
            logger.info(f"🔄 FALLBACK: okno nocne {start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%Y-%m-%d %H:%M')}")

            return {
                "success": True,
                "fallback": True,
                "fallback_reason": reason,
                "data": {
                    "summary": {
                        "scheduledSlots": 1,
                        "totalEnergy": round(11 * duration_h, 1),  # ~11 kW * czas okna
                        "totalCost": 0,
                        "averagePrice": 0
                    },
                    "chargingSchedule": [{
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "charge_amount": round(11 * duration_h, 1),
                        "cost": 0
                    }]
                }
            }

        try:
            # Konfiguracja API - pobierz z Google Cloud Secrets
            if not self.project_id:
                logger.warning("⚠️ Brak konfiguracji Google Cloud Project - nie można pobrać sekretów OFF PEAK CHARGE API")
                return _create_fallback_response("brak konfiguracji Google Cloud")
            
            # OPTYMALIZACJA: Pobierz URL i klucz API z ENV (zamiast Secret Manager API)
            # Sekrety są zaciągane jako ENV w cloud-run-service-worker.yaml
            api_url = os.getenv('OFF_PEAK_CHARGE_API_URL')
            if not api_url:
                api_url = 'http://localhost:3000/api/external-calculate'
                logger.info(f"⚠️ Używam domyślnego URL OFF PEAK CHARGE API: {api_url}")

            api_key = os.getenv('OFF_PEAK_CHARGE_API_KEY')
            if not api_key:
                logger.warning("⚠️ Brak zmiennej środowiskowej 'OFF_PEAK_CHARGE_API_KEY'")
                return _create_fallback_response("brak klucza API")
            
            # Przygotuj dane żądania zgodnie z dokumentacją.
            # Parametry pojazdu z env — wcześniej zahardkodowane wartości liczyły
            # plan dla "statystycznego" auta, nie rzeczywistego
            request_data = {
                "batteryLevel": battery_level,
                "batteryCapacity": float(os.getenv('VEHICLE_BATTERY_CAPACITY_KWH', '75')),
                "consumption": float(os.getenv('VEHICLE_CONSUMPTION_KWH_100KM', '18')),
                "dailyMileage": float(os.getenv('VEHICLE_DAILY_MILEAGE_KM', '50')),
                "chargeLimits": {
                    "optimalUpper": float(os.getenv('CHARGE_LIMIT_OPTIMAL_UPPER', '0.8')),
                    "optimalLower": float(os.getenv('CHARGE_LIMIT_OPTIMAL_LOWER', '0.5')),
                    "emergency": float(os.getenv('CHARGE_LIMIT_EMERGENCY', '0.2')),
                    "chargingRate": float(os.getenv('VEHICLE_CHARGING_RATE_KW', '11'))
                }
            }
            
            # Przygotuj headers
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': api_key
            }
            
            # Loguj żądanie
            warsaw_time = self._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            logger.info(f"{time_str} 🔄 Wywołuję OFF PEAK CHARGE API")
            logger.info(f"URL: {api_url}")
            logger.info(f"Dane: {json.dumps(request_data, indent=2)}")
            
            # Wykonaj żądanie HTTP POST z timeout'em
            response = requests.post(
                api_url,
                json=request_data,
                headers=headers,
                timeout=30  # 30 sekund timeout
            )
            
            # Sprawdź status odpowiedzi
            if response.status_code == 200:
                response_data = response.json()
                
                # Loguj pomyślną odpowiedź
                logger.info(f"{time_str} ✅ OFF PEAK CHARGE API - sukces")
                logger.info("=== ODPOWIEDŹ OFF PEAK CHARGE API ===")
                logger.info(json.dumps(response_data, indent=2, ensure_ascii=False))
                logger.info("===================================")
                
                # Dodatkowe logowanie kluczowych informacji
                if response_data.get('success') and 'data' in response_data:
                    data = response_data['data']
                    summary = data.get('summary', {})
                    schedule_count = summary.get('scheduledSlots', 0)
                    total_energy = summary.get('totalEnergy', 0)
                    total_cost = summary.get('totalCost', 0)
                    avg_price = summary.get('averagePrice', 0)
                    
                    logger.info(f"{time_str} 📊 Harmonogram: {schedule_count} sesji, {total_energy} kWh, {total_cost:.2f} zł (średnia: {avg_price:.3f} zł/kWh)")
                    
                    # Loguj harmonogram ładowania
                    charging_schedule = data.get('chargingSchedule', [])
                    for i, slot in enumerate(charging_schedule, 1):
                        start_time = slot.get('start_time', '')
                        end_time = slot.get('end_time', '')
                        charge_amount = slot.get('charge_amount', 0)
                        cost = slot.get('cost', 0)
                        logger.info(f"{time_str} ⚡ Sesja #{i}: {start_time} - {end_time}, {charge_amount} kWh, {cost:.2f} zł")
                
                return response_data
            else:
                logger.error(f"{time_str} ❌ Błąd OFF PEAK CHARGE API - status {response.status_code}")
                return _create_fallback_response(f"błąd HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Błąd połączenia z OFF PEAK CHARGE API: {str(e)}")
            return _create_fallback_response(f"błąd połączenia: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Nieoczekiwany błąd podczas wywoływania OFF PEAK CHARGE API: {str(e)}")
            return _create_fallback_response(f"nieoczekiwany błąd: {str(e)}")
    
    def _log_event(self, message: str, battery_level: Optional[int] = None, 
                   vehicle_vin: Optional[str] = None, extra_data: Optional[Dict] = None):
        """
        Loguje zdarzenie do Google Cloud Logging z czasem warszawskim
        
        Args:
            message: Wiadomość do zalogowania
            battery_level: Poziom baterii (opcjonalnie)
            vehicle_vin: VIN pojazdu (opcjonalnie)
            extra_data: Dodatkowe dane (opcjonalnie)
        """
        warsaw_time = self._get_warsaw_time()
        log_data = {
            'timestamp': warsaw_time.isoformat(),
            'timestamp_utc': datetime.utcnow().isoformat(),
            'timezone': str(self.timezone),
            'event_message': message,  # Zmieniono z 'message' na 'event_message'
        }
        
        if battery_level is not None:
            log_data['battery_level'] = battery_level
            
        if vehicle_vin:
            log_data['vehicle_vin'] = vehicle_vin
            
        if extra_data:
            log_data.update(extra_data)
        
        # Logowanie do standardowego loggera (bez extra - to powodowało konflikt)
        logger.info(f"Tesla Monitor: {message}")
        
        # Dodatkowe logowanie do Cloud Logging jeśli dostępne
        if self.firestore_client:
            try:
                collection = self.firestore_client.collection('tesla_monitor_logs')
                collection.add(log_data)
            except Exception as e:
                logger.error(f"Błąd zapisu do Firestore: {e}")
    
    def _get_monitoring_schedule_interval(self) -> int:
        """
        Zwraca interwał monitorowania w minutach na podstawie aktualnej godziny warszawskiej
        
        Returns:
            int: Interwał w minutach (15 lub 60)
        """
        warsaw_time = self._get_warsaw_time()
        current_hour = warsaw_time.hour
        
        # CZAS WARSZAWSKI (Europe/Warsaw):
        # 07:00-23:00 (7-22): co 15 minut
        # 23:00-07:00 (23-6): co 60 minut
        if 7 <= current_hour <= 22:
            return 15
        else:
            return 60
    
    def reset_vehicle_state(self, vehicle_vin: str = None):
        """
        Resetuje zapamiętany stan pojazdu aby wymusić wykrycie jako nowy stan
        
        Args:
            vehicle_vin: VIN pojazdu do zresetowania (jeśli None, resetuje wszystkie)
        """
        if vehicle_vin:
            if vehicle_vin in self.last_vehicle_state:
                del self.last_vehicle_state[vehicle_vin]
                logger.info(f"🔄 Zresetowano stan pojazdu {vehicle_vin[-4:]}")
        else:
            self.last_vehicle_state.clear()
            logger.info("🔄 Zresetowano stan wszystkich pojazdów")
    
    def reset_all_monitoring_state(self):
        """
        Kompletny reset stanu monitorowania - wszystkie dane wracają do stanu początkowego
        """
        warsaw_time = self._get_warsaw_time()
        time_str = warsaw_time.strftime("[%H:%M]")
        
        logger.info(f"{time_str} 🔄 === KOMPLETNY RESET STANU MONITOROWANIA ===")
        
        # 1. Reset stanów pojazdów
        vehicles_count = len(self.last_vehicle_state)
        self.last_vehicle_state.clear()
        logger.info(f"{time_str} ✅ Zresetowano stany {vehicles_count} pojazdów")
        
        # 2. Reset aktywnych przypadków
        cases_count = len(self.active_cases)
        self.active_cases.clear()
        logger.info(f"{time_str} ✅ Zresetowano {cases_count} aktywnych przypadków monitorowania")
        
        # 3. Reset cache harmonogramów OFF PEAK
        off_peak_count = len(self.last_off_peak_schedules)
        self.last_off_peak_schedules.clear()
        logger.info(f"{time_str} ✅ Zresetowano cache {off_peak_count} harmonogramów OFF PEAK")
        
        # 4. Reset cache harmonogramów Tesla HOME
        tesla_home_count = len(self.last_tesla_schedules_home)
        self.last_tesla_schedules_home.clear()
        logger.info(f"{time_str} ✅ Zresetowano cache {tesla_home_count} harmonogramów Tesla HOME")
        
        # 5. Zapisz pusty stan do Cloud Storage
        try:
            self._save_monitoring_state()
            logger.info(f"{time_str} ✅ Zapisano pusty stan do Cloud Storage")
        except Exception as e:
            logger.error(f"{time_str} ❌ Błąd zapisu pustego stanu: {e}")
        
        # 6. Log zdarzenia resetu
        self._log_event(
            message="Complete monitoring state reset performed",
            extra_data={
                'action': 'complete_reset',
                'reset_vehicle_states': vehicles_count,
                'reset_active_cases': cases_count,
                'reset_off_peak_cache': off_peak_count,
                'reset_tesla_home_cache': tesla_home_count,
                'reset_timestamp': warsaw_time.isoformat(),
                'reset_reason': 'manual_testing_reset'
            }
        )
        
        logger.info(f"{time_str} 🎉 RESET ZAKOŃCZONY - aplikacja gotowa do testowania od początku")
        
        return {
            'reset_completed': True,
            'reset_timestamp': warsaw_time.isoformat(),
            'reset_counts': {
                'vehicle_states': vehicles_count,
                'active_cases': cases_count,
                'off_peak_cache': off_peak_count,
                'tesla_home_cache': tesla_home_count
            }
        }
    
    def reset_tesla_home_schedules(self, vehicle_vin: str = None) -> Dict[str, Any]:
        """
        Resetuje wszystkie harmonogramy HOME w Tesla - pobiera aktualne harmonogramy HOME i wszystkie usuwa
        
        Args:
            vehicle_vin: VIN pojazdu (opcjonalny, jeśli nie podano użyje pierwszego dostępnego)
            
        Returns:
            Dict z wynikami operacji
        """
        warsaw_time = self._get_warsaw_time()
        time_str = warsaw_time.strftime("[%H:%M]")
        
        logger.info(f"{time_str} 🔄 === RESET HARMONOGRAMÓW HOME W TESLA ===")
        
        try:
            # 1. Sprawdź połączenie z Tesla Controller
            if not self.tesla_controller.connect():
                error_msg = "Nie można połączyć się z Tesla API"
                logger.error(f"{time_str} ❌ {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'timestamp': warsaw_time.isoformat()
                }
            
            # 2. Wybierz pojazd
            if not vehicle_vin:
                # Użyj pierwszego dostępnego pojazdu
                if self.tesla_controller.vehicles:
                    vehicle_vin = self.tesla_controller.vehicles[0].get('vin')
                    logger.info(f"{time_str} 🚗 Użyto pierwszego dostępnego pojazdu: {vehicle_vin[-4:]}")
                else:
                    error_msg = "Brak dostępnych pojazdów"
                    logger.error(f"{time_str} ❌ {error_msg}")
                    return {
                        'success': False,
                        'error': error_msg,
                        'timestamp': warsaw_time.isoformat()
                    }
            
            # 3. Pobierz wszystkie harmonogramy HOME z Tesla
            logger.info(f"{time_str} 📋 Pobieranie aktualnych harmonogramów HOME z Tesla...")
            home_schedules = self._get_home_schedules_from_tesla(vehicle_vin)

            if home_schedules is None:
                logger.error(f"{time_str} ❌ Nie udało się odczytać harmonogramów HOME")
                return {
                    'success': False,
                    'error': 'Błąd odczytu harmonogramów z Tesla',
                    'timestamp': warsaw_time.isoformat()
                }

            if not home_schedules:
                logger.info(f"{time_str} ✅ Brak harmonogramów HOME do usunięcia")
                return {
                    'success': True,
                    'message': 'Brak harmonogramów HOME do usunięcia',
                    'schedules_found': 0,
                    'schedules_removed': 0,
                    'timestamp': warsaw_time.isoformat()
                }
            
            logger.info(f"{time_str} 📋 Znaleziono {len(home_schedules)} harmonogramów HOME do usunięcia")
            
            # 4. Wyświetl szczegóły harmonogramów przed usunięciem
            for i, schedule in enumerate(home_schedules):
                schedule_id = schedule.get('id', 'BRAK')
                start_time = schedule.get('start_time', 'N/A')
                end_time = schedule.get('end_time', 'N/A')
                enabled = schedule.get('enabled', False)
                lat = schedule.get('latitude', 0.0)
                lon = schedule.get('longitude', 0.0)
                
                logger.info(f"{time_str} 📋 Harmonogram #{i+1}: ID={schedule_id}, {start_time}-{end_time}, enabled={enabled}, coords=({lat:.6f}, {lon:.6f})")
            
            # 5. Uruchom Tesla HTTP Proxy on-demand dla komend usuwania
            logger.info(f"{time_str} 🚀 Uruchamianie Tesla HTTP Proxy on-demand...")
            if not self._start_proxy_on_demand():
                logger.warning(f"{time_str} ⚠️ Tesla HTTP Proxy nie uruchomiony - próbuję usuwać przez Fleet API")

            # 5.5 OPTYMALIZACJA: Jeden wake_up przed całą sekwencją usuwania (unika HTTP 429)
            logger.info(f"{time_str} 🔄 Budzenie pojazdu przed usunięciem {len(home_schedules)} harmonogramów...")
            use_proxy = bool(hasattr(self.tesla_controller.fleet_api, 'proxy_url') and self.tesla_controller.fleet_api.proxy_url)
            if not self.tesla_controller.wake_up_vehicle(use_proxy=use_proxy):
                logger.warning(f"{time_str} ⚠️ Wake_up nie powiodło się - kontynuuję mimo to (pojazd może być już online)")

            # 6. Usuń wszystkie harmonogramy HOME jeden po drugim
            success_count = 0
            error_count = 0
            removed_schedule_ids = []

            for schedule in home_schedules:
                schedule_id = schedule.get('id')
                if schedule_id:
                    logger.info(f"{time_str} 🗑️ Usuwanie harmonogramu HOME ID: {schedule_id}")
                    
                    try:
                        # OPTYMALIZACJA: skip_wake=True bo wake_up już wywołane na początku sekwencji
                        if self.tesla_controller.remove_charge_schedule(schedule_id, skip_wake=True):
                            success_count += 1
                            removed_schedule_ids.append(schedule_id)
                            logger.info(f"{time_str} ✅ Usunięto harmonogram ID: {schedule_id}")
                        else:
                            error_count += 1
                            logger.error(f"{time_str} ❌ Nie udało się usunąć harmonogramu ID: {schedule_id}")
                    except Exception as remove_error:
                        error_count += 1
                        logger.error(f"{time_str} ❌ Błąd usuwania harmonogramu ID {schedule_id}: {remove_error}")
                else:
                    error_count += 1
                    logger.error(f"{time_str} ❌ Harmonogram bez ID - pomijam")
            
            # 7. Zatrzymaj Tesla HTTP Proxy
            logger.info(f"{time_str} 🛑 Zatrzymywanie Tesla HTTP Proxy...")
            self._stop_proxy()
            
            # 8. Weryfikacja - sprawdź czy harmonogramy zostały usunięte
            logger.info(f"{time_str} 🔍 Weryfikacja usunięcia harmonogramów...")
            remaining_schedules = self._get_home_schedules_from_tesla(vehicle_vin)
            if remaining_schedules is None:
                logger.warning(f"{time_str} ⚠️ Nie udało się zweryfikować pozostałych harmonogramów")
                remaining_schedules = []

            # 9. Wyczyść cache harmonogramów Tesla HOME
            if vehicle_vin in self.last_tesla_schedules_home:
                del self.last_tesla_schedules_home[vehicle_vin]
                logger.info(f"{time_str} 🧹 Wyczyszczono cache harmonogramów Tesla HOME")
            
            # 10. Loguj wyniki
            result = {
                'success': success_count > 0 or len(home_schedules) == 0,
                'schedules_found': len(home_schedules),
                'schedules_removed': success_count,
                'schedules_failed': error_count,
                'removed_schedule_ids': removed_schedule_ids,
                'remaining_schedules': len(remaining_schedules),
                'timestamp': warsaw_time.isoformat(),
                'vehicle_vin': vehicle_vin[-4:] if vehicle_vin else 'Unknown'
            }
            
            # 11. Log zdarzenia
            self._log_event(
                message="Tesla HOME schedules reset completed",
                vehicle_vin=vehicle_vin,
                extra_data={
                    'action': 'reset_tesla_home_schedules',
                    'schedules_found': len(home_schedules),
                    'schedules_removed': success_count,
                    'schedules_failed': error_count,
                    'remaining_schedules': len(remaining_schedules),
                    'removed_ids': removed_schedule_ids
                }
            )
            
            if success_count == len(home_schedules):
                logger.info(f"{time_str} 🎉 RESET HARMONOGRAMÓW ZAKOŃCZONY POMYŚLNIE - usunięto {success_count}/{len(home_schedules)} harmonogramów")
            elif success_count > 0:
                logger.warning(f"{time_str} ⚠️ RESET CZĘŚCIOWO POMYŚLNY - usunięto {success_count}/{len(home_schedules)} harmonogramów")
            else:
                logger.error(f"{time_str} ❌ RESET NIEUDANY - nie usunięto żadnego harmonogramu")
            
            return result
            
        except Exception as e:
            error_msg = f"Błąd resetowania harmonogramów HOME: {e}"
            logger.error(f"{time_str} ❌ {error_msg}")
            
            # Zatrzymaj proxy w przypadku błędu
            try:
                self._stop_proxy()
            except:
                pass
            
            return {
                'success': False,
                'error': error_msg,
                'timestamp': warsaw_time.isoformat()
            }
    
    def _check_vehicle_status(self) -> Optional[Dict[str, Any]]:
        """
        Sprawdza status pojazdu
        
        Returns:
            Dict z statusem pojazdu lub None w przypadku błędu
        """
        try:
            # Test połączenia z Tesla API (bez szczegółowych logów)
            try:
                if not self.tesla_controller.connect():
                    logger.error("❌ Błąd połączenia z Tesla API")
                    
                    # Sprawdź stan autoryzacji dla lepszej diagnostyki
                    if hasattr(self.tesla_controller, 'check_authorization'):
                        try:
                            self.tesla_controller.check_authorization()
                        except Exception as auth_check_error:
                            logger.error(f"💥 Błąd sprawdzania autoryzacji: {auth_check_error}")
                    
                    return None
            except Exception as conn_error:
                logger.error(f"❌ Błąd połączenia z Tesla API: {conn_error}")
                
                # Dodatkowe informacje diagnostyczne dla błędów autoryzacji
                if "401" in str(conn_error) or "unauthorized" in str(conn_error).lower():
                    logger.error("🚫 Błąd autoryzacji - sprawdź tokeny Tesla API")
                    # NAPRAWKA: Rzuć wyjątek autoryzacji aby główna pętla mogła przejść w tryb oczekiwania
                    raise TeslaAuthenticationError("Token wygasł lub nieprawidłowy", 401)
                elif "403" in str(conn_error) or "forbidden" in str(conn_error).lower():
                    logger.error("🚫 Brak uprawnień - sprawdź scope'y aplikacji w Tesla Developer Portal")
                    raise TeslaAuthenticationError("Brak uprawnień", 403)
                
                return None
            
            # Pobieranie statusu pojazdu z timeout'em
            try:
                # NAPRAWKA: Dodaj timeout na poziomie aplikacji
                import signal
                import threading
                
                status_result = None
                status_error = None
                status_finished = threading.Event()
                
                def get_status_with_timeout():
                    nonlocal status_result, status_error
                    try:
                        status_result = self.tesla_controller.get_vehicle_status()
                    except Exception as e:
                        status_error = e
                    finally:
                        status_finished.set()
                
                # Uruchom w osobnym wątku z timeout'em
                status_thread = threading.Thread(target=get_status_with_timeout, daemon=True)
                status_thread.start()
                
                # Czekaj maksymalnie 90 sekund na odpowiedź Tesla API
                if status_finished.wait(timeout=90):
                    if status_error:
                        raise status_error
                    status = status_result
                else:
                    logger.error("⏰ TIMEOUT pobierania statusu pojazdu (90s) - Tesla API nie odpowiada")
                    return None
                
                if not status:
                    logger.error("❌ Nie udało się pobrać statusu pojazdu - otrzymano None")
                    return None
            except Exception as status_error:
                logger.error(f"❌ Błąd pobierania statusu: {status_error}")
                
                # NAPRAWKA: Sprawdź czy to błąd autoryzacji
                if "401" in str(status_error) or "unauthorized" in str(status_error).lower():
                    logger.error("🚫 Token Tesla wygasł podczas pobierania statusu")
                    raise TeslaAuthenticationError("Token wygasł podczas operacji", 401)
                
                return None
            
            # Logowanie prostego statusu pojazdu
            _log_simple_status(status)
                
            return status
            
        except Exception as e:
            logger.error(f"❌ KRYTYCZNY błąd sprawdzania statusu pojazdu: {e}")
            return None
    
    def _handle_condition_a(self, status: Dict[str, Any], force: bool = False) -> bool:
        """
        Obsługuje warunek A: ONLINE + is_charging_ready=true + HOME

        Args:
            status: Status pojazdu
            force: True (midnight wake / failsafe) — pomija guard przejścia stanu
                   ORAZ porównanie hasha: zawsze świeże wywołanie OFF PEAK API
                   i pełna rekoncyliacja. Bez tego pojazd wpięty od wieczora nigdy
                   nie dostawał planu na nowy dzień (guard widział "stan bez zmian").
                   Rekoncyliacja gwarantuje, że przy zgodnym stanie nie polecą
                   żadne komendy do pojazdu.

        Returns:
            bool: True gdy nic nie było do zrobienia albo operacje się powiodły;
                  False gdy próba zastosowania harmonogramu zawiodła (cykl ma
                  NIE zapisywać stanu, żeby następny tick ponowił próbę)
        """
        battery_level = status.get('battery_level', 0)
        vehicle_vin = status.get('vin', 'Unknown')
        apply_ok = True
        
        # Pobierz aktualny czas warszawski
        warsaw_time = self._get_warsaw_time()
        time_str = warsaw_time.strftime("[%H:%M]")
        
        # Sprawdź czy to jest zmiana stanu (loguj tylko zmiany)
        last_state = self.last_vehicle_state.get(vehicle_vin, {})
        was_ready = last_state.get('is_charging_ready', False)
        was_home = last_state.get('location_status') == 'HOME'
        was_online = last_state.get('online', False)
        

        
        # Loguj tylko jeśli to pierwsza detekcja tego stanu
        # (force = midnight/failsafe: wykonaj pełny blok niezależnie od przejścia stanu)
        if force or not (was_ready and was_home and was_online):
            self._log_event(
                message="Car ready for schedule",
                battery_level=battery_level,
                vehicle_vin=vehicle_vin,
                extra_data={
                    'condition': 'A',
                    'charging_ready': True,
                    'location': 'HOME',
                    'state_change': 'new_ready_state'
                }
            )
            # Użyj prostego logowania statusu
            _log_simple_status(status, "gotowy do ładowania")
            
            # NOWA FUNKCJONALNOŚĆ: Wywołaj OFF PEAK CHARGE API i zarządzaj harmonogramami
            try:
                api_response = self._call_off_peak_charge_api(battery_level, vehicle_vin)
                if api_response and api_response.get('success'):
                    # Sprawdź czy harmonogram jest różny od poprzedniego
                    # (force pomija hash — rekoncyliacja i tak nie wyśle zbędnych komend)
                    if force or self._is_schedule_different(vehicle_vin, api_response):
                        schedule_hash = self._generate_schedule_hash(api_response)

                        # RETRY-BUDGET: po wyczerpaniu prób nie spamuj pojazdu komendami
                        if self._schedule_apply_blocked(vehicle_vin, schedule_hash):
                            return False

                        logger.info(f"{time_str} 🔄 Harmonogram RÓŻNY - rozpoczynam zarządzanie harmonogramami Tesla")

                        # Zarządzaj harmonogramami Tesla
                        if self._manage_tesla_charging_schedules(api_response, vehicle_vin, vehicle_status=status):
                            logger.info(f"{time_str} ✅ Pomyślnie zaktualizowano harmonogramy ładowania Tesla")

                            # Hash zatwierdzany dopiero po potwierdzonym sukcesie
                            self._commit_schedule_hash(vehicle_vin, api_response)
                            self._clear_schedule_apply_failures(vehicle_vin)

                            # Zapisz informacje o pełnej operacji
                            self._log_event(
                                message="OFF PEAK CHARGE schedule applied to Tesla successfully",
                                battery_level=battery_level,
                                vehicle_vin=vehicle_vin,
                                extra_data={
                                    'condition': 'A_schedule_update',
                                    'api_success': True,
                                    'schedule_updated': True,
                                    'scheduled_slots': api_response.get('data', {}).get('summary', {}).get('scheduledSlots', 0),
                                    'total_energy': api_response.get('data', {}).get('summary', {}).get('totalEnergy', 0),
                                    'total_cost': api_response.get('data', {}).get('summary', {}).get('totalCost', 0)
                                }
                            )
                        else:
                            logger.error(f"{time_str} ❌ Błąd aktualizacji harmonogramów Tesla")
                            self._record_schedule_apply_failure(vehicle_vin, schedule_hash)
                            apply_ok = False
                            self._log_event(
                                message="Failed to apply OFF PEAK CHARGE schedule to Tesla",
                                battery_level=battery_level,
                                vehicle_vin=vehicle_vin,
                                extra_data={
                                    'condition': 'A_schedule_update_failed',
                                    'api_success': True,
                                    'schedule_updated': False,
                                    'error': 'Tesla schedule management failed'
                                }
                            )
                    else:
                        logger.info(f"{time_str} 📋 Harmonogram IDENTYCZNY - nie wykonuję zmian w Tesla")
                        
                        # Zapisz informacje o pominięciu aktualizacji
                        self._log_event(
                            message="OFF PEAK CHARGE schedule unchanged - no Tesla update needed",
                            battery_level=battery_level,
                            vehicle_vin=vehicle_vin,
                            extra_data={
                                'condition': 'A_schedule_unchanged',
                                'api_success': True,
                                'schedule_updated': False,
                                'reason': 'identical_schedule'
                            }
                        )
                else:
                    logger.warning("⚠️ OFF PEAK CHARGE API - brak prawidłowej odpowiedzi")
                    apply_ok = False  # brak planu = próba nieudana; stan niezapisany → retry przy następnym ticku
                    self._log_event(
                        message="OFF PEAK CHARGE API failed or returned invalid response",
                        battery_level=battery_level,
                        vehicle_vin=vehicle_vin,
                        extra_data={
                            'condition': 'A_api_failed',
                            'api_success': False,
                            'error': 'No valid API response'
                        }
                    )
            except Exception as api_error:
                logger.error(f"❌ Błąd obsługi OFF PEAK CHARGE API: {api_error}")
                apply_ok = False
                self._log_event(
                    message="OFF PEAK CHARGE API processing error",
                    battery_level=battery_level,
                    vehicle_vin=vehicle_vin,
                    extra_data={
                        'condition': 'A_api_error',
                        'api_success': False,
                        'error': str(api_error)
                    }
                )
        
        # NAPRAWKA: Zakończ aktywny przypadek B jeśli pojazd stał się gotowy
        if vehicle_vin in self.active_cases:
            case = self.active_cases[vehicle_vin]
            warsaw_tz = pytz.timezone('Europe/Warsaw')
            now = datetime.now(warsaw_tz)
            time_str = now.strftime("[%H:%M]")
            
            # Loguj zakończenie przypadku B z powodu gotowości
            self._log_event(
                message="Monitoring case B terminated - car ready for charging",
                battery_level=battery_level,
                vehicle_vin=vehicle_vin,
                extra_data={
                    'condition': 'B_terminated_by_A',
                    'case_duration_minutes': (self._get_warsaw_time() - case.start_time).total_seconds() / 60,
                    'termination_reason': 'charging_ready_true'
                }
            )
            
            # Usuń przypadek z aktywnych
            del self.active_cases[vehicle_vin]
            self._save_monitoring_state()
            logger.info(f"{time_str} ✅ Zakończono przypadek B - pojazd gotowy do ładowania")

        return apply_ok

    def _handle_condition_b(self, status: Dict[str, Any]):
        """
        Obsługuje warunek B: ONLINE + HOME + is_charging_ready=false (pierwszy raz)
        
        Args:
            status: Status pojazdu
        """
        vehicle_vin = status.get('vin', 'Unknown')
        battery_level = status.get('battery_level', 0)
        
        # Sprawdź czy to jest zmiana stanu (loguj tylko zmiany)
        last_state = self.last_vehicle_state.get(vehicle_vin, {})
        was_ready = last_state.get('is_charging_ready', True)  # Domyślnie True, żeby wykryć zmianę na False
        was_home = last_state.get('location_status') == 'HOME'
        was_online = last_state.get('online', False)
        
        # Loguj tylko jeśli to zmiana z gotowego na niegotowy
        if was_ready and not status.get('is_charging_ready', False):
            self._log_event(
                message="Car not ready for charging - monitoring started",
                battery_level=battery_level,
                vehicle_vin=vehicle_vin,
                extra_data={
                    'condition': 'B',
                    'charging_ready': False,
                    'location': 'HOME',
                    'state_change': 'ready_to_not_ready'
                }
            )
            # Użyj prostego logowania statusu
            _log_simple_status(status, "niegotowy do ładowania")
        
        # Sprawdź czy już mamy aktywny przypadek dla tego pojazdu
        if vehicle_vin not in self.active_cases:
            # Utwórz nowy przypadek monitorowania tylko jeśli nie istnieje
            case_id = f"{vehicle_vin}_{int(time.time())}"
            new_case = VehicleMonitoringCase(
                case_id=case_id,
                vehicle_vin=vehicle_vin,
                start_time=self._get_warsaw_time(),
                state=MonitoringState.WAITING_FOR_OFFLINE,
                last_battery_level=status.get('battery_level', 0),
                last_check_time=self._get_warsaw_time()
            )
            
            self.active_cases[vehicle_vin] = new_case
            self._save_monitoring_state()
            
            warsaw_tz = pytz.timezone('Europe/Warsaw')
            now = datetime.now(warsaw_tz)
            time_str = now.strftime("[%H:%M]")
            logger.info(f"{time_str} 🔄 Rozpoczęto monitorowanie przypadku B")
        else:
            # Aktualizuj istniejący przypadek
            case = self.active_cases[vehicle_vin]
            case.last_check_time = self._get_warsaw_time()
            case.last_battery_level = battery_level
    
    def _process_active_cases(self, current_status: Optional[Dict[str, Any]]):
        """
        Przetwarza aktywne przypadki monitorowania
        
        Args:
            current_status: Aktualny status pojazdu
        """
        if not current_status:
            return
        
        vehicle_vin = current_status.get('vin')
        if not vehicle_vin or vehicle_vin not in self.active_cases:
            return
        
        case = self.active_cases[vehicle_vin]
        is_online = current_status.get('online', False)
        
        if case.state == MonitoringState.WAITING_FOR_OFFLINE:
            if not is_online:
                # Pojazd przeszedł w stan OFFLINE - wykonaj akcje
                battery_level = case.last_battery_level or 0
                
                # Log: "Car ready for checking status"
                self._log_event(
                    message="Car ready for checking status",
                    battery_level=battery_level,
                    vehicle_vin=vehicle_vin,
                    extra_data={
                        'condition': 'B_offline',
                        'case_duration_minutes': (self._get_warsaw_time() - case.start_time).total_seconds() / 60
                    }
                )
                
                # Wybudź pojazd
                warsaw_tz = pytz.timezone('Europe/Warsaw')
                now = datetime.now(warsaw_tz)
                time_str = now.strftime("[%H:%M]")
                logger.info(f"{time_str} 🔄 Budzenie pojazdu {vehicle_vin[-4:]}")
                wake_success = self.tesla_controller.wake_up_vehicle(use_proxy=False)  # Przypadek B - bez proxy
                
                # Log: "Car was awaken"
                self._log_event(
                    message="Car was awaken",
                    vehicle_vin=vehicle_vin,
                    extra_data={
                        'condition': 'B_wake',
                        'wake_success': wake_success
                    }
                )
                
                # Sprawdź status po wybudzeniu
                if wake_success:
                    time.sleep(3)  # Krótka pauza po wybudzeniu
                    new_status = self._check_vehicle_status()
                    if new_status:
                        # Użyj prostego logowania statusu po wybudzeniu
                        _log_simple_status(new_status, "po wybudzeniu")
                        
                        # NAPRAWKA: Sprawdź czy po wybudzeniu pojazd spełnia warunek A
                        is_online_after_wake = new_status.get('online', False)
                        is_charging_ready_after_wake = new_status.get('is_charging_ready', False)
                        location_after_wake = new_status.get('location_status', 'UNKNOWN')
                        
                        if is_online_after_wake and is_charging_ready_after_wake and location_after_wake == 'HOME':
                            logger.info(f"{time_str} ✅ Po wybudzeniu: pojazd spełnia warunek A - wywołuję OFF PEAK CHARGE API")
                            try:
                                self._handle_condition_a(new_status)
                            except Exception as api_ex:
                                logger.error(f"❌ Błąd wywołania warunku A po wybudzeniu: {api_ex}")
                
                # Zakończ przypadek
                del self.active_cases[vehicle_vin]
                self._save_monitoring_state()
                logger.info(f"{time_str} ✅ Zakończono monitorowanie przypadku B")
            else:
                # Pojazd nadal ONLINE - aktualizuj timestamp
                case.last_check_time = self._get_warsaw_time()
                case.last_battery_level = current_status.get('battery_level', case.last_battery_level)
    
    def run_monitoring_cycle(self) -> str:
        """
        Wykonuje pojedynczy cykl monitorowania pod lease-lockiem.

        Returns:
            str: 'ok'     — cykl zakończony pomyślnie,
                 'busy'   — inny cykl w toku (no-op, NIE jest błędem),
                 'failed' — cykl nieudany (endpoint HTTP powinien zwrócić 500,
                            żeby retry Cloud Schedulera zadziałał)
        """
        if not self._acquire_cycle_lock():
            return 'busy'
        try:
            return self._run_monitoring_cycle_locked()
        finally:
            self._release_cycle_lock()

    def _run_monitoring_cycle_locked(self) -> str:
        """Właściwy cykl monitorowania (wołać tylko pod lockiem)."""
        cycle_id = int(time.time())
        try:
            # NAPRAWKA: Jeśli Smart Proxy Mode i komponenty gotowe, przygotuj proxy na początku cyklu
            if self.smart_proxy_mode and self.proxy_available:
                private_key_ready = os.getenv('TESLA_PRIVATE_KEY_READY', 'false').lower() == 'true'
                if private_key_ready and not self.proxy_running:
                    warsaw_time = self._get_warsaw_time()
                    time_str = warsaw_time.strftime("[%H:%M]")
                    logger.info(f"{time_str} 🚀 Przygotowywanie Tesla HTTP Proxy dla cyklu monitorowania...")
                    
                    # Próbuj uruchomić proxy
                    try:
                        proxy_started = self._start_proxy_on_demand()
                        if proxy_started:
                            logger.info(f"{time_str} ✅ Tesla HTTP Proxy gotowy dla cyklu")
                        else:
                            logger.warning(f"{time_str} ⚠️ Tesla HTTP Proxy nie uruchomiony - cykl będzie ograniczony")
                    except Exception as proxy_ex:
                        logger.warning(f"{time_str} ⚠️ Błąd uruchamiania proxy: {proxy_ex}")
            
            # Pobierz status pojazdu (bez szczegółowych logów cyklu)
            try:
                status = self._check_vehicle_status()
                if not status:
                    logger.warning(f"⚠️ Nie udało się pobrać statusu pojazdu")
                    return 'failed'
            except TeslaAuthenticationError as auth_ex:
                logger.error(f"🚫 Błąd autoryzacji Tesla: {auth_ex}")
                logger.error(f"⚠️ Możliwe wygaśnięcie tokenów - należy ponownie autoryzować aplikację")
                # Nie przerywaj aplikacji - po prostu pomiń ten cykl
                return 'failed'
            except Exception as status_ex:
                logger.error(f"❌ Błąd pobierania statusu: {status_ex}")
                return 'failed'
            
            is_online = status.get('online', False)
            is_charging_ready = status.get('is_charging_ready', False)
            location_status = status.get('location_status', 'UNKNOWN')
            
            # NOWA LOGIKA: Jeśli Worker został wywołany, a pojazd jest offline → wybudź pojazd
            if not is_online:
                warsaw_time = self._get_warsaw_time()
                time_str = warsaw_time.strftime("[%H:%M]")
                vehicle_vin = status.get('vin', 'unknown')
                
                logger.info(f"🔄 [WORKER] Pojazd {vehicle_vin[-4:]} jest offline - wybudzam przed cyklem")
                logger.info(f"{time_str} 🚨 WORKER: Pojazd offline wymaga wybudzenia")
                
                try:
                    # Sprawdź czy pojazd został wybrany
                    if not self.tesla_controller.current_vehicle:
                        logger.info(f"{time_str} 🔗 Łączenie z Tesla API dla wybudzenia...")
                        tesla_connected = self.tesla_controller.connect()
                        if not tesla_connected:
                            logger.error(f"{time_str} ❌ Nie można połączyć się z Tesla API")
                            logger.warning(f"{time_str} ⚠️ Kontynuuję cykl bez wybudzenia pojazdu")
                        elif not self.tesla_controller.current_vehicle:
                            logger.error(f"{time_str} ❌ Nie wybrano żadnego pojazdu po połączeniu")
                            logger.warning(f"{time_str} ⚠️ Kontynuuję cykl bez wybudzenia pojazdu")
                        else:
                            selected_vin = self.tesla_controller.current_vehicle.get('vin', 'unknown')
                            logger.info(f"{time_str} ✅ Wybrany pojazd do wybudzenia: {selected_vin[-4:]}")
                    
                    # Wybudź pojazd (bez proxy - Fleet API)
                    if self.tesla_controller.current_vehicle:
                        selected_vin = self.tesla_controller.current_vehicle.get('vin', 'unknown')
                        logger.info(f"🔄 [WORKER] Budzenie pojazdu {selected_vin[-4:]} przez Fleet API...")
                        wake_success = self.tesla_controller.wake_up_vehicle(use_proxy=False)
                        
                        if wake_success:
                            logger.info(f"✅ [WORKER] Pojazd {selected_vin[-4:]} wybudzony pomyślnie")
                            logger.info(f"{time_str} ⏳ Oczekiwanie 5 sekund na pełne wybudzenie pojazdu...")
                            time.sleep(5)  # Pauza po wybudzeniu
                            
                            # Pobierz nowy status po wybudzeniu
                            logger.info(f"{time_str} 🔄 Sprawdzanie statusu pojazdu po wybudzeniu...")
                            new_status = self._check_vehicle_status()
                            if new_status:
                                status = new_status  # Użyj nowego statusu
                                is_online = status.get('online', False)
                                is_charging_ready = status.get('is_charging_ready', False)
                                location_status = status.get('location_status', 'UNKNOWN')
                                logger.info(f"{time_str} 📊 Status po wybudzeniu: online={is_online}, charging_ready={is_charging_ready}, location={location_status}")
                            else:
                                logger.warning(f"{time_str} ⚠️ Nie udało się pobrać statusu po wybudzeniu")
                        else:
                            logger.error(f"❌ [WORKER] Nie udało się wybudzić pojazdu {selected_vin[-4:]}")
                            logger.warning(f"{time_str} ⚠️ Kontynuuję cykl mimo niepowodzenia wybudzenia")
                        
                except Exception as wake_ex:
                    logger.error(f"❌ [WORKER] Błąd wybudzania pojazdu: {wake_ex}")
                    logger.warning(f"{time_str} ⚠️ Kontynuuję cykl mimo błędu wybudzenia")
                
                logger.info(f"{time_str} 🚀 Kontynuuję cykl monitorowania po próbie wybudzenia...")
            
            # Przetwórz aktywne przypadki (bez szczegółowych logów)
            try:
                self._process_active_cases(status)
            except Exception as cases_ex:
                logger.error(f"❌ Błąd przetwarzania przypadków: {cases_ex}")
                # Kontynuuj mimo błędu
            
            # Sprawdź warunki główne (bez szczegółowych logów)
            condition_a_ok = True
            if is_online and location_status == 'HOME':
                if is_charging_ready:
                    # Warunek A: ONLINE + is_charging_ready=true + HOME
                    try:
                        condition_a_ok = self._handle_condition_a(status)
                    except Exception as cond_a_ex:
                        logger.error(f"❌ Błąd obsługi warunku A: {cond_a_ex}")
                        condition_a_ok = False
                else:
                    # Warunek B: ONLINE + HOME + is_charging_ready=false
                    try:
                        self._handle_condition_b(status)
                    except Exception as cond_b_ex:
                        logger.error(f"❌ Błąd obsługi warunku B: {cond_b_ex}")
            else:
                # Inne przypadki - loguj tylko jeśli zmienił się stan
                vehicle_vin = status.get('vin', 'Unknown')
                last_state = self.last_vehicle_state.get(vehicle_vin, {})
                last_online = last_state.get('online', False)
                last_location = last_state.get('location_status', 'UNKNOWN')
                last_ready = last_state.get('is_charging_ready', False)
                
                # Sprawdź różne typy zmian stanu
                state_changed = False
                change_messages = []
                
                if last_online != is_online:
                    if is_online:
                        change_messages.append("pojazd ONLINE")
                    else:
                        change_messages.append("pojazd OFFLINE")
                    state_changed = True
                
                if last_location != location_status:
                    if location_status == 'HOME':
                        change_messages.append("przyjechał do DOMU")
                    elif last_location == 'HOME' and location_status not in ['UNKNOWN', 'UNAVAILABLE']:
                        # Tylko jeśli lokalizacja jest znana i różna od HOME
                        change_messages.append("wyjechał z DOMU")
                    elif last_location == 'HOME' and location_status in ['UNKNOWN', 'UNAVAILABLE']:
                        # Pojazd był w domu, teraz lokalizacja nieznana
                        change_messages.append("lokalizacja NIEZNANA (pojazd może być nadal w domu)")
                    else:
                        change_messages.append(f"lokalizacja: {location_status}")
                    state_changed = True
                
                if last_ready != is_charging_ready:
                    if is_charging_ready:
                        change_messages.append("GOTOWY do ładowania")
                    else:
                        change_messages.append("NIEGOTOWY do ładowania")
                    state_changed = True
                
                if state_changed:
                    # Loguj znaczące zmiany stanu z prostym formatem
                    change_description = ", ".join(change_messages)
                    warsaw_tz = pytz.timezone('Europe/Warsaw')
                    now = datetime.now(warsaw_tz)
                    time_str = now.strftime("[%H:%M]")
                    logger.info(f"{time_str} 📍 ZMIANA: {change_description}")
                    
                    # Loguj do bucket tylko znaczące zmiany
                    if (last_location == 'HOME' and location_status not in ['HOME', 'UNKNOWN', 'UNAVAILABLE']):
                        # Pojazd rzeczywiście wyjechał z domu (lokalizacja znana i różna od HOME)
                        self._log_event(
                            message="Car left home",
                            battery_level=status.get('battery_level', 0),
                            vehicle_vin=vehicle_vin,
                            extra_data={
                                'condition': 'departure',
                                'new_location': location_status,
                                'state_change': 'left_home'
                            }
                        )
                        _log_simple_status(status, "wyjazd z domu")
                    elif (last_location == 'HOME' and location_status in ['UNKNOWN', 'UNAVAILABLE']):
                        # Pojazd był w domu, teraz lokalizacja nieznana - nie loguj jako wyjazd
                        self._log_event(
                            message="Car location unknown - may still be at home",
                            battery_level=status.get('battery_level', 0),
                            vehicle_vin=vehicle_vin,
                            extra_data={
                                'condition': 'location_unknown',
                                'previous_location': 'HOME',
                                'new_location': location_status,
                                'state_change': 'home_to_unknown'
                            }
                        )
                        _log_simple_status(status, "lokalizacja nieznana")
                    elif (last_location != 'HOME' and location_status == 'HOME'):
                        # Pojazd przyjechał do domu
                        self._log_event(
                            message="Car arrived home",
                            battery_level=status.get('battery_level', 0),
                            vehicle_vin=vehicle_vin,
                            extra_data={
                                'condition': 'arrival',
                                'charging_ready': is_charging_ready,
                                'state_change': 'arrived_home'
                            }
                        )
                        _log_simple_status(status, "przyjazd do domu")
            
            # Zapisz aktualny stan pojazdu dla porównania w następnym cyklu.
            # Przy nieudanej próbie zastosowania harmonogramu stan celowo NIE jest
            # zapisywany — następny tick zobaczy ponownie "zmianę" i ponowi próbę
            # (ograniczone przez retry-budget w _schedule_apply_blocked).
            vehicle_vin = status.get('vin', 'Unknown')
            if condition_a_ok:
                self.last_vehicle_state[vehicle_vin] = {
                    'online': is_online,
                    'is_charging_ready': is_charging_ready,
                    'location_status': location_status,
                    'battery_level': status.get('battery_level', 0),
                    'last_update': self._get_warsaw_time().isoformat()
                }
                self._save_monitoring_state()
            else:
                logger.warning(f"⚠️ Stan pojazdu {vehicle_vin[-4:]} NIE zapisany (nieudana aplikacja harmonogramu) — retry przy następnym cyklu")

            return 'ok' if condition_a_ok else 'failed'

        except Exception as e:
            logger.error(f"❌ KRYTYCZNY błąd w cyklu monitorowania: {e}")
            # Nie przerywaj aplikacji - loguj i zwróć porażkę (endpoint odda 500 → retry schedulera)
            return 'failed'
    
    def run_midnight_wake_check(self):
        """Wykonuje jednorazowe wybudzenie pojazdu o godzinie 0:00 czasu warszawskiego i sprawdza stan"""
        # Ten sam lease-lock co zwykły cykl — midnight nie może nakładać się
        # z triggerem Scout ani retry schedulera
        if not self._acquire_cycle_lock():
            logger.info("🔒 Midnight wake pominięty — inny cykl w toku")
            return
        try:
            self._run_midnight_wake_check_locked()
        finally:
            self._release_cycle_lock()

    def _run_midnight_wake_check_locked(self):
        try:
            warsaw_time = self._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            logger.info(f"{time_str} 🌙 Nocne wybudzenie pojazdu")
            
            # NAPRAWKA: Połączenie z Tesla API przed nocnym wybudzeniem
            logger.info(f"{time_str} 🔗 Łączenie z Tesla API przed nocnym wybudzeniem...")
            tesla_connected = self.tesla_controller.connect()
            if not tesla_connected:
                logger.error(f"{time_str} ❌ Nie można połączyć się z Tesla API")
                logger.error(f"{time_str} ❌ Nocne wybudzenie przerwane - brak połączenia z Tesla")
                return
            
            # Sprawdź czy pojazd został wybrany
            if not self.tesla_controller.current_vehicle:
                logger.error(f"{time_str} ❌ Nie wybrano żadnego pojazdu po połączeniu")
                logger.error(f"{time_str} ❌ Nocne wybudzenie przerwane - brak wybranego pojazdu")
                return
                
            selected_vin = self.tesla_controller.current_vehicle.get('vin', 'unknown')
            logger.info(f"{time_str} ✅ Wybrany pojazd do wybudzenia: {selected_vin[-4:]}")
            
            # SMART PROXY: Uruchom proxy on-demand dla komendy wake_up
            proxy_started = False
            if self.smart_proxy_mode and self.proxy_available:
                logger.info(f"{time_str} 🚀 Uruchamianie Tesla HTTP Proxy on-demand dla wake_up...")
                proxy_started = self._start_proxy_on_demand()
                if not proxy_started:
                    logger.warning(f"{time_str} ⚠️ Nie udało się uruchomić Tesla HTTP Proxy - próbuję wake_up bez proxy")
                else:
                    logger.info(f"{time_str} ✅ Tesla HTTP Proxy uruchomiony dla wake_up")
            
            try:
                # Wybudź pojazd (z proxy jeśli dostępny)
                logger.info(f"{time_str} 🔄 Budzenie pojazdu {selected_vin[-4:]} {'przez Tesla HTTP Proxy' if proxy_started else 'bezpośrednio Fleet API'}")
                wake_success = self.tesla_controller.wake_up_vehicle(use_proxy=proxy_started)
                
                # Log wybudzenia
                self._log_event(
                    message="Midnight wake-up initiated",
                    extra_data={
                        'action': 'midnight_wake',
                        'wake_success': wake_success,
                        'proxy_used': proxy_started,
                        'scheduled_time': '00:00',
                        'scheduled_timezone': 'Europe/Warsaw'
                    }
                )
                
                if wake_success:
                    # Poczekaj chwilę na pełne wybudzenie
                    time.sleep(5)
                    
                    # Sprawdź status po wybudzeniu
                    status = self._check_vehicle_status()
                    if status:
                        # Log stanu po wybudzeniu
                        self._log_event(
                            message="Midnight status check completed",
                            battery_level=status.get('battery_level', 0),
                            vehicle_vin=status.get('vin', 'Unknown'),
                            extra_data={
                                'action': 'midnight_status_check',
                                'charging_ready': status.get('is_charging_ready', False),
                                'location': status.get('location_status', 'UNKNOWN'),
                                'online': status.get('online', False),
                                'proxy_used': proxy_started,
                                'scheduled_time': '00:00',
                                'scheduled_timezone': 'Europe/Warsaw'
                            }
                        )
                        
                        # Użyj prostego logowania statusu
                        _log_simple_status(status, "nocne sprawdzenie")
                        
                        # NAPRAWKA: Sprawdź czy po nocnym wybudzeniu pojazd spełnia warunek A
                        is_online_midnight = status.get('online', False)
                        is_charging_ready_midnight = status.get('is_charging_ready', False)
                        location_midnight = status.get('location_status', 'UNKNOWN')
                        

                        
                        if is_online_midnight and is_charging_ready_midnight and location_midnight == 'HOME':
                            logger.info(f"{time_str} ✅ Po nocnym wybudzeniu: pojazd spełnia warunek A - wywołuję OFF PEAK CHARGE API (force)")
                            try:
                                # force=True: midnight to failsafe — musi wymusić świeży plan
                                # na nowy dzień nawet przy "niezmienionym" stanie/hashu
                                self._handle_condition_a(status, force=True)
                            except Exception as api_ex:
                                logger.error(f"❌ Błąd wywołania warunku A po nocnym wybudzeniu: {api_ex}")
                        else:
                            logger.info(f"{time_str} ℹ️ Po nocnym wybudzeniu: pojazd nie spełnia warunku A (online={is_online_midnight}, ready={is_charging_ready_midnight}, location={location_midnight})")
                    else:
                        logger.warning(f"{time_str} ⚠️ Nie udało się pobrać statusu po nocnym wybudzeniu")
                else:
                    logger.warning(f"{time_str} ⚠️ Nie udało się wybudzić pojazdu (proxy_used={proxy_started})")
                    
            finally:
                # SMART PROXY: Zatrzymaj proxy po zakończeniu komendy wake_up
                if proxy_started and self.proxy_running:
                    logger.info(f"{time_str} 🛑 Zatrzymywanie Tesla HTTP Proxy po wake_up...")
                    self._stop_proxy()
                
        except Exception as e:
            warsaw_time = self._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            logger.error(f"{time_str} ❌ Błąd podczas nocnego wybudzenia: {e}")
            
            # Zatrzymaj proxy w przypadku błędu
            if hasattr(self, 'proxy_running') and self.proxy_running:
                self._stop_proxy()
    
    def setup_schedule(self):
        """Konfiguruje harmonogram monitorowania"""
        # NAPRAWKA: Nie czyść harmonogramu jeśli już istnieje z tym samym interwałem
        current_interval = self._get_monitoring_schedule_interval()
        
        # Sprawdź czy harmonogram już istnieje z właściwym interwałem
        existing_jobs = schedule.jobs
        if existing_jobs:
            # Sprawdź czy mamy już zadanie z właściwym interwałem
            for job in existing_jobs:
                if hasattr(job, 'interval') and job.interval == current_interval * 60:  # schedule używa sekund
                    warsaw_time = self._get_warsaw_time()
                    logger.debug(f"Harmonogram już istnieje z interwałem {current_interval} min (czas: {warsaw_time.strftime('%H:%M:%S')})")
                    return  # Nie zmieniaj istniejącego harmonogramu
        
        # Wyczyść poprzednie zadania TYLKO jeśli potrzebna zmiana
        schedule.clear()
        
        # Konfiguruj harmonogram na podstawie aktualnej godziny
        interval = current_interval
        
        warsaw_time = self._get_warsaw_time()
        
        if interval == 15:
            # Godziny dzienne: co 15 minut
            schedule.every(15).minutes.do(self.run_monitoring_cycle)
            logger.info(f"Harmonogram: sprawdzanie co 15 minut (godziny dzienne 07:00-23:00 czasu warszawskiego, aktualnie: {warsaw_time.strftime('%H:%M:%S')})")
        else:
            # Godziny nocne: co 60 minut
            schedule.every(60).minutes.do(self.run_monitoring_cycle)
            logger.info(f"Harmonogram: sprawdzanie co 60 minut (godziny nocne 23:00-07:00 czasu warszawskiego, aktualnie: {warsaw_time.strftime('%H:%M:%S')})")
        
        # Jednorazowe wybudzenie pojazdu o godzinie 0:00 czasu warszawskiego
        schedule.every().day.at("00:00", "Europe/Warsaw").do(self.run_midnight_wake_check)
        logger.info("Harmonogram: jednorazowe wybudzenie pojazdu o godzinie 00:00 czasu warszawskiego (Europe/Warsaw)")
        
        # NAPRAWKA: Sprawdzaj interwał rzadziej - co 2 godziny zamiast co godzinę
        schedule.every(2).hours.do(self.setup_schedule)
    
    def _start_health_server(self):
        """Uruchamia HTTP server dla health check"""
        try:
            port = int(os.getenv('PORT', '8080'))
            
            def handler(*args, **kwargs):
                return HealthCheckHandler(self, *args, **kwargs)
            
            self.http_server = HTTPServer(('0.0.0.0', port), handler)
            self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_thread.start()
            
            logger.info(f"Health check server uruchomiony na porcie {port}")
        except Exception as e:
            logger.error(f"Błąd uruchamiania health check server: {e}")
    
    def start_monitoring(self):
        """Uruchamia monitorowanie w trybie scheduler lub continuous"""
        warsaw_time = self._get_warsaw_time()
        time_str = warsaw_time.strftime("[%H:%M]")
        
        # Sprawdź tryb działania
        continuous_mode = os.getenv('CONTINUOUS_MODE', 'false').lower() == 'true'
        
        if continuous_mode:
            logger.info(f"{time_str} 🔄 Uruchamianie Cloud Tesla Monitor w trybie CONTINUOUS")
            self._start_continuous_monitoring()
        else:
            logger.info(f"{time_str} 📅 Uruchamianie Cloud Tesla Monitor w trybie SCHEDULER (optymalizacja kosztów)")
            self._start_scheduler_monitoring()
    
    def _start_scheduler_monitoring(self):
        """Uruchamia monitorowanie w trybie scheduler (optymalizacja kosztów)"""
        warsaw_time = self._get_warsaw_time()
        time_str = warsaw_time.strftime("[%H:%M]")
        
        logger.info(f"{time_str} 💰 TRYB SCHEDULER: Cloud Run skaluje do zera między wywołaniami")
        logger.info(f"{time_str} 📅 Harmonogram zarządzany przez Cloud Scheduler")
        logger.info(f"{time_str} 🔗 Endpointy dostępne:")
        logger.info(f"{time_str}   - GET/POST /run-cycle - cykl monitorowania")
        logger.info(f"{time_str}   - GET/POST /run-midnight-wake - nocne wybudzenie")
        logger.info(f"{time_str}   - GET /health - sprawdzenie stanu")
        logger.info(f"{time_str}   - GET /reset - reset stanu")
        logger.info(f"{time_str}   - GET /reset-tesla-schedules - reset harmonogramów Tesla")
        
        # Uruchom tylko HTTP server
        self._start_health_server()
        
        # Test połączenia z Tesla (bez uruchamiania harmonogramu)
        tesla_connected = self.tesla_controller.connect()
        if tesla_connected:
            logger.info(f"{time_str} ✅ Tesla API połączone - gotowe do obsługi wywołań")
        else:
            logger.warning(f"{time_str} ⚠️ Tesla API niedostępne - aplikacja działa w trybie oczekiwania")
        
        self.is_running = True
        
        # Prosta pętla utrzymująca aplikację przy życiu
        try:
            logger.info(f"{time_str} 🎯 Aplikacja gotowa do obsługi wywołań Cloud Scheduler")
            
            while self.is_running:
                # Minimalne utrzymanie przy życiu - sprawdzaj co 5 minut
                time.sleep(300)
                
                # Heartbeat co godzinę
                current_time = self._get_warsaw_time()
                if current_time.minute == 0:  # Raz na godzinę
                    time_str = current_time.strftime("[%H:%M]")
                    logger.info(f"{time_str} 💓 Scheduler mode: Aplikacja aktywna, oczekuje na Cloud Scheduler")
                
        except KeyboardInterrupt:
            logger.info("⛔ Otrzymano sygnał przerwania - zatrzymywanie monitora")
            self.stop_monitoring()
        except Exception as e:
            logger.error(f"💥 KRYTYCZNY BŁĄD w trybie scheduler: {e}")
            self.stop_monitoring()
            raise
    
    def _start_continuous_monitoring(self):
        """Uruchamia monitorowanie w trybie continuous (poprzednia implementacja)"""
        warsaw_time = self._get_warsaw_time()
        time_str = warsaw_time.strftime("[%H:%M]")
        
        logger.info(f"{time_str} 🔄 TRYB CONTINUOUS: Aplikacja działa ciągle (wyższe koszty)")
        logger.info(f"{time_str} ⚠️ Uwaga: Ten tryb generuje stałe koszty Cloud Run")
        
        # Uruchom health check server
        self._start_health_server()
        
        # Pierwsza konfiguracja harmonogramu
        self.setup_schedule()
        
        # Test połączenia z Tesla
        tesla_connected = self.tesla_controller.connect()
        if not tesla_connected:
            logger.error(f"{time_str} ❌ Nie udało się połączyć z Tesla API")
            logger.info(f"{time_str} ⚠️ Aplikacja będzie działać w trybie oczekiwania")
            # Nie kończymy aplikacji - niech działa jako serwer
        
        self.is_running = True
        if tesla_connected:
            logger.info(f"{time_str} ✅ Monitoring uruchomiony z połączeniem Tesla")
            # Wykonaj pierwszy cykl monitorowania tylko jeśli Tesla jest połączona
            self.run_monitoring_cycle()
        else:
            logger.info(f"{time_str} ⚠️ Monitoring uruchomiony w trybie oczekiwania")
        
        # Główna pętla monitorowania
        loop_iteration = 0
        try:
            while self.is_running:
                loop_iteration += 1
                warsaw_time = self._get_warsaw_time()
                
                # Uproszczony heartbeat - tylko co 60 minut
                if loop_iteration % 60 == 0:  # Co 60 iteracji (60 minut)
                    time_str = warsaw_time.strftime("[%H:%M]")
                    logger.info(f"{time_str} 💓 Monitor działa")
                
                # Sprawdź i wykonaj zaplanowane zadania (tylko jeśli Tesla jest połączona)
                if tesla_connected:
                    try:
                        # Wykonaj zadania z timeout'em przy użyciu threading
                        import threading
                        import signal
                        
                        schedule_finished = threading.Event()
                        schedule_error = None
                        
                        def run_schedule_with_timeout():
                            nonlocal schedule_error
                            try:
                                schedule.run_pending()
                            except Exception as e:
                                schedule_error = e
                            finally:
                                schedule_finished.set()
                        
                        # Uruchom schedule w osobnym wątku
                        schedule_thread = threading.Thread(target=run_schedule_with_timeout, daemon=True)
                        schedule_thread.start()
                        
                        # Czekaj maksymalnie 5 minut na zakończenie zadań
                        if schedule_finished.wait(timeout=300):  # 5 minut timeout
                            if schedule_error:
                                raise schedule_error
                        else:
                            time_str = warsaw_time.strftime("[%H:%M]")
                            logger.error(f"{time_str} ⏰ TIMEOUT harmonogramu - zadanie trwa ponad 5 minut!")
                            
                    except Exception as schedule_error:
                        time_str = warsaw_time.strftime("[%H:%M]")
                        logger.error(f"{time_str} ❌ Błąd w harmonogramie: {schedule_error}")
                        
                        # NAPRAWKA: W przypadku błędu, sprawdź czy to nie problem z tokenami Tesla
                        if "401" in str(schedule_error) or "unauthorized" in str(schedule_error).lower():
                            logger.error(f"{time_str} 🚫 Błąd autoryzacji Tesla - możliwe wygaśnięcie tokenów")
                            tesla_connected = False  # Przejdź w tryb oczekiwania
                        
                        # Nie przerywaj pętli - loguj i kontynuuj
                else:
                    # W trybie oczekiwania - sprawdź co jakiś czas czy można się połączyć
                    if loop_iteration % 60 == 0:  # Co godzinę próbuj połączyć się z Tesla
                        time_str = warsaw_time.strftime("[%H:%M]")
                        logger.info(f"{time_str} 🔄 Próba ponownego połączenia z Tesla API...")
                        if self.tesla_controller.connect():
                            tesla_connected = True
                            logger.info(f"{time_str} ✅ Pomyślnie połączono z Tesla API")
                            self.setup_schedule()  # Ustaw harmonogram
                        else:
                            logger.info(f"{time_str} ❌ Nadal brak połączenia z Tesla API")
                
                time.sleep(60)  # Sprawdzaj co minutę czy są zadania do wykonania
                
        except KeyboardInterrupt:
            logger.info("⛔ Otrzymano sygnał przerwania - zatrzymywanie monitora")
            self.stop_monitoring()
        except Exception as e:
            logger.error(f"💥 KRYTYCZNY BŁĄD w pętli monitorowania (iteracja #{loop_iteration}): {e}")
            logger.error(f"💥 Typ błędu: {type(e).__name__}")
            import traceback
            logger.error(f"💥 Stack trace: {traceback.format_exc()}")
            self.stop_monitoring()
            raise  # Re-raise żeby Cloud Run widział crash
    
    def stop_monitoring(self):
        """Zatrzymuje monitorowanie"""
        import traceback
        warsaw_time = self._get_warsaw_time()
        logger.info(f"🛑 === ZATRZYMYWANIE CLOUD TESLA MONITOR === (czas: {warsaw_time.strftime('%H:%M:%S')})")
        
        # Loguj stan przed zatrzymaniem
        try:
            import psutil
            process = psutil.Process()
            memory = process.memory_info()
            logger.info(f"🔍 Stan przed zatrzymaniem: pamięć={memory.rss / 1024 / 1024:.1f}MB, wątki={process.num_threads()}")
        except Exception as e:
            logger.warning(f"🔍 Nie można pobrać informacji o procesie: {e}")
        
        # Loguj stack trace aby zobaczyć skąd wywołano stop_monitoring
        logger.info(f"🔍 Stop monitoring wywołane z:")
        for line in traceback.format_stack():
            logger.info(f"🔍   {line.strip()}")
        
        self.is_running = False
        logger.info("🔴 is_running ustawione na False")
        
        # SMART PROXY: Zatrzymaj proxy jeśli działa
        if hasattr(self, 'proxy_running') and self.proxy_running:
            logger.info("🛑 Zatrzymywanie Tesla HTTP Proxy...")
            self._stop_proxy()
        
        # Zatrzymaj HTTP server
        if self.http_server:
            try:
                self.http_server.shutdown()
                logger.info("✅ Health check server zatrzymany")
            except Exception as e:
                logger.error(f"❌ Błąd zatrzymywania health check server: {e}")
        
        # Zapisz stan przed zakończeniem
        try:
            self._save_monitoring_state()
            logger.info("✅ Stan monitorowania zapisany")
        except Exception as e:
            logger.error(f"❌ Błąd zapisywania stanu: {e}")
        
        logger.info("🏁 === MONITORING ZATRZYMANY ===")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca aktualny status monitora
        
        Returns:
            Dict z informacjami o stanie monitora
        """
        return {
            'is_running': self.is_running,
            'active_cases_count': len(self.active_cases),
            'active_cases': [case.to_dict() for case in self.active_cases.values()],
            'current_interval_minutes': self._get_monitoring_schedule_interval(),
            'last_vehicle_states': self.last_vehicle_state,
            'project_id': self.project_id,
            'bucket_name': self.bucket_name,
            'last_check': self._get_warsaw_time().isoformat(),
            'timezone': 'Europe/Warsaw',
            'monitoring_logic': 'continuous_with_state_change_detection'
        }

    def _generate_schedule_hash(self, schedule_data: Dict[str, Any]) -> str:
        """
        Generuje hash dla harmonogramu ładowania z API OFF PEAK CHARGE
        
        Args:
            schedule_data: Dane harmonogramu z API OFF PEAK CHARGE
            
        Returns:
            str: Hash MD5 harmonogramu
        """
        try:
            # Wyciągnij tylko istotne dane do porównania (bez timestamp, requestId itp.)
            charging_schedule = schedule_data.get('data', {}).get('chargingSchedule', [])
            
            # Posortuj harmonogram według czasu rozpoczęcia dla konsystencji
            sorted_schedule = sorted(charging_schedule, key=lambda x: x.get('start_time', ''))
            
            # Utwórz hash na podstawie dat i czasów ładowania
            hash_data = []
            for slot in sorted_schedule:
                hash_data.append({
                    'start_time': slot.get('start_time'),
                    'end_time': slot.get('end_time'),
                    'charge_amount': slot.get('charge_amount')
                })
            
            # Konwertuj na string i oblicz hash
            hash_string = json.dumps(hash_data, sort_keys=True)
            return hashlib.md5(hash_string.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Błąd generowania hash harmonogramu: {e}")
            return ""
    
    def _is_schedule_different(self, vehicle_vin: str, new_schedule_data: Dict[str, Any]) -> bool:
        """
        Sprawdza czy nowy harmonogram różni się od poprzedniego
        
        Args:
            vehicle_vin: VIN pojazdu
            new_schedule_data: Nowe dane harmonogramu z API OFF PEAK CHARGE
            
        Returns:
            bool: True jeśli harmonogram jest różny lub to pierwsza próba
        """
        new_hash = self._generate_schedule_hash(new_schedule_data)
        last_hash = self.last_off_peak_schedules.get(vehicle_vin, {}).get('hash', '')

        is_different = new_hash != last_hash

        # UWAGA: sama detekcja NIE zapisuje hasha. Zapis następuje dopiero po
        # potwierdzonym zastosowaniu w pojeździe (_commit_schedule_hash) —
        # inaczej porażka wysyłki blokowałaby retry ("IDENTYCZNY" mimo tego,
        # że w aucie nic się nie zmieniło).
        if is_different:
            logger.info(f"📋 Harmonogram dla {vehicle_vin[-4:]}: {'RÓŻNY' if last_hash else 'PIERWSZY'} (hash: {new_hash[:8]}...)")
        else:
            logger.info(f"📋 Harmonogram dla {vehicle_vin[-4:]}: IDENTYCZNY (hash: {new_hash[:8]}...)")

        return is_different

    def _commit_schedule_hash(self, vehicle_vin: str, new_schedule_data: Dict[str, Any]):
        """
        Zatwierdza hash harmonogramu PO potwierdzonym zastosowaniu w pojeździe.
        Wołać wyłącznie gdy _manage_tesla_charging_schedules zwróciło True.
        """
        new_hash = self._generate_schedule_hash(new_schedule_data)
        self.last_off_peak_schedules[vehicle_vin] = {
            'hash': new_hash,
            'timestamp': datetime.now().isoformat(),
            'schedule_data': new_schedule_data
        }
        logger.info(f"📋 Hash harmonogramu zatwierdzony po sukcesie dla {vehicle_vin[-4:]} (hash: {new_hash[:8]}...)")
        # Persystuj — hash musi przeżyć scale-to-zero, inaczej cold start robi pełny rewrite
        self._save_monitoring_state()

    def _is_schedule_for_today(self, start_warsaw: datetime, end_warsaw: datetime) -> bool:
        """
        Sprawdza czy harmonogram dotyczy dzisiejszego dnia kalendarzowego.
        Midnight wake o 00:00 zapewnia że po północy zostanie wykonane
        świeże wywołanie API z harmonogramami na nowy dzień.
        """
        now_warsaw = self._get_warsaw_time()
        today = now_warsaw.date()
        start_date = start_warsaw.date()

        # Przypadek 1: Harmonogram zaczyna się dzisiaj
        if start_date == today:
            return True

        # Przypadek 2: Harmonogram aktywny (zaczął się wczoraj, wciąż trwa)
        yesterday = today - timedelta(days=1)
        if start_date == yesterday and now_warsaw < end_warsaw:
            return True

        return False

    def _convert_off_peak_to_tesla_schedules(self, off_peak_data: Dict[str, Any], vehicle_vin: str) -> List[ChargeSchedule]:
        """
        Konwertuje harmonogram z API OFF PEAK CHARGE do formatu Tesla ChargeSchedule
        
        Args:
            off_peak_data: Dane z API OFF PEAK CHARGE
            vehicle_vin: VIN pojazdu
            
        Returns:
            List[ChargeSchedule]: Lista harmonogramów w formacie Tesla
        """
        schedules = []
        charging_schedule = off_peak_data.get('data', {}).get('chargingSchedule', [])
        
        # Sprawdź czy harmonogram jest pusty (na podstawie summary)
        summary = off_peak_data.get('data', {}).get('summary', {})
        scheduled_slots = summary.get('scheduledSlots', 0)
        total_energy = summary.get('totalEnergy', 0)
        
        # Loguj informacje o harmonogramie
        if scheduled_slots == 0 or total_energy == 0:
            logger.warning(f"⚠️  OFF PEAK API zwróciło pusty harmonogram: {scheduled_slots} sesji, {total_energy} kWh")
        else:
            logger.info(f"📊 OFF PEAK harmonogram: {scheduled_slots} sesji, {total_energy} kWh")
        
        try:
            # Pobierz lokalizację HOME z kontrolera Tesla
            if self.tesla_controller.current_vehicle:
                home_lat = self.tesla_controller.default_latitude
                home_lon = self.tesla_controller.default_longitude
            else:
                # Fallback do domyślnych wartości
                home_lat = float(os.getenv('HOME_LATITUDE', '52.334215'))
                home_lon = float(os.getenv('HOME_LONGITUDE', '20.937516'))

            # FAZA 2: tryb one_time — sloty (także jutrzejsze) wysyłane jako harmonogramy
            # jednorazowe zamiast filtrowania "tylko na dziś". Auto zawsze ma realny plan
            # nocny i nie zależy od midnight wake. Za flagą do czasu weryfikacji na aucie.
            use_one_time = os.getenv('USE_ONE_TIME_SCHEDULES', 'false').lower() == 'true'
            now_warsaw = self._get_warsaw_time()

            filtered_count = 0
            for i, slot in enumerate(charging_schedule):
                # Parsuj czasy z formatu ISO 8601
                start_time_str = slot.get('start_time', '')
                end_time_str = slot.get('end_time', '')
                
                if not start_time_str or not end_time_str:
                    continue
                
                try:
                    # Konwertuj na czas warszawski i wyciągnij minuty od północy
                    start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    
                    # Konwertuj na czas warszawski
                    warsaw_tz = pytz.timezone('Europe/Warsaw')
                    start_warsaw = start_dt.astimezone(warsaw_tz)
                    end_warsaw = end_dt.astimezone(warsaw_tz)

                    # Slot całkowicie miniony nie ma sensu w żadnym trybie — z days=All
                    # wykonałby się JUTRO według DZISIEJSZYCH cen (błąd klasy L10)
                    if end_warsaw <= now_warsaw:
                        logger.info(f"⏰ Harmonogram #{i+1}: {start_warsaw.strftime('%Y-%m-%d %H:%M')}-"
                                   f"{end_warsaw.strftime('%Y-%m-%d %H:%M')} - POMINIĘTY (już miniony)")
                        filtered_count += 1
                        continue

                    if use_one_time:
                        # Tryb one_time: przyjmujemy sloty dzisiejsze i przyszłe —
                        # harmonogram jednorazowy wykona się w najbliższym pasującym
                        # oknie (czyli dokładnie w zaplanowanym terminie) i zniknie
                        pass
                    elif not self._is_schedule_for_today(start_warsaw, end_warsaw):
                        # Tryb legacy: przepuszczaj tylko harmonogramy na dzisiejszy dzień
                        logger.info(f"🔜 Harmonogram #{i+1}: {start_warsaw.strftime('%Y-%m-%d %H:%M')}-"
                                   f"{end_warsaw.strftime('%Y-%m-%d %H:%M')} - POMINIĘTY (nie dotyczy dzisiaj)")
                        filtered_count += 1
                        continue

                    # Oblicz minuty od północy
                    start_minutes = start_warsaw.hour * 60 + start_warsaw.minute
                    end_minutes = end_warsaw.hour * 60 + end_warsaw.minute
                    
                    # NAPRAWKA: Obsługa przejścia przez północ (np. 23:00-00:00)
                    # Jeśli end_minutes < start_minutes, oznacza to przejście przez północ
                    if end_minutes < start_minutes:
                        # Sprawdź czy to rzeczywiście przejście przez północ
                        if start_warsaw.day != end_warsaw.day or end_warsaw.hour < start_warsaw.hour:
                            # Dodaj 24h w minutach dla kolejnego dnia
                            end_minutes += 24 * 60
                            logger.info(f"🌙 Wykryto przejście przez północ: {start_warsaw.strftime('%H:%M')}-{end_warsaw.strftime('%H:%M')} "
                                      f"→ {start_minutes}-{end_minutes} min")
                    
                    # Normalizuj end_time do zakresu 0-1439 minut dla Tesla API
                    normalized_end_minutes = end_minutes % (24 * 60)
                    
                    # Utwórz harmonogram Tesla
                    schedule = ChargeSchedule(
                        enabled=True,
                        start_time=start_minutes,
                        end_time=normalized_end_minutes,
                        start_enabled=True,
                        end_enabled=True,
                        days_of_week="All",  # Wszystkie dni tygodnia
                        lat=home_lat,
                        lon=home_lon,
                        one_time=use_one_time
                    )
                    
                    schedules.append(schedule)
                    
                    # Loguj konwersję z informacją o normalizacji
                    if end_minutes != normalized_end_minutes:
                        logger.info(f"📅 Harmonogram #{i+1}: {start_warsaw.strftime('%H:%M')}-{end_warsaw.strftime('%H:%M')} "
                                  f"({start_minutes}-{end_minutes} min → normalizacja: {normalized_end_minutes} min), "
                                  f"{slot.get('charge_amount', 0)} kWh")
                    else:
                        logger.info(f"📅 Harmonogram #{i+1}: {start_warsaw.strftime('%H:%M')}-{end_warsaw.strftime('%H:%M')} "
                                  f"({start_minutes}-{end_minutes} min), "
                                  f"{slot.get('charge_amount', 0)} kWh")
                
                except Exception as e:
                    logger.error(f"Błąd parsowania slotu #{i+1}: {e}")
                    continue
            
            # OKNO-STRAŻNIK: gdy po konwersji nie ma ŻADNEGO okna, pojazd bez
            # harmonogramu ładowałby NATYCHMIAST po wpięciu (pełna moc, droga taryfa).
            # Minimalne okno 23:58-23:59 "okupuje" scheduler Tesli i wymusza czekanie.
            # (Poprzedni slot 23:59-1440 wykraczał poza zakres 0-1439 minut.)
            if not schedules:
                if filtered_count > 0:
                    logger.info(f"⚠️ Wszystkie {filtered_count} sloty z OFF PEAK API pominięte (minione/przyszłe dni)")
                logger.warning("⚠️ Brak okien do zaplanowania - tworzę okno-strażnik 23:58-23:59")

                guard_schedule = ChargeSchedule(
                    enabled=True,
                    start_time=23 * 60 + 58,  # 23:58 = 1438
                    end_time=23 * 60 + 59,    # 23:59 = 1439 (w zakresie 0-1439)
                    start_enabled=True,
                    end_enabled=True,
                    days_of_week="All",
                    lat=home_lat,
                    lon=home_lon,
                    one_time=False  # strażnik ma trwać, dopóki nie pojawi się realny plan
                )
                schedules.append(guard_schedule)
                logger.info(f"🛡️ STRAŻNIK: okno 23:58-23:59 (1438-1439 min) — blokuje natychmiastowe ładowanie po wpięciu")
            
            if filtered_count > 0:
                logger.info(f"🔜 Pominięto {filtered_count} harmonogramów (dotyczą przyszłych dni)")
            logger.info(f"✅ Skonwertowano {len(schedules)} harmonogramów z API OFF PEAK CHARGE (dla dzisiaj)")
            return schedules
            
        except Exception as e:
            logger.error(f"Błąd konwersji harmonogramów: {e}")
            return []
    
    def _resolve_schedule_overlaps(self, schedules: List[ChargeSchedule], vehicle_vin: str) -> List[ChargeSchedule]:
        """
        Rozwiązuje nakładające się harmonogramy ładowania zachowując priorytety z API
        
        Logika:
        1. Wykryj czy są jakiekolwiek nakładania (optymalizacja)
        2. Jeśli brak nakładań, zwróć oryginalną listę
        3. Jeśli są nakładania, usuń harmonogramy o niższym priorytecie
        4. Kolejność z API = priorytet (pierwszy = najważniejszy)
        
        Args:
            schedules: Lista harmonogramów do sprawdzenia
            vehicle_vin: VIN pojazdu (do logowania)
            
        Returns:
            List[ChargeSchedule]: Lista harmonogramów bez nakładań
        """
        if not schedules:
            return schedules
        
        # KROK 1: Szybkie wykrycie czy są jakiekolwiek nakładania
        has_overlaps = self._detect_any_overlaps(schedules)
        
        if not has_overlaps:
            logger.info(f"✅ Brak nakładań w {len(schedules)} harmonogramach - zwracam oryginalną listę")
            return schedules
        
        logger.warning(f"⚠️ Wykryto nakładania w harmonogramach - rozwiązywanie konfliktów...")
        
        # KROK 2: Rozwiąż nakładania zachowując priorytety
        resolved_schedules = []
        
        for i, current_schedule in enumerate(schedules):
            # Sprawdź czy current_schedule nakłada się z już zaakceptowanymi harmonogramami
            has_conflict = False
            
            for accepted_schedule in resolved_schedules:
                if self._schedules_overlap(current_schedule, accepted_schedule):
                    logger.info(f"🚫 Harmonogram #{i+1} ({self.tesla_controller.minutes_to_time(current_schedule.start_time)}-"
                              f"{self.tesla_controller.minutes_to_time(current_schedule.end_time)}) "
                              f"nakłada się z wyższym priorytetem - POMIJAM")
                    has_conflict = True
                    break
            
            if not has_conflict:
                resolved_schedules.append(current_schedule)
                logger.info(f"✅ Harmonogram #{i+1} ({self.tesla_controller.minutes_to_time(current_schedule.start_time)}-"
                          f"{self.tesla_controller.minutes_to_time(current_schedule.end_time)}) "
                          f"zaakceptowany (priorytet #{len(resolved_schedules)})")
        
        logger.info(f"🔧 Rozwiązano nakładania: {len(schedules)} → {len(resolved_schedules)} harmonogramów")
        return resolved_schedules

    def _detect_any_overlaps(self, schedules: List[ChargeSchedule]) -> bool:
        """
        Szybkie sprawdzenie czy w liście harmonogramów są jakiekolwiek nakładania
        
        Args:
            schedules: Lista harmonogramów do sprawdzenia
            
        Returns:
            bool: True jeśli znaleziono przynajmniej jedno nakładanie
        """
        for i, schedule1 in enumerate(schedules):
            for j, schedule2 in enumerate(schedules[i+1:], start=i+1):
                if self._schedules_overlap(schedule1, schedule2):
                    return True
        return False

    def _schedules_overlap(self, schedule1: ChargeSchedule, schedule2: ChargeSchedule) -> bool:
        """
        Sprawdza czy dwa harmonogramy nakładają się czasowo
        
        Args:
            schedule1: Pierwszy harmonogram
            schedule2: Drugi harmonogram
            
        Returns:
            bool: True jeśli harmonogramy się nakładają
        """
        # Okno przez północ dzielimy na segmenty w obrębie doby — poprzednia
        # formuła (start1<end2 AND start2<end1) po normalizacji end<start
        # NIE wykrywała realnych nakładań okien typu 23:00-01:00
        def _segments(s: ChargeSchedule):
            start = s.start_time % 1440
            end = s.end_time - 1440 if s.end_time > 1440 else s.end_time
            end = end % 1440 if end != 1440 else 0
            if start < end:
                return [(start, end)]
            if start == end:
                return []  # okno zerowej długości
            return [(start, 1440), (0, end)]  # przez północ

        for a_start, a_end in _segments(schedule1):
            for b_start, b_end in _segments(schedule2):
                if a_start < b_end and b_start < a_end:
                    return True
        return False
    
    def _get_home_schedules_from_tesla(self, vehicle_vin: str) -> List[Dict]:
        """
        Pobiera harmonogramy ładowania z lokalizacji HOME z pojazdu Tesla
        
        Args:
            vehicle_vin: VIN pojazdu
            
        Returns:
            List[Dict]: Lista harmonogramów HOME z Tesla
        """
        try:
            # Upewnij się że Tesla Controller jest połączony i ma wybrany pojazd
            if not self.tesla_controller.current_vehicle:
                # Spróbuj połączyć się i wybrać pierwszy pojazd
                if self.tesla_controller.connect():
                    self.tesla_controller.list_vehicles()
                    if self.tesla_controller.vehicles:
                        # Znajdź pojazd o danym VIN
                        for i, vehicle in enumerate(self.tesla_controller.vehicles):
                            if vehicle.get('vin') == vehicle_vin:
                                if self.tesla_controller.select_vehicle(i):
                                    break
                        else:
                            # Jeśli nie znaleziono VIN, użyj pierwszego pojazdu
                            self.tesla_controller.select_vehicle(0)
                else:
                    logger.error("Nie można połączyć się z Tesla API")
                    return None

            if not self.tesla_controller.current_vehicle:
                logger.error(f"Nie można znaleźć pojazdu {vehicle_vin[-4:]}")
                return None

            # Pobierz wszystkie harmonogramy
            all_schedules = self.tesla_controller.get_charge_schedules()

            if all_schedules is None:
                # Błąd odczytu — NIE oznacza braku harmonogramów; wołający nie może
                # na tej podstawie dodawać nowych okien obok nieznanych starych
                logger.error(f"📍 Błąd odczytu harmonogramów z Tesla dla {vehicle_vin[-4:]}")
                return None

            if not all_schedules:
                logger.info(f"📍 Brak harmonogramów w Tesla dla {vehicle_vin[-4:]}")
                return []
            
            # DEBUG: Wyloguj strukturę pierwszego harmonogramu
            if all_schedules:
                first_schedule = all_schedules[0]
                logger.debug(f"📋 DEBUG: Struktura harmonogramu - dostępne pola: {list(first_schedule.keys())}")
                logger.debug(f"📋 DEBUG: Przykładowy harmonogram: {first_schedule}")
            
            # Filtruj harmonogramy HOME (w okolicy domowej lokalizacji)
            home_schedules = []
            home_lat = self.tesla_controller.default_latitude
            home_lon = self.tesla_controller.default_longitude
            home_radius = self.tesla_controller.home_radius
            
            for schedule in all_schedules:
                # NAPRAWKA: Tesla API używa 'latitude' i 'longitude', nie 'lat' i 'lon'
                schedule_lat = schedule.get('latitude', 0.0)
                schedule_lon = schedule.get('longitude', 0.0)
                
                # Oblicz odległość od domu (proste przybliżenie)
                if schedule_lat != 0.0 and schedule_lon != 0.0:
                    import math
                    lat_diff = abs(schedule_lat - home_lat)
                    lon_diff = abs(schedule_lon - home_lon) * math.cos(math.radians(home_lat))
                    distance = (lat_diff**2 + lon_diff**2)**0.5
                    
                    if distance <= home_radius:
                        home_schedules.append(schedule)
                        logger.debug(f"📍 Harmonogram HOME: ID={schedule.get('id')}, odległość={distance:.4f}, współrzędne=({schedule_lat:.6f}, {schedule_lon:.6f})")
                    else:
                        logger.debug(f"📍 Harmonogram OUTSIDE: ID={schedule.get('id')}, odległość={distance:.4f}, współrzędne=({schedule_lat:.6f}, {schedule_lon:.6f})")
                else:
                    # Brak współrzędnych - pomijamy taki harmonogram (powinien być bardzo rzadki)
                    logger.warning(f"📍 Harmonogram bez współrzędnych: ID={schedule.get('id')} - pomijam")
            
            logger.info(f"📍 Znaleziono {len(home_schedules)} harmonogramów HOME z {len(all_schedules)} całkowitych")
            return home_schedules
            
        except Exception as e:
            logger.error(f"Błąd pobierania harmonogramów HOME: {e}")
            return None

    def _schedule_content_matches(self, vehicle_schedule: Dict, desired: 'ChargeSchedule') -> bool:
        """
        Porównuje harmonogram odczytany z pojazdu z pożądanym po treści
        (czasy + enabled). Umożliwia idempotentną rekoncylację: retry po
        częściowej porażce nie duplikuje już obecnych okien.
        """
        if 'one_time' in vehicle_schedule and bool(vehicle_schedule['one_time']) != bool(desired.one_time):
            # Porównuj one_time tylko gdy pojazd raportuje to pole — brak klucza
            # w odczycie nie może wymuszać wiecznego przepisywania okien
            return False
        return (
            vehicle_schedule.get('start_time') == desired.start_time
            and vehicle_schedule.get('end_time') == desired.end_time
            and bool(vehicle_schedule.get('enabled', False)) == bool(desired.enabled)
        )

    def _add_schedules_to_tesla(self, schedules: List[ChargeSchedule], vehicle_vin: str) -> bool:
        """
        Dodaje harmonogramy ładowania do pojazdu Tesla z opóźnieniami i weryfikacją
        
        Args:
            schedules: Lista harmonogramów do dodania
            vehicle_vin: VIN pojazdu
            
        Returns:
            bool: True jeśli dodano wszystkie harmonogramy pomyślnie
        """
        if not schedules:
            logger.info(f"📅 Brak harmonogramów do dodania dla {vehicle_vin[-4:]}")
            return True

        try:
            # OPTYMALIZACJA: Jeden wake_up na początku sekwencji zamiast przed każdą komendą
            logger.info(f"🔄 Budzenie pojazdu przed dodaniem {len(schedules)} harmonogramów...")
            use_proxy = bool(hasattr(self.tesla_controller.fleet_api, 'proxy_url') and self.tesla_controller.fleet_api.proxy_url)
            if not self.tesla_controller.wake_up_vehicle(use_proxy=use_proxy):
                logger.warning(f"⚠️ Wake_up nie powiodło się - kontynuuję mimo to (pojazd może być już online)")

            success_count = 0
            failed_schedules = []

            for i, schedule in enumerate(schedules):
                # NAPRAWKA: Dodaj opóźnienie między harmonogramami (Tesla API może nie nadążać)
                if i > 0:
                    logger.info(f"⏳ Opóźnienie 3s między harmonogramami...")
                    time.sleep(3)
                
                start_time = self.tesla_controller.minutes_to_time(schedule.start_time) if schedule.start_time else "N/A"
                end_time = self.tesla_controller.minutes_to_time(schedule.end_time) if schedule.end_time else "N/A"
                
                logger.info(f"🔄 Dodawanie harmonogramu #{i+1}: {start_time}-{end_time}")

                # OPTYMALIZACJA: skip_wake=True bo wake_up już wywołane na początku sekwencji
                if self.tesla_controller.add_charge_schedule(schedule, skip_wake=True):
                    success_count += 1
                    logger.info(f"✅ Dodano harmonogram #{i+1}: {start_time}-{end_time}")
                else:
                    failed_schedules.append(f"#{i+1}: {start_time}-{end_time}")
                    logger.error(f"❌ Błąd dodawania harmonogramu #{i+1}: {start_time}-{end_time}")
            
            # NAPRAWKA: Dodaj weryfikację po dodaniu harmonogramów
            if success_count > 0:
                logger.info(f"🔍 Weryfikacja dodanych harmonogramów...")
                time.sleep(2)  # Krótkie opóźnienie przed weryfikacją

                # Sprawdź czy KAŻDY dodany harmonogram jest rzeczywiście w Tesla.
                # (Porównanie samych liczb było bez sensu: przed usunięciem starych
                # w pojeździe są jeszcze stare okna — liczby prawie nigdy się nie zgadzały.)
                verification_schedules = self._get_home_schedules_from_tesla(vehicle_vin)
                if verification_schedules is None:
                    # Best-effort: komendy add mają już twardą weryfikację przez pole result;
                    # nieudany odczyt kontrolny nie unieważnia operacji
                    logger.warning(f"⚠️ Nie udało się odczytać harmonogramów do weryfikacji — pomijam kontrolę")
                    verification_schedules = []
                else:
                    missing = [
                        s for s in schedules
                        if not any(self._schedule_content_matches(v, s) for v in verification_schedules)
                    ]
                    if missing:
                        for s in missing:
                            logger.error(f"❌ Harmonogram {s.start_time}-{s.end_time} min zgłoszony jako dodany, "
                                         f"ale NIE znaleziony w pojeździe")
                        return False

                logger.info(f"📊 Weryfikacja: dodano {success_count}, w pojeździe {len(verification_schedules)} harmonogramów HOME")

                # Loguj szczegóły znalezionych harmonogramów
                for j, verified_schedule in enumerate(verification_schedules):
                    schedule_id = verified_schedule.get('id', 'BRAK')
                    start_time_min = verified_schedule.get('start_time', 'N/A')
                    end_time_min = verified_schedule.get('end_time', 'N/A')
                    enabled = verified_schedule.get('enabled', False)
                    
                    # Konwertuj minuty na czas dla lepszego wyświetlenia
                    if isinstance(start_time_min, int):
                        start_time_display = self.tesla_controller.minutes_to_time(start_time_min)
                    else:
                        start_time_display = str(start_time_min)
                    
                    if isinstance(end_time_min, int):
                        end_time_display = self.tesla_controller.minutes_to_time(end_time_min)
                    else:
                        end_time_display = str(end_time_min)
                    
                    logger.info(f"📋 Harmonogram #{j+1} w Tesla: ID={schedule_id}, "
                              f"{start_time_display}-{end_time_display}, enabled={enabled}")
                
                logger.info(f"✅ Weryfikacja pomyślna: wszystkie dodane harmonogramy obecne w pojeździe")
            
            # Loguj szczegółowe wyniki
            logger.info(f"📊 Wynik dodawania harmonogramów:")
            logger.info(f"   ✅ Pomyślnie: {success_count}/{len(schedules)}")
            logger.info(f"   ❌ Nieudane: {len(failed_schedules)}")
            
            if failed_schedules:
                logger.error(f"❌ Nieudane harmonogramy: {', '.join(failed_schedules)}")
            
            return success_count == len(schedules)
            
        except Exception as e:
            logger.error(f"Błąd dodawania harmonogramów do Tesla: {e}")
            return False
    
    def _manage_tesla_charging_schedules(self, off_peak_data: Dict[str, Any], vehicle_vin: str,
                                         vehicle_status: Optional[Dict[str, Any]] = None) -> bool:
        """
        Zarządza harmonogramami ładowania Tesla na podstawie danych z API OFF PEAK CHARGE
        Używa Smart Proxy Mode - uruchamia proxy on-demand dla komend
        NOWA SEKWENCJA: pobiera obecne -> przygotowuje nowe -> wysyła nowe -> usuwa stare
        
        Args:
            off_peak_data: Dane z API OFF PEAK CHARGE
            vehicle_vin: VIN pojazdu
            
        Returns:
            bool: True jeśli zarządzanie harmonogramami powiodło się
        """
        try:
            warsaw_time = self._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 🔧 Rozpoczęto zarządzanie harmonogramami Tesla dla {vehicle_vin[-4:]}")
            
            # NAPRAWKA: Dodaj szczegółową diagnostykę Smart Proxy Mode
            logger.info(f"{time_str} 🔍 Diagnostyka Smart Proxy Mode:")
            logger.info(f"   smart_proxy_mode = {self.smart_proxy_mode}")
            logger.info(f"   proxy_available = {self.proxy_available}")
            logger.info(f"   proxy_running = {self.proxy_running}")
            
            # Sprawdź zmienne środowiskowe
            logger.info(f"   TESLA_SMART_PROXY_MODE = {os.getenv('TESLA_SMART_PROXY_MODE')}")
            logger.info(f"   TESLA_PROXY_AVAILABLE = {os.getenv('TESLA_PROXY_AVAILABLE')}")
            logger.info(f"   TESLA_HTTP_PROXY_HOST = {os.getenv('TESLA_HTTP_PROXY_HOST')}")
            logger.info(f"   TESLA_HTTP_PROXY_PORT = {os.getenv('TESLA_HTTP_PROXY_PORT')}")
            
            # SMART PROXY: Uruchom proxy on-demand dla komend
            proxy_started = False
            # Szczegółowa diagnostyka Smart Proxy Mode
            logger.info(f"{time_str} 🔍 Smart Proxy Mode diagnostyka:")
            logger.info(f"   smart_proxy_mode = {self.smart_proxy_mode}")
            logger.info(f"   proxy_available = {self.proxy_available}")
            logger.info(f"   TESLA_SMART_PROXY_MODE = {os.getenv('TESLA_SMART_PROXY_MODE')}")
            logger.info(f"   TESLA_PROXY_AVAILABLE = {os.getenv('TESLA_PROXY_AVAILABLE')}")
            logger.info(f"   TESLA_HTTP_PROXY_HOST = {os.getenv('TESLA_HTTP_PROXY_HOST')}")
            logger.info(f"   TESLA_HTTP_PROXY_PORT = {os.getenv('TESLA_HTTP_PROXY_PORT')}")
            
            if self.smart_proxy_mode and self.proxy_available:
                logger.info(f"{time_str} 🚀 Uruchamianie Tesla HTTP Proxy on-demand...")
                proxy_started = self._start_proxy_on_demand()
                if not proxy_started:
                    logger.error(f"{time_str} ❌ Nie udało się uruchomić Tesla HTTP Proxy")
                    logger.warning(f"{time_str} ⚠️ Próba zarządzania harmonogramami bez proxy (może nie działać)")
                else:
                    logger.info(f"{time_str} ✅ Tesla HTTP Proxy uruchomiony pomyślnie")
                    
                    # NAPRAWKA: Upewnij się że TeslaController używa proxy
                    if hasattr(self.tesla_controller, 'fleet_api'):
                        # Sprawdź konfigurację proxy w TeslaController
                        proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST', 'localhost')
                        proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT', '4443')
                        expected_proxy_url = f"https://{proxy_host}:{proxy_port}"
                        
                        current_proxy_url = getattr(self.tesla_controller.fleet_api, 'proxy_url', None)
                        
                        if current_proxy_url:
                            logger.info(f"{time_str} ✅ TeslaController ma skonfigurowany proxy: {current_proxy_url}")
                        else:
                            # Ustaw proxy_url w fleet_api (to powinno być zrobione przez konstruktor)
                            if hasattr(self.tesla_controller.fleet_api, 'proxy_url'):
                                self.tesla_controller.fleet_api.proxy_url = expected_proxy_url
                                logger.info(f"{time_str} 🔗 Skonfigurowano proxy w TeslaController: {expected_proxy_url}")
                            else:
                                logger.warning(f"{time_str} ⚠️ TeslaController nie obsługuje konfiguracji proxy")
            else:
                logger.warning(f"{time_str} ⚠️ Smart Proxy Mode wyłączony lub niedostępny")
                if not self.smart_proxy_mode:
                    logger.warning(f"   - smart_proxy_mode = False (wyłączony)")
                if not self.proxy_available:
                    logger.warning(f"   - proxy_available = False (niedostępny)")
            
            try:
                # 1. Pobierz obecne harmonogramy HOME z Tesla
                logger.info(f"{time_str} 📋 Pobieranie obecnych harmonogramów HOME...")
                current_home_schedules = self._get_home_schedules_from_tesla(vehicle_vin)

                if current_home_schedules is None:
                    # Bez wiedzy o obecnym stanie pojazdu nie można bezpiecznie
                    # rekoncyliować — dodanie "na ślepo" tworzy duplikaty/osierocone okna
                    logger.error(f"{time_str} ❌ Nie udało się odczytać obecnych harmonogramów — przerywam (retry w następnym cyklu)")
                    return False

                if current_home_schedules:
                    logger.info(f"{time_str} 📍 Znaleziono {len(current_home_schedules)} starych harmonogramów HOME")
                else:
                    logger.info(f"{time_str} 📍 Brak starych harmonogramów HOME")
                
                # 2. Konwertuj harmonogramy z API OFF PEAK CHARGE
                logger.info(f"{time_str} 🔄 Konwersja harmonogramów z API OFF PEAK CHARGE...")
                new_schedules = self._convert_off_peak_to_tesla_schedules(off_peak_data, vehicle_vin)
                
                if not new_schedules:
                    logger.warning(f"{time_str} ⚠️ Brak harmonogramów do dodania z API OFF PEAK CHARGE")
                    return True  # Techniczne powodzenie - po prostu nie ma harmonogramów
                
                # 3. Rozwiąż nakładania harmonogramów (zachowaj kolejność priorytetów z API)
                logger.info(f"{time_str} 🔍 Sprawdzanie nakładań harmonogramów...")
                resolved_schedules = self._resolve_schedule_overlaps(new_schedules, vehicle_vin)

                # REKONCYLIACJA (idempotencja): porównaj pożądany stan z obecnym.
                # Dodawaj tylko okna, których nie ma; usuwaj tylko te, które nie
                # pasują do nowego planu. Retry po częściowej porażce oraz podwójny
                # trigger nie duplikują wtedy okien w pojeździe.
                schedules_to_add = [
                    s for s in resolved_schedules
                    if not any(self._schedule_content_matches(c, s) for c in current_home_schedules)
                ]
                # OCHRONA SPECIAL CHARGING: okna aktywnych/zaplanowanych sesji special
                # nie podlegają wymieceniu przez zwykły cykl
                protected_ids = self._get_protected_schedule_ids(vehicle_vin)
                if protected_ids is None:
                    logger.error(f"{time_str} ❌ Nie można ustalić chronionych harmonogramów special — przerywam (retry w następnym cyklu)")
                    return False

                schedules_to_remove = [
                    c for c in current_home_schedules
                    if c.get('id') not in protected_ids
                    and not any(self._schedule_content_matches(c, s) for s in resolved_schedules)
                ]

                if not schedules_to_add and not schedules_to_remove:
                    logger.info(f"{time_str} ✅ Stan pojazdu zgodny z planem — brak operacji do wykonania")
                    return True

                # NAPRAWKA: Szczegółowe logowanie harmonogramów przed dodaniem
                logger.info(f"{time_str} 📋 Harmonogramy do dodania ({len(schedules_to_add)}) / usunięcia ({len(schedules_to_remove)}):")
                for k, schedule in enumerate(schedules_to_add):
                    start_time_display = self.tesla_controller.minutes_to_time(schedule.start_time) if schedule.start_time else "N/A"
                    end_time_display = self.tesla_controller.minutes_to_time(schedule.end_time) if schedule.end_time else "N/A"
                    logger.info(f"   +#{k+1}: {start_time_display}-{end_time_display} "
                              f"(minuty: {schedule.start_time}-{schedule.end_time}), "
                              f"enabled={schedule.enabled}")
                for k, old in enumerate(schedules_to_remove):
                    logger.info(f"   -#{k+1}: ID={old.get('id')}, {old.get('start_time')}-{old.get('end_time')} min")

                # 4. Dodaj nowe harmonogramy do Tesla (wymaga proxy)
                logger.info(f"{time_str} ➕ Dodawanie {len(schedules_to_add)} nowych harmonogramów...")
                
                if proxy_started:
                    # Poczekaj na pełne uruchomienie proxy
                    logger.info(f"{time_str} ⏳ Oczekiwanie na stabilizację proxy (3s)...")
                    time.sleep(3)
                    
                    addition_success = self._add_schedules_to_tesla(schedules_to_add, vehicle_vin)
                    if addition_success:
                        logger.info(f"{time_str} ✅ Pomyślnie dodano nowe harmonogramy Tesla")
                        
                        # NAPRAWKA: Dodaj szczegółowe logowanie stanu po dodaniu
                        logger.info(f"{time_str} 🔍 Stan harmonogramów HOME w Tesla po dodaniu:")
                        updated_schedules = self._get_home_schedules_from_tesla(vehicle_vin)
                        if updated_schedules:
                            for f, updated_schedule in enumerate(updated_schedules):
                                schedule_id = updated_schedule.get('id', 'BRAK')
                                start_time_min = updated_schedule.get('start_time', 'N/A')
                                end_time_min = updated_schedule.get('end_time', 'N/A')
                                enabled = updated_schedule.get('enabled', False)
                                
                                if isinstance(start_time_min, int):
                                    start_display = self.tesla_controller.minutes_to_time(start_time_min)
                                else:
                                    start_display = str(start_time_min)
                                
                                if isinstance(end_time_min, int):
                                    end_display = self.tesla_controller.minutes_to_time(end_time_min)
                                else:
                                    end_display = str(end_time_min)
                                
                                logger.info(f"   Harmonogram #{f+1}: ID={schedule_id}, "
                                          f"{start_display}-{end_display}, enabled={enabled}")
                        
                        # 5. NOWA SEKWENCJA: Usuń stare harmonogramy PO dodaniu nowych
                        removal_success = True
                        if schedules_to_remove:
                            logger.info(f"{time_str} 🗑️ Usuwanie {len(schedules_to_remove)} starych harmonogramów HOME...")
                            removal_success = self._remove_old_schedules_from_tesla(schedules_to_remove, vehicle_vin)
                            if not removal_success:
                                # Częściowa porażka NIE jest sukcesem: pozostawione stare okna
                                # (days=All) odpalą się w złych godzinach. Zwracamy False, żeby
                                # hash nie został zatwierdzony i retry dokończył sprzątanie
                                # (rekoncyliacja zapewnia, że retry nie zduplikuje dodanych okien).
                                logger.error(f"{time_str} ❌ Nie wszystkie stare harmonogramy zostały usunięte — operacja NIEUDANA (retry dokończy)")
                            else:
                                logger.info(f"{time_str} ✅ Pomyślnie usunięto stare harmonogramy HOME")
                        else:
                            logger.info(f"{time_str} 📍 Brak starych harmonogramów HOME do usunięcia")
                        
                        # NAPRAWKA: Dodaj szczegółowe logowanie końcowego stanu
                        logger.info(f"{time_str} 🔍 Końcowy stan harmonogramów HOME w Tesla:")
                        final_schedules = self._get_home_schedules_from_tesla(vehicle_vin)
                        if final_schedules:
                            for f, final_schedule in enumerate(final_schedules):
                                schedule_id = final_schedule.get('id', 'BRAK')
                                start_time_min = final_schedule.get('start_time', 'N/A')
                                end_time_min = final_schedule.get('end_time', 'N/A')
                                enabled = final_schedule.get('enabled', False)
                                
                                if isinstance(start_time_min, int):
                                    start_display = self.tesla_controller.minutes_to_time(start_time_min)
                                else:
                                    start_display = str(start_time_min)
                                
                                if isinstance(end_time_min, int):
                                    end_display = self.tesla_controller.minutes_to_time(end_time_min)
                                else:
                                    end_display = str(end_time_min)
                                
                                logger.info(f"   Aktywny #{f+1}: ID={schedule_id}, "
                                          f"{start_display}-{end_display}, enabled={enabled}")
                        else:
                            logger.info(f"{time_str} 📍 Brak harmonogramów HOME w Tesla po operacji")
                        
                        # Zapisz informacje o operacji
                        operation_data = {
                            'operation': 'schedule_management_new_sequence',
                            'old_schedules_count': len(current_home_schedules),
                            'added_schedules': len(schedules_to_add),
                            'removed_schedules': len(schedules_to_remove),
                            'removal_success': removal_success,
                            'final_schedules': len(final_schedules) if final_schedules else 0,
                            'operation_success': removal_success,
                            'proxy_used': True,
                            'sequence_version': 'v3.1_reconciliation'
                        }

                        self._log_event(
                            message="Tesla charging schedules updated with reconciliation sequence",
                            vehicle_vin=vehicle_vin,
                            extra_data=operation_data
                        )

                        # FAZA 2: wyrównaj faktyczny stan ładowania z nowym planem
                        # (auto charge_start w oknie / charge_stop poza oknem — patrz docstring)
                        self._align_charging_with_plan(resolved_schedules, vehicle_vin, vehicle_status)

                        return removal_success
                    else:
                        logger.error(f"{time_str} ❌ Błąd dodawania nowych harmonogramów")
                        
                        # NAPRAWKA: Loguj stan po nieudanym dodaniu
                        logger.error(f"{time_str} 🔍 Stan harmonogramów HOME po nieudanym dodaniu:")
                        error_schedules = self._get_home_schedules_from_tesla(vehicle_vin)
                        if error_schedules:
                            for e, error_schedule in enumerate(error_schedules):
                                schedule_id = error_schedule.get('id', 'BRAK')
                                start_time_min = error_schedule.get('start_time', 'N/A')
                                end_time_min = error_schedule.get('end_time', 'N/A')
                                enabled = error_schedule.get('enabled', False)
                                logger.error(f"   Pozostały #{e+1}: ID={schedule_id}, "
                                           f"{start_time_min}-{end_time_min}, enabled={enabled}")
                        else:
                            logger.error(f"{time_str} ❌ Brak harmonogramów HOME w Tesla po nieudanym dodaniu")
                        
                        return False
                else:
                    logger.error(f"{time_str} ❌ Nie można dodać harmonogramów - brak Tesla HTTP Proxy")
                    logger.error(f"{time_str} 💡 Komendy add/remove_charge_schedule wymagają Tesla HTTP Proxy")
                    logger.error(f"{time_str} 💡 Fleet API nie obsługuje tych komend bez proxy")
                    
                    self._log_event(
                        message="Tesla charging schedules management failed - no proxy available",
                        vehicle_vin=vehicle_vin,
                        extra_data={
                            'operation': 'schedule_management_failed',
                            'error': 'no_proxy_available',
                            'operation_success': False,
                            'proxy_used': False,
                            'smart_proxy_mode': self.smart_proxy_mode,
                            'proxy_available': self.proxy_available
                        }
                    )
                    return False
                    
            finally:
                # SMART PROXY: Zatrzymaj proxy po zakończeniu komend
                if proxy_started and self.proxy_running:
                    logger.info(f"{time_str} 🛑 Zatrzymywanie Tesla HTTP Proxy po zakończeniu komend...")
                    self._stop_proxy()
                    
                    # NAPRAWKA: Przywróć TeslaController do używania Fleet API
                    if hasattr(self.tesla_controller, 'fleet_api') and hasattr(self.tesla_controller.fleet_api, 'use_proxy'):
                        self.tesla_controller.fleet_api.use_proxy = False
                        logger.info(f"{time_str} 🔙 TeslaController przywrócony do Fleet API")
                    
        except Exception as e:
            logger.error(f"Błąd zarządzania harmonogramami Tesla: {e}")
            logger.error(f"Typ błędu: {type(e).__name__}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
            
            self._log_event(
                message=f"Tesla charging schedules management error: {e}",
                vehicle_vin=vehicle_vin,
                extra_data={
                    'operation': 'schedule_management_error',
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'operation_success': False
                }
            )
            return False

    def _disable_home_schedules_from_tesla(self, vehicle_vin: str) -> bool:
        """
        Wyłącza wszystkie harmonogramy ładowania z lokalizacji HOME z pojazdu Tesla
        (alternatywa dla usuwania, gdy Fleet API nie obsługuje remove_charge_schedule)
        
        Args:
            vehicle_vin: VIN pojazdu
            
        Returns:
            bool: True jeśli wyłączono harmonogramy pomyślnie
        """
        try:
            home_schedules = self._get_home_schedules_from_tesla(vehicle_vin)

            if home_schedules is None:
                logger.error(f"📍 Błąd odczytu harmonogramów HOME dla {vehicle_vin[-4:]} — nie można wyłączać")
                return False

            if not home_schedules:
                logger.info(f"📍 Brak harmonogramów HOME do wyłączenia dla {vehicle_vin[-4:]}")
                return True

            # OPTYMALIZACJA: Jeden wake_up przed całą sekwencją wyłączania (unika HTTP 429)
            logger.info(f"🔄 Budzenie pojazdu przed wyłączeniem {len(home_schedules)} harmonogramów...")
            use_proxy = bool(hasattr(self.tesla_controller.fleet_api, 'proxy_url') and self.tesla_controller.fleet_api.proxy_url)
            if not self.tesla_controller.wake_up_vehicle(use_proxy=use_proxy):
                logger.warning(f"⚠️ Wake_up nie powiodło się - kontynuuję mimo to (pojazd może być już online)")

            success_count = 0
            for schedule in home_schedules:
                schedule_id = schedule.get('id')
                if schedule_id and schedule.get('enabled', False):
                    # Wyłącz harmonogram modyfikując go z enabled=False
                    try:
                        modified_schedule = ChargeSchedule(
                            id=schedule_id,
                            enabled=False,  # Wyłącz harmonogram
                            days_of_week=schedule.get('days_of_week', 'All'),
                            lat=schedule.get('latitude', self.tesla_controller.default_latitude),
                            lon=schedule.get('longitude', self.tesla_controller.default_longitude),
                            start_enabled=schedule.get('start_enabled', False),
                            end_enabled=schedule.get('end_enabled', False),
                            start_time=schedule.get('start_time'),
                            end_time=schedule.get('end_time'),
                            one_time=schedule.get('one_time', False)
                        )
                        
                        # OPTYMALIZACJA: skip_wake=True bo wake_up już wywołane na początku sekwencji
                        if self.tesla_controller.add_charge_schedule(modified_schedule, skip_wake=True):
                            success_count += 1
                            logger.info(f"🔕 Wyłączono harmonogram HOME ID: {schedule_id}")
                        else:
                            logger.error(f"❌ Błąd wyłączania harmonogramu HOME ID: {schedule_id}")
                    except Exception as modify_error:
                        logger.error(f"❌ Błąd modyfikacji harmonogramu HOME ID {schedule_id}: {modify_error}")
                elif schedule_id and not schedule.get('enabled', True):
                    logger.info(f"ℹ️ Harmonogram HOME ID {schedule_id} już wyłączony")
                    success_count += 1
            
            logger.info(f"🔕 Wyłączono {success_count}/{len(home_schedules)} harmonogramów HOME")
            return success_count == len(home_schedules)
            
        except Exception as e:
            logger.error(f"Błąd wyłączania harmonogramów HOME: {e}")
            return False

    def _start_proxy_on_demand(self) -> bool:
        """
        Uruchamia Tesla HTTP Proxy on-demand
        
        Returns:
            bool: True jeśli proxy został uruchomiony pomyślnie
        """
        if not self.smart_proxy_mode or not self.proxy_available:
            logger.warning("⚠️ Smart Proxy Mode wyłączony lub proxy niedostępny")
            logger.warning(f"   smart_proxy_mode = {self.smart_proxy_mode}")
            logger.warning(f"   proxy_available = {self.proxy_available}")
            return False
        
        # NAPRAWKA: Sprawdź gotowość private key przed uruchomieniem proxy
        private_key_ready = os.getenv('TESLA_PRIVATE_KEY_READY', 'false').lower() == 'true'
        if not private_key_ready:
            logger.warning("⚠️ Private key nie jest gotowy - nie można uruchomić Tesla HTTP Proxy")
            logger.warning("💡 Sprawdź czy startup_worker.sh poprawnie pobrał private key")
            return False
        
        # Sprawdź czy plik private key istnieje i nie jest pusty
        if not os.path.exists('private-key.pem'):
            logger.error("❌ Plik private-key.pem nie istnieje")
            return False
        
        try:
            key_size = os.path.getsize('private-key.pem')
            if key_size == 0:
                logger.error("❌ Plik private-key.pem jest pusty")
                return False
            logger.info(f"✅ Private key zweryfikowany ({key_size} bajtów)")
        except Exception as key_error:
            logger.error(f"❌ Błąd sprawdzania private key: {key_error}")
            return False
        
        if self.proxy_running:
            logger.info("🔧 Tesla HTTP Proxy już działa - sprawdzam połączenie...")
            if self._test_proxy_connection():
                logger.info("✅ Tesla HTTP Proxy jest aktywny i odpowiada")
                return True
            else:
                logger.warning("⚠️ Tesla HTTP Proxy proces działa ale nie odpowiada - restartuję...")
                self._stop_proxy()
        
        try:
            import subprocess
            import time
            
            proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST', 'localhost')
            proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT', '4443')
            
            logger.info(f"🚀 Uruchamianie Tesla HTTP Proxy on-demand...")
            logger.info(f"   Host: {proxy_host}")
            logger.info(f"   Port: {proxy_port}")
            
            # Sprawdź czy port jest wolny
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((proxy_host, int(proxy_port)))
            sock.close()
            
            if result == 0:
                logger.warning(f"⚠️ Port {proxy_port} jest już zajęty - sprawdzam czy to nasze proxy...")
                if self._test_proxy_connection():
                    logger.info("✅ Znaleziono działające Tesla HTTP Proxy na porcie")
                    self.proxy_running = True
                    return True
                else:
                    logger.error(f"❌ Port {proxy_port} zajęty przez inny proces")
                    return False
            
            # Sprawdź czy private-key.pem istnieje
            if not os.path.exists('private-key.pem'):
                logger.error("❌ Brak pliku private-key.pem - proxy nie może być uruchomiony")
                logger.error("💡 Sprawdź czy klucz został pobrany z Secret Manager")
                return False
            
            # Sprawdź rozmiar klucza prywatnego
            try:
                key_size = os.path.getsize('private-key.pem')
                if key_size == 0:
                    logger.error("❌ Plik private-key.pem jest pusty")
                    return False
                logger.info(f"✅ Klucz prywatny znaleziony ({key_size} bajtów)")
            except Exception as key_error:
                logger.error(f"❌ Błąd sprawdzania klucza prywatnego: {key_error}")
                return False
            
            # Generuj certyfikaty TLS jeśli nie istnieją
            if not os.path.exists('tls-key.pem') or not os.path.exists('tls-cert.pem'):
                logger.info("🔐 Generowanie certyfikatów TLS...")
                try:
                    result = subprocess.run([
                        'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
                        '-keyout', 'tls-key.pem', '-out', 'tls-cert.pem',
                        '-days', '365', '-nodes',
                        '-subj', '/C=PL/ST=Mazowieckie/L=Warsaw/O=Tesla Monitor/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'
                    ], check=True, capture_output=True, text=True)
                    logger.info("✅ Certyfikaty TLS wygenerowane pomyślnie")
                except subprocess.CalledProcessError as cert_error:
                    logger.error(f"❌ Błąd generowania certyfikatów TLS: {cert_error}")
                    logger.error(f"stdout: {cert_error.stdout}")
                    logger.error(f"stderr: {cert_error.stderr}")
                    return False
            
            # Sprawdź czy tesla-http-proxy jest dostępny
            try:
                result = subprocess.run(['tesla-http-proxy', '--help'], 
                                      capture_output=True, text=True, timeout=5)
                logger.info("✅ tesla-http-proxy jest dostępny")
            except subprocess.TimeoutExpired:
                logger.error("❌ tesla-http-proxy timeout - może być zawieszony")
                return False
            except FileNotFoundError:
                logger.error("❌ tesla-http-proxy nie znaleziony w PATH")
                logger.error("💡 Sprawdź czy tesla-http-proxy jest zainstalowany")
                return False
            except Exception as proxy_check_error:
                logger.error(f"❌ Błąd sprawdzania tesla-http-proxy: {proxy_check_error}")
                return False
            
            # Uruchom Tesla HTTP Proxy
            proxy_cmd = [
                'tesla-http-proxy',
                '-tls-key', 'tls-key.pem',
                '-cert', 'tls-cert.pem',
                '-port', proxy_port,
                '-host', proxy_host,
                '-key-name', 'tesla-fleet-api',
                '-keyring-type', 'file',
                '-key-file', 'private-key.pem',
                '-verbose'  # NAPRAWKA: Dodaj verbose dla lepszego debugowania
            ]
            
            logger.info(f"🔧 Komenda proxy: {' '.join(proxy_cmd)}")
            
            self.proxy_process = subprocess.Popen(
                proxy_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            logger.info(f"⏳ Oczekiwanie na uruchomienie proxy (PID: {self.proxy_process.pid})...")
            
            # Poczekaj na uruchomienie proxy z progressivnym timeout'em
            for attempt in range(1, 11):  # 10 prób
                time.sleep(1)
                
                # Sprawdź czy proces nadal działa
                if self.proxy_process.poll() is not None:
                    # Proxy się zatrzymał
                    stdout, stderr = self.proxy_process.communicate()
                    logger.error(f"❌ Tesla HTTP Proxy zatrzymał się podczas startu (próba {attempt})")
                    logger.error(f"stdout: {stdout}")
                    logger.error(f"stderr: {stderr}")
                    return False
                
                # Test połączenia
                if self._test_proxy_connection():
                    self.proxy_running = True
                    logger.info(f"✅ Tesla HTTP Proxy uruchomiony pomyślnie po {attempt}s (PID: {self.proxy_process.pid})")
                    
                    # Dodatkowy test autoryzacji
                    try:
                        proxy_url = f"https://{proxy_host}:{proxy_port}"
                        response = requests.get(f"{proxy_url}/api/1/vehicles", 
                                              timeout=5, verify=False)
                        logger.info(f"🔗 Test autoryzacji proxy: status {response.status_code}")
                    except Exception as auth_test_error:
                        logger.debug(f"Test autoryzacji błąd: {auth_test_error}")
                    
                    return True
                
                if attempt % 3 == 0:  # Co 3 sekundy
                    logger.info(f"⏳ Próba {attempt}/10 - czekam na odpowiedź proxy...")
            
            # Timeout - proxy nie odpowiada
            logger.error("❌ Tesla HTTP Proxy nie odpowiada po 10 sekundach")
            
            # Sprawdź czy proces jeszcze działa
            if self.proxy_process.poll() is None:
                logger.error("🔍 Proces proxy działa ale nie odpowiada - sprawdzam logi...")
                # Spróbuj odczytać partial output
                try:
                    stdout, stderr = self.proxy_process.communicate(timeout=2)
                    if stdout:
                        logger.error(f"stdout: {stdout[:500]}...")
                    if stderr:
                        logger.error(f"stderr: {stderr[:500]}...")
                except subprocess.TimeoutExpired:
                    logger.error("⏰ Nie można odczytać logów proxy - timeout")
            
            self._stop_proxy()
            return False
                
        except subprocess.SubprocessError as e:
            logger.error(f"❌ Błąd uruchamiania Tesla HTTP Proxy: {e}")
            return False
        except Exception as e:
            logger.error(f"💥 Nieoczekiwany błąd uruchamiania proxy: {e}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return False
    
    def _stop_proxy(self):
        """Zatrzymuje Tesla HTTP Proxy"""
        if self.proxy_process and self.proxy_process.poll() is None:
            try:
                self.proxy_process.terminate()
                self.proxy_process.wait(timeout=10)
                logger.info("🛑 Tesla HTTP Proxy zatrzymany")
            except subprocess.TimeoutExpired:
                self.proxy_process.kill()
                logger.warning("⚠️ Tesla HTTP Proxy zabity (timeout)")
            except Exception as e:
                logger.error(f"❌ Błąd zatrzymywania proxy: {e}")
        
        self.proxy_running = False
        self.proxy_process = None
        
        # Wyczyść certyfikaty TLS
        try:
            if os.path.exists('tls-key.pem'):
                os.remove('tls-key.pem')
            if os.path.exists('tls-cert.pem'):
                os.remove('tls-cert.pem')
        except Exception as e:
            logger.debug(f"Błąd czyszczenia certyfikatów: {e}")
    
    def _test_proxy_connection(self) -> bool:
        """
        Testuje połączenie z Tesla HTTP Proxy
        
        Returns:
            bool: True jeśli proxy odpowiada
        """
        try:
            import requests
            
            proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST', 'localhost')
            proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT', '4443')
            proxy_url = f"https://{proxy_host}:{proxy_port}"
            
            # Test połączenia z timeout'em i bez weryfikacji SSL (self-signed cert)
            response = requests.get(
                f"{proxy_url}/api/1/vehicles",
                timeout=10,
                verify=False  # Tesla HTTP Proxy używa self-signed cert
            )
            
            if response.status_code in [200, 401, 403]:  # 200=OK, 401/403=auth error ale proxy działa
                return True
            else:
                logger.warning(f"⚠️ Tesla HTTP Proxy niespodziewany status: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            return False
        except requests.exceptions.Timeout:
            return False
        except Exception as e:
            logger.debug(f"Błąd testowania proxy: {e}")
            return False

    def _test_tesla_proxy_connection(self, proxy_host: str, proxy_port: str):
        """
        Testuje połączenie z Tesla HTTP Proxy
        
        Args:
            proxy_host: Host proxy (np. localhost)
            proxy_port: Port proxy (np. 4443)
        """
        try:
            import requests
            import ssl
            
            proxy_url = f"https://{proxy_host}:{proxy_port}"
            logger.info(f"🔗 Testuję połączenie z Tesla HTTP Proxy: {proxy_url}")
            
            # Test połączenia z timeout'em i bez weryfikacji SSL (self-signed cert)
            response = requests.get(
                f"{proxy_url}/api/1/vehicles",
                timeout=10,
                verify=False  # Tesla HTTP Proxy używa self-signed cert
            )
            
            if response.status_code in [200, 401, 403]:  # 200=OK, 401/403=auth error ale proxy działa
                logger.info(f"✅ Tesla HTTP Proxy odpowiada (status: {response.status_code})")
                if response.status_code == 401:
                    logger.info("🔐 Tesla HTTP Proxy wymaga autoryzacji - to normalne")
            else:
                logger.warning(f"⚠️ Tesla HTTP Proxy niespodziewany status: {response.status_code}")
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Nie można połączyć się z Tesla HTTP Proxy: {e}")
            logger.error(f"💡 Sprawdź czy Tesla HTTP Proxy jest uruchomiony na {proxy_host}:{proxy_port}")
        except requests.exceptions.Timeout:
            logger.error(f"⏰ Timeout połączenia z Tesla HTTP Proxy (10s)")
        except Exception as e:
            logger.error(f"💥 Błąd testowania Tesla HTTP Proxy: {e}")

    def _get_firestore_client(self):
        """Zwraca klienta Firestore dla Worker Service"""
        return self.firestore_client



    def _remove_old_schedules_from_tesla(self, old_schedules: List[Dict], vehicle_vin: str) -> bool:
        """
        Usuwa konkretne harmonogramy ładowania z pojazdu Tesla
        NOWA WERSJA: bez logiki charge_stop - usuwa tylko podane harmonogramy
        
        Args:
            old_schedules: Lista starych harmonogramów do usunięcia
            vehicle_vin: VIN pojazdu
            
        Returns:
            bool: True jeśli usunięto wszystkie harmonogramy pomyślnie
        """
        try:
            if not old_schedules:
                logger.info(f"📍 Brak harmonogramów do usunięcia dla {vehicle_vin[-4:]}")
                return True

            # OPTYMALIZACJA: Jeden wake_up na początku sekwencji zamiast przed każdą komendą
            logger.info(f"🔄 Budzenie pojazdu przed usunięciem {len(old_schedules)} harmonogramów...")
            use_proxy = bool(hasattr(self.tesla_controller.fleet_api, 'proxy_url') and self.tesla_controller.fleet_api.proxy_url)
            if not self.tesla_controller.wake_up_vehicle(use_proxy=use_proxy):
                logger.warning(f"⚠️ Wake_up nie powiodło się - kontynuuję mimo to (pojazd może być już online)")

            # Usuń podane harmonogramy
            logger.info(f"🗑️ Usuwanie {len(old_schedules)} starych harmonogramów...")
            success_count = 0

            for schedule in old_schedules:
                schedule_id = schedule.get('id')
                if schedule_id:
                    logger.info(f"🗑️ Próba usunięcia starego harmonogramu ID: {schedule_id}")
                    
                    # Wyświetl szczegóły harmonogramu przed usunięciem
                    start_time = schedule.get('start_time', 'N/A')
                    end_time = schedule.get('end_time', 'N/A')
                    enabled = schedule.get('enabled', False)
                    logger.info(f"📋 Stary harmonogram {schedule_id}: {start_time}-{end_time}, enabled={enabled}")
                    
                    try:
                        # OPTYMALIZACJA: skip_wake=True bo wake_up już wywołane na początku sekwencji
                        if self.tesla_controller.remove_charge_schedule(schedule_id, skip_wake=True):
                            success_count += 1
                            logger.info(f"✅ Usunięto stary harmonogram ID: {schedule_id}")
                        else:
                            logger.error(f"❌ Błąd usuwania starego harmonogramu ID: {schedule_id}")
                            
                            # Sprawdź czy harmonogram nadal istnieje.
                            # Przy błędzie odczytu (None) załóż ostrożnie, że istnieje —
                            # NIE wolno liczyć nieusuniętego okna jako sukces.
                            current_schedules = self._get_home_schedules_from_tesla(vehicle_vin)
                            still_exists = current_schedules is None or any(s.get('id') == schedule_id for s in current_schedules)
                            if still_exists:
                                logger.error(f"🔍 Stary harmonogram {schedule_id} nadal istnieje w Tesla")
                            else:
                                logger.info(f"🤔 Stary harmonogram {schedule_id} nie istnieje w Tesla - może został już usunięty")
                                success_count += 1  # Traktuj jako sukces
                            
                    except Exception as remove_error:
                        logger.error(f"💥 Wyjątek podczas usuwania starego harmonogramu ID {schedule_id}: {remove_error}")
                        logger.error(f"💡 Typ błędu: {type(remove_error).__name__}")
                        
                        # Sprawdź czy to błąd autoryzacji
                        if "401" in str(remove_error) or "unauthorized" in str(remove_error).lower():
                            logger.error(f"🚫 Błąd autoryzacji - sprawdź tokeny Tesla")
                        elif "412" in str(remove_error) or "not supported" in str(remove_error).lower():
                            logger.error(f"🚫 Komenda nie obsługiwana - sprawdź czy Tesla HTTP Proxy działa")
                        elif "timeout" in str(remove_error).lower():
                            logger.error(f"⏰ Timeout - Tesla API może być przeciążone")
                else:
                    logger.error(f"❌ Stary harmonogram bez ID - pomijam")
            
            logger.info(f"🗑️ Usunięto {success_count}/{len(old_schedules)} starych harmonogramów")
            
            # Jeśli nie udało się usunąć wszystkich, ale udało się przynajmniej część
            if success_count > 0 and success_count < len(old_schedules):
                logger.warning(f"⚠️ Częściowy sukces usuwania starych harmonogramów ({success_count}/{len(old_schedules)})")
                
            return success_count == len(old_schedules)
            
        except Exception as e:
            logger.error(f"Błąd usuwania starych harmonogramów: {e}")
            return False

def main():
    """Główna funkcja uruchamiająca monitor"""
    logger.info("🚀 === URUCHAMIANIE TESLA MONITOR ===")
    
    try:
        logger.info("🏗️ Tworzenie instancji CloudTeslaMonitor...")
        monitor = CloudTeslaMonitor()
        logger.info("✅ Instancja CloudTeslaMonitor utworzona pomyślnie")
    except Exception as init_error:
        logger.error(f"💥 KRYTYCZNY błąd tworzenia monitora: {init_error}")
        logger.error(f"💥 Typ błędu: {type(init_error).__name__}")
        import traceback
        logger.error(f"💥 Stack trace: {traceback.format_exc()}")
        return 1
    
    try:
        logger.info("▶️ Rozpoczynam monitoring...")
        monitor.start_monitoring()
        logger.info("✅ Monitoring zakończony normalnie")
    except Exception as e:
        logger.error(f"💥 KRYTYCZNY błąd uruchamiania monitora: {e}")
        logger.error(f"💥 Typ błędu: {type(e).__name__}")
        import traceback
        logger.error(f"💥 Stack trace: {traceback.format_exc()}")
        return 1
    
    logger.info("🏁 === KONIEC TESLA MONITOR ===")
    return 0

if __name__ == "__main__":
    try:
        logger.info("🎬 === URUCHAMIANIE GŁÓWNEJ FUNKCJI ===")
        exit_code = main()
        logger.info(f"🏁 Aplikacja kończy działanie z kodem: {exit_code}")
        
        # Loguj dlaczego aplikacja się kończy
        import traceback
        logger.info("🔍 Aplikacja kończy się z:")
        for line in traceback.format_stack():
            logger.info(f"🔍   {line.strip()}")
            
        logger.info(f"⚡ Wywołuję exit({exit_code})")
        exit(exit_code)
    except Exception as final_error:
        logger.error(f"💥 FINAŁOWY błąd aplikacji: {final_error}")
        import traceback
        logger.error(f"💥 Stack trace: {traceback.format_exc()}")
        logger.info("⚡ Wywołuję exit(1) przez błąd")
        exit(1) 