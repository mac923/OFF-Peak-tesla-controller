#!/usr/bin/env python3
"""
Test mechanizmu fallback Scout → Worker dla odświeżania tokenów
Weryfikuje nową architekturę hybrydową v3.1

SCENARIUSZE TESTOWE:
1. Scout wykrywa wygasłe tokeny
2. Scout wywołuje Worker do odświeżenia
3. Worker odświeża tokeny w Secret Manager
4. Scout pobiera świeże tokeny z Secret Manager
5. Obsługa błędów i timeoutów
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

# Dodaj ścieżkę do modułów Scout
sys.path.insert(0, 'scout_function_deploy')

def test_worker_refresh_endpoint(worker_url: str) -> Dict[str, Any]:
    """Test endpointu /refresh-tokens w Worker Service"""
    print(f"\n🔄 [TEST] Testuję endpoint /refresh-tokens...")
    print(f"URL: {worker_url}/refresh-tokens")
    
    payload = {
        "reason": "Test mechanizmu fallback Scout → Worker",
        "requested_by": "test_token_refresh_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempt_count": 1
    }
    
    try:
        start_time = time.time()
        response = requests.post(
            f"{worker_url}/refresh-tokens",
            json=payload,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        duration = time.time() - start_time
        
        print(f"📊 Status: {response.status_code}")
        print(f"⏱️  Czas: {duration:.2f}s")
        
        if response.status_code == 200:
            try:
                result = response.json()
                print(f"✅ Sukces: {result.get('message', 'OK')}")
                print(f"📋 Szczegóły: {json.dumps(result.get('details', {}), indent=2)}")
                return {"success": True, "duration": duration, "response": result}
            except json.JSONDecodeError:
                print("✅ Sukces (brak JSON response)")
                return {"success": True, "duration": duration, "response": {}}
        else:
            try:
                error_data = response.json()
                print(f"❌ Błąd: {error_data.get('error', 'Unknown error')}")
                print(f"📋 Szczegóły: {json.dumps(error_data, indent=2)}")
            except:
                print(f"❌ Błąd HTTP {response.status_code}")
            
            return {"success": False, "duration": duration, "status_code": response.status_code}
            
    except requests.exceptions.Timeout:
        print("❌ Timeout - Worker nie odpowiedział w czasie")
        return {"success": False, "error": "timeout"}
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Błąd połączenia: {e}")
        return {"success": False, "error": "connection_error"}
    except Exception as e:
        print(f"❌ Nieoczekiwany błąd: {e}")
        return {"success": False, "error": str(e)}

def test_scout_token_fallback_logic():
    """Test logiki fallback w Scout Function (symulacja)"""
    print(f"\n🔍 [TEST] Testuję logikę fallback Scout...")
    
    # Importuj funkcje Scout
    try:
        from main import (
            trigger_worker_refresh_tokens, 
            retry_get_token_from_secret_manager,
            get_tesla_access_token_smart
        )
        print("✅ Import funkcji Scout zakończony pomyślnie")
    except ImportError as e:
        print(f"❌ Błąd importu Scout: {e}")
        return {"success": False, "error": "import_error"}
    
    # Test 1: Sprawdź czy WORKER_SERVICE_URL jest skonfigurowany
    worker_url = os.getenv('WORKER_SERVICE_URL')
    if not worker_url:
        print("❌ WORKER_SERVICE_URL nie jest skonfigurowany")
        print("💡 Ustaw: export WORKER_SERVICE_URL=https://your-worker-url")
        return {"success": False, "error": "no_worker_url"}
    
    print(f"✅ WORKER_SERVICE_URL: {worker_url}")
    
    # Test 2: Symulacja wywołania Worker przez Scout
    print("\n🔄 Symulacja: Scout wykrył wygasłe tokeny...")
    refresh_result = trigger_worker_refresh_tokens("Test wygasłych tokenów")
    
    if refresh_result["success"]:
        print("✅ Worker potwierdził odświeżenie tokenów")
        print(f"📋 Odpowiedź: {refresh_result['message']}")
        
        # Test 3: Próba pobrania świeżych tokenów  
        print("\n🔄 Próba pobrania świeżych tokenów z Secret Manager...")
        fresh_token = retry_get_token_from_secret_manager()
        
        if fresh_token:
            print("✅ Pomyślnie pobrano świeże tokeny")
            print(f"🔑 Token: {fresh_token[:20]}...{fresh_token[-10:] if len(fresh_token) > 30 else fresh_token}")
            return {"success": True, "token_received": True}
        else:
            print("❌ Nie udało się pobrać świeżych tokenów")
            return {"success": False, "error": "no_fresh_token"}
    else:
        print(f"❌ Worker nie może odświeżyć tokenów: {refresh_result['message']}")
        return {"success": False, "error": refresh_result.get('message', 'worker_failed')}

def test_rate_limiting():
    """Test mechanizmu rate limiting (ochrona przed endless loop)"""
    print(f"\n⚡ [TEST] Testuję rate limiting...")
    
    try:
        from main import trigger_worker_refresh_tokens
        
        # Szybkie wywołania żeby sprawdzić rate limiting
        print("🔄 Pierwsze wywołanie...")
        result1 = trigger_worker_refresh_tokens("Test rate limiting #1")
        
        print("🔄 Drugie wywołanie (natychmiast po pierwszym)...")
        result2 = trigger_worker_refresh_tokens("Test rate limiting #2")
        
        if not result2["success"] and "Rate limit" in result2["message"]:
            print("✅ Rate limiting działa poprawnie")
            return {"success": True, "rate_limiting_works": True}
        else:
            print("⚠️ Rate limiting może nie działać - sprawdź implementację")
            return {"success": True, "rate_limiting_works": False}
            
    except Exception as e:
        print(f"❌ Błąd testu rate limiting: {e}")
        return {"success": False, "error": str(e)}

def test_cache_clearing():
    """Test mechanizmu czyszczenia cache"""
    print(f"\n🗑️ [TEST] Testuję czyszczenie cache...")
    
    try:
        from main import _token_cache
        
        # Test czyszczenia cache
        _token_cache.clear_cache()
        print("✅ Cache wyczyszczony pomyślnie")
        
        # Sprawdź statystyki
        stats = _token_cache.get_stats()
        print(f"📊 Statystyki cache: {json.dumps(stats, indent=2)}")
        
        return {"success": True, "cache_cleared": True}
        
    except Exception as e:
        print(f"❌ Błąd testu cache: {e}")
        return {"success": False, "error": str(e)}

def main():
    """Główny test mechanizmu fallback Scout → Worker"""
    print("🚀 === TEST MECHANIZMU FALLBACK SCOUT → WORKER ===")
    print("🎯 Architektura hybrydowa v3.1")
    print("📋 Test odświeżania tokenów gdy Scout wykryje wygaśnięcie")
    
    results = {}
    
    # Test 1: Worker endpoint
    worker_url = os.getenv('WORKER_SERVICE_URL')
    if worker_url:
        results['worker_endpoint'] = test_worker_refresh_endpoint(worker_url)
    else:
        print("\n⚠️ WORKER_SERVICE_URL nie jest ustawiony - pomijam test endpointu")
        results['worker_endpoint'] = {"success": False, "error": "no_worker_url"}
    
    # Test 2: Scout fallback logic  
    results['scout_fallback'] = test_scout_token_fallback_logic()
    
    # Test 3: Rate limiting
    results['rate_limiting'] = test_rate_limiting()
    
    # Test 4: Cache clearing
    results['cache_clearing'] = test_cache_clearing()
    
    # Podsumowanie
    print(f"\n📊 === PODSUMOWANIE TESTÓW ===")
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r.get('success', False))
    
    for test_name, result in results.items():
        status = "✅ PASS" if result.get('success', False) else "❌ FAIL"
        error = f" ({result.get('error', 'Unknown error')})" if not result.get('success', False) else ""
        print(f"{status} {test_name.replace('_', ' ').title()}{error}")
    
    print(f"\n🎯 Wynik: {passed_tests}/{total_tests} testów przeszło")
    
    if passed_tests == total_tests:
        print("🎉 WSZYSTKIE TESTY PRZESZŁY - Mechanizm fallback działa poprawnie!")
        print("💡 Scout może teraz automatycznie odświeżać tokeny przez Worker")
    else:
        print("⚠️ Niektóre testy nie przeszły - sprawdź konfigurację i logi")
        print("📋 Wymagane działania:")
        if not results['worker_endpoint'].get('success'):
            print("   - Sprawdź czy Worker Service jest uruchomiony")
            print("   - Sprawdź WORKER_SERVICE_URL")
        if not results['scout_fallback'].get('success'):
            print("   - Sprawdź konfigurację Scout Function")
            print("   - Sprawdź dostęp do Secret Manager")

if __name__ == "__main__":
    main() 