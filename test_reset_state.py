#!/usr/bin/env python3
"""
Test skript do resetowania stanu Tesla Monitor
Wykonuje kompletny reset stanu monitorowania dla testów
"""

import requests
import json
import time
from datetime import datetime

def test_reset_locally():
    """Testuje reset na lokalnej instancji"""
    print("🔄 Testowanie resetu lokalnie...")
    
    try:
        response = requests.get('http://localhost:8080/reset', timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Reset lokalny zakończony pomyślnie!")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ Reset lokalny nieudany: {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  Brak lokalnej instancji na porcie 8080")
        return False
    except Exception as e:
        print(f"❌ Błąd resetu lokalnego: {e}")
        return False

def test_reset_cloud():
    """Testuje reset na cloud instancji"""
    print("🌐 Testowanie resetu na cloud...")
    
    cloud_url = "https://tesla-monitor-74pl3bqokq-ew.a.run.app"
    
    try:
        response = requests.get(f'{cloud_url}/reset', timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Reset cloud zakończony pomyślnie!")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ Reset cloud nieudany: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"❌ Błąd resetu cloud: {e}")
        return False

def check_health_after_reset(url):
    """Sprawdza health check po resecie"""
    print(f"🏥 Sprawdzanie health check: {url}")
    
    try:
        response = requests.get(f'{url}/health', timeout=10)
        
        if response.status_code == 200:
            health = response.json()
            print("✅ Health check OK po resecie")
            print(f"   Status: {health['status']}")
            print(f"   Active cases: {health['active_cases']}")
            print(f"   Timestamp: {health['timestamp']}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Błąd health check: {e}")
        return False

def main():
    """Główna funkcja testowa"""
    print("=" * 60)
    print("🔄 TESLA MONITOR - TEST RESETU STANU")
    print("=" * 60)
    print(f"Czas rozpoczęcia: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test lokalny
    local_success = test_reset_locally()
    if local_success:
        time.sleep(2)
        check_health_after_reset("http://localhost:8080")
    
    print()
    print("-" * 40)
    print()
    
    # Test cloud
    cloud_success = test_reset_cloud()
    if cloud_success:
        time.sleep(2)
        check_health_after_reset("https://tesla-monitor-74pl3bqokq-ew.a.run.app")
    
    print()
    print("=" * 60)
    if local_success or cloud_success:
        print("🎉 RESET ZAKOŃCZONY - APLIKACJA GOTOWA DO TESTOWANIA")
        print()
        print("Następne kroki:")
        print("1. Stan aplikacji został całkowicie zresetowany")
        print("2. Pierwszy check pojazdu będzie traktowany jako nowy")
        print("3. Pierwsze wywołanie OFF PEAK CHARGE API jako inicjalne")
        print("4. Wszystkie zmiany harmonogramów będą logowane jako pierwsze")
        print()
        print("Monitoruj logi aplikacji aby zobaczyć działanie od początku:")
        print("gcloud logs tail tesla-monitor --location=europe-west1")
    else:
        print("❌ RESET NIE POWIÓDŁ SIĘ")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 