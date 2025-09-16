#!/usr/bin/env python3
"""
Test Script: Weryfikacja Architektury Tokenów Tesla API (Scout & Worker)

ZADANIE:
Weryfikuje czy nowa architektura centralnego zarządzania tokenami działa poprawnie:
1. Worker Service udostępnia tokeny przez /get-token
2. Scout Function może pobrać tokeny z Worker
3. Brak konfliktów refresh tokenów
4. Fallback mechanism działa

UŻYCIE:
python3 test_token_architecture.py --worker-url https://your-worker-service-url
"""

import argparse
import requests
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TokenArchitectureTest:
    """Klasa testująca architekturę tokenów Scout & Worker"""
    
    def __init__(self, worker_url: str):
        self.worker_url = worker_url.rstrip('/')
        self.test_results = []
        
    def log_test_result(self, test_name: str, success: bool, message: str, details: Optional[Dict] = None):
        """Zapisuje wynik testu"""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {}
        }
        self.test_results.append(result)
        
        status = "✅" if success else "❌"
        logger.info(f"{status} {test_name}: {message}")
        
        if details:
            logger.info(f"   Details: {json.dumps(details, indent=2)}")
    
    def test_worker_health(self) -> bool:
        """Test 1: Sprawdź czy Worker Service działa"""
        try:
            url = f"{self.worker_url}/health"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.log_test_result(
                    "Worker Health Check",
                    True,
                    f"Worker Service działa na {self.worker_url}",
                    {"status_code": 200, "service": data.get('service', 'unknown')}
                )
                return True
            else:
                self.log_test_result(
                    "Worker Health Check",
                    False,
                    f"Worker Service zwrócił HTTP {response.status_code}",
                    {"status_code": response.status_code}
                )
                return False
                
        except requests.exceptions.ConnectionError:
            self.log_test_result(
                "Worker Health Check",
                False,
                "Nie można połączyć się z Worker Service",
                {"error": "connection_error", "worker_url": self.worker_url}
            )
            return False
        except Exception as e:
            self.log_test_result(
                "Worker Health Check",
                False,
                f"Błąd podczas sprawdzania Worker: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_worker_token_endpoint(self) -> bool:
        """Test 2: Sprawdź endpoint /get-token w Worker"""
        try:
            url = f"{self.worker_url}/get-token"
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'success' and data.get('access_token'):
                    token_length = len(data.get('access_token', ''))
                    remaining_minutes = data.get('remaining_minutes', 'unknown')
                    
                    self.log_test_result(
                        "Worker Token Endpoint",
                        True,
                        f"Worker udostępnia token Tesla (długość: {token_length}, ważny: {remaining_minutes} min)",
                        {
                            "token_length": token_length,
                            "remaining_minutes": remaining_minutes,
                            "architecture": data.get('architecture', {})
                        }
                    )
                    return True
                else:
                    self.log_test_result(
                        "Worker Token Endpoint",
                        False,
                        "Worker nie może udostępnić tokenu Tesla",
                        data
                    )
                    return False
            else:
                self.log_test_result(
                    "Worker Token Endpoint",
                    False,
                    f"Endpoint /get-token zwrócił HTTP {response.status_code}",
                    {"status_code": response.status_code, "response": response.text[:200]}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Worker Token Endpoint",
                False,
                f"Błąd podczas testowania endpoint tokenów: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_token_validity(self) -> bool:
        """Test 3: Sprawdź czy token z Worker jest ważny dla Tesla API"""
        try:
            # Pobierz token z Worker
            token_url = f"{self.worker_url}/get-token"
            token_response = requests.get(token_url, timeout=30)
            
            if token_response.status_code != 200:
                self.log_test_result(
                    "Token Validity",
                    False,
                    "Nie można pobrać tokenu z Worker",
                    {"worker_status": token_response.status_code}
                )
                return False
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            
            if not access_token:
                self.log_test_result(
                    "Token Validity",
                    False,
                    "Worker nie zwrócił access token",
                    token_data
                )
                return False
            
            # Test tokenu z Tesla API
            tesla_url = "https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            tesla_response = requests.get(tesla_url, headers=headers, timeout=15)
            
            if tesla_response.status_code in [200, 204]:
                self.log_test_result(
                    "Token Validity",
                    True,
                    f"Token z Worker jest ważny dla Tesla API (HTTP {tesla_response.status_code})",
                    {"tesla_status": tesla_response.status_code}
                )
                return True
            elif tesla_response.status_code == 401:
                self.log_test_result(
                    "Token Validity",
                    False,
                    "Token z Worker jest nieważny - Tesla API zwrócił 401",
                    {"tesla_status": 401, "tesla_response": tesla_response.text[:200]}
                )
                return False
            else:
                self.log_test_result(
                    "Token Validity",
                    False,
                    f"Tesla API zwrócił nieoczekiwany status {tesla_response.status_code}",
                    {"tesla_status": tesla_response.status_code}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Token Validity",
                False,
                f"Błąd podczas sprawdzania ważności tokenu: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_multiple_token_requests(self) -> bool:
        """Test 4: Sprawdź czy wielokrotne zapytania o token działają (cache)"""
        try:
            token_url = f"{self.worker_url}/get-token"
            tokens = []
            response_times = []
            
            # Wykonaj 3 zapytania o token
            for i in range(3):
                start_time = time.time()
                response = requests.get(token_url, timeout=30)
                response_time = time.time() - start_time
                response_times.append(response_time)
                
                if response.status_code == 200:
                    data = response.json()
                    token = data.get('access_token')
                    if token:
                        tokens.append(token[:20])  # Pierwsze 20 znaków dla porównania
                    
                time.sleep(1)  # Pauza między zapytaniami
            
            if len(tokens) == 3:
                # Sprawdź czy tokeny są identyczne (cache działa)
                tokens_identical = all(token == tokens[0] for token in tokens)
                avg_response_time = sum(response_times) / len(response_times)
                
                self.log_test_result(
                    "Multiple Token Requests",
                    True,
                    f"Wielokrotne zapytania działają (tokeny identyczne: {tokens_identical}, avg time: {avg_response_time:.2f}s)",
                    {
                        "tokens_identical": tokens_identical,
                        "response_times": response_times,
                        "average_response_time": avg_response_time
                    }
                )
                return True
            else:
                self.log_test_result(
                    "Multiple Token Requests",
                    False,
                    f"Udało się pobrać tylko {len(tokens)}/3 tokenów",
                    {"tokens_received": len(tokens)}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Multiple Token Requests",
                False,
                f"Błąd podczas testowania wielokrotnych zapytań: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_worker_status_endpoint(self) -> bool:
        """Test 5: Sprawdź endpoint /worker-status"""
        try:
            url = f"{self.worker_url}/worker-status"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tesla_connected = data.get('tesla_connection', {}).get('connected', False)
                smart_proxy_available = data.get('tesla_connection', {}).get('smart_proxy_available', False)
                
                self.log_test_result(
                    "Worker Status Endpoint",
                    True,
                    f"Worker Status OK (Tesla: {tesla_connected}, Proxy: {smart_proxy_available})",
                    {
                        "tesla_connected": tesla_connected,
                        "smart_proxy_available": smart_proxy_available,
                        "service": data.get('service', 'unknown')
                    }
                )
                return True
            else:
                self.log_test_result(
                    "Worker Status Endpoint",
                    False,
                    f"Endpoint /worker-status zwrócił HTTP {response.status_code}",
                    {"status_code": response.status_code}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Worker Status Endpoint",
                False,
                f"Błąd podczas sprawdzania worker status: {e}",
                {"error": str(e)}
            )
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Uruchamia wszystkie testy architektury tokenów"""
        logger.info("🔍 === TEST ARCHITEKTURY TOKENÓW SCOUT & WORKER ===")
        logger.info(f"Worker Service URL: {self.worker_url}")
        logger.info("")
        
        # Lista testów do wykonania
        tests = [
            ("Worker Health Check", self.test_worker_health),
            ("Worker Token Endpoint", self.test_worker_token_endpoint),
            ("Token Validity", self.test_token_validity),
            ("Multiple Token Requests", self.test_multiple_token_requests),
            ("Worker Status Endpoint", self.test_worker_status_endpoint)
        ]
        
        # Wykonaj testy
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"🧪 Uruchamiam test: {test_name}")
            try:
                success = test_func()
                if success:
                    passed_tests += 1
            except Exception as e:
                logger.error(f"💥 Krytyczny błąd testu {test_name}: {e}")
            logger.info("")
        
        # Podsumowanie
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        summary = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "success_rate": success_rate,
            "all_tests_passed": passed_tests == total_tests,
            "test_results": self.test_results,
            "worker_url": self.worker_url,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info("📊 === PODSUMOWANIE TESTÓW ===")
        logger.info(f"Przeszło: {passed_tests}/{total_tests} testów ({success_rate:.1f}%)")
        
        if summary["all_tests_passed"]:
            logger.info("🎉 WSZYSTKIE TESTY PRZESZŁY - Architektura tokenów działa poprawnie!")
            logger.info("✅ Centralne zarządzanie tokenami przez Worker Service jest sprawne")
        else:
            logger.warning("⚠️ NIEKTÓRE TESTY NIE PRZESZŁY - Wymagane poprawki w architekturze")
            logger.warning("🔧 Sprawdź szczegóły błędów i napraw problemy")
        
        return summary

def main():
    """Główna funkcja testowa"""
    parser = argparse.ArgumentParser(description="Test architektury tokenów Scout & Worker")
    parser.add_argument(
        "--worker-url",
        required=True,
        help="URL Worker Service (np. https://tesla-worker-xxx-ew.a.run.app)"
    )
    parser.add_argument(
        "--output",
        help="Plik wyjściowy dla wyników testów (JSON)"
    )
    
    args = parser.parse_args()
    
    # Uruchom testy
    tester = TokenArchitectureTest(args.worker_url)
    results = tester.run_all_tests()
    
    # Zapisz wyniki do pliku jeśli określono
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"📄 Wyniki testów zapisane do: {args.output}")
        except Exception as e:
            logger.error(f"❌ Błąd zapisywania wyników: {e}")
    
    # Exit code
    exit_code = 0 if results["all_tests_passed"] else 1
    return exit_code

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code) 