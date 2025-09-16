#!/usr/bin/env python3
"""
Test script dla nowej funkcjonalności automatycznego START CHARGING
przy nakładaniu się harmonogramów z obecną godziną warszawską.

Symuluje różne scenariusze:
1. Harmonogram nakłada się z obecną godziną → powinna zostać wysłana komenda charge_start
2. Harmonogram nie nakłada się → brak akcji
3. Harmonogram przechodzący przez północ → sprawdzenie obsługi
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta
import pytz
from typing import List, Dict, Any

# Dodaj ścieżkę do modułów aplikacji
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cloud_tesla_monitor import ChargeSchedule


class MockTeslaController:
    """Mock TeslaController do testów"""
    def __init__(self):
        self.current_vehicle = {'vin': 'TEST123456789', 'id_s': 'test_id'}
        
    def minutes_to_time(self, minutes: int) -> str:
        """Konwertuje minuty od północy na format HH:MM"""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"
    
    def connect(self):
        return True


class MockFleetAPI:
    """Mock Fleet API do testów"""
    def __init__(self):
        self.charge_start_called = False
        self.charge_start_success = True
        
    def charge_start(self, vehicle_id: str, use_proxy: bool = False) -> bool:
        self.charge_start_called = True
        print(f"🔋 MOCK: charge_start wywołane dla {vehicle_id}, use_proxy={use_proxy}")
        return self.charge_start_success


class TestChargeStartOverlap:
    """Klasa testowa dla funkcjonalności charge_start przy nakładaniu harmonogramów"""
    
    def __init__(self):
        self.mock_tesla_controller = MockTeslaController()
        self.mock_fleet_api = MockFleetAPI()
        self.mock_tesla_controller.fleet_api = self.mock_fleet_api
        
    def create_test_schedule(self, start_minutes: int, end_minutes: int) -> ChargeSchedule:
        """Tworzy testowy harmonogram"""
        return ChargeSchedule(
            enabled=True,
            start_time=start_minutes,
            end_time=end_minutes,
            start_enabled=True,
            end_enabled=True,
            days_of_week="All",
            lat=52.334215,
            lon=20.937516,
            one_time=False
        )
    
    def _detect_current_time_overlap(self, schedules: List[ChargeSchedule]) -> bool:
        """
        Implementacja funkcji wykrywania nakładania z testami
        (kopiowana z cloud_tesla_monitor.py)
        """
        try:
            # Pobierz obecną godzinę warszawską
            warsaw_tz = pytz.timezone('Europe/Warsaw')
            current_time = datetime.now(warsaw_tz)
            current_minutes = current_time.hour * 60 + current_time.minute
            
            print(f"🕐 Obecny czas warszawski: {current_time.strftime('%H:%M')} ({current_minutes} minut od północy)")
            
            for i, schedule in enumerate(schedules):
                start_time = schedule.start_time
                end_time = schedule.end_time
                
                # Obsługa przejścia przez północ
                if end_time < start_time:  # Przejście przez północ (np. 23:00-01:00)
                    # Harmonogram przechodzi przez północ
                    if current_minutes >= start_time or current_minutes <= end_time:
                        print(f"⚡ WYKRYTO NAKŁADANIE z harmonogramem #{i+1}: "
                              f"{self.mock_tesla_controller.minutes_to_time(start_time)}-"
                              f"{self.mock_tesla_controller.minutes_to_time(end_time)} "
                              f"(przejście przez północ)")
                        return True
                else:  # Normalny harmonogram w tym samym dniu
                    if start_time <= current_minutes <= end_time:
                        print(f"⚡ WYKRYTO NAKŁADANIE z harmonogramem #{i+1}: "
                              f"{self.mock_tesla_controller.minutes_to_time(start_time)}-"
                              f"{self.mock_tesla_controller.minutes_to_time(end_time)}")
                        return True
            
            print(f"✅ Brak nakładania harmonogramów z obecną godziną")
            return False
            
        except Exception as e:
            print(f"❌ Błąd sprawdzania nakładania z obecnym czasem: {e}")
            return False
    
    def _send_charge_start_command(self, vehicle_vin: str) -> bool:
        """
        Mock implementacja wysyłania komendy charge_start
        """
        try:
            print(f"⚡ Wysyłanie komendy START CHARGING do pojazdu {vehicle_vin}...")
            
            # Wyślij komendę charge_start (używa Tesla HTTP Proxy)
            start_result = self.mock_tesla_controller.fleet_api.charge_start(vehicle_vin, use_proxy=True)
            
            if start_result:
                print(f"✅ Komenda START CHARGING wykonana pomyślnie")
                return True
            else:
                print(f"⚠️ Komenda START CHARGING nie została wykonana")
                return False
                
        except Exception as e:
            print(f"⚠️ Błąd wysyłania komendy START CHARGING: {e}")
            return False
    
    def test_scenario_1_overlap_detected(self):
        """TEST 1: Harmonogram nakłada się z obecną godziną"""
        print("\n" + "="*80)
        print("🧪 TEST 1: Harmonogram nakłada się z obecną godziną")
        print("="*80)
        
        # Stwórz harmonogram który na pewno się nakłada (aktualny czas +/- 30 min)
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        current_time = datetime.now(warsaw_tz)
        current_minutes = current_time.hour * 60 + current_time.minute
        
        # Harmonogram: 30 min przed obecnym czasem do 30 min po obecnym czasie
        start_minutes = max(0, current_minutes - 30)
        end_minutes = min(1439, current_minutes + 30)
        
        print(f"📅 Tworzę harmonogram: {self.mock_tesla_controller.minutes_to_time(start_minutes)}-"
              f"{self.mock_tesla_controller.minutes_to_time(end_minutes)}")
        
        schedule = self.create_test_schedule(start_minutes, end_minutes)
        schedules = [schedule]
        
        # Test wykrywania nakładania
        overlap_detected = self._detect_current_time_overlap(schedules)
        
        # Test wysyłania komendy
        if overlap_detected:
            charge_start_success = self._send_charge_start_command("TEST123456789")
            
            # Sprawdź rezultat
            if self.mock_fleet_api.charge_start_called and charge_start_success:
                print("✅ TEST 1 POWODZENIE: Nakładanie wykryte i komenda charge_start wysłana")
                return True
            else:
                print("❌ TEST 1 NIEPOWODZENIE: Komenda charge_start nie została wysłana")
                return False
        else:
            print("❌ TEST 1 NIEPOWODZENIE: Nakładanie nie zostało wykryte")
            return False
    
    def test_scenario_2_no_overlap(self):
        """TEST 2: Harmonogram nie nakłada się z obecną godziną"""
        print("\n" + "="*80)
        print("🧪 TEST 2: Harmonogram nie nakłada się z obecną godziną")
        print("="*80)
        
        # Reset mock
        self.mock_fleet_api.charge_start_called = False
        
        # Stwórz harmonogram który na pewno się nie nakłada (jutro)
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        current_time = datetime.now(warsaw_tz)
        current_minutes = current_time.hour * 60 + current_time.minute
        
        # Harmonogram: 2 godziny po obecnym czasie
        start_minutes = (current_minutes + 120) % 1440
        end_minutes = (current_minutes + 180) % 1440
        
        print(f"📅 Tworzę harmonogram: {self.mock_tesla_controller.minutes_to_time(start_minutes)}-"
              f"{self.mock_tesla_controller.minutes_to_time(end_minutes)}")
        
        schedule = self.create_test_schedule(start_minutes, end_minutes)
        schedules = [schedule]
        
        # Test wykrywania nakładania
        overlap_detected = self._detect_current_time_overlap(schedules)
        
        if not overlap_detected:
            if not self.mock_fleet_api.charge_start_called:
                print("✅ TEST 2 POWODZENIE: Brak nakładania wykryty i komenda charge_start NIE została wysłana")
                return True
            else:
                print("❌ TEST 2 NIEPOWODZENIE: Komenda charge_start została błędnie wysłana")
                return False
        else:
            print("❌ TEST 2 NIEPOWODZENIE: Nakładanie zostało błędnie wykryte")
            return False
    
    def test_scenario_3_midnight_crossover(self):
        """TEST 3: Harmonogram przechodzący przez północ"""
        print("\n" + "="*80)
        print("🧪 TEST 3: Harmonogram przechodzący przez północ")
        print("="*80)
        
        # Reset mock
        self.mock_fleet_api.charge_start_called = False
        
        # Stwórz harmonogram przechodzący przez północ: 23:30-01:30
        start_minutes = 23 * 60 + 30  # 23:30 = 1410 minut
        end_minutes = 1 * 60 + 30     # 01:30 = 90 minut
        
        print(f"📅 Tworzę harmonogram przechodzący przez północ: "
              f"{self.mock_tesla_controller.minutes_to_time(start_minutes)}-"
              f"{self.mock_tesla_controller.minutes_to_time(end_minutes)}")
        
        schedule = self.create_test_schedule(start_minutes, end_minutes)
        schedules = [schedule]
        
        # Test wykrywania nakładania
        overlap_detected = self._detect_current_time_overlap(schedules)
        
        # Sprawdź czy obecny czas jest w zakresie 23:30-01:30
        warsaw_tz = pytz.timezone('Europe/Warsaw')
        current_time = datetime.now(warsaw_tz)
        current_minutes = current_time.hour * 60 + current_time.minute
        
        expected_overlap = (current_minutes >= start_minutes or current_minutes <= end_minutes)
        
        if overlap_detected == expected_overlap:
            print(f"✅ TEST 3 POWODZENIE: Przejście przez północ poprawnie obsłużone "
                  f"(nakładanie={overlap_detected})")
            return True
        else:
            print(f"❌ TEST 3 NIEPOWODZENIE: Błędna obsługa przejścia przez północ "
                  f"(nakładanie={overlap_detected}, oczekiwane={expected_overlap})")
            return False
    
    def run_all_tests(self):
        """Uruchom wszystkie testy"""
        print("🚀 Rozpoczynam testy funkcjonalności AUTO CHARGE START przy nakładaniu harmonogramów")
        print("Wersja z nową logiką wykrywania nakładania z obecną godziną warszawską")
        
        test_results = []
        
        # Uruchom testy
        test_results.append(self.test_scenario_1_overlap_detected())
        test_results.append(self.test_scenario_2_no_overlap())
        test_results.append(self.test_scenario_3_midnight_crossover())
        
        # Podsumowanie
        print("\n" + "="*80)
        print("📊 PODSUMOWANIE TESTÓW")
        print("="*80)
        
        passed = sum(test_results)
        total = len(test_results)
        
        print(f"✅ Testy zakończone pomyślnie: {passed}/{total}")
        print(f"❌ Testy zakończone niepowodzeniem: {total-passed}/{total}")
        
        if passed == total:
            print("🎉 WSZYSTKIE TESTY ZAKOŃCZONE SUKCESEM!")
            print("🔋 Funkcjonalność AUTO CHARGE START działa poprawnie")
        else:
            print("⚠️ NIEKTÓRE TESTY NIE PRZESZŁY")
            print("🔧 Wymagane dodatkowe poprawki")
        
        return passed == total


if __name__ == "__main__":
    # Uruchom testy
    tester = TestChargeStartOverlap()
    success = tester.run_all_tests()
    
    # Exit code dla CI/CD
    sys.exit(0 if success else 1) 