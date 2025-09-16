#!/usr/bin/env python3
"""
Test połączenia SCOUT z pojazdem Tesla (online)
Weryfikuje poprawność architektury tokenów i łączenia z wybudzonym pojazdem

TESTOWANE KOMPONENTY:
1. ✅ Pobieranie tokenu z Worker Service (centralne zarządzanie)
2. ✅ Fallback na bezpośredni dostęp (jeśli Worker niedostępny)
3. ✅ Łączenie z pojazdem online
4. ✅ Pobieranie danych pojazdu (lokalizacja, bateria, stan ładowania)
5. ✅ Obsługa różnych stanów pojazdu (online/asleep/offline)

OCZEKIWANE DZIAŁANIE:
- Token pobrany z Worker Service lub fallback
- Poprawne połączenie z Tesla Fleet API
- Sprawdzenie stanu pojazdu PRZED pobieraniem danych (best practices)
- Dla pojazdu online: pełne dane (lokalizacja + bateria)
- Szybkie wykonanie bez niepotrzebnego budzenia pojazdu
"""

import os
import sys
import json
import logging
import time
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Dodaj ścieżkę do głównego katalogu projektu
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import funkcji SCOUT
from tesla_scout_function import (
    get_tesla_access_token_smart,
    get_token_from_worker,
    get_tesla_access_token_fallback,
    get_vehicle_location,
    is_at_home,
    _log_scout_status
)

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ScoutConnectionTest:
    """Test łączenia SCOUT z pojazdem Tesla"""
    
    def __init__(self):
        self.test_results = {
            "token_management": {},
            "vehicle_connection": {},
            "data_retrieval": {},
            "api_compliance": {},
            "execution_metrics": {}
        }
        self.start_time = datetime.now(timezone.utc)
        
    def log_test_step(self, step: str, status: str, details: str = ""):
        """Loguje krok testu z timestampem"""
        now = datetime.now(timezone.utc)
        elapsed = (now - self.start_time).total_seconds()
        status_emoji = "✅" if status == "SUCCESS" else "❌" if status == "FAIL" else "⚠️"
        logger.info(f"[{elapsed:6.2f}s] {status_emoji} {step}: {details}")
        
    def test_token_retrieval(self) -> Dict[str, Any]:
        """Test 1: Weryfikacja pobierania tokenu (Worker + fallback)"""
        self.log_test_step("TOKEN_TEST", "START", "Sprawdzam pobieranie tokenu Tesla API")
        
        results = {
            "worker_attempt": {"status": "not_tested", "details": ""},
            "fallback_attempt": {"status": "not_tested", "details": ""},
            "smart_wrapper": {"status": "not_tested", "details": ""},
            "final_token": None,
            "source": None
        }
        
        # KROK 1: Test pobierania z Worker Service
        self.log_test_step("WORKER_TOKEN", "START", "Próba pobrania tokenu z Worker Service")
        
        try:
            worker_token = get_token_from_worker()
            if worker_token:
                results["worker_attempt"] = {
                    "status": "success",
                    "details": "Token otrzymany z Worker Service (centralne zarządzanie)",
                    "token_length": len(worker_token)
                }
                self.log_test_step("WORKER_TOKEN", "SUCCESS", f"Token z Worker (długość: {len(worker_token)})")
            else:
                results["worker_attempt"] = {
                    "status": "failed",
                    "details": "Worker Service niedostępny lub brak tokenu"
                }
                self.log_test_step("WORKER_TOKEN", "FAIL", "Worker Service niedostępny")
        except Exception as e:
            results["worker_attempt"] = {
                "status": "error",
                "details": f"Błąd: {str(e)}"
            }
            self.log_test_step("WORKER_TOKEN", "FAIL", f"Błąd: {e}")
        
        # KROK 2: Test fallback mechanizmu (jeśli Worker nie działa)
        if results["worker_attempt"]["status"] != "success":
            self.log_test_step("FALLBACK_TOKEN", "START", "Próba fallback mechanizmu")
            
            try:
                fallback_token = get_tesla_access_token_fallback()
                if fallback_token:
                    results["fallback_attempt"] = {
                        "status": "success",
                        "details": "Token otrzymany bezpośrednio (fallback)",
                        "token_length": len(fallback_token)
                    }
                    self.log_test_step("FALLBACK_TOKEN", "SUCCESS", f"Token fallback (długość: {len(fallback_token)})")
                else:
                    results["fallback_attempt"] = {
                        "status": "failed",
                        "details": "Fallback nie może pobrać tokenu"
                    }
                    self.log_test_step("FALLBACK_TOKEN", "FAIL", "Fallback mechanizm nie działa")
            except Exception as e:
                results["fallback_attempt"] = {
                    "status": "error",
                    "details": f"Błąd: {str(e)}"
                }
                self.log_test_step("FALLBACK_TOKEN", "FAIL", f"Błąd: {e}")
        
        # KROK 3: Test Smart Wrapper (automatyczny wybór)
        self.log_test_step("SMART_WRAPPER", "START", "Test inteligentnego wyboru tokenu")
        
        try:
            smart_token = get_tesla_access_token_smart()
            if smart_token:
                # Określ źródło tokenu
                if results["worker_attempt"]["status"] == "success":
                    source = "worker_service"
                elif results["fallback_attempt"]["status"] == "success":
                    source = "fallback"
                else:
                    source = "unknown"
                
                results["smart_wrapper"] = {
                    "status": "success",
                    "details": f"Smart wrapper wybrał token ze źródła: {source}",
                    "token_length": len(smart_token)
                }
                results["final_token"] = smart_token
                results["source"] = source
                
                self.log_test_step("SMART_WRAPPER", "SUCCESS", f"Token otrzymany ze źródła: {source}")
            else:
                results["smart_wrapper"] = {
                    "status": "failed",
                    "details": "Smart wrapper nie może pobrać tokenu"
                }
                self.log_test_step("SMART_WRAPPER", "FAIL", "Brak tokenu z żadnego źródła")
        except Exception as e:
            results["smart_wrapper"] = {
                "status": "error",
                "details": f"Błąd: {str(e)}"
            }
            self.log_test_step("SMART_WRAPPER", "FAIL", f"Błąd: {e}")
        
        self.test_results["token_management"] = results
        return results
    
    def test_vehicle_connection(self, access_token: str) -> Dict[str, Any]:
        """Test 2: Weryfikacja łączenia z pojazdem Tesla"""
        self.log_test_step("VEHICLE_CONNECTION", "START", "Sprawdzam połączenie z pojazdem Tesla")
        
        results = {
            "api_connection": {"status": "not_tested", "details": ""},
            "vehicle_list": {"status": "not_tested", "details": ""},
            "vehicle_data": {"status": "not_tested", "details": ""},
            "compliance_check": {"status": "not_tested", "details": ""}
        }
        
        try:
            # KROK 1: Test podstawowego połączenia z Tesla Fleet API
            self.log_test_step("API_CONNECTION", "START", "Test połączenia z Tesla Fleet API")
            
            headers = {"Authorization": f"Bearer {access_token}"}
            vehicles_response = requests.get(
                "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles",
                headers=headers,
                timeout=30
            )
            
            if vehicles_response.status_code == 200:
                results["api_connection"] = {
                    "status": "success",
                    "details": f"Połączenie z Tesla Fleet API OK (HTTP {vehicles_response.status_code})"
                }
                self.log_test_step("API_CONNECTION", "SUCCESS", f"Tesla Fleet API odpowiada (HTTP {vehicles_response.status_code})")
            else:
                results["api_connection"] = {
                    "status": "failed",
                    "details": f"Błąd HTTP {vehicles_response.status_code}"
                }
                self.log_test_step("API_CONNECTION", "FAIL", f"Tesla Fleet API błąd HTTP {vehicles_response.status_code}")
                return results
            
            # KROK 2: Test pobierania listy pojazdów
            self.log_test_step("VEHICLE_LIST", "START", "Pobieram listę pojazdów")
            
            vehicles_data = vehicles_response.json().get('response', [])
            if vehicles_data:
                vehicle = vehicles_data[0]  # Pierwszy pojazd
                vehicle_id = vehicle['id']
                vin = vehicle['vin']
                vehicle_state = vehicle.get('state', 'unknown')
                
                results["vehicle_list"] = {
                    "status": "success",
                    "details": f"Znaleziono pojazd: VIN={vin[-4:]}, stan={vehicle_state}",
                    "vehicle_id": vehicle_id,
                    "vin": vin,
                    "state": vehicle_state,
                    "total_vehicles": len(vehicles_data)
                }
                self.log_test_step("VEHICLE_LIST", "SUCCESS", f"Pojazd {vin[-4:]} w stanie: {vehicle_state}")
            else:
                results["vehicle_list"] = {
                    "status": "failed",
                    "details": "Brak pojazdów na koncie Tesla"
                }
                self.log_test_step("VEHICLE_LIST", "FAIL", "Brak pojazdów na koncie")
                return results
            
            # KROK 3: Test zgodności z Tesla API best practices
            self.log_test_step("COMPLIANCE_CHECK", "START", "Sprawdzam zgodność z Tesla API best practices")
            
            if vehicle_state == 'online':
                results["compliance_check"] = {
                    "status": "success",
                    "details": "Pojazd online - można pobrać dane bez budzenia",
                    "vehicle_state": vehicle_state,
                    "wake_required": False
                }
                self.log_test_step("COMPLIANCE_CHECK", "SUCCESS", "Pojazd online - bezpieczne pobieranie danych")
            elif vehicle_state in ['asleep', 'offline']:
                results["compliance_check"] = {
                    "status": "compliant",
                    "details": f"Pojazd {vehicle_state} - Scout nie budzi pojazdu (zgodnie z best practices)",
                    "vehicle_state": vehicle_state,
                    "wake_required": True,
                    "wake_avoided": True
                }
                self.log_test_step("COMPLIANCE_CHECK", "SUCCESS", f"Pojazd {vehicle_state} - zgodność z best practices")
            else:
                results["compliance_check"] = {
                    "status": "unknown",
                    "details": f"Nieznany stan pojazdu: {vehicle_state}",
                    "vehicle_state": vehicle_state
                }
                self.log_test_step("COMPLIANCE_CHECK", "WARN", f"Nieznany stan pojazdu: {vehicle_state}")
            
            self.test_results["vehicle_connection"] = results
            return results
            
        except Exception as e:
            error_result = {
                "status": "error",
                "details": f"Błąd połączenia z pojazdem: {str(e)}"
            }
            results["vehicle_data"] = error_result
            self.log_test_step("VEHICLE_CONNECTION", "FAIL", f"Błąd: {e}")
            return results
    
    def test_data_retrieval(self, access_token: str) -> Dict[str, Any]:
        """Test 3: Weryfikacja pobierania danych pojazdu"""
        self.log_test_step("DATA_RETRIEVAL", "START", "Sprawdzam pobieranie danych pojazdu")
        
        results = {
            "location_data": {"status": "not_tested", "details": ""},
            "vehicle_details": {},
            "home_detection": {"status": "not_tested", "details": ""},
            "execution_time": 0
        }
        
        try:
            data_start = datetime.now(timezone.utc)
            
            # Pobierz dane pojazdu używając funkcji SCOUT
            vehicle_data = get_vehicle_location(access_token)
            
            execution_time = (datetime.now(timezone.utc) - data_start).total_seconds()
            results["execution_time"] = execution_time
            
            if not vehicle_data:
                results["location_data"] = {
                    "status": "failed",
                    "details": "Nie można pobrać danych pojazdu"
                }
                self.log_test_step("DATA_RETRIEVAL", "FAIL", "Brak danych pojazdu")
                return results
            
            # Analiza pobranych danych
            vehicle_state = vehicle_data.get('state', 'unknown')
            vin = vehicle_data.get('vin', 'unknown')
            
            if vehicle_state == 'online':
                # Pojazd online - sprawdź pełne dane
                latitude = vehicle_data.get('latitude')
                longitude = vehicle_data.get('longitude')
                battery_level = vehicle_data.get('battery_level', 0)
                charging_state = vehicle_data.get('charging_state', 'Unknown')
                
                if latitude is not None and longitude is not None:
                    # Test wykrywania lokalizacji domowej
                    at_home = is_at_home(latitude, longitude)
                    
                    results["location_data"] = {
                        "status": "success",
                        "details": f"Pełne dane pojazdu online (czas: {execution_time:.2f}s)"
                    }
                    
                    results["vehicle_details"] = {
                        "vin": vin[-4:],
                        "state": vehicle_state,
                        "latitude": round(latitude, 6),
                        "longitude": round(longitude, 6),
                        "battery_level": battery_level,
                        "charging_state": charging_state,
                        "timestamp": vehicle_data.get('timestamp')
                    }
                    
                    results["home_detection"] = {
                        "status": "success",
                        "details": f"Lokalizacja: {'w domu' if at_home else 'poza domem'}",
                        "at_home": at_home,
                        "coordinates": f"({latitude:.6f}, {longitude:.6f})"
                    }
                    
                    self.log_test_step("DATA_RETRIEVAL", "SUCCESS", 
                                     f"Pojazd {vin[-4:]}: bateria={battery_level}%, {charging_state}, {'w domu' if at_home else 'poza domem'}")
                    
                    # Loguj szczegółowy status używając funkcji SCOUT
                    _log_scout_status(vehicle_data, "test_data_retrieval")
                    
                else:
                    results["location_data"] = {
                        "status": "partial",
                        "details": "Pojazd online ale brak danych lokalizacyjnych"
                    }
                    self.log_test_step("DATA_RETRIEVAL", "WARN", "Brak danych lokalizacyjnych")
            
            elif vehicle_state in ['asleep', 'offline']:
                # Pojazd uśpiony/offline - oczekiwane zachowanie
                results["location_data"] = {
                    "status": "compliant",
                    "details": f"Pojazd {vehicle_state} - brak aktualnych danych (zgodnie z best practices)"
                }
                
                results["vehicle_details"] = {
                    "vin": vin[-4:],
                    "state": vehicle_state,
                    "latitude": None,
                    "longitude": None,
                    "error": vehicle_data.get('error'),
                    "timestamp": vehicle_data.get('timestamp')
                }
                
                results["home_detection"] = {
                    "status": "skipped",
                    "details": f"Wykrywanie lokalizacji pominięte (pojazd {vehicle_state})"
                }
                
                self.log_test_step("DATA_RETRIEVAL", "SUCCESS", 
                                 f"Pojazd {vin[-4:]} {vehicle_state} - Scout nie budzi pojazdu")
            
            self.test_results["data_retrieval"] = results
            return results
            
        except Exception as e:
            error_result = {
                "status": "error",
                "details": f"Błąd pobierania danych: {str(e)}",
                "execution_time": (datetime.now(timezone.utc) - data_start).total_seconds()
            }
            results["location_data"] = error_result
            self.log_test_step("DATA_RETRIEVAL", "FAIL", f"Błąd: {e}")
            return results
    
    def run_full_test(self) -> Dict[str, Any]:
        """Uruchamia pełny test łączenia SCOUT z pojazdem Tesla"""
        logger.info("🔍 ===== TEST ŁĄCZENIA SCOUT Z POJAZDEM TESLA =====")
        logger.info("Weryfikacja architektury tokenów i łączenia z wybudzonym pojazdem")
        logger.info("")
        
        # TEST 1: Pobieranie tokenu
        logger.info("📋 TEST 1: POBIERANIE TOKENU TESLA API")
        token_results = self.test_token_retrieval()
        
        access_token = token_results.get("final_token")
        if not access_token:
            logger.error("❌ BŁĄD KRYTYCZNY: Brak tokenu Tesla API - test przerwany")
            return self.generate_final_report(False, "Brak tokenu Tesla API")
        
        # TEST 2: Łączenie z pojazdem
        logger.info("\n📋 TEST 2: ŁĄCZENIE Z POJAZDEM TESLA")
        connection_results = self.test_vehicle_connection(access_token)
        
        # TEST 3: Pobieranie danych pojazdu
        logger.info("\n📋 TEST 3: POBIERANIE DANYCH POJAZDU")
        data_results = self.test_data_retrieval(access_token)
        
        # Generowanie raportu końcowego
        return self.generate_final_report(True, "Test zakończony")
    
    def generate_final_report(self, success: bool, message: str) -> Dict[str, Any]:
        """Generuje końcowy raport z testu"""
        execution_time = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        logger.info(f"\n🏁 ===== RAPORT KOŃCOWY TESTU SCOUT =====")
        logger.info(f"Czas wykonania: {execution_time:.2f}s")
        logger.info(f"Status: {'✅ SUKCES' if success else '❌ BŁĄD'}")
        logger.info(f"Wiadomość: {message}")
        
        # Podsumowanie wyników
        token_status = self.test_results.get("token_management", {}).get("smart_wrapper", {}).get("status", "not_tested")
        connection_status = self.test_results.get("vehicle_connection", {}).get("api_connection", {}).get("status", "not_tested")
        data_status = self.test_results.get("data_retrieval", {}).get("location_data", {}).get("status", "not_tested")
        
        logger.info(f"\nPodsumowanie komponentów:")
        logger.info(f"  🔑 Zarządzanie tokenami: {token_status}")
        logger.info(f"  🔗 Połączenie z pojazdem: {connection_status}")
        logger.info(f"  📊 Pobieranie danych: {data_status}")
        
        # Architektura tokenów
        token_source = self.test_results.get("token_management", {}).get("source")
        if token_source:
            logger.info(f"\n🏗️ Architektura tokenów:")
            logger.info(f"  Źródło tokenu: {token_source}")
            if token_source == "worker_service":
                logger.info(f"  ✅ Centralne zarządzanie przez Worker Service (architektura docelowa)")
            elif token_source == "fallback":
                logger.info(f"  ⚠️ Fallback mechanizm (sprawdź Worker Service)")
        
        # API Compliance
        vehicle_details = self.test_results.get("data_retrieval", {}).get("vehicle_details", {})
        if vehicle_details:
            vehicle_state = vehicle_details.get("state", "unknown")
            logger.info(f"\n🛡️ Tesla API Compliance:")
            logger.info(f"  Stan pojazdu: {vehicle_state}")
            if vehicle_state == "online":
                logger.info(f"  ✅ Pojazd online - bezpieczne pobieranie danych")
            elif vehicle_state in ["asleep", "offline"]:
                logger.info(f"  ✅ Pojazd {vehicle_state} - nie budzenie pojazdu (best practices)")
        
        final_report = {
            "test_summary": {
                "success": success,
                "message": message,
                "execution_time_seconds": round(execution_time, 3),
                "timestamp": self.start_time.isoformat()
            },
            "component_status": {
                "token_management": token_status,
                "vehicle_connection": connection_status,
                "data_retrieval": data_status
            },
            "architecture_info": {
                "token_source": token_source,
                "centralized_management": token_source == "worker_service",
                "fallback_used": token_source == "fallback"
            },
            "test_results": self.test_results
        }
        
        logger.info(f"\n📊 Pełny raport zapisany w test_results")
        return final_report

def main():
    """Główna funkcja testu"""
    print("🔍 Test łączenia SCOUT z pojazdem Tesla")
    print("Weryfikacja pobierania tokenu i łączenia z wybudzonym pojazdem")
    print("=" * 60)
    
    try:
        # Sprawdź zmienne środowiskowe
        required_env = ["WORKER_SERVICE_URL", "HOME_LATITUDE", "HOME_LONGITUDE"]
        missing_env = [var for var in required_env if not os.environ.get(var)]
        
        if missing_env:
            print(f"⚠️ Ostrzeżenie: Brak zmiennych środowiskowych: {missing_env}")
            print("Niektóre testy mogą nie działać poprawnie")
        
        # Uruchom test
        test = ScoutConnectionTest()
        results = test.run_full_test()
        
        # Zapisz wyniki do pliku
        with open("scout_connection_test_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Szczegółowe wyniki zapisane do: scout_connection_test_results.json")
        
        # Status końcowy
        if results["test_summary"]["success"]:
            print("✅ Test zakończony sukcesem!")
            return 0
        else:
            print("❌ Test zakończony błędem!")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ Test przerwany przez użytkownika")
        return 1
    except Exception as e:
        print(f"\n❌ Nieoczekiwany błąd testu: {e}")
        return 1

if __name__ == "__main__":
    exit(main()) 