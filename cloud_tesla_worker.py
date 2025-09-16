#!/usr/bin/env python3
"""
Cloud Tesla Worker - Ciężka usługa Cloud Run dla pełnej logiki Tesla
Część architektury "Scout & Worker" dla agresywnej optymalizacji kosztów

ZADANIE:
- Uruchamiana TYLKO gdy Scout wykryje powrót pojazdu do domu (2-3x dziennie)
- Wykonuje pełną logikę: OFF PEAK CHARGE API + Tesla HTTP Proxy + harmonogramy
- Skaluje do zera między wywołaniami
- Używa tej samej logiki co cloud_tesla_monitor.py ale bez ciągłego działania

ARCHITEKTURA:
Scout Function (tania, częsta) -> Worker Service (droga, rzadka)
"""

import os
import sys
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import gspread
from google.oauth2.service_account import Credentials

# Importuj całą logikę z głównej aplikacji
# Dziedziczymy wszystkie funkcjonalności z cloud_tesla_monitor.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from cloud_tesla_monitor import (
        CloudTeslaMonitor,
        HealthCheckHandler,
        get_secret,
        _log_simple_status
    )
    from tesla_controller import ChargeSchedule
except ImportError as e:
    logging.error(f"❌ Błąd importu z cloud_tesla_monitor.py: {e}")
    sys.exit(1)

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import signal

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Stałe dla Special Charging
CHARGING_RATE = 11  # kW/h (średnia moc ładowania)
PEAK_HOURS = [(6, 10), (19, 22)]  # Godziny drogie (6:00-10:00, 19:00-22:00)
SAFETY_BUFFER_HOURS = 1.5  # Buffer bezpieczeństwa
MIN_ADVANCE_HOURS = 6  # Minimum 6h przed docelowym czasem
MAX_ADVANCE_HOURS = 24  # Maximum 24h przed docelowym czasem
BATTERY_CAPACITY_KWH = 75  # Pojemność baterii (domyślna)

# Zmienne środowiskowe dla Dynamic Scheduler
PROJECT_ID = os.getenv('GOOGLE_CLOUD_PROJECT')
LOCATION = os.getenv('GOOGLE_CLOUD_LOCATION', 'europe-west1')  
WORKER_SERVICE_URL = os.getenv('WORKER_SERVICE_URL')  # URL Worker Service
PROJECT_LOCATION = f"projects/{PROJECT_ID}/locations/{LOCATION}"

# Import Google Cloud Scheduler (dodany dla Dynamic Scheduler)
try:
    from google.cloud import scheduler_v1
    SCHEDULER_AVAILABLE = True
    logger.info("✅ Google Cloud Scheduler client dostępny")
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.warning("⚠️ Google Cloud Scheduler client niedostępny - dynamic jobs wyłączone")

class WorkerHealthCheckHandler(BaseHTTPRequestHandler):
    """
    Handler dla Worker Service - rozszerza funkcjonalność o obsługę wywołań od Scout
    """
        
    def __init__(self, monitor_instance, worker_instance, *args, **kwargs):
        self.monitor = monitor_instance
        self.worker = worker_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Obsługuje żądania GET"""
        if self.path == '/health':
            self._handle_health_check()
        elif self.path == '/worker-status':
            self._handle_worker_status()
        elif self.path == '/get-token':
            self._handle_get_token()
        elif self.path == '/reset':
            self._handle_reset()
        elif self.path == '/reset-tesla-schedules':
            self._handle_reset_tesla_schedules()
        else:
            self._send_response(404, {"error": "Endpoint not found"})
    
    def do_POST(self):
        """Obsługuje żądania POST"""
        if self.path == '/run-cycle':
            self._handle_run_cycle()
        elif self.path == '/run-midnight-wake':
            self._handle_midnight_wake()
        elif self.path == '/scout-trigger':
            self._handle_scout_trigger()
        elif self.path == '/refresh-tokens':
            self._handle_refresh_tokens()
        elif self.path == '/sync-tokens':
            self._handle_sync_tokens()
        elif self.path == '/daily-special-charging-check':
            self._handle_daily_special_charging_check()
        elif self.path == '/send-special-schedule-immediate':
            self._handle_send_special_schedule_immediate()
        elif self.path == '/send-special-schedule':
            self._handle_send_special_schedule()
        elif self.path == '/cleanup-single-session':
            self._handle_cleanup_single_session()
        else:
            self._send_response(404, {"error": "Endpoint not found"})
    
    def _handle_health_check(self):
        """Health check dla Worker Service"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            
            response = {
                "status": "healthy",
                "service": "tesla-worker",
                "architecture": "scout-worker-optimized",
                "mode": "worker",
                "timestamp": warsaw_time.isoformat(),
                "warsaw_time": warsaw_time.strftime("%Y-%m-%d %H:%M:%S"),
                "cost_optimization": {
                    "type": "Worker Service",
                    "trigger": "On-demand by Scout or Scheduler",
                    "frequency": "2-3x daily + 1x failsafe",
                    "estimated_daily_cost": "~20 groszy"
                },
                "endpoints": {
                    "GET /health": "Health check",
                    "GET /worker-status": "Detailed worker status",
                    "GET /get-token": "Get Tesla API token for Scout (centralized token management)",
                    "POST /run-cycle": "Execute full monitoring cycle",
                    "POST /run-midnight-wake": "Midnight wake check",
                    "POST /scout-trigger": "Handle Scout trigger",
                    "POST /refresh-tokens": "Force Tesla token refresh (when Scout detects auth errors)",
                    "POST /sync-tokens": "Synchronize tokens from legacy secrets to centralized fleet-tokens",
                    "POST /daily-special-charging-check": "Daily special charging check",
                    "POST /send-special-schedule-immediate": "TESTOWY: Wysłanie Special Charging harmonogramu natychmiast do pojazdu",
                    "POST /send-special-schedule": "Wysyłanie special charging harmonogramu przez dynamiczny scheduler",
                    "POST /cleanup-single-session": "One-shot cleanup dla konkretnej special charging sesji",
                    "GET /reset": "Reset monitoring state",
                    "GET /reset-tesla-schedules": "Reset Tesla schedules"
                }
            }
            
            self._send_response(200, response)
            
        except Exception as e:
            logger.error(f"❌ Błąd health check: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_worker_status(self):
        """Szczegółowy status Worker Service"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            
            # Sprawdź połączenie z Tesla
            tesla_connected = self.monitor.tesla_controller.connect()
            
            response = {
                "status": "active",
                "service": "tesla-worker",
                "timestamp": warsaw_time.isoformat(),
                "tesla_connection": {
                    "connected": tesla_connected,
                    "smart_proxy_available": os.getenv('TESLA_PROXY_AVAILABLE', 'false').lower() == 'true',
                    "proxy_mode": os.getenv('TESLA_SMART_PROXY_MODE', 'false').lower() == 'true'
                },
                "monitoring_state": self.monitor.get_status(),
                "architecture_info": {
                    "type": "Worker Service (Heavy)",
                    "purpose": "Full Tesla logic with proxy",
                    "triggered_by": ["Scout Function", "Cloud Scheduler failsafe"],
                    "execution_frequency": "2-3x daily when vehicle returns home",
                    "cost_per_execution": "~5-10 groszy",
                    "scales_to_zero": True
                }
            }
            
            self._send_response(200, response)
            
        except Exception as e:
            logger.error(f"❌ Błąd worker status: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_get_token(self):
        """Udostępnia token Tesla API dla Scout Function - centralne zarządzanie tokenami"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"📡 [WORKER] Scout żąda tokenu Tesla API")
            
            # Sprawdź połączenie z Tesla i pobierz token
            tesla_connected = self.monitor.tesla_controller.connect()
            if not tesla_connected:
                logger.error(f"{time_str} ❌ Worker nie może połączyć się z Tesla API")
                response = {
                    "status": "error",
                    "error": "Worker cannot connect to Tesla API",
                    "tesla_connected": False,
                    "timestamp": warsaw_time.isoformat()
                }
                self._send_response(500, response)
                return
            
            # Pobierz aktualny token z TeslaFleetAPIClient
            access_token = self.monitor.tesla_controller.fleet_api.access_token
            if not access_token:
                logger.error(f"{time_str} ❌ Worker nie ma ważnego tokenu Tesla")
                response = {
                    "status": "error", 
                    "error": "Worker has no valid Tesla token",
                    "tesla_connected": True,
                    "has_token": False,
                    "timestamp": warsaw_time.isoformat()
                }
                self._send_response(500, response)
                return
            
            # Sprawdź czas wygaśnięcia tokenu
            token_expires_at = getattr(self.monitor.tesla_controller.fleet_api, 'token_expires_at', None)
            remaining_minutes = None
            if token_expires_at:
                from datetime import timezone as dt_timezone
                remaining_seconds = (token_expires_at - datetime.now(dt_timezone.utc)).total_seconds()
                remaining_minutes = max(0, int(remaining_seconds / 60))
            
            response = {
                "status": "success",
                "message": "Token Tesla API udostępniony przez Worker (centralne zarządzanie)",
                "access_token": access_token,
                "tesla_connected": True,
                "has_token": True,
                "token_source": "worker_tesla_controller",
                "remaining_minutes": remaining_minutes,
                "timestamp": warsaw_time.isoformat(),
                "architecture": {
                    "type": "centralized_token_management",
                    "description": "Worker zarządza tokenami centralnie, Scout używa tokenów z Worker",
                    "benefits": ["Brak konfliktów refresh token", "Stabilne zarządzanie tokenami", "24h ważność tokenu"]
                }
            }
            
            logger.info(f"✅ [WORKER] Token Tesla udostępniony Scout (pozostało: {remaining_minutes or 'unknown'} min)")
            self._send_response(200, response)
            
        except Exception as e:
            logger.error(f"❌ Błąd udostępniania tokenu: {e}")
            self._send_response(500, {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    def _handle_scout_trigger(self):
        """Obsługuje wywołanie od Scout Function"""
        try:
            # Pobierz dane z żądania
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    scout_data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    scout_data = {}
            else:
                scout_data = {}
            
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"🔍➡️🔧 [WORKER] Otrzymano wywołanie od Scout Function")
            logger.info(f"{time_str} Scout reason: {scout_data.get('reason', 'unknown')}")
            
            # NAPRAWKA: Sprawdź czy system jest gotowy do wykonania cyklu
            if not self._prepare_worker_for_cycle():
                logger.error(f"{time_str} ❌ Worker nie jest gotowy do wykonania cyklu")
                response = {
                    "status": "error",
                    "error": "Worker not ready for monitoring cycle",
                    "details": "Private key or Tesla HTTP Proxy not available",
                    "timestamp": warsaw_time.isoformat()
                }
                self._send_response(500, response)
                return
            
            # Wykonaj pełny cykl monitorowania
            start_time = datetime.now(timezone.utc)
            
            try:
                self.monitor.run_monitoring_cycle()
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                response = {
                    "status": "success",
                    "message": "Worker cycle executed successfully",
                    "triggered_by": "scout_function",
                    "scout_data": scout_data,
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat(),

                    "cost_optimization": {
                        "scout_cost": "~0.01 groszy",
                        "worker_cost": f"~{round(execution_time * 0.1, 2)} groszy",
                        "total_cost": f"~{round(execution_time * 0.1 + 0.01, 2)} groszy"
                    }
                }
                
                logger.info(f"✅ [WORKER] Cykl zakończony pomyślnie w {execution_time:.3f}s")
                self._send_response(200, response)
                
            except Exception as e:
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.error(f"❌ [WORKER] Błąd podczas cyklu: {e}")
                
                response = {
                    "status": "error",
                    "error": str(e),
                    "triggered_by": "scout_function",
                    "scout_data": scout_data,
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat()
                }
                
                self._send_response(500, response)
                
        except Exception as e:
            logger.error(f"❌ Błąd obsługi Scout trigger: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _prepare_worker_for_cycle(self) -> bool:
        """
        Przygotowuje Worker do wykonania cyklu monitorowania
        Sprawdza czy wszystkie wymagane komponenty są dostępne
        
        Returns:
            bool: True jeśli Worker jest gotowy do cyklu
        """
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 🔍 Przygotowywanie Worker do cyklu monitorowania...")
            
            # NOWE: KROK 0 - Zapewnij aktualne tokeny Tesla w centralnym miejscu
            logger.info(f"{time_str} 🔐 KROK 0: Zapewnianie aktualnych tokenów Tesla...")
            if not self.worker._ensure_centralized_tokens():
                logger.error(f"{time_str} ❌ Nie można zapewnić aktualnych tokenów Tesla")
                logger.error(f"{time_str} 💡 Worker wymaga ważnych tokenów do działania")
                return False
            
            logger.info(f"{time_str} ✅ Tokeny Tesla są dostępne i ważne")
            
            # Sprawdź zmienne środowiskowe
            proxy_available = os.getenv('TESLA_PROXY_AVAILABLE', 'false').lower() == 'true'
            private_key_ready = os.getenv('TESLA_PRIVATE_KEY_READY', 'false').lower() == 'true'
            smart_proxy_mode = os.getenv('TESLA_SMART_PROXY_MODE', 'false').lower() == 'true'
            
            logger.info(f"{time_str} 📊 Stan komponentów:")
            logger.info(f"   - Tesla HTTP Proxy dostępny: {proxy_available}")
            logger.info(f"   - Private key gotowy: {private_key_ready}")
            logger.info(f"   - Smart Proxy Mode: {smart_proxy_mode}")
            
            # Sprawdź czy private key istnieje i jest prawidłowy
            if proxy_available and private_key_ready:
                if not os.path.exists('private-key.pem'):
                    logger.error(f"{time_str} ❌ Plik private-key.pem nie istnieje")
                    return False
                
                key_size = os.path.getsize('private-key.pem')
                if key_size == 0:
                    logger.error(f"{time_str} ❌ Plik private-key.pem jest pusty")
                    return False
                
                logger.info(f"{time_str} ✅ Private key zveryfikowany ({key_size} bajtów)")
            
            # Sprawdź połączenie z Tesla API (używa nowych tokenów)
            logger.info(f"{time_str} 🔗 Testowanie połączenia z Tesla Fleet API...")
            tesla_connected = self.monitor.tesla_controller.connect()
            if not tesla_connected:
                logger.warning(f"{time_str} ⚠️ Nie można połączyć się z Tesla Fleet API")
                # Nie przerywamy - tokeny są ważne, ale może być inny problem
            else:
                logger.info(f"{time_str} ✅ Tesla Fleet API dostępne")
            
            # NAPRAWKA: Jeśli Smart Proxy Mode, przygotuj proxy przed cyklem
            if smart_proxy_mode and proxy_available and private_key_ready:
                logger.info(f"{time_str} 🚀 Smart Proxy Mode - przygotowywanie Tesla HTTP Proxy...")
                
                # Sprawdź czy proxy nie działa już
                if hasattr(self.monitor, 'proxy_running') and self.monitor.proxy_running:
                    logger.info(f"{time_str} ✅ Tesla HTTP Proxy już działa")
                else:
                    # Uruchom proxy on-demand
                    if hasattr(self.monitor, '_start_proxy_on_demand'):
                        proxy_started = self.monitor._start_proxy_on_demand()
                        if proxy_started:
                            logger.info(f"{time_str} ✅ Tesla HTTP Proxy uruchomiony on-demand")
                        else:
                            logger.warning(f"{time_str} ⚠️ Nie udało się uruchomić Tesla HTTP Proxy")
                            logger.warning(f"{time_str} 💡 Worker będzie działać tylko z Fleet API")
                    else:
                        logger.warning(f"{time_str} ⚠️ Monitor nie obsługuje _start_proxy_on_demand")
            
            logger.info(f"{time_str} ✅ Worker przygotowany do wykonania cyklu")
            return True
            
        except Exception as e:
            logger.error(f"❌ Błąd przygotowywania Worker do cyklu: {e}")
            return False
    
    def _handle_refresh_tokens(self):
        """Wymusza odświeżenie tokenów Tesla na żądanie Scout Function"""
        try:
            # Pobierz dane z żądania
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    request_data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    request_data = {}
            else:
                request_data = {}
            
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            # Ulepszone logowanie wywołania od Scout
            requester = request_data.get('requested_by', 'unknown')
            reason = request_data.get('reason', 'Błąd autoryzacji')
            attempt_count = request_data.get('attempt_count', 1)
            
            logger.info(f"🔄 [WORKER] {requester.upper()} żąda wymuszenia odświeżenia tokenów Tesla")
            logger.info(f"{time_str} Powód: {reason}")
            logger.info(f"{time_str} Próba #{attempt_count}")
            
            start_time = datetime.now(timezone.utc)
            
            # KROK 1: Sprawdź czy Worker może odświeżać tokeny
            if not self.monitor.tesla_controller.fleet_api:
                error_msg = "TeslaFleetAPIClient nie jest zainicjalizowany"
                logger.error(f"❌ [WORKER] {error_msg}")
                response = {
                    "status": "error",
                    "error": error_msg,
                    "step": "worker_initialization",
                    "timestamp": warsaw_time.isoformat(),
                    "requested_by": requester,
                    "duration_ms": 0
                }
                self._send_response(500, response)
                return

            # KROK 2: Wymuś odświeżenie tokenów Tesla
            try:
                logger.info(f"{time_str} 🔄 Rozpoczynam wymuszenie odświeżenia tokenów...")
                
                # Sprawdź obecny stan tokenów przed odświeżeniem
                had_tokens_before = bool(self.monitor.tesla_controller.fleet_api.access_token)
                logger.info(f"{time_str} Stan tokenów przed odświeżeniem: {'OBECNE' if had_tokens_before else 'BRAK'}")
                
                # Wymuś pełne zapewnienie aktualnych tokenów  
                tokens_ensured = self.worker._ensure_centralized_tokens()
                
                if tokens_ensured:
                    # Sprawdź stan tokenów po odświeżeniu
                    has_tokens_after = bool(self.monitor.tesla_controller.fleet_api.access_token)
                    token_expires_at = getattr(self.monitor.tesla_controller.fleet_api, 'token_expires_at', None)
                    
                    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                    
                    # Sprawdź czas wygaśnięcia odświeżonego tokenu
                    remaining_minutes = None
                    if token_expires_at:
                        from datetime import timezone as dt_timezone
                        remaining_seconds = (token_expires_at - datetime.now(dt_timezone.utc)).total_seconds()
                        remaining_minutes = max(0, int(remaining_seconds / 60))
                    
                    response = {
                        "status": "success",
                        "message": "Tokeny Tesla odświeżone pomyślnie przez Worker",
                        "details": {
                            "had_tokens_before": had_tokens_before,
                            "has_tokens_after": has_tokens_after,
                            "remaining_minutes": remaining_minutes,
                            "token_source": "centralized_token_management"
                        },
                        "step": "token_refresh_completed",
                        "timestamp": warsaw_time.isoformat(),
                        "requested_by": requester,
                        "duration_ms": duration_ms,
                        "recommendation": "Scout can now retry fetching tokens from Secret Manager"
                    }
                    
                    logger.info(f"✅ [WORKER] Tokeny odświeżone pomyślnie w {duration_ms}ms")
                    logger.info(f"{time_str} Token ważny przez: {remaining_minutes or 'unknown'} minut")
                    logger.info(f"💡 [WORKER] Scout może teraz pobrać świeże tokeny z Secret Manager")
                    
                    self._send_response(200, response)
                    
                else:
                    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                    error_msg = "Nie można zapewnić aktualnych tokenów Tesla"
                    
                    response = {
                        "status": "error", 
                        "error": error_msg,
                        "details": {
                            "possible_causes": [
                                "Refresh token wygasł lub jest nieważny",
                                "Problemy z Tesla Fleet API",
                                "Błędna konfiguracja Secret Manager",
                                "Brak wymaganych sekretów"
                            ],
                            "recommended_actions": [
                                "Sprawdź logi Worker dla szczegółów",
                                "Uruchom: python3 generate_token.py",
                                "Sprawdź sekrety w Google Secret Manager",
                                "Sprawdź uprawnienia Google Cloud IAM"
                            ]
                        },
                        "step": "token_refresh_failed",
                        "timestamp": warsaw_time.isoformat(),
                        "requested_by": requester,
                        "duration_ms": duration_ms
                    }
                    
                    logger.error(f"❌ [WORKER] {error_msg} w {duration_ms}ms")
                    logger.error(f"{time_str} Sprawdź _ensure_centralized_tokens() dla szczegółów")
                    
                    self._send_response(500, response)
                    
            except Exception as refresh_error:
                duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                error_msg = f"Nieoczekiwany błąd podczas odświeżania tokenów: {refresh_error}"
                
                logger.error(f"❌ [WORKER] {error_msg}")
                logger.error(f"{time_str} Exception details: {str(refresh_error)}")
                
                response = {
                    "status": "error",
                    "error": error_msg,
                    "details": {
                        "exception_type": type(refresh_error).__name__,
                        "exception_message": str(refresh_error)
                    },
                    "step": "token_refresh_exception",
                    "timestamp": warsaw_time.isoformat(),
                    "requested_by": requester,
                    "duration_ms": duration_ms
                }
                
                self._send_response(500, response)
                
        except Exception as e:
            logger.error(f"❌ [WORKER] Krytyczny błąd endpointu /refresh-tokens: {e}")
            error_response = {
                "status": "error",
                "error": f"Critical endpoint error: {str(e)}",
                "step": "endpoint_error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self._send_response(500, error_response)
    
    def _handle_run_cycle(self):
        """Obsługuje wywołanie cyklu monitorowania (kompatybilność z poprzednią wersją)"""
        try:
            # Pobierz dane z żądania
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    request_data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    request_data = {}
            else:
                request_data = {}
            
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            trigger_source = request_data.get('trigger', 'unknown')
            logger.info(f"🔧 [WORKER] Uruchamianie cyklu monitorowania (trigger: {trigger_source})")
            
            # NAPRAWKA: Sprawdź czy system jest gotowy do wykonania cyklu
            if not self._prepare_worker_for_cycle():
                logger.error(f"{time_str} ❌ Worker nie jest gotowy do wykonania cyklu")
                response = {
                    "status": "error", 
                    "error": "Worker not ready for monitoring cycle",
                    "details": "Private key or Tesla HTTP Proxy not available",
                    "trigger": trigger_source,
                    "timestamp": warsaw_time.isoformat()
                }
                self._send_response(500, response)
                return
            
            start_time = datetime.now(timezone.utc)
            
            try:
                self.monitor.run_monitoring_cycle()
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                response = {
                    "status": "success",
                    "message": "Monitoring cycle completed",
                    "trigger": trigger_source,
                    "request_data": request_data,
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat(),
                    "worker_info": {
                        "service": "tesla-worker",
                        "architecture": "scout-worker-optimized",
                        "cost_per_execution": f"~{round(execution_time * 0.1, 2)} groszy"
                    }
                }
                
                logger.info(f"✅ [WORKER] Cykl monitorowania zakończony w {execution_time:.3f}s")
                self._send_response(200, response)
                
            except Exception as e:
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.error(f"❌ [WORKER] Błąd cyklu monitorowania: {e}")
                
                response = {
                    "status": "error",
                    "error": str(e),
                    "trigger": trigger_source,
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat()
                }
                
                self._send_response(500, response)
                
        except Exception as e:
            logger.error(f"❌ Błąd obsługi run-cycle: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_midnight_wake(self):
        """Obsługuje nocne wybudzenie pojazdu (kompatybilność z poprzednią wersją)"""
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"🌙 [WORKER] Uruchamianie nocnego wybudzenia pojazdu")
            
            start_time = datetime.now(timezone.utc)
            
            try:
                self.monitor.run_midnight_wake_check()
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                response = {
                    "status": "success",
                    "message": "Midnight wake check completed",
                    "trigger": "cloud_scheduler_worker_failsafe",
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat(),
                    "worker_info": {
                        "service": "tesla-worker",
                        "action": "midnight_wake_check",
                        "cost_per_execution": f"~{round(execution_time * 0.1, 2)} groszy"
                    }
                }
                
                logger.info(f"✅ [WORKER] Nocne wybudzenie zakończone w {execution_time:.3f}s")
                self._send_response(200, response)
                
            except Exception as e:
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.error(f"❌ [WORKER] Błąd nocnego wybudzenia: {e}")
                
                response = {
                    "status": "error",
                    "error": str(e),
                    "trigger": "cloud_scheduler_worker_failsafe",
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat()
                }
                
                self._send_response(500, response)
                
        except Exception as e:
            logger.error(f"❌ Błąd obsługi midnight wake: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_reset(self):
        """Reset stanu monitorowania (kompatybilność z poprzednią wersją)"""
        try:
            self.monitor.reset_all_monitoring_state()
            
            response = {
                "status": "success",
                "message": "Monitoring state reset successfully",
                "service": "tesla-worker",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info("✅ [WORKER] Stan monitorowania zresetowany")
            self._send_response(200, response)
            
        except Exception as e:
            logger.error(f"❌ Błąd resetowania stanu: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_reset_tesla_schedules(self):
        """Reset harmonogramów Tesla (kompatybilność z poprzednią wersją)"""
        try:
            result = self.monitor.reset_tesla_home_schedules()
            
            response = {
                "status": "success",
                "message": "Tesla schedules reset successfully",
                "service": "tesla-worker",
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info("✅ [WORKER] Harmonogramy Tesla zresetowane")
            self._send_response(200, response)
            
        except Exception as e:
            logger.error(f"❌ Błąd resetowania harmonogramów Tesla: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_sync_tokens(self):
        """
        POST /sync-tokens
        Wymusza synchronizację tokenów z legacy sekretów do fleet-tokens
        Endpoint dla debugowania i naprawy desynchronizacji
        """
        try:
            # Pobierz dane z żądania
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    request_data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    request_data = {}
            else:
                request_data = {}
            
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"🔄 [WORKER] Żądanie synchronizacji tokenów Tesla")
            logger.info(f"{time_str} Powód: {request_data.get('reason', 'Synchronizacja tokenów')}")
            
            start_time = datetime.now(timezone.utc)
            
            # Wymuś zapewnienie aktualnych tokenów (migracja + odświeżenie)
            if self.worker._ensure_centralized_tokens():
                # Sprawdź wynikowe tokeny
                new_token = self.monitor.tesla_controller.fleet_api.access_token
                token_expires_at = self.monitor.tesla_controller.fleet_api.token_expires_at
                
                remaining_minutes = None
                if token_expires_at:
                    from datetime import timezone as dt_timezone
                    remaining_seconds = (token_expires_at - datetime.now(dt_timezone.utc)).total_seconds()
                    remaining_minutes = max(0, int(remaining_seconds / 60))
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                response = {
                    "status": "success",
                    "message": "Tokeny Tesla zsynchronizowane pomyślnie",
                    "access_token": new_token[:50] + "..." if new_token else None,  # Skrócony dla bezpieczeństwa
                    "remaining_minutes": remaining_minutes,
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat(),
                    "triggered_by": "manual_sync_request",
                    "architecture": {
                        "type": "centralized_token_sync",
                        "description": "Worker zsynchronizował tokeny z legacy do fleet-tokens",
                        "source": "centralized_token_management"
                    }
                }
                
                logger.info(f"✅ [WORKER] Tokeny zsynchronizowane pomyślnie (pozostało: {remaining_minutes or 'unknown'} min)")
                self._send_response(200, response)
                
            else:
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                response = {
                    "status": "error",
                    "error": "Nie udało się zsynchronizować tokenów Tesla",
                    "details": "Sprawdź logi Worker Service dla szczegółów",
                    "execution_time_seconds": round(execution_time, 3),
                    "timestamp": start_time.isoformat(),
                    "triggered_by": "manual_sync_request"
                }
                
                logger.error(f"❌ [WORKER] Nie udało się zsynchronizować tokenów Tesla")
                self._send_response(500, response)
                
        except Exception as e:
            logger.error(f"❌ Błąd obsługi żądania synchronizacji tokenów: {e}")
            self._send_response(500, {"error": str(e)})
    
    def _handle_daily_special_charging_check(self):
        """
        POST /daily-special-charging-check
        Sprawdza Google Sheets dla wyjątkowych potrzeb ładowania
        Uruchamiany codziennie o 00:01 przez Cloud Scheduler
        """
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"🔋 [WORKER] Sprawdzanie special charging needs - daily check")
            logger.info(f"{time_str} ⚡ Daily Special Charging Check rozpoczęty")
            
            start_time = datetime.now()
            
            # Pobierz dane z żądania
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    request_data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    request_data = {}
            else:
                request_data = {}
            
            # Wykonaj daily special charging check
            result = self._perform_daily_special_charging_check(request_data)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            response = {
                "status": "success",
                "message": "Daily special charging check zakończony",
                "result": result,
                "execution_time_seconds": round(execution_time, 3),
                "timestamp": start_time.isoformat(),
                "triggered_by": "cloud_scheduler_daily"
            }
            
            logger.info(f"✅ [WORKER] Daily special charging check zakończony ({execution_time:.2f}s)")
            self._send_response(200, response)
            
        except Exception as e:
            logger.error(f"❌ Błąd daily special charging check: {e}")
            self._send_response(500, {"error": str(e)})

    def _handle_send_special_schedule(self):
        """
        Handler dla dynamicznego Cloud Scheduler job
        Wywoływany o wyznaczonej godzinie send_schedule_at
        """
        try:
            # Pobierz dane z request
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            session_id = data.get('session_id')
            if not session_id:
                self._send_response(400, {"error": "Brak session_id w żądaniu"})
                return
            
            logger.info(f"⏰ [SPECIAL] Otrzymano trigger dynamicznego schedulera dla session: {session_id}")
            
            # KROK 1: Wybudź pojazd
            wake_success = self._wake_vehicle_for_special_charging(session_id)
            if not wake_success:
                logger.error(f"❌ [SPECIAL] Nie udało się wybudzić pojazdu dla session {session_id}")
                self._send_response(500, {"error": "Failed to wake vehicle"})
                return
            
            # KROK 2: Wykonaj scheduled special charging
            result = self._execute_scheduled_special_charging(session_id)
            
            # KROK 3: Cleanup dynamiczny scheduler job
            self._cleanup_dynamic_scheduler_job(session_id)
            
            if result.get('success'):
                logger.info(f"✅ [SPECIAL] Harmonogram wysłany pomyślnie dla session {session_id}")
                self._send_response(200, result)
            else:
                logger.error(f"❌ [SPECIAL] Błąd wysyłania harmonogramu dla session {session_id}")
                self._send_response(500, result)
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd obsługi send-special-schedule: {e}")
            self._send_response(500, {"error": str(e)})

    def _handle_cleanup_single_session(self):
        """
        Handler dla one-shot cleanup konkretnej special charging sesji
        Wywoływany przez dynamiczny scheduler job po zakończeniu ładowania
        """
        try:
            # Odczytaj request data
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                logger.error("❌ [SPECIAL] Brak danych w żądaniu cleanup")
                self._send_response(400, {"error": "Brak danych w żądaniu"})
                return
                
            request_body = self.rfile.read(content_length).decode('utf-8')
            request_data = json.loads(request_body)
            
            session_id = request_data.get('session_id')
            if not session_id:
                logger.error("❌ [SPECIAL] Brak session_id w żądaniu cleanup")
                self._send_response(400, {"error": "Brak session_id"})
                return
            
            logger.info(f"🧹 [SPECIAL] One-shot cleanup dla session: {session_id}")
            
            # 1. Pobierz session data
            session_data = self._get_special_charging_session(session_id)
            if not session_data:
                logger.warning(f"⚠️ [SPECIAL] Session {session_id} nie znaleziony - może już został usunięty")
                self._send_response(200, {
                    "session_id": session_id, 
                    "cleaned": False, 
                    "reason": "session_not_found"
                })
                return
            
            # 2. Cleanup session tylko jeśli status ACTIVE
            cleaned = False
            if session_data.get('status') == 'ACTIVE':
                if self._complete_special_charging_session(session_data):
                    cleaned = True
                    logger.info(f"✅ [SPECIAL] Session {session_id} ukończony (charge limit przywrócony)")
                else:
                    logger.error(f"❌ [SPECIAL] Błąd completion session {session_id}")
            else:
                logger.info(f"ℹ️ [SPECIAL] Session {session_id} ma status {session_data.get('status', 'unknown')} - pomijam cleanup")
            
            # 3. Usuń cleanup job (siebie)
            cleanup_job_name = f"special-cleanup-{session_id}"
            try:
                if SCHEDULER_AVAILABLE:
                    client = scheduler_v1.CloudSchedulerClient()
                    full_job_name = f"{PROJECT_LOCATION}/jobs/{cleanup_job_name}"
                    client.delete_job(name=full_job_name)
                    logger.info(f"🗑️ [SPECIAL] Usunięty one-shot cleanup job: {cleanup_job_name}")
                else:
                    logger.warning("⚠️ [SPECIAL] Scheduler niedostępny - nie można usunąć cleanup job")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ [SPECIAL] Błąd usuwania cleanup job {cleanup_job_name}: {cleanup_error}")
            
            logger.info(f"🏁 [SPECIAL] One-shot cleanup zakończony dla {session_id}")
            self._send_response(200, {
                "session_id": session_id,
                "cleaned": cleaned,
                "cleanup_job_deleted": True
            })
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd one-shot cleanup: {e}")
            self._send_response(500, {"error": str(e)})

    def _wake_vehicle_for_special_charging(self, session_id: str) -> bool:
        """
        Wybudza pojazd przed wysłaniem special charging harmonogramu
        NAPRAWKA: Dodano połączenie z Tesla API i wybór pojazdu przed wybudzeniem
        """
        try:
            # Pobierz session data
            session_data = self._get_special_charging_session(session_id)
            if not session_data:
                logger.error(f"❌ [SPECIAL] Nie znaleziono session {session_id}")
                return False
                
            vin = session_data.get('vin', 'unknown')
            logger.info(f"🔄 [SPECIAL] Budzenie pojazdu {vin[-4:]} dla session {session_id}")
            
            # NAPRAWKA: Najpierw połącz się z Tesla API i wybierz pojazd
            logger.info(f"🔗 [SPECIAL] Łączenie z Tesla API i wybór pojazdu...")
            tesla_connected = self.monitor.tesla_controller.connect()
            if not tesla_connected:
                logger.error(f"❌ [SPECIAL] Nie można połączyć się z Tesla API")
                return False
            
            # Sprawdź czy pojazd został wybrany
            if not self.monitor.tesla_controller.current_vehicle:
                logger.error(f"❌ [SPECIAL] Nie wybrano żadnego pojazdu po połączeniu")
                return False
            
            # Opcjonalnie: wybierz konkretny pojazd po VIN jeśli mamy więcej niż jeden
            selected_vin = self.monitor.tesla_controller.current_vehicle.get('vin', 'unknown')
            logger.info(f"✅ [SPECIAL] Wybrany pojazd: {selected_vin[-4:]}")
            
            # NAPRAWKA: Uruchom Tesla HTTP Proxy przed wybudzeniem pojazdu
            proxy_started = False
            if self.monitor.smart_proxy_mode and self.monitor.proxy_available:
                logger.info(f"🚀 [SPECIAL] Uruchamianie Tesla HTTP Proxy dla wake_up...")
                proxy_started = self.monitor._start_proxy_on_demand()
                if not proxy_started:
                    logger.error(f"❌ [SPECIAL] Nie udało się uruchomić Tesla HTTP Proxy")
                    logger.error(f"❌ [SPECIAL] Bez proxy wybudzenie może nie działać poprawnie")
                    return False
                else:
                    logger.info(f"✅ [SPECIAL] Tesla HTTP Proxy uruchomiony pomyślnie")
            
            # Wybudź pojazd z proxy (potrzebny dla komend harmonogramów)
            logger.info(f"🔄 [SPECIAL] Budzenie pojazdu {selected_vin[-4:]} {'przez Tesla HTTP Proxy' if proxy_started else 'bezpośrednio Fleet API'}")
            wake_success = self.monitor.tesla_controller.wake_up_vehicle(use_proxy=proxy_started)
            
            if wake_success:
                logger.info(f"✅ [SPECIAL] Pojazd {selected_vin[-4:]} wybudzony pomyślnie")
                return True
            else:
                logger.error(f"❌ [SPECIAL] Nie udało się wybudzić pojazdu {selected_vin[-4:]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd wybudzania pojazdu: {e}")
            return False

    def _execute_scheduled_special_charging(self, session_id: str) -> Dict[str, Any]:
        """
        Wykonuje zaplanowany special charging - wysyła harmonogram do pojazdu
        """
        try:
            # Pobierz session data z Firestore
            session_data = self._get_special_charging_session(session_id)
            if not session_data:
                return {"success": False, "error": f"Nie znaleziono session {session_id}"}
            
            vin = session_data.get('vin')
            charging_plan = session_data.get('charging_plan')
            
            if not charging_plan:
                return {"success": False, "error": "Brak charging_plan w session"}
            
            logger.info(f"⚡ [SPECIAL] Wykonuję scheduled charging dla session {session_id}")
            
            # Pobierz aktualne dane pojazdu
            vehicle_data = self._get_current_vehicle_data()
            if not vehicle_data:
                return {"success": False, "error": "Nie udało się pobrać danych pojazdu"}
            
            # Utwórz dane need na podstawie session (z parsowaniem target_datetime)
            target_datetime_str = session_data.get('target_datetime')
            target_datetime = None
            if target_datetime_str:
                try:
                    target_datetime = datetime.fromisoformat(target_datetime_str.replace('Z', '+00:00'))
                except Exception as e:
                    logger.warning(f"⚠️ [SPECIAL] Błąd parsowania target_datetime: {e}")
                    target_datetime = target_datetime_str  # Fallback do string
            
            need = {
                'target_battery_percent': session_data.get('target_battery_level'),
                'target_datetime': target_datetime,
                'row': session_data.get('sheets_row')
            }
            
            # Wyślij special charging schedule
            success = self._send_special_charging_schedule(charging_plan, need, vehicle_data)
            
            if success:
                return {
                    "success": True,
                    "session_id": session_id,
                    "vin": vin[-4:] if vin else "unknown",
                    "message": "Harmonogram wysłany pomyślnie"
                }
            else:
                return {
                    "success": False, 
                    "error": "Nie udało się wysłać harmonogramu do pojazdu"
                }
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd execute scheduled charging: {e}")
            return {"success": False, "error": str(e)}

    def _get_special_charging_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Pobiera special charging session z Firestore"""
        try:
            db = self.monitor._get_firestore_client()
            doc_ref = db.collection('special_charging_sessions').document(session_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                logger.error(f"❌ [SPECIAL] Session {session_id} nie istnieje w Firestore")
                return None
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd pobierania session {session_id}: {e}")
            return None

    def _create_dynamic_scheduler_job(self, charging_plan: Dict[str, Any], session_id: str) -> bool:
        """
        Tworzy tymczasowy Cloud Scheduler job na godzinę send_schedule_at
        """
        try:
            if not SCHEDULER_AVAILABLE:
                logger.error("❌ [SPECIAL] Google Cloud Scheduler niedostępny - nie można utworzyć dynamic job")
                return False
                
            if not WORKER_SERVICE_URL:
                logger.error("❌ [SPECIAL] WORKER_SERVICE_URL nie ustawiony - nie można utworzyć dynamic job")
                return False
            
            send_time = charging_plan['send_schedule_at']
            
            # Konwertuj na cron expression
            cron_expression = f"{send_time.minute} {send_time.hour} {send_time.day} {send_time.month} *"
            job_name = f"special-charging-{session_id}"
            full_job_name = f"{PROJECT_LOCATION}/jobs/{job_name}"
            
            logger.info(f"🕒 [SPECIAL] Tworzę dynamic scheduler job: {job_name} na {send_time.strftime('%H:%M')}")
            
            client = scheduler_v1.CloudSchedulerClient()
            
            # Sprawdź czy job już istnieje
            try:
                existing_job = client.get_job(name=full_job_name)
                logger.warning(f"⚠️ [SPECIAL] Job {job_name} już istnieje - usuwam stary")
                try:
                    client.delete_job(name=full_job_name)
                    logger.info(f"🗑️ [SPECIAL] Usunięty stary job: {job_name}")
                    # Krótkie opóźnienie po usunięciu
                    import time
                    time.sleep(1)
                except Exception as delete_error:
                    logger.warning(f"⚠️ [SPECIAL] Błąd usuwania starego job: {delete_error}")
                    
            except Exception:
                # Job nie istnieje - to OK, możemy utworzyć nowy
                pass
            
            job = {
                "name": full_job_name,
                "schedule": cron_expression,
                "time_zone": "Europe/Warsaw",
                "description": f"Special Charging - session {session_id}",
                "http_target": {
                    "uri": f"{WORKER_SERVICE_URL}/send-special-schedule",
                    "http_method": scheduler_v1.HttpMethod.POST,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "session_id": session_id,
                        "trigger": "dynamic_scheduler",
                        "action": "send_special_schedule"
                    }).encode(),
                    # ✅ NAPRAWKA: Dodanie autoryzacji OIDC dla dynamicznych Cloud Scheduler jobs
                    "oidc_token": {
                        "service_account_email": f"{PROJECT_ID}@appspot.gserviceaccount.com"
                    }
                }
            }
            
            # Utwórz job
            client.create_job(parent=PROJECT_LOCATION, job=job)
            
            logger.info(f"✅ [SPECIAL] Dynamic scheduler job utworzony: {job_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd tworzenia dynamic scheduler job: {e}")
            return False
    
    def _create_cleanup_dynamic_scheduler_job(self, charging_plan: Dict[str, Any], session_id: str) -> bool:
        """
        Tworzy one-shot cleanup dynamic scheduler job na charging_end + 30min
        """
        try:
            if not SCHEDULER_AVAILABLE:
                logger.error("❌ [SPECIAL] Google Cloud Scheduler niedostępny - nie można utworzyć cleanup job")
                return False
                
            if not WORKER_SERVICE_URL:
                logger.error("❌ [SPECIAL] WORKER_SERVICE_URL nie ustawiony - nie można utworzyć cleanup job")
                return False
            
            # Cleanup job uruchamia się 30 minut po charging_end
            cleanup_time = charging_plan['charging_end'] + timedelta(minutes=30)
            
            # Konwertuj na cron expression
            cron_expression = f"{cleanup_time.minute} {cleanup_time.hour} {cleanup_time.day} {cleanup_time.month} *"
            job_name = f"special-cleanup-{session_id}"
            full_job_name = f"{PROJECT_LOCATION}/jobs/{job_name}"
            
            logger.info(f"🧹 [SPECIAL] Tworzę one-shot cleanup job: {job_name} na {cleanup_time.strftime('%H:%M')}")
            
            client = scheduler_v1.CloudSchedulerClient()
            
            # Sprawdź czy cleanup job już istnieje
            try:
                existing_job = client.get_job(name=full_job_name)
                logger.warning(f"⚠️ [SPECIAL] Cleanup job {job_name} już istnieje - usuwam stary")
                try:
                    client.delete_job(name=full_job_name)
                    logger.info(f"🗑️ [SPECIAL] Usunięty stary cleanup job: {job_name}")
                    # Krótkie opóźnienie po usunięciu
                    import time
                    time.sleep(1)
                except Exception as delete_error:
                    logger.warning(f"⚠️ [SPECIAL] Błąd usuwania starego cleanup job: {delete_error}")
                    
            except Exception:
                # Job nie istnieje - to OK, możemy utworzyć nowy
                pass
            
            job = {
                "name": full_job_name,
                "schedule": cron_expression,
                "time_zone": "Europe/Warsaw",
                "description": f"Special Charging One-Shot Cleanup - session {session_id}",
                "http_target": {
                    "uri": f"{WORKER_SERVICE_URL}/cleanup-single-session",
                    "http_method": scheduler_v1.HttpMethod.POST,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "session_id": session_id,
                        "trigger": "one_shot_cleanup",
                        "action": "cleanup_single_special_session"
                    }).encode(),
                    # ✅ NAPRAWKA: Dodanie autoryzacji OIDC dla cleanup dynamic jobs
                    "oidc_token": {
                        "service_account_email": f"{PROJECT_ID}@appspot.gserviceaccount.com"
                    }
                }
            }
            
            # Utwórz job
            client.create_job(parent=PROJECT_LOCATION, job=job)
            
            logger.info(f"✅ [SPECIAL] One-shot cleanup job utworzony: {job_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd tworzenia cleanup job {session_id}: {e}")
            return False

    def _cleanup_dynamic_scheduler_job(self, session_id: str):
        """
        Usuwa dynamiczny scheduler job po użyciu
        """
        try:
            if not SCHEDULER_AVAILABLE:
                logger.warning("⚠️ [SPECIAL] Scheduler niedostępny - nie można usunąć dynamic job")
                return
            
            job_name = f"special-charging-{session_id}"
            full_job_name = f"{PROJECT_LOCATION}/jobs/{job_name}"
            
            client = scheduler_v1.CloudSchedulerClient()
            client.delete_job(name=full_job_name)
            
            logger.info(f"🗑️ [SPECIAL] Usunięty dynamic scheduler job: {job_name}")
            
        except Exception as e:
            # Nie błąd krytyczny - loguj jako warning
            logger.warning(f"⚠️ [SPECIAL] Błąd usuwania dynamic job {session_id}: {e}")
    
    def _send_special_charging_schedule(self, charging_plan: Dict[str, Any], need: Dict[str, Any], vehicle_data: Dict[str, Any]) -> bool:
        """
        Wysyła special charging schedule do pojazdu z zarządzaniem charge limit
        NAPRAWKA: Używa tej samej logiki proxy co _send_special_charging_to_vehicle
        """
        try:
            vin = vehicle_data.get('vin', 'unknown')
            target_battery_percent = charging_plan['target_battery_percent']
            
            logger.info(f"🔧 [SPECIAL] Wysyłam special charging schedule dla {vin[-4:]} przez Tesla HTTP Proxy")
            
            # === TESLA HTTP PROXY SETUP === (NAPRAWKA: Dodane z _send_special_charging_to_vehicle)
            # KROK 1: Uruchom Tesla HTTP Proxy on-demand (zgodnie z Worker Service)
            proxy_started = False
            
            # Sprawdź konfigurację Smart Proxy Mode
            smart_proxy_mode = os.getenv('TESLA_SMART_PROXY_MODE') == 'true'
            proxy_available = os.getenv('TESLA_PROXY_AVAILABLE') == 'true'
            
            logger.info(f"🔍 [SPECIAL] Smart Proxy Mode diagnostyka:")
            logger.info(f"   TESLA_SMART_PROXY_MODE = {smart_proxy_mode}")
            logger.info(f"   TESLA_PROXY_AVAILABLE = {proxy_available}")
            logger.info(f"   TESLA_HTTP_PROXY_HOST = {os.getenv('TESLA_HTTP_PROXY_HOST')}")
            logger.info(f"   TESLA_HTTP_PROXY_PORT = {os.getenv('TESLA_HTTP_PROXY_PORT')}")
            
            if smart_proxy_mode and proxy_available:
                logger.info(f"🚀 [SPECIAL] Uruchamianie Tesla HTTP Proxy on-demand...")
                proxy_started = self.monitor._start_proxy_on_demand()
                if not proxy_started:
                    logger.error(f"❌ [SPECIAL] Nie udało się uruchomić Tesla HTTP Proxy")
                    logger.error(f"❌ [SPECIAL] PRZYCZYNA: Bez proxy komendy set_charge_limit i add_charge_schedule będą odrzucane")
                    return False
                else:
                    logger.info(f"✅ [SPECIAL] Tesla HTTP Proxy uruchomiony pomyślnie")
                    
                    # Skonfiguruj TeslaController do używania proxy
                    if hasattr(self.monitor.tesla_controller, 'fleet_api'):
                        proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST', 'localhost')
                        proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT', '4443')
                        expected_proxy_url = f"https://{proxy_host}:{proxy_port}"
                        
                        if hasattr(self.monitor.tesla_controller.fleet_api, 'proxy_url'):
                            self.monitor.tesla_controller.fleet_api.proxy_url = expected_proxy_url
                            logger.info(f"🔗 [SPECIAL] TeslaController skonfigurowany do używania proxy: {expected_proxy_url}")
                        else:
                            logger.warning(f"⚠️ [SPECIAL] TeslaController nie obsługuje konfiguracji proxy")
            else:
                logger.error(f"❌ [SPECIAL] Smart Proxy Mode wyłączony lub niedostępny")
                logger.error(f"❌ [SPECIAL] WYMAGANE: Tesla HTTP Proxy do podpisywania komend (zgodnie z Tesla API)")
                if not smart_proxy_mode:
                    logger.error(f"   - TESLA_SMART_PROXY_MODE = false (wyłączony)")
                if not proxy_available:
                    logger.error(f"   - TESLA_PROXY_AVAILABLE = false (niedostępny)")
                return False

            try:
                # === VEHICLE COMMANDS === (NAPRAWKA: Przeniesione do try/finally dla cleanup)
                # KROK 2: Pobierz obecny charge limit
                current_charge_limit = self._get_current_charge_limit(vin)
                if current_charge_limit is None:
                    logger.error(f"❌ [SPECIAL] Nie udało się pobrać obecnego charge limit")
                    return False
                
                logger.info(f"📊 [SPECIAL] Obecny charge limit: {current_charge_limit}%")
                
                # KROK 3: Ustaw charge limit jeśli potrzeba (używa Tesla HTTP Proxy)
                if current_charge_limit < target_battery_percent:
                    logger.info(f"🔧 [SPECIAL] Zwiększam charge limit: {current_charge_limit}% → {target_battery_percent}% (przez proxy)")
                    
                    if not self._set_charge_limit(vin, target_battery_percent):
                        logger.error(f"❌ [SPECIAL] Nie udało się ustawić charge limit na {target_battery_percent}%")
                        return False
                    
                    # Czekaj na zastosowanie zmiany
                    time.sleep(3)
                    logger.info(f"✅ [SPECIAL] Charge limit ustawiony na {target_battery_percent}% (przez Tesla HTTP Proxy)")
                
                # KROK 4: Przygotuj harmonogram Tesla
                tesla_schedule = self._convert_charging_plan_to_tesla_schedule(charging_plan)
                
                # KROK 5: Wyślij harmonogram do Tesla (używa Tesla HTTP Proxy)
                if not self._send_tesla_charging_schedule(vin, tesla_schedule):
                    logger.error(f"❌ [SPECIAL] Nie udało się wysłać harmonogramu do Tesla")
                    return False
                
                # KROK 6: Zapisz special charging session
                session_data = {
                    'session_id': f"special_{need['row']}_{need['target_datetime'].strftime('%Y%m%d_%H%M')}",
                    'vin': vin,
                    'status': 'ACTIVE',
                    'target_battery_level': target_battery_percent,
                    'target_datetime': need['target_datetime'].isoformat(),
                    'charging_start': charging_plan['charging_start'].isoformat(),
                    'charging_end': charging_plan['charging_end'].isoformat(),
                    'original_charge_limit': current_charge_limit,
                    'sheets_row': need['row'],
                    'created_at': self.monitor._get_warsaw_time().isoformat(),
                    'charging_plan': charging_plan
                }
                
                if not self._create_special_charging_session(session_data):
                    logger.warning(f"⚠️ [SPECIAL] Nie udało się zapisać session, ale harmonogram wysłany")
                
                logger.info(f"✅ [SPECIAL] Special charging schedule wysłany pomyślnie przez Tesla HTTP Proxy")
                return True
            
            finally:
                # === CLEANUP === (NAPRAWKA: Dodane z _send_special_charging_to_vehicle)
                # KROK 7: Zatrzymaj Tesla HTTP Proxy po zakończeniu
                if proxy_started and hasattr(self.monitor, '_stop_proxy'):
                    try:
                        self.monitor._stop_proxy()
                        logger.info(f"🛑 [SPECIAL] Tesla HTTP Proxy zatrzymany")
                    except Exception as cleanup_error:
                        logger.warning(f"⚠️ [SPECIAL] Błąd zatrzymywania proxy: {cleanup_error}")
                
                # Przywróć TeslaController do bezpośredniego Fleet API
                if hasattr(self.monitor.tesla_controller, 'fleet_api') and hasattr(self.monitor.tesla_controller.fleet_api, 'proxy_url'):
                    self.monitor.tesla_controller.fleet_api.proxy_url = None
                    logger.info(f"🔄 [SPECIAL] TeslaController przywrócony do bezpośredniego Fleet API")
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd wysyłania special charging schedule: {e}")
            return False

    def _set_charge_limit(self, vin: str, limit_percent: int) -> bool:
        """
        Ustawia limit ładowania w pojeździe przez Tesla HTTP Proxy
        WYMAGANE: TeslaController musi być skonfigurowany z proxy_url
        """
        try:
            logger.info(f"🔧 [SPECIAL] Ustawianie charge limit na {limit_percent}% przez Tesla HTTP Proxy")
            
            # Sprawdź czy TeslaController ma skonfigurowany proxy
            if hasattr(self.monitor.tesla_controller, 'fleet_api') and hasattr(self.monitor.tesla_controller.fleet_api, 'proxy_url'):
                proxy_url = self.monitor.tesla_controller.fleet_api.proxy_url
                if proxy_url:
                    logger.info(f"✅ [SPECIAL] Używam Tesla HTTP Proxy: {proxy_url}")
                else:
                    logger.warning(f"⚠️ [SPECIAL] TeslaController nie ma skonfigurowanego proxy - komenda może zostać odrzucona")
            
            # Wywołaj set_charge_limit z wymuszonym proxy (wymagane dla podpisanych komend)
            result = self.monitor.tesla_controller.set_charge_limit(limit_percent, use_proxy=True)
            
            if result:
                logger.info(f"✅ [SPECIAL] Charge limit {limit_percent}% ustawiony przez Tesla HTTP Proxy")
            else:
                logger.error(f"❌ [SPECIAL] Nie udało się ustawić charge limit {limit_percent}%")
            
            return result
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd ustawiania charge limit: {e}")
            return False

    def _get_current_charge_limit(self, vin: str) -> Optional[int]:
        """Pobiera obecny limit ładowania z pojazdu"""
        try:
            vehicle_data = self.monitor.tesla_controller.fleet_api.get_vehicle_data(vin, endpoints='charge_state')
            return vehicle_data['charge_state']['charge_limit_soc']
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd pobierania charge limit: {e}")
            return None

    def _convert_charging_plan_to_tesla_schedule(self, charging_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Konwertuje plan ładowania na format Tesla charging schedules
        """
        try:
            # Pobierz współrzędne HOME z .env (analogicznie do warunku A)
            home_lat = float(os.getenv('HOME_LATITUDE', '0.0'))
            home_lon = float(os.getenv('HOME_LONGITUDE', '0.0'))
            
            schedules = []
            for sched in charging_plan.get('schedules', []):
                start_time = sched.get('start_time', '00:00')
                end_time = sched.get('end_time', '06:00')
                
                start_minutes = self._time_str_to_minutes(start_time)
                end_minutes = self._time_str_to_minutes(end_time)
                
                # Stwórz ChargeSchedule z współrzędnymi (analogicznie do warunku A)
                charge_schedule = ChargeSchedule(
                    enabled=True,
                    start_time=start_minutes,
                    end_time=end_minutes,
                    start_enabled=True,
                    end_enabled=True,  # NAPRAWKA: kończyć ładowanie o określonym czasie
                    lat=home_lat,
                    lon=home_lon,
                    days_of_week=sched.get("days_of_week", "All")
                )
                
                schedules.append({
                    'start_time': start_minutes,
                    'end_time': end_minutes,
                    'enabled': True,
                    'lat': home_lat,
                    'lon': home_lon,
                    'days_of_week': sched.get("days_of_week", "All"),
                    'charge_schedule': charge_schedule
                })
                
            return schedules
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd konwersji planu ładowania: {e}")
            return []
    
    def _send_tesla_charging_schedule(self, vin: str, schedule: List[Dict[str, Any]]) -> bool:
        """
        Wysyła harmonogram ładowania do pojazdu Tesla z prawidłowymi współrzędnymi
        """
        try:
            # Pobierz współrzędne HOME z .env (analogicznie do warunku A)
            home_lat = float(os.getenv('HOME_LATITUDE', '0.0'))
            home_lon = float(os.getenv('HOME_LONGITUDE', '0.0'))
            
            # Konwertuj na ChargeSchedule obiekty
            charge_schedules = []
            for sched in schedule:
                charge_schedule = ChargeSchedule(
                    enabled=True,
                    start_time=sched.get('start_time', 0),
                    end_time=sched.get('end_time', 360),
                    start_enabled=True,
                    end_enabled=True,  # NAPRAWKA: kończyć ładowanie o określonym czasie
                    lat=home_lat,
                    lon=home_lon,
                    days_of_week="All"
                )
                charge_schedules.append(charge_schedule)
            
            # Rozwiąż nakładania przed wysłaniem
            logger.info(f"🔍 [SPECIAL] Sprawdzanie nakładań w {len(charge_schedules)} harmonogramach...")
            resolved_schedules = self.monitor._resolve_schedule_overlaps(charge_schedules, vin)
            
            logger.info(f"📋 [SPECIAL] Wysyłanie {len(resolved_schedules)} harmonogramów (po usunięciu nakładań)")
            
            # Wysyłaj rozwiązane harmonogramy
            for i, schedule_obj in enumerate(resolved_schedules):
                start_minutes = schedule_obj.start_time
                end_minutes = schedule_obj.end_time
                
                logger.info(f"📋 [SPECIAL] Harmonogram {i+1}: {start_minutes//60:02d}:{start_minutes%60:02d}-{end_minutes//60:02d}:{end_minutes%60:02d}, enabled=True, lat={home_lat}, lon={home_lon}")
                
                # Dodaj harmonogram do pojazdu
                success = self.monitor.tesla_controller.add_charge_schedule(schedule_obj)
                if not success:
                    logger.error(f"❌ [SPECIAL] Nie udało się dodać harmonogramu {i+1}")
                    return False
                    
                # Opóźnienie między harmonogramami (jak w warunku A)
                if i < len(resolved_schedules) - 1:
                    time.sleep(3)
            
            logger.info(f"✅ [SPECIAL] Wszystkie harmonogramy wysłane pomyślnie")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd wysyłania harmonogramów: {e}")
            return False
    
    def _time_str_to_minutes(self, time_str: str) -> int:
        """Konwertuje string czasu 'HH:MM' na minuty od północy"""
        try:
            hours, minutes = map(int, time_str.split(':'))
            return hours * 60 + minutes
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd konwersji czasu '{time_str}': {e}")
            return 0
    
    def _get_special_charging_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Pobiera special charging session z Firestore"""
        try:
            db = self.monitor._get_firestore_client()
            doc_ref = db.collection('special_charging_sessions').document(session_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd pobierania session {session_id}: {e}")
            return None
    
    def _create_special_charging_session(self, session_data: Dict[str, Any]) -> bool:
        """Tworzy nową special charging session w Firestore"""
        try:
            db = self.monitor._get_firestore_client()
            session_id = session_data['session_id']
            
            doc_ref = db.collection('special_charging_sessions').document(session_id)
            doc_ref.set(session_data)
            
            logger.info(f"✅ [SPECIAL] Session utworzony: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd tworzenia session: {e}")
            return False

    def _complete_special_charging_session(self, session_data: Dict[str, Any]) -> bool:
        """Kończy special charging session i przywraca oryginalne ustawienia"""
        try:
            session_id = session_data.get('session_id', 'unknown')
            vin = session_data.get('vin', 'unknown')
            original_limit = session_data.get('original_charge_limit', 80)
            
            logger.info(f"🏁 [SPECIAL] Kończę session {session_id} dla {vin[-4:]}")
            
            # Sprawdź obecny poziom baterii
            current_vehicle_data = self._get_current_vehicle_data()
            current_battery = current_vehicle_data.get('battery_level', 0) if current_vehicle_data else 0
            
            # Przywróć oryginalny charge limit jeśli potrzeba
            current_limit = self._get_current_charge_limit(vin)
            if current_limit and current_limit != original_limit:
                logger.info(f"🔧 [SPECIAL] Przywracam oryginalny limit: {current_limit}% → {original_limit}%")
                self._set_charge_limit(vin, original_limit)
                time.sleep(3)
            
            # Aktualizuj status session w Firestore
            db = self.monitor._get_firestore_client()
            doc_ref = db.collection('special_charging_sessions').document(session_id)
            doc_ref.update({
                'status': 'COMPLETED',
                'completed_at': self.monitor._get_warsaw_time().isoformat(),
                'final_battery_level': current_battery
            })
            
            logger.info(f"✅ [SPECIAL] Session {session_id} zakończony (bateria: {current_battery}%)")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd completion session: {e}")
            return False

    def _get_current_vehicle_data(self) -> Optional[Dict[str, Any]]:
        """Pobiera aktualne dane pojazdu (wykorzystuje istniejącą logikę z monitor)"""
        try:
            # NAPRAWKA: Zapewnij połączenie z Tesla przed pobieraniem pojazdów
            logger.info("🔗 [SPECIAL] Sprawdzanie połączenia z Tesla API...")
            tesla_connected = self.monitor.tesla_controller.connect()
            if not tesla_connected:
                logger.error("❌ [SPECIAL] Nie można połączyć się z Tesla API")
                return None
            
            logger.info("✅ [SPECIAL] Połączono z Tesla API pomyślnie")
            
            # Używa istniejącej logiki z CloudTeslaMonitor
            all_vehicles = self.monitor.tesla_controller.get_all_vehicles()
            if not all_vehicles:
                logger.warning("❌ [SPECIAL] Brak dostępnych pojazdów")
                return None
            
            # Zakładamy pierwszy pojazd (można rozszerzyć dla wielu pojazdów)
            vehicle = all_vehicles[0]
            vin = vehicle.get('vin', 'unknown')
            logger.info(f"🚗 [SPECIAL] Pobieranie danych pojazdu VIN: {vin[-4:]}")
            
            # NAPRAWKA: Użyj prawidłowej metody get_vehicle_status zamiast nieistniejącej get_vehicle_location_data
            vehicle_data = self.monitor.tesla_controller.get_vehicle_status(vin)
            if not vehicle_data:
                logger.error(f"❌ [SPECIAL] get_vehicle_status zwróciło puste dane dla VIN: {vin[-4:]}")
                return None
            
            is_online = vehicle_data.get('online', False)
            logger.info(f"✅ [SPECIAL] Pobrano dane pojazdu: online={is_online}")
            
            # NOWA LOGIKA: Inteligentne pobieranie battery_level
            battery_level = vehicle_data.get('battery_level', None)
            
            if battery_level is None and not is_online:
                # Pojazd offline - spróbuj pobrać ostatnią znaną wartość z Firestore
                logger.info(f"🔋 [SPECIAL] Pojazd offline, pobieranie ostatniego znanego poziomu baterii...")
                last_known_battery = self._get_last_known_battery_level(vin)
                
                if last_known_battery is not None:
                    battery_level = last_known_battery
                    logger.info(f"📚 [SPECIAL] Użyto ostatniej znanej wartości baterii: {battery_level}%")
                else:
                    # Brak danych historycznych - użyj rozsądnej wartości domyślnej
                    battery_level = 50  # Zamiast 0% użyj 50% jako rozumnej wartości domyślnej
                    logger.warning(f"⚠️ [SPECIAL] Brak danych baterii, używam wartości domyślnej: {battery_level}%")
            elif battery_level is None:
                battery_level = 50  # Fallback dla innych przypadków
                logger.warning(f"⚠️ [SPECIAL] Brak battery_level, używam wartości domyślnej: {battery_level}%")
            else:
                logger.info(f"🔋 [SPECIAL] Aktualny poziom baterii: {battery_level}%")
            
            return {
                'vin': vin,
                'battery_level': battery_level,
                'charging_state': vehicle_data.get('charging_state', 'Unknown'),
                'is_charging_ready': vehicle_data.get('is_charging_ready', False),
                'online': is_online,
                'vehicle_state': vehicle_data.get('vehicle_state', 'unknown'),
                'display_name': vehicle_data.get('display_name', 'Unknown')
            }
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd pobierania danych pojazdu: {e}")
            logger.error(f"❌ [SPECIAL] Szczegóły błędu: {type(e).__name__}: {str(e)}")
            return None
    
    def _get_last_known_battery_level(self, vin: str) -> Optional[int]:
        """Pobiera ostatnią znaną wartość battery_level z Firestore"""
        try:
            firestore_client = self.monitor._get_firestore_client()
            
            # Sprawdź ostatni dokument ze statusem pojazdu
            collection_name = f"vehicle_status_{vin[-4:]}"
            query = firestore_client.collection(collection_name).order_by('timestamp', direction='DESCENDING').limit(10)
            docs = list(query.stream())
            
            for doc in docs:
                data = doc.to_dict()
                battery_level = data.get('battery_level')
                if battery_level is not None and battery_level > 0:
                    logger.info(f"📚 [SPECIAL] Znaleziono ostatnią wartość baterii w Firestore: {battery_level}% z {data.get('timestamp', 'brak_czasu')}")
                    return int(battery_level)
            
            logger.info(f"📚 [SPECIAL] Nie znaleziono historycznych danych baterii w Firestore")
            return None
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd pobierania z Firestore: {e}")
            return None
    
    def _send_response(self, status_code: int, data: dict):
        """Wysyła odpowiedź HTTP"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        """Wyłącza domyślne logowanie HTTP"""
        pass

    def _ensure_centralized_tokens(self) -> bool:
        """
        NAPRAWKA: Deleguje do CloudTeslaWorker._ensure_centralized_tokens
        Unika błędu 'NoneType' object has no attribute 'makefile'
        """
        return self.worker._ensure_centralized_tokens()

    def _perform_daily_special_charging_check(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wykonuje daily special charging check - główna logika special charging
        1. NOWE: Czyści zombie sessions
        2. Pobiera dane z Google Sheets
        3. Oblicza plany ładowania
        4. Wysyła harmonogramy lub tworzy scheduled jobs
        """
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 📋 [SPECIAL] Rozpoczynam daily special charging check")
            
            # KROK 0: Wyczyść zombie sessions PRZED sprawdzaniem nowych potrzeb
            logger.info(f"{time_str} 🧹 [SPECIAL] KROK 0: Czyszczenie zombie sessions...")
            cleaned_sessions = self._cleanup_expired_special_sessions()
            
            result = {
                "active_needs": 0,
                "processed_needs": 0,
                "sent_schedules": 0,
                "created_sessions": 0,
                "cleaned_zombie_sessions": cleaned_sessions,
                "errors": []
            }
            
            # KROK 1: Pobierz special charging needs z Google Sheets
            try:
                logger.info(f"{time_str} 📊 [SPECIAL] Pobieranie danych z Google Sheets...")
                special_needs = self._get_special_charging_needs_from_sheets()
                
                if not special_needs:
                    logger.info(f"{time_str} ℹ️ [SPECIAL] Brak aktywnych special charging needs w Google Sheets")
                    return result
                
                result["active_needs"] = len(special_needs)
                logger.info(f"{time_str} 📋 [SPECIAL] Znaleziono {len(special_needs)} aktywnych potrzeb ładowania")
                
            except Exception as e:
                error_msg = f"Błąd pobierania danych z Google Sheets: {str(e)}"
                logger.error(f"❌ [SPECIAL] {error_msg}")
                result["errors"].append(error_msg)
                return result
            
            # KROK 2: Pobierz aktualne dane pojazdu
            try:
                vehicle_data = self._get_current_vehicle_data()
                if not vehicle_data:
                    error_msg = "Nie udało się pobrać danych pojazdu"
                    logger.error(f"❌ [SPECIAL] {error_msg}")
                    result["errors"].append(error_msg)
                    return result
                    
                logger.info(f"{time_str} 🔋 [SPECIAL] Aktualny poziom baterii: {vehicle_data.get('battery_level', 'unknown')}%")
                
            except Exception as e:
                error_msg = f"Błąd pobierania danych pojazdu: {str(e)}"
                logger.error(f"❌ [SPECIAL] {error_msg}")
                result["errors"].append(error_msg)
                return result
            
            # KROK 3: Przetwórz każdą potrzebę ładowania
            for need in special_needs:
                try:
                    result["processed_needs"] += 1
                    
                    # Oblicz plan ładowania
                    charging_plan = self._calculate_charging_plan(need, vehicle_data)
                    if not charging_plan:
                        logger.warning(f"⚠️ [SPECIAL] Nie udało się obliczyć planu dla need {need.get('row', 'unknown')}")
                        continue
                    
                    logger.info(f"{time_str} 🔍 [SPECIAL] Szukam optymalnego slotu dla {charging_plan['required_hours']:.1f}h ładowania, target: {need['target_datetime'].strftime('%Y-%m-%d %H:%M')}")
                    
                    # Sprawdź czy teraz wysłać harmonogram czy zaplanować na później
                    current_time = warsaw_time
                    send_time = charging_plan.get('send_schedule_at')
                    
                    if send_time and current_time >= send_time:
                        # Wyślij harmonogram teraz
                        logger.info(f"{time_str} ⏰ [SPECIAL] Czas wysłać harmonogram dla need {need.get('row', 'unknown')}")
                        
                        if self._send_special_charging_schedule(charging_plan, need, vehicle_data):
                            result["sent_schedules"] += 1
                            logger.info(f"✅ [SPECIAL] Harmonogram wysłany pomyślnie")
                        else:
                            logger.error(f"❌ [SPECIAL] Nie udało się wysłać harmonogramu")
                            result["errors"].append(f"Błąd wysyłania harmonogramu dla need {need.get('row', 'unknown')}")
                    
                    elif send_time:
                        # Utwórz scheduled job na później
                        logger.info(f"{time_str} ⏳ [SPECIAL] Planowanie harmonogramu na {send_time.strftime('%H:%M')}")
                        
                        session_id = f"special_{need.get('row', '0')}_{need['target_datetime'].strftime('%Y%m%d_%H%M')}"
                        
                        # Utwórz session w Firestore
                        session_data = {
                            'session_id': session_id,
                            'vin': vehicle_data.get('vin'),
                            'status': 'SCHEDULED',
                            'target_battery_level': need.get('target_battery_percent'),
                            'target_datetime': need['target_datetime'].isoformat(),
                            'charging_start': charging_plan['charging_start'].isoformat(),
                            'charging_end': charging_plan['charging_end'].isoformat(),
                            'send_schedule_at': send_time.isoformat(),
                            'sheets_row': need.get('row'),
                            'created_at': current_time.isoformat(),
                            'charging_plan': charging_plan
                        }
                        
                        if self._create_special_charging_session(session_data):
                            result["created_sessions"] += 1
                            
                            # Utwórz dynamic scheduler job
                            if self._create_dynamic_scheduler_job(charging_plan, session_id):
                                logger.info(f"✅ [SPECIAL] Session i dynamic job utworzone dla {session_id}")
                            else:
                                logger.warning(f"⚠️ [SPECIAL] Session utworzony ale błąd dynamic job dla {session_id}")
                        else:
                            logger.error(f"❌ [SPECIAL] Błąd tworzenia session {session_id}")
                    
                    else:
                        logger.warning(f"⚠️ [SPECIAL] Brak send_schedule_at w charging_plan")
                
                except Exception as need_error:
                    error_msg = f"Błąd przetwarzania need {need.get('row', 'unknown')}: {str(need_error)}"
                    logger.error(f"❌ [SPECIAL] {error_msg}")
                    result["errors"].append(error_msg)
                    continue
            
            logger.info(f"✅ [SPECIAL] Daily check zakończony: {result['processed_needs']} przetworzonych, {result['sent_schedules']} wysłanych, {result['created_sessions']} zaplanowanych")
            return result
            
        except Exception as e:
            error_msg = f"Krytyczny błąd daily special charging check: {str(e)}"
            logger.error(f"❌ [SPECIAL] {error_msg}")
            return {
                "active_needs": 0,
                "processed_needs": 0, 
                "sent_schedules": 0,
                "created_sessions": 0,
                "errors": [error_msg]
            }

    def _get_special_charging_needs_from_sheets(self) -> List[Dict[str, Any]]:
        """Pobiera special charging needs z Google Sheets"""
        try:
            logger.info("📊 [SPECIAL] Łączenie z Google Sheets...")
            
            # Konfiguracja Google Sheets API
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = Credentials.from_service_account_file('tesla-sheets-key.json', scopes=scope)
            client = gspread.authorize(creds)
            
            # Otwórz arkusz
            sheet = client.open("TESLA - special charging").sheet1
            logger.info("✅ [SPECIAL] Połączono z Google Sheets pomyślnie")
            
            # Pobierz wszystkie rekordy
            records = sheet.get_all_records()
            logger.info(f"📋 [SPECIAL] Pobrano {len(records)} rekordów z arkusza")
            
            # Filtruj aktywne potrzeby
            active_needs = []
            current_time = self.monitor._get_warsaw_time()
            
            for i, record in enumerate(records, start=2):  # Start=2 bo pierwszy wiersz to nagłówki
                try:
                    # Sprawdź czy rekord jest aktywny
                    status = record.get('Status', '').strip().upper()
                    if status != 'ACTIVE':
                        continue
                    
                    # Parsuj target_datetime
                    target_date = record.get('Data', '').strip()
                    target_time = record.get('Godzina', '').strip()
                    
                    if not target_date or not target_time:
                        logger.warning(f"⚠️ [SPECIAL] Wiersz {i}: Brak Data lub Godzina")
                        continue
                    
                    # Parsuj datetime
                    target_datetime_str = f"{target_date} {target_time}"
                    target_datetime = datetime.strptime(target_datetime_str, '%Y-%m-%d %H:%M')
                    
                    # Ustaw timezone na Warsaw
                    import pytz
                    warsaw_tz = pytz.timezone('Europe/Warsaw')
                    target_datetime = warsaw_tz.localize(target_datetime)
                    
                    # Sprawdź czy target_datetime jest w przyszłości
                    if target_datetime <= current_time:
                        logger.info(f"ℹ️ [SPECIAL] Wiersz {i}: Target datetime {target_datetime} już minął")
                        continue
                    
                    # Parsuj target_battery_percent
                    target_battery = record.get('Docelowy %', '')
                    if not target_battery:
                        logger.warning(f"⚠️ [SPECIAL] Wiersz {i}: Brak Docelowy %")
                        continue
                    
                    try:
                        target_battery_percent = int(target_battery)
                        if not (50 <= target_battery_percent <= 100):
                            logger.warning(f"⚠️ [SPECIAL] Wiersz {i}: Docelowy % {target_battery_percent}% poza zakresem 50-100%")
                            continue
                    except ValueError:
                        logger.warning(f"⚠️ [SPECIAL] Wiersz {i}: Nieprawidłowy Docelowy %: {target_battery}")
                        continue
                    
                    # Dodaj do aktywnych potrzeb
                    need = {
                        'row': i,
                        'target_datetime': target_datetime,
                        'target_battery_percent': target_battery_percent,
                        'date': target_date,
                        'time': target_time,
                        'description': record.get('Description', '').strip()
                    }
                    
                    active_needs.append(need)
                    logger.info(f"✅ [SPECIAL] Wiersz {i}: Aktywna potrzeba {target_battery_percent}% do {target_datetime.strftime('%Y-%m-%d %H:%M')}")
                
                except Exception as row_error:
                    logger.error(f"❌ [SPECIAL] Błąd parsowania wiersza {i}: {row_error}")
                    continue
            
            logger.info(f"📋 [SPECIAL] Znaleziono {len(active_needs)} aktywnych potrzeb ładowania")
            return active_needs
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd pobierania z Google Sheets: {e}")
            return []

    def _calculate_charging_plan(self, need: Dict[str, Any], vehicle_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Oblicza plan ładowania dla special charging need"""
        try:
            current_battery = vehicle_data.get('battery_level', 50)
            target_battery = need.get('target_battery_percent', 80)
            target_datetime = need.get('target_datetime')
            
            if target_battery <= current_battery:
                logger.info(f"ℹ️ [SPECIAL] Bateria już na poziomie {current_battery}% >= {target_battery}%")
                return None
            
            # Oblicz wymaganą energię
            battery_diff = target_battery - current_battery
            required_energy = (battery_diff / 100) * BATTERY_CAPACITY_KWH
            required_hours = required_energy / CHARGING_RATE
            
            logger.info(f"🔋 [SPECIAL] Wymagane ładowanie: {current_battery}% → {target_battery}% ({battery_diff}%, {required_energy:.1f}kWh, {required_hours:.1f}h)")
            
            # Znajdź optymalny slot
            optimal_slot = self._find_optimal_charging_slot(required_hours, target_datetime)
            if not optimal_slot:
                logger.error(f"❌ [SPECIAL] Nie znaleziono optymalnego slotu dla {required_hours:.1f}h ładowania")
                return None
            
            charging_plan = {
                'target_battery_percent': target_battery,
                'current_battery_percent': current_battery,
                'required_energy_kwh': required_energy,
                'required_hours': required_hours,
                'charging_start': optimal_slot['start'],
                'charging_end': optimal_slot['end'],
                'send_schedule_at': optimal_slot['send_time'],
                'schedules': [{
                    'start_time': optimal_slot['start'].strftime('%H:%M'),
                    'end_time': optimal_slot['end'].strftime('%H:%M'),
                    'days_of_week': 'All'
                }]
            }
            
            return charging_plan
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd obliczania planu ładowania: {e}")
            return None

    def _find_optimal_charging_slot(self, required_hours: float, target_datetime: datetime) -> Optional[Dict[str, Any]]:
        """
        Znajduje optymalny slot ładowania z hierarchią strategii:
        1. Slot 100% unikający peak hours (najlepszy)
        2. Slot wcześniejszy unikający peak hours  
        3. Slot z minimalną kolizją z peak hours
        4. Slot zapewniający target time (ostateczność)
        """
        try:
            logger.info(f"🔍 [SPECIAL] Szukam optymalnego slotu dla {required_hours:.1f}h ładowania, target: {target_datetime.strftime('%H:%M')}")
            
            # STRATEGIA 1: Slot optymalny (bez kolizji)
            optimal_slot = self._find_slot_avoiding_peak_hours(required_hours, target_datetime)
            if optimal_slot:
                logger.info(f"✅ [SPECIAL] STRATEGIA 1: Znaleziono optymalny slot: {optimal_slot['start'].strftime('%H:%M')}-{optimal_slot['end'].strftime('%H:%M')} (unika peak hours)")
                return optimal_slot
            
            # STRATEGIA 2: Slot wcześniejszy (poprzedni dzień/wcześniejsze godziny)
            earlier_slot = self._find_earlier_slot(required_hours, target_datetime)
            if earlier_slot:
                logger.warning(f"⚠️ [SPECIAL] STRATEGIA 2: Używam wcześniejszy slot: {earlier_slot['start'].strftime('%H:%M')}-{earlier_slot['end'].strftime('%H:%M')} (unika peak hours)")
                return earlier_slot
            
            # STRATEGIA 3: Slot z minimalną kolizją
            minimal_collision_slot = self._find_minimal_collision_slot(required_hours, target_datetime)
            if minimal_collision_slot:
                collision_hours = minimal_collision_slot.get('collision_hours', 0)
                logger.warning(f"🚨 [SPECIAL] STRATEGIA 3: Slot z minimalną kolizją: {minimal_collision_slot['start'].strftime('%H:%M')}-{minimal_collision_slot['end'].strftime('%H:%M')} ({collision_hours:.1f}h kolizji)")
                return minimal_collision_slot
            
            # STRATEGIA 4: Fallback - zapewnij target time
            fallback_slot = self._create_fallback_slot(required_hours, target_datetime)
            logger.error(f"🚨 [SPECIAL] STRATEGIA 4 (FALLBACK): Wymuszam slot zapewniający target time: {fallback_slot['start'].strftime('%H:%M')}-{fallback_slot['end'].strftime('%H:%M')}")
            logger.error(f"🚨 [SPECIAL] UWAGA: Slot może kolidować z peak hours ale zapewnia docelowy poziom baterii!")
            return fallback_slot
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd znajdowania optymalnego slotu: {e}")
            return None

    def _find_slot_avoiding_peak_hours(self, required_hours: float, target_datetime: datetime) -> Optional[Dict[str, Any]]:
        """
        STRATEGIA 1: Znajdź slot unikający peak hours w standardowym oknie
        """
        try:
            # Najpóźniejszy możliwy start (z safety buffer)
            latest_start = target_datetime - timedelta(hours=required_hours + SAFETY_BUFFER_HOURS)
            
            # Sprawdź slot rozpoczynający się najpóźniej
            slot_start = latest_start.replace(minute=0, second=0, microsecond=0)
            slot_end = slot_start + timedelta(hours=required_hours)
            
            logger.info(f"🔍 [SPECIAL] STRATEGIA 1: Sprawdzam standardowy slot {slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}")
            
            # Sprawdź czy slot unika peak hours
            if self._slot_avoids_peak_hours(slot_start, slot_end):
                send_time = slot_start - timedelta(hours=2)
                return {
                    'start': slot_start,
                    'end': slot_end,
                    'send_time': send_time,
                    'strategy': 'optimal'
                }
            else:
                logger.info(f"⚠️ [SPECIAL] STRATEGIA 1: Slot koliduje z peak hours")
                return None
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd STRATEGIA 1: {e}")
            return None

    def _find_earlier_slot(self, required_hours: float, target_datetime: datetime) -> Optional[Dict[str, Any]]:
        """
        STRATEGIA 2: Znajdź wcześniejszy slot unikający peak hours
        Opcje: 22:00-01:00, 03:45-06:00, itp.
        """
        try:
            logger.info(f"🔍 [SPECIAL] STRATEGIA 2: Szukam wcześniejszego slotu unikającego peak hours")
            
            # Opcja A: Slot kończący się przed peak hours (przed 06:00)
            end_before_peak = target_datetime.replace(hour=6, minute=0, second=0, microsecond=0)
            start_before_peak = end_before_peak - timedelta(hours=required_hours)
            
            logger.info(f"🔍 [SPECIAL] STRATEGIA 2A: Sprawdzam slot przed peak hours: {start_before_peak.strftime('%H:%M')}-{end_before_peak.strftime('%H:%M')}")
            
            # Sprawdź czy to dobry slot nocny (22:00-06:00)
            if (start_before_peak.hour >= 22 or start_before_peak.hour <= 3) and start_before_peak < target_datetime:
                if self._slot_avoids_peak_hours(start_before_peak, end_before_peak):
                    send_time = start_before_peak - timedelta(hours=2)
                    logger.info(f"✅ [SPECIAL] STRATEGIA 2A: Znaleziono wcześniejszy slot przed peak hours")
                    return {
                        'start': start_before_peak,
                        'end': end_before_peak,
                        'send_time': send_time,
                        'strategy': 'earlier_before_peak'
                    }
            
            # Opcja B: Slot poprzedniego wieczoru (22:00-xx:xx)
            current_time = self.monitor._get_warsaw_time()
            
            # Jeśli sprawdzenie jest po północy, sprawdź slot z poprzedniego wieczoru
            if current_time.hour <= 6:  # Sprawdzenie między 00:00-06:00
                previous_evening_start = target_datetime.replace(hour=22, minute=0) - timedelta(days=1)
                previous_evening_end = previous_evening_start + timedelta(hours=required_hours)
                
                logger.info(f"🔍 [SPECIAL] STRATEGIA 2B: Sprawdzam slot poprzedniego wieczoru: {previous_evening_start.strftime('%H:%M')}-{previous_evening_end.strftime('%H:%M')}")
                
                # Sprawdź czy kończy się przed 02:00 (dobry slot nocny)
                if previous_evening_end.hour <= 2 or previous_evening_end.hour >= 22:
                    if self._slot_avoids_peak_hours(previous_evening_start, previous_evening_end):
                        send_time = previous_evening_start - timedelta(hours=1)  # Krócej niż zwykle
                        logger.info(f"✅ [SPECIAL] STRATEGIA 2B: Znaleziono slot poprzedniego wieczoru")
                        return {
                            'start': previous_evening_start,
                            'end': previous_evening_end,
                            'send_time': send_time,
                            'strategy': 'previous_evening'
                        }
            
            # Opcja C: Wcześniejszy slot w tym samym dniu
            for start_hour in [3, 2, 1, 0, 23, 22]:  # Sprawdź różne godziny startowe
                if start_hour >= 22:  # Poprzedni dzień
                    slot_start = target_datetime.replace(hour=start_hour, minute=0) - timedelta(days=1)
                else:
                    slot_start = target_datetime.replace(hour=start_hour, minute=0)
                
                slot_end = slot_start + timedelta(hours=required_hours)
                
                # Sprawdź czy slot jest przed target_datetime i unika peak hours
                if slot_end < target_datetime and self._slot_avoids_peak_hours(slot_start, slot_end):
                    send_time = slot_start - timedelta(hours=1.5)
                    logger.info(f"✅ [SPECIAL] STRATEGIA 2C: Znaleziono wcześniejszy slot: {slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}")
                    return {
                        'start': slot_start,
                        'end': slot_end,
                        'send_time': send_time,
                        'strategy': 'earlier_same_day'
                    }
            
            logger.info(f"⚠️ [SPECIAL] STRATEGIA 2: Nie znaleziono wcześniejszego slotu unikającego peak hours")
            return None
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd STRATEGIA 2: {e}")
            return None

    def _find_minimal_collision_slot(self, required_hours: float, target_datetime: datetime) -> Optional[Dict[str, Any]]:
        """
        STRATEGIA 3: Znajdź slot z minimalną kolizją z peak hours
        Maksymalnie 50% czasu ładowania może kolidować z peak hours
        """
        try:
            logger.info(f"🔍 [SPECIAL] STRATEGIA 3: Szukam slotu z minimalną kolizją z peak hours")
            
            # Sprawdź różne opcje startowe wokół optymalnego czasu
            base_start = target_datetime - timedelta(hours=required_hours + SAFETY_BUFFER_HOURS)
            
            for hour_offset in [0, -1, -2, -3, 1]:  # Sprawdź różne przesunięcia
                slot_start = base_start.replace(minute=0) + timedelta(hours=hour_offset)
                slot_end = slot_start + timedelta(hours=required_hours)
                
                # Sprawdź czy slot jest w rozsądnym przedziale czasowym
                if slot_end > target_datetime:
                    continue
                
                collision_hours = self._calculate_peak_collision(slot_start, slot_end)
                collision_percentage = (collision_hours / required_hours) * 100
                
                logger.info(f"🔍 [SPECIAL] STRATEGIA 3: Slot {slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')} ma {collision_hours:.1f}h kolizji ({collision_percentage:.1f}%)")
                
                # Akceptuj slot z maksymalnie 50% kolizji
                if collision_percentage <= 50:
                    send_time = slot_start - timedelta(hours=2)
                    logger.info(f"✅ [SPECIAL] STRATEGIA 3: Akceptuję slot z {collision_percentage:.1f}% kolizji")
                    return {
                        'start': slot_start,
                        'end': slot_end,
                        'send_time': send_time,
                        'collision_hours': collision_hours,
                        'collision_percentage': collision_percentage,
                        'strategy': 'minimal_collision'
                    }
            
            logger.info(f"⚠️ [SPECIAL] STRATEGIA 3: Wszystkie sloty mają >50% kolizji z peak hours")
            return None
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd STRATEGIA 3: {e}")
            return None

    def _create_fallback_slot(self, required_hours: float, target_datetime: datetime) -> Dict[str, Any]:
        """
        STRATEGIA 4: Ostateczność - slot zapewniający target time mimo kolizji z peak hours
        Minimalny buffer bezpieczeństwa ale gwarantuje docelowy poziom baterii
        """
        try:
            # Minimalny buffer 0.5h zamiast 1.5h
            latest_start = target_datetime - timedelta(hours=required_hours + 0.5)
            slot_start = latest_start.replace(minute=0, second=0, microsecond=0)
            slot_end = slot_start + timedelta(hours=required_hours)
            
            collision_hours = self._calculate_peak_collision(slot_start, slot_end)
            collision_percentage = (collision_hours / required_hours) * 100
            
            logger.warning(f"🚨 [SPECIAL] STRATEGIA 4 (FALLBACK): Slot {slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}")
            logger.warning(f"🚨 [SPECIAL] Kolizja z peak hours: {collision_hours:.1f}h ({collision_percentage:.1f}%)")
            logger.warning(f"🚨 [SPECIAL] UZASADNIENIE: Zapewnia docelowy poziom baterii na czas!")
            
            send_time = slot_start - timedelta(hours=1)  # Krótszy czas przygotowania
            
            return {
                'start': slot_start,
                'end': slot_end,
                'send_time': send_time,
                'collision_hours': collision_hours,
                'collision_percentage': collision_percentage,
                'strategy': 'fallback',
                'fallback': True
            }
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd STRATEGIA 4: {e}")
            # Ostateczny fallback
            latest_start = target_datetime - timedelta(hours=required_hours)
            return {
                'start': latest_start,
                'end': target_datetime,
                'send_time': latest_start - timedelta(minutes=30),
                'strategy': 'emergency_fallback',
                'fallback': True
            }

    def _calculate_peak_collision(self, start: datetime, end: datetime) -> float:
        """
        Oblicza ile godzin slotu koliduje z peak hours
        """
        try:
            total_collision = 0.0
            
            for peak_start, peak_end in PEAK_HOURS:
                # Konwertuj na minuty od północy
                slot_start_minutes = start.hour * 60 + start.minute
                slot_end_minutes = end.hour * 60 + end.minute
                peak_start_minutes = peak_start * 60
                peak_end_minutes = peak_end * 60
                
                # Obsłuż przejście przez północ dla slotu
                if slot_end_minutes < slot_start_minutes:
                    slot_end_minutes += 24 * 60
                
                # Oblicz kolizję
                collision_start = max(slot_start_minutes, peak_start_minutes)
                collision_end = min(slot_end_minutes, peak_end_minutes)
                
                if collision_start < collision_end:
                    collision_minutes = collision_end - collision_start
                    total_collision += collision_minutes / 60.0
            
            return total_collision
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd obliczania kolizji z peak hours: {e}")
            return 0.0

    def _slot_avoids_peak_hours(self, start: datetime, end: datetime) -> bool:
        """Sprawdza czy slot ładowania unika peak hours"""
        try:
            # Peak hours: 6:00-10:00, 19:00-22:00
            for peak_start, peak_end in PEAK_HOURS:
                # Sprawdź kolizję z peak hours
                slot_start_hour = start.hour + start.minute / 60
                slot_end_hour = end.hour + end.minute / 60
                
                # Obsłuż przejście przez północ
                if slot_end_hour < slot_start_hour:
                    slot_end_hour += 24
                
                # Sprawdź kolizję
                if not (slot_end_hour <= peak_start or slot_start_hour >= peak_end):
                    logger.info(f"⚠️ [SPECIAL] Slot {start.strftime('%H:%M')}-{end.strftime('%H:%M')} koliduje z peak hours {peak_start:02d}:00-{peak_end:02d}:00")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ [SPECIAL] Błąd sprawdzania peak hours: {e}")
            return False

    def _handle_send_special_schedule_immediate(self):
        """
        TESTOWY endpoint - wysyła special charging harmonogram natychmiast do pojazdu
        Używany do testowania funkcjonalności bez Google Sheets
        """
        try:
            # Pobierz dane z żądania
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                try:
                    request_data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    request_data = {}
            else:
                request_data = {}
            
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 🔧 [SPECIAL-TEST] TESTOWY endpoint - wysyłanie harmonogramu natychmiast")
            
            # Parametry testowe
            target_percent = request_data.get('target_percent', 85)
            force_send = request_data.get('force_send', False)
            reason = request_data.get('reason', 'immediate_test')
            
            logger.info(f"{time_str} 🎯 [SPECIAL-TEST] Target: {target_percent}%, Force: {force_send}, Reason: {reason}")
            
            # Pobierz aktualne dane pojazdu
            vehicle_data = self._get_current_vehicle_data()
            if not vehicle_data:
                error_msg = "Nie udało się pobrać danych pojazdu"
                logger.error(f"❌ [SPECIAL-TEST] {error_msg}")
                self._send_response(500, {"error": error_msg})
                return
            
            current_battery = vehicle_data.get('battery_level', 50)
            logger.info(f"{time_str} 🔋 [SPECIAL-TEST] Aktualny poziom baterii: {current_battery}%")
            
            # Oblicz plan ładowania (prosty - 4h od teraz)
            charging_start = warsaw_time + timedelta(hours=2)
            charging_end = charging_start + timedelta(hours=4)
            
            # Stwórz testowy plan ładowania
            charging_plan = {
                'target_battery_percent': target_percent,
                'current_battery_percent': current_battery,
                'required_energy_kwh': ((target_percent - current_battery) / 100) * BATTERY_CAPACITY_KWH,
                'required_hours': 4.0,
                'charging_start': charging_start,
                'charging_end': charging_end,
                'schedules': [{
                    'start_time': charging_start.strftime('%H:%M'),
                    'end_time': charging_end.strftime('%H:%M'),
                    'days_of_week': 'All'
                }]
            }
            
            # Stwórz testowy need
            need = {
                'row': 999,  # Testowy wiersz
                'target_battery_percent': target_percent,
                'target_datetime': charging_end,
                'description': f'TEST: {reason}'
            }
            
            logger.info(f"{time_str} 📋 [SPECIAL-TEST] Plan ładowania: {charging_start.strftime('%H:%M')}-{charging_end.strftime('%H:%M')} ({charging_plan['required_hours']:.1f}h, {charging_plan['required_energy_kwh']:.1f}kWh)")
            
            # Wyślij harmonogram do pojazdu (używa naprawionej logiki proxy)
            success = self._send_special_charging_schedule(charging_plan, need, vehicle_data)
            
            if success:
                response = {
                    "status": "success",
                    "message": "Special Charging Schedule wysłany pomyślnie",
                    "details": {
                        "vin": vehicle_data.get('vin', 'unknown')[-4:],
                        "current_battery": current_battery,
                        "target_battery": target_percent,
                        "charging_plan": f"{charging_start.strftime('%H:%M')}-{charging_end.strftime('%H:%M')}",
                        "required_energy": f"{charging_plan['required_energy_kwh']:.1f}kWh",
                        "test_reason": reason
                    },
                    "timestamp": warsaw_time.isoformat(),
                    "endpoint": "send-special-schedule-immediate"
                }
                
                logger.info(f"✅ [SPECIAL-TEST] Harmonogram wysłany pomyślnie do pojazdu {vehicle_data.get('vin', 'unknown')[-4:]}")
                self._send_response(200, response)
                
            else:
                error_msg = "Nie udało się wysłać harmonogramu do pojazdu"
                logger.error(f"❌ [SPECIAL-TEST] {error_msg}")
                
                response = {
                    "status": "error",
                    "error": error_msg,
                    "details": {
                        "vin": vehicle_data.get('vin', 'unknown')[-4:],
                        "current_battery": current_battery,
                        "target_battery": target_percent,
                        "test_reason": reason
                    },
                    "timestamp": warsaw_time.isoformat(),
                    "endpoint": "send-special-schedule-immediate"
                }
                
                self._send_response(500, response)
                
        except Exception as e:
            logger.error(f"❌ [SPECIAL-TEST] Błąd testowego endpointu: {e}")
            self._send_response(500, {
                "error": str(e),
                "endpoint": "send-special-schedule-immediate",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    def _cleanup_expired_special_sessions(self) -> int:
        """
        Automatycznie czyści przeterminowane special charging sessions
        Oznacza jako COMPLETED sessions które już się zakończyły
        
        Returns:
            int: Liczba wyczyszczonych sessions
        """
        try:
            from google.cloud import firestore
            import pytz
            
            db = firestore.Client()
            current_time = datetime.now(pytz.timezone('Europe/Warsaw'))
            
            logger.info(f"🧹 [CLEANUP] Rozpoczynam czyszczenie przeterminowanych special charging sessions")
            logger.info(f"🧹 [CLEANUP] Aktualny czas Warsaw: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Znajdź wszystkie ACTIVE sessions
            sessions_ref = db.collection('special_charging_sessions')
            active_sessions = list(sessions_ref.where('status', '==', 'ACTIVE').stream())
            
            logger.info(f"🧹 [CLEANUP] Znaleziono {len(active_sessions)} aktywnych sessions do sprawdzenia")
            
            cleaned_count = 0
            zombie_sessions = []
            
            for session_doc in active_sessions:
                try:
                    session_data = session_doc.to_dict()
                    session_id = session_data.get('session_id', session_doc.id)
                    charging_end_str = session_data.get('charging_end')
                    
                    if not charging_end_str or charging_end_str == 'Unknown':
                        logger.warning(f"⚠️ [CLEANUP] Session {session_id} bez charging_end - pomijam")
                        continue
                    
                    # Parse charging_end time
                    try:
                        if charging_end_str.endswith('Z'):
                            charging_end_str = charging_end_str.replace('Z', '+00:00')
                        
                        charging_end = datetime.fromisoformat(charging_end_str)
                        
                        # Ensure timezone awareness
                        if charging_end.tzinfo is None:
                            warsaw_tz = pytz.timezone('Europe/Warsaw')
                            charging_end = warsaw_tz.localize(charging_end)
                        
                        # Convert to Warsaw timezone for comparison
                        charging_end_warsaw = charging_end.astimezone(pytz.timezone('Europe/Warsaw'))
                        
                        # Add safety buffer of 2 hours after charging end
                        cleanup_time = charging_end_warsaw + timedelta(hours=2)
                        
                        logger.info(f"🧹 [CLEANUP] Session {session_id}: end={charging_end_warsaw.strftime('%Y-%m-%d %H:%M')}, cleanup_time={cleanup_time.strftime('%Y-%m-%d %H:%M')}")
                        
                        if current_time > cleanup_time:
                            # Session przeterminowana - oznacz jako COMPLETED
                            session_doc.reference.update({
                                'status': 'COMPLETED',
                                'completed_at': current_time.isoformat(),
                                'completion_reason': 'auto_expired_daily_cleanup',
                                'cleanup_time': cleanup_time.isoformat(),
                                'cleaned_by': 'worker_daily_check'
                            })
                            
                            cleaned_count += 1
                            zombie_sessions.append({
                                'session_id': session_id,
                                'charging_end': charging_end_warsaw.strftime('%Y-%m-%d %H:%M'),
                                'hours_overdue': round((current_time - charging_end_warsaw).total_seconds() / 3600, 1)
                            })
                            
                            logger.info(f"🧹 [CLEANUP] ✅ Session {session_id} oznaczony jako COMPLETED (przeterminowany o {round((current_time - charging_end_warsaw).total_seconds() / 3600, 1)}h)")
                        else:
                            logger.info(f"🧹 [CLEANUP] ✅ Session {session_id} nadal aktywny (kończy się za {round((cleanup_time - current_time).total_seconds() / 3600, 1)}h)")
                        
                    except Exception as time_error:
                        logger.warning(f"⚠️ [CLEANUP] Błąd parsowania czasu dla session {session_id}: {time_error}")
                        logger.warning(f"⚠️ [CLEANUP] charging_end_str: '{charging_end_str}'")
                        continue
                        
                except Exception as session_error:
                    logger.warning(f"⚠️ [CLEANUP] Błąd przetwarzania session {session_doc.id}: {session_error}")
                    continue
            
            if cleaned_count > 0:
                logger.info(f"🧹 [CLEANUP] ✅ SUKCES: Wyczyszczono {cleaned_count} zombie sessions")
                for zombie in zombie_sessions:
                    logger.info(f"🧹 [CLEANUP]   - {zombie['session_id']}: zakończone {zombie['charging_end']}, przeterminowane o {zombie['hours_overdue']}h")
            else:
                logger.info(f"🧹 [CLEANUP] ✅ Brak zombie sessions - wszystkie aktywne sessions są aktualne")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"❌ [CLEANUP] Krytyczny błąd czyszczenia sessions: {e}")
            return 0

class CloudTeslaWorker:
    """
    Główna klasa Worker Service - zarządza HTTP serverem i instancją monitora
    """
    
    def __init__(self):
        self.server = None
        self.server_thread = None
        self.monitor = None
        self._setup_worker()
    
    def _setup_worker(self):
        """Konfiguruje Worker Service"""
        try:
            logger.info("⚙️ [WORKER] Inicjalizacja Worker Service...")
            
            # Utwórz instancję CloudTeslaMonitor
            self.monitor = CloudTeslaMonitor()
            logger.info("✅ [WORKER] CloudTeslaMonitor zainicjalizowany")
            
        except Exception as e:
            logger.error(f"❌ [WORKER] Błąd inicjalizacji: {e}")
            raise
    
    def start_worker_service(self):
        """Uruchamia Worker Service HTTP server"""
        try:
            port = int(os.getenv('PORT', 8080))
            
            logger.info(f"🚀 [WORKER] Uruchamianie Worker Service na porcie {port}")
            
            # Utwórz handler z referencjami do monitor i worker
            def handler_factory(*args, **kwargs):
                return WorkerHealthCheckHandler(self.monitor, self, *args, **kwargs)
            
            self.server = HTTPServer(('', port), handler_factory)
            
            logger.info("✅ [WORKER] Worker Service uruchomiony pomyślnie")
            logger.info(f"🔗 [WORKER] Dostępne endpointy:")
            logger.info(f"   GET  /health - Health check")
            logger.info(f"   GET  /worker-status - Szczegółowy status")
            logger.info(f"   GET  /get-token - Token Tesla API dla Scout")
            logger.info(f"   POST /run-cycle - Wykonaj cykl monitorowania")
            logger.info(f"   POST /scout-trigger - Obsłuż wywołanie od Scout")
            logger.info(f"   POST /refresh-tokens - Odśwież tokeny Tesla")
            logger.info(f"   POST /daily-special-charging-check - Daily special charging check")
            logger.info(f"   POST /send-special-schedule-immediate - TESTOWY: Natychmiastowe wysłanie harmonogramu")
            logger.info("")
            logger.info("🎯 [WORKER] Worker Service gotowy do obsługi żądań od Scout Function")
            
            # Uruchom server (blokuje)
            self.server.serve_forever()
            
        except Exception as e:
            logger.error(f"❌ [WORKER] Błąd uruchamiania Worker Service: {e}")
            raise
    
    def stop_worker_service(self):
        """Zatrzymuje Worker Service"""
        try:
            if self.server:
                logger.info("🛑 [WORKER] Zatrzymywanie Worker Service...")
                self.server.shutdown()
                self.server.server_close()
                logger.info("✅ [WORKER] Worker Service zatrzymany")
                
        except Exception as e:
            logger.error(f"❌ [WORKER] Błąd zatrzymywania Worker Service: {e}")
    
    def _ensure_centralized_tokens(self) -> bool:
        """
        Zapewnia aktualne tokeny w centralnym miejscu (fleet-tokens)
        
        KROK 1: Sprawdź fleet-tokens 
        KROK 2: Jeśli wygasłe/brak -> spróbuj odświeżyć
        KROK 3: Jeśli odświeżanie nie działa -> migruj z legacy sekretów
        KROK 4: Zapisz aktualne tokeny do fleet-tokens
        
        Returns:
            bool: True jeśli tokeny są dostępne i ważne
        """
        try:
            warsaw_time = self.monitor._get_warsaw_time()
            time_str = warsaw_time.strftime("[%H:%M]")
            
            logger.info(f"{time_str} 🔐 [WORKER] Zapewnianie aktualnych tokenów Tesla w centralnym miejscu...")
            
            # Sprawdź czy TeslaFleetAPIClient jest zainicjalizowany
            if not self.monitor.tesla_controller.fleet_api:
                logger.error(f"{time_str} ❌ [WORKER] TeslaFleetAPIClient nie jest zainicjalizowany")
                return False
            
            # KROK 1: Spróbuj załadować tokeny z fleet-tokens
            logger.info(f"{time_str} 🔄 [WORKER] KROK 1: Sprawdzanie tokenów w fleet-tokens...")
            if self.monitor.tesla_controller.fleet_api._load_from_secret_manager():
                if self.monitor.tesla_controller.fleet_api._are_tokens_valid():
                    logger.info(f"{time_str} ✅ [WORKER] Tokeny w fleet-tokens są ważne")
                    return True
                else:
                    logger.warning(f"{time_str} ⚠️ [WORKER] Tokeny w fleet-tokens są nieważne lub wygasłe")
            else:
                logger.warning(f"{time_str} ⚠️ [WORKER] Nie można załadować tokenów z fleet-tokens")
            
            # KROK 2: Spróbuj odświeżyć tokeny jeśli mamy refresh token
            if self.monitor.tesla_controller.fleet_api.refresh_token:
                logger.info(f"{time_str} 🔄 [WORKER] KROK 2: Próba odświeżenia tokenów...")
                if self.monitor.tesla_controller.fleet_api._refresh_access_token():
                    logger.info(f"{time_str} ✅ [WORKER] Tokeny odświeżone pomyślnie")
                    # Tokeny automatycznie zapisane w _refresh_access_token
                    logger.info(f"{time_str} ✅ [WORKER] Tokeny zapisane do fleet-tokens")
                    return True
                else:
                    logger.warning(f"{time_str} ⚠️ [WORKER] Nie udało się odświeżyć tokenów")
            
            # KROK 3: Migracja z legacy sekretów
            logger.info(f"{time_str} 🔄 [WORKER] KROK 3: Próba migracji z legacy sekretów...")
            if self.monitor.tesla_controller.fleet_api._migrate_from_legacy_tokens():
                logger.info(f"{time_str} ✅ [WORKER] Migracja z legacy sekretów udana")
                # Tokeny automatycznie zapisane w _migrate_from_legacy_tokens
                logger.info(f"{time_str} ✅ [WORKER] Zmigrowane tokeny zapisane do fleet-tokens")
                return True
            else:
                logger.error(f"{time_str} ❌ [WORKER] Migracja z legacy sekretów nie udana")
            
            # KROK 4: Ostateczna weryfikacja
            logger.error(f"{time_str} ❌ [WORKER] Nie można zapewnić ważnych tokenów Tesla")
            logger.error(f"{time_str} 💡 [WORKER] Wymagane działania:")
            logger.error(f"{time_str}    1. Sprawdź sekrety w Google Secret Manager")
            logger.error(f"{time_str}    2. Uruchom: python3 generate_token.py") 
            logger.error(f"{time_str}    3. Sprawdź uprawnienia Google Cloud IAM")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ [WORKER] Błąd zapewniania tokenów Tesla: {e}")
            logger.error(f"❌ [WORKER] Exception type: {type(e).__name__}")
            logger.error(f"❌ [WORKER] Exception details: {str(e)}")
            return False

def main():
    """Główna funkcja Worker Service"""
    
    # Sprawdź czy to Worker mode
    worker_mode = os.getenv('TESLA_WORKER_MODE', 'true').lower() == 'true'
    if not worker_mode:
        logger.error("❌ TESLA_WORKER_MODE nie jest ustawiony na 'true'")
        logger.info("💡 To jest Worker Service - ustaw TESLA_WORKER_MODE=true")
        sys.exit(1)
    
    # Sprawdź kluczowe zmienne środowiskowe
    required_vars = ['GOOGLE_CLOUD_PROJECT']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Brak wymaganych zmiennych środowiskowych: {missing_vars}")
        sys.exit(1)
    
    # TESLA_CLIENT_ID jest w Google Secret Manager, nie w env vars
    logger.info("ℹ️ Tesla credentials pobierane z Google Secret Manager")
    
    logger.info("🔧 === TESLA WORKER SERVICE (SCOUT & WORKER ARCHITECTURE) ===")
    logger.info("💰 Agresywna optymalizacja kosztów: Worker uruchamiany on-demand")
    logger.info("🔍 Scout Function sprawdza lokalizację -> Worker wykonuje pełną logikę")
    logger.info("")
    
    # Obsługa sygnałów
    worker = CloudTeslaWorker()
    
    def signal_handler(signum, frame):
        logger.info(f"🛑 Otrzymano sygnał {signum} - zatrzymywanie Worker Service")
        worker.stop_worker_service()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        worker.start_worker_service()
    except Exception as e:
        logger.error(f"💥 Krytyczny błąd Worker Service: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 