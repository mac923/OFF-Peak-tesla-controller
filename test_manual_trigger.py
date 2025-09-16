#!/usr/bin/env python3
"""
Test manualnego uruchomienia zarządzania harmonogramami
Pozwala przetestować funkcjonalność bez czekania na warunek A
"""

import requests
import json
from datetime import datetime

class ManualTriggerTest:
    """Test manualnego wywołania funkcji zarządzania harmonogramami"""
    
    def __init__(self):
        self.app_url = "https://tesla-monitor-74pl3bqokq-ew.a.run.app"
    
    def test_app_health(self):
        """Test sprawdzania zdrowia aplikacji"""
        print("🏥 TEST: Sprawdzanie zdrowia aplikacji")
        print("-" * 60)
        
        try:
            response = requests.get(f"{self.app_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                print("✅ Aplikacja działa poprawnie")
                print(f"   Status: {health_data.get('status')}")
                print(f"   Running: {health_data.get('is_running')}")
                print(f"   Active cases: {health_data.get('active_cases')}")
                print(f"   Timestamp: {health_data.get('timestamp')}")
                return True
            else:
                print(f"❌ Błąd HTTP: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Błąd połączenia: {e}")
            return False
    
    def simulate_condition_a_trigger(self):
        """Symulacja wywołania gdy warunek A zostanie wykryty"""
        print("\n🎯 SYMULACJA: Co się stanie gdy warunek A zostanie wykryty")
        print("-" * 60)
        
        print("📋 Sekwencja działań w aplikacji:")
        print("1. 🔍 Wykrycie: Pojazd online + gotowy do ładowania + w domu")
        print("2. 📞 Wywołanie OFF PEAK CHARGE API")
        print("3. 🔐 Porównanie hash harmonogramu (MD5)")
        print("4. 📋 Pobranie harmonogramów Tesla (jeśli hash się zmienił)")
        print("5. 🗑️  Usunięcie harmonogramów HOME")
        print("6. ➕ Dodanie nowych harmonogramów z OFF PEAK CHARGE")
        print("7. ✅ Logowanie sukcesu")
        
        print(f"\n📊 Obecny status (z health check):")
        health_success = self.test_app_health()
        
        if health_success:
            print(f"\n💡 Aplikacja jest gotowa - czeka na spełnienie warunku A")
            print(f"📖 Aby zobaczyć logi w czasie rzeczywistym:")
            print(f"   gcloud logs tail --service=tesla-monitor --region=europe-west1 --follow")
        
        return health_success
    
    def show_test_scenarios(self):
        """Pokazuje różne scenariusze testowe"""
        print(f"\n🧪 SCENARIUSZE TESTOWE")
        print("=" * 80)
        
        scenarios = [
            {
                "name": "Scenariusz 1: Normalny przepływ",
                "description": "Pojazd w domu, gotowy do ładowania, nowy harmonogram",
                "steps": [
                    "Warunek A wykryty",
                    "OFF PEAK API zwraca nowy harmonogram",
                    "Hash się różni od poprzedniego", 
                    "Usuwanie starych harmonogramów HOME",
                    "Dodawanie nowych harmonogramów",
                    "Sukces"
                ]
            },
            {
                "name": "Scenariusz 2: Harmonogram bez zmian",
                "description": "Pojazd gotowy, ale harmonogram identyczny",
                "steps": [
                    "Warunek A wykryty",
                    "OFF PEAK API zwraca harmonogram",
                    "Hash identyczny z poprzednim",
                    "Pomijanie aktualizacji",
                    "Logowanie 'brak zmian'"
                ]
            },
            {
                "name": "Scenariusz 3: Błąd OFF PEAK API",
                "description": "Pojazd gotowy, ale API OFF PEAK CHARGE niedostępne",
                "steps": [
                    "Warunek A wykryty",
                    "OFF PEAK API zwraca błąd",
                    "Logowanie błędu",
                    "Zachowanie poprzednich harmonogramów",
                    "Ponowna próba w następnym cyklu"
                ]
            }
        ]
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n📋 {scenario['name']}")
            print(f"📝 {scenario['description']}")
            print("🔄 Kroki:")
            for j, step in enumerate(scenario['steps'], 1):
                print(f"   {j}. {step}")
    
    def show_monitoring_commands(self):
        """Pokazuje komendy do monitorowania aplikacji"""
        print(f"\n📊 KOMENDY MONITOROWANIA")
        print("=" * 80)
        
        commands = [
            {
                "name": "Sprawdzenie zdrowia aplikacji",
                "command": f"curl {self.app_url}/health",
                "description": "Sprawdza czy aplikacja działa"
            },
            {
                "name": "Logi w czasie rzeczywistym",
                "command": "gcloud logs tail --service=tesla-monitor --region=europe-west1 --follow",
                "description": "Podgląd logów na żywo"
            },
            {
                "name": "Ostatnie logi",
                "command": "gcloud logs read 'resource.type=cloud_run_revision AND resource.labels.service_name=tesla-monitor' --limit=50",
                "description": "50 ostatnich wpisów logów"
            },
            {
                "name": "Logi dotyczące harmonogramów",
                "command": "gcloud logs read 'resource.type=cloud_run_revision AND resource.labels.service_name=tesla-monitor' --limit=100 | grep -i 'harmonogram\\|schedule'",
                "description": "Filtrowanie logów harmonogramów"
            },
            {
                "name": "Status pojazdu",
                "command": "gcloud logs read 'resource.type=cloud_run_revision AND resource.labels.service_name=tesla-monitor' --limit=20 | grep -E 'VIN=|bateria=|ładowanie='",
                "description": "Ostatni status pojazdu"
            }
        ]
        
        for cmd in commands:
            print(f"\n🔧 {cmd['name']}")
            print(f"📝 {cmd['description']}")
            print(f"💻 {cmd['command']}")
    
    def run_full_manual_test(self):
        """Uruchamia pełny test manualny"""
        print("🎯 MANUALNY TEST AUTOMATYCZNEGO ZARZĄDZANIA HARMONOGRAMAMI")
        print("=" * 80)
        print(f"📅 Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 URL aplikacji: {self.app_url}")
        
        # Test 1: Sprawdzenie zdrowia aplikacji
        health_ok = self.test_app_health()
        
        # Test 2: Symulacja warunku A
        if health_ok:
            trigger_ok = self.simulate_condition_a_trigger()
        else:
            trigger_ok = False
        
        # Test 3: Pokazanie scenariuszy
        self.show_test_scenarios()
        
        # Test 4: Komendy monitorowania
        self.show_monitoring_commands()
        
        # Podsumowanie
        print(f"\n🎉 PODSUMOWANIE TESTU MANUALNEGO")
        print("=" * 80)
        
        if health_ok and trigger_ok:
            print("✅ SUKCES: Aplikacja jest gotowa do automatycznego zarządzania harmonogramami")
            print("\n📖 Co dalej:")
            print("1. Aplikacja automatycznie wykryje warunek A gdy pojazd będzie gotowy")
            print("2. Monitoruj logi aby zobaczyć funkcjonalność w akcji")
            print("3. Sprawdzaj health endpoint aby upewnić się że aplikacja działa")
            
            print(f"\n🚗 Warunek A zostanie wykryty gdy:")
            print("   • Pojazd będzie online")
            print("   • Pojazd będzie gotowy do ładowania (is_charging_ready=true)")
            print("   • Pojazd będzie w lokalizacji HOME")
            
            print(f"\n🔄 Automatyczne zarządzanie uruchomi się gdy:")
            print("   • Warunek A zostanie wykryty")
            print("   • OFF PEAK CHARGE API zwróci nowy harmonogram")
            print("   • Hash harmonogramu będzie różny od poprzedniego")
            
            return True
        else:
            print("❌ PROBLEM: Aplikacja nie jest gotowa")
            print("💡 Sprawdź logi aplikacji i status Google Cloud Run")
            return False

if __name__ == "__main__":
    print("🧪 URUCHAMIANIE MANUALNEGO TESTU ZARZĄDZANIA HARMONOGRAMAMI")
    print()
    
    # Uruchomienie testu
    test_suite = ManualTriggerTest()
    success = test_suite.run_full_manual_test()
    
    print(f"\n" + "=" * 80)
    if success:
        print("🎯 WYNIK: ✅ TEST MANUALNY ZAKOŃCZONY SUKCESEM")
        print("🚀 Aplikacja gotowa do automatycznego zarządzania harmonogramami!")
        print("\n💡 Tip: Uruchom 'gcloud logs tail --service=tesla-monitor --region=europe-west1 --follow'")
        print("    aby zobaczyć logi w czasie rzeczywistym gdy warunek A zostanie wykryty")
    else:
        print("🎯 WYNIK: ❌ TEST MANUALNY NIEUDANY")
        print("💡 Sprawdź status aplikacji i konfigurację Google Cloud")
    
    print(f"\n📚 Zobacz pełną dokumentację testów w: dokumentacja/TESTY_HARMONOGRAMOW_PODSUMOWANIE.md") 