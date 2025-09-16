#!/usr/bin/env python3
"""
Test Special Charging Functionality
Testuje integrację Google Sheets i special charging logic
"""

import os
import json
import requests
import sys
from datetime import datetime, timedelta
import pytz

def test_special_charging_endpoint(worker_url: str):
    """Test special charging endpoint"""
    print("🧪 Testowanie Special Charging Endpoint...")
    
    try:
        url = f"{worker_url}/daily-special-charging-check"
        headers = {"Content-Type": "application/json"}
        data = {
            "trigger": "manual_test",
            "action": "daily_special_charging_check",
            "test_mode": True
        }
        
        print(f"📤 Wysyłam żądanie do: {url}")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"📥 Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Endpoint odpowiada poprawnie")
            print(f"📊 Wynik: {json.dumps(result, indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"❌ Błąd endpoint: {response.status_code}")
            print(f"📝 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Błąd testu endpoint: {e}")
        return False

def test_google_sheets_config():
    """Test konfiguracji Google Sheets"""
    print("🧪 Testowanie konfiguracji Google Sheets...")
    
    # Test czy zmienne środowiskowe są dostępne
    sheets_url = os.getenv('GOOGLE_SHEETS_URL')
    service_account_key = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    
    if not sheets_url:
        print("❌ Brak GOOGLE_SHEETS_URL w zmiennych środowiskowych")
        return False
    
    if not service_account_key:
        print("❌ Brak GOOGLE_SERVICE_ACCOUNT_KEY w zmiennych środowiskowych")
        return False
    
    print(f"✅ GOOGLE_SHEETS_URL: {sheets_url[:50]}...")
    print(f"✅ GOOGLE_SERVICE_ACCOUNT_KEY: {len(service_account_key)} znaków")
    
    # Test czy można parsować service account key
    try:
        key_data = json.loads(service_account_key)
        client_email = key_data.get('client_email', 'unknown')
        print(f"✅ Service Account Email: {client_email}")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ Błąd parsowania Service Account Key: {e}")
        return False

def test_google_sheets_connection():
    """Test połączenia z Google Sheets"""
    print("🧪 Testowanie połączenia z Google Sheets...")
    
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        sheets_url = os.getenv('GOOGLE_SHEETS_URL')
        service_account_key = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
        
        if not sheets_url or not service_account_key:
            print("❌ Brak konfiguracji Google Sheets")
            return False
        
        # Konfiguracja credentials
        creds = Credentials.from_service_account_info(
            json.loads(service_account_key),
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        gc = gspread.authorize(creds)
        
        # Próba otwarcia arkusza
        sheet = gc.open_by_url(sheets_url).sheet1
        
        # Pobierz dane testowe
        records = sheet.get_all_records()
        
        print(f"✅ Połączenie z Google Sheets: OK")
        print(f"📊 Znaleziono {len(records)} wierszy danych")
        
        # Wyświetl pierwszy wiersz jako przykład
        if records:
            first_record = records[0]
            print(f"📝 Przykładowy wiersz: {first_record}")
        
        return True
        
    except ImportError:
        print("❌ Brak biblioteki gspread - zainstaluj: pip install gspread google-auth")
        return False
    except Exception as e:
        print(f"❌ Błąd połączenia z Google Sheets: {e}")
        return False

def create_test_charging_plan():
    """Tworzy testowy plan ładowania"""
    print("🧪 Testowanie logiki obliczania planu ładowania...")
    
    try:
        from datetime import datetime, timedelta
        import pytz
        
        # Parametry testowe
        current_battery = 45
        target_battery = 85
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        target_datetime = datetime.now(warsaw_tz) + timedelta(hours=8)  # Za 8h
        
        print(f"🔋 Test: {current_battery}% → {target_battery}% na {target_datetime.strftime('%Y-%m-%d %H:%M')}")
        
        # Stałe (kopiowane z cloud_tesla_worker.py)
        CHARGING_RATE = 11  # kW/h
        BATTERY_CAPACITY_KWH = 75
        SAFETY_BUFFER_HOURS = 1.5
        PEAK_HOURS = [(6, 10), (19, 22)]
        
        # Obliczenia
        needed_percent = target_battery - current_battery
        needed_kwh = (needed_percent * BATTERY_CAPACITY_KWH) / 100
        charging_hours = (needed_kwh / CHARGING_RATE) + SAFETY_BUFFER_HOURS
        
        print(f"📊 Potrzebne kWh: {needed_kwh:.1f}")
        print(f"⏰ Czas ładowania: {charging_hours:.1f}h")
        
        # Znajdź slot (uproszczona wersja)
        latest_start = target_datetime - timedelta(hours=charging_hours)
        optimal_start = latest_start - timedelta(hours=2)  # 2h wcześniej dla bezpieczeństwa
        optimal_end = optimal_start + timedelta(hours=charging_hours)
        
        print(f"🎯 Optymalny slot: {optimal_start.strftime('%H:%M')}-{optimal_end.strftime('%H:%M')}")
        
        # Sprawdź peak hours
        start_hour = optimal_start.hour
        end_hour = optimal_end.hour
        
        conflicts = []
        for peak_start, peak_end in PEAK_HOURS:
            if start_hour < peak_end and end_hour > peak_start:
                conflicts.append(f"{peak_start:02d}:00-{peak_end:02d}:00")
        
        if conflicts:
            print(f"⚠️ Konflikt z peak hours: {', '.join(conflicts)}")
        else:
            print("✅ Brak konfliktów z peak hours")
        
        return True
        
    except Exception as e:
        print(f"❌ Błąd testu planu ładowania: {e}")
        return False

def main():
    """Główna funkcja testowa"""
    print("🔋 Tesla Special Charging - Test Suite")
    print("=" * 50)
    
    # Pobierz URL Worker Service
    worker_url = os.getenv('WORKER_SERVICE_URL')
    if len(sys.argv) > 1:
        worker_url = sys.argv[1]
    
    if not worker_url:
        print("❌ Brak WORKER_SERVICE_URL")
        print("Użycie: python3 test_special_charging.py https://your-worker-service-url")
        sys.exit(1)
    
    print(f"🌐 Worker Service URL: {worker_url}")
    print()
    
    # Lista testów
    tests = [
        ("Google Sheets Config", test_google_sheets_config),
        ("Google Sheets Connection", test_google_sheets_connection),
        ("Charging Plan Logic", create_test_charging_plan),
        ("Special Charging Endpoint", lambda: test_special_charging_endpoint(worker_url))
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"📋 Test: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")
            results.append((test_name, False))
        
        print("-" * 30)
    
    # Podsumowanie
    print("🎯 PODSUMOWANIE TESTÓW:")
    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\n📊 Wynik: {passed}/{len(results)} testów przeszło")
    
    if failed == 0:
        print("🎉 Wszystkie testy przeszły pomyślnie!")
        print("🚀 Special Charging jest gotowy do użycia!")
    else:
        print("⚠️ Niektóre testy nie przeszły - sprawdź konfigurację")

if __name__ == "__main__":
    main() 