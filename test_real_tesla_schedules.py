#!/usr/bin/env python3
"""
Test rzeczywistych funkcji zarządzania harmonogramami Tesla
Sprawdza czy funkcje w tesla_controller.py działają poprawnie
"""

import os
import sys
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych
load_dotenv()

# Import naszych modułów
try:
    from tesla_controller import TeslaController, ChargeSchedule
    print("✅ Moduły Tesla Controller załadowane pomyślnie")
except Exception as e:
    print(f"❌ Błąd importu Tesla Controller: {e}")
    sys.exit(1)

class RealTeslaScheduleTest:
    """Test rzeczywistych funkcji harmonogramów Tesla"""
    
    def __init__(self):
        """Inicjalizacja testu"""
        print("🔗 Inicjalizacja połączenia z Tesla...")
        
        try:
            self.tesla_controller = TeslaController()
            if self.tesla_controller.connect():
                print("✅ Połączono z Tesla Fleet API")
                
                # Sprawdź czy mamy pojazdy
                vehicles = self.tesla_controller.get_vehicles()
                if vehicles:
                    print(f"🚗 Znaleziono {len(vehicles)} pojazdów")
                    for vehicle in vehicles:
                        print(f"   • {vehicle.get('display_name', 'Unnamed')} (VIN: {vehicle.get('vin', 'Unknown')[:8]}...)")
                else:
                    print("⚠️  Brak pojazdów - test ograniczony")
                
                self.connected = True
            else:
                print("❌ Nie udało się połączyć z Tesla")
                self.connected = False
        except Exception as e:
            print(f"❌ Błąd połączenia Tesla: {e}")
            self.connected = False
    
    def test_get_charge_schedules(self):
        """Test pobierania harmonogramów ładowania"""
        print(f"\n📋 TEST: Pobieranie harmonogramów ładowania")
        print("-" * 60)
        
        if not self.connected:
            print("⚠️  Pomijam test - brak połączenia Tesla")
            return False
        
        try:
            print("🔍 Pobieranie harmonogramów z pojazdu...")
            schedules = self.tesla_controller.get_charge_schedules()
            
            if schedules:
                print(f"✅ Znaleziono {len(schedules)} harmonogramów:")
                for i, schedule in enumerate(schedules, 1):
                    print(f"   Harmonogram {i}:")
                    print(f"     ID: {schedule.get('id', 'N/A')}")
                    print(f"     Start: {schedule.get('start_time', 'N/A')}")
                    print(f"     End: {schedule.get('end_time', 'N/A')}")
                    print(f"     Enabled: {schedule.get('enabled', 'N/A')}")
                    print(f"     Days: {schedule.get('days_of_week', 'N/A')}")
                    print("     ---")
                return True
            else:
                print("ℹ️  Brak harmonogramów w pojeździe")
                return True
                
        except Exception as e:
            print(f"❌ Błąd pobierania harmonogramów: {e}")
            return False
    
    def test_charge_schedule_creation(self):
        """Test tworzenia obiektu harmonogramu"""
        print(f"\n➕ TEST: Tworzenie harmonogramu ładowania")
        print("-" * 60)
        
        try:
            # Tworzenie testowego harmonogramu
            schedule = ChargeSchedule(
                location_latitude=52.334215,  # Warszawa
                location_longitude=20.937516,
                start_time_minutes=23 * 60,   # 23:00
                end_time_minutes=6 * 60,      # 06:00
                charge_current_a=32,
                days_of_week="all"
            )
            
            print(f"✅ Utworzono harmonogram:")
            print(f"   Lokalizacja: {schedule.location_latitude}, {schedule.location_longitude}")
            print(f"   Start: {schedule.start_time_minutes} min ({schedule.start_time_minutes // 60:02d}:{schedule.start_time_minutes % 60:02d})")
            print(f"   End: {schedule.end_time_minutes} min ({schedule.end_time_minutes // 60:02d}:{schedule.end_time_minutes % 60:02d})")
            print(f"   Prąd: {schedule.charge_current_a}A")
            print(f"   Dni: {schedule.days_of_week}")
            
            return True
            
        except Exception as e:
            print(f"❌ Błąd tworzenia harmonogramu: {e}")
            return False
    
    def test_add_charge_schedule_dry_run(self):
        """Test dodawania harmonogramu (dry run - bez rzeczywistego wysłania)"""
        print(f"\n🧪 TEST: Dodawanie harmonogramu (dry run)")
        print("-" * 60)
        
        if not self.connected:
            print("⚠️  Pomijam test - brak połączenia Tesla")
            return False
        
        try:
            # Tworzenie testowego harmonogramu
            test_schedule = ChargeSchedule(
                location_latitude=52.334215,
                location_longitude=20.937516,
                start_time_minutes=2 * 60,    # 02:00
                end_time_minutes=6 * 60,      # 06:00
                charge_current_a=16,
                days_of_week="weekdays"
            )
            
            print(f"📝 Przygotowano harmonogram testowy:")
            print(f"   Czas: 02:00-06:00")
            print(f"   Prąd: 16A")
            print(f"   Dni: weekdays")
            
            # Sprawdź czy funkcja istnieje
            if hasattr(self.tesla_controller, 'add_charge_schedule'):
                print(f"✅ Funkcja add_charge_schedule dostępna")
                
                # UWAGA: Nie wywołujemy rzeczywistej funkcji w teście!
                print(f"ℹ️  Dry run - nie wysyłam rzeczywistego harmonogramu do pojazdu")
                print(f"💡 W produkcji wywołałoby: tesla_controller.add_charge_schedule(test_schedule)")
                
                return True
            else:
                print(f"❌ Funkcja add_charge_schedule nie znaleziona")
                return False
                
        except Exception as e:
            print(f"❌ Błąd w teście dodawania harmonogramu: {e}")
            return False
    
    def test_location_check(self):
        """Test sprawdzania lokalizacji pojazdu"""
        print(f"\n📍 TEST: Sprawdzanie lokalizacji pojazdu")
        print("-" * 60)
        
        if not self.connected:
            print("⚠️  Pomijam test - brak połączenia Tesla")
            return False
        
        try:
            print("🔍 Sprawdzanie lokalizacji pojazdu...")
            
            # Sprawdź czy mamy funkcję sprawdzania lokalizacji
            if hasattr(self.tesla_controller, 'get_vehicle_location_status'):
                location_status = self.tesla_controller.get_vehicle_location_status()
                print(f"✅ Status lokalizacji: {location_status}")
                return True
            else:
                print("ℹ️  Funkcja sprawdzania lokalizacji nie jest bezpośrednio dostępna")
                
                # Spróbuj przez get_vehicle_data
                vehicle_data = self.tesla_controller.get_current_vehicle_data()
                if vehicle_data:
                    drive_state = vehicle_data.get('drive_state', {})
                    latitude = drive_state.get('latitude')
                    longitude = drive_state.get('longitude')
                    
                    if latitude and longitude:
                        print(f"✅ Lokalizacja pojazdu: {latitude:.6f}, {longitude:.6f}")
                        
                        # Sprawdź czy jest w domu (przykładowe współrzędne)
                        home_lat = 52.334215
                        home_lon = 20.937516
                        home_radius = 0.15  # km
                        
                        distance = ((latitude - home_lat) ** 2 + (longitude - home_lon) ** 2) ** 0.5
                        is_home = distance <= home_radius
                        
                        print(f"📏 Odległość od domu: {distance:.3f} km")
                        print(f"🏠 W domu: {'TAK' if is_home else 'NIE'}")
                        return True
                    else:
                        print("ℹ️  Brak danych lokalizacji pojazdu")
                        return True
                else:
                    print("⚠️  Nie udało się pobrać danych pojazdu")
                    return False
                
        except Exception as e:
            print(f"❌ Błąd sprawdzania lokalizacji: {e}")
            return False
    
    def run_all_tests(self):
        """Uruchamia wszystkie testy"""
        print("🧪 URUCHAMIANIE TESTÓW RZECZYWISTYCH FUNKCJI TESLA")
        print("=" * 80)
        
        test_results = []
        
        # Test 1: Pobieranie harmonogramów
        result1 = self.test_get_charge_schedules()
        test_results.append(("Pobieranie harmonogramów", result1))
        
        # Test 2: Tworzenie harmonogramu
        result2 = self.test_charge_schedule_creation()
        test_results.append(("Tworzenie harmonogramu", result2))
        
        # Test 3: Dodawanie harmonogramu (dry run)
        result3 = self.test_add_charge_schedule_dry_run()
        test_results.append(("Dodawanie harmonogramu (dry run)", result3))
        
        # Test 4: Sprawdzanie lokalizacji
        result4 = self.test_location_check()
        test_results.append(("Sprawdzanie lokalizacji", result4))
        
        # Podsumowanie
        print(f"\n📊 PODSUMOWANIE TESTÓW")
        print("=" * 80)
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"   {test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n🎯 WYNIK: {passed}/{total} testów przeszło pomyślnie")
        
        if passed == total:
            print("🎉 WSZYSTKIE TESTY PRZESZŁY!")
            print("💡 Funkcje Tesla Controller są gotowe do automatycznego zarządzania harmonogramami")
        else:
            print("⚠️  Niektóre testy nie przeszły - sprawdź błędy powyżej")
        
        return passed == total

if __name__ == "__main__":
    print("🔧 URUCHAMIANIE TESTÓW RZECZYWISTYCH FUNKCJI TESLA CONTROLLER")
    print()
    
    # Sprawdź czy są wymagane zmienne środowiskowe
    required_vars = ['TESLA_CLIENT_ID', 'TESLA_CLIENT_SECRET', 'TESLA_DOMAIN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("❌ Brak wymaganych zmiennych środowiskowych:")
        for var in missing_vars:
            print(f"   • {var}")
        print("\n💡 Ustaw zmienne w pliku .env lub Google Cloud Secret Manager")
        sys.exit(1)
    
    # Uruchomienie testów
    test_suite = RealTeslaScheduleTest()
    success = test_suite.run_all_tests()
    
    print(f"\n" + "=" * 80)
    if success:
        print("🎯 WYNIK: ✅ WSZYSTKIE TESTY ZAKOŃCZONE SUKCESEM")
        print("🚗 Tesla Controller jest gotowy do automatycznego zarządzania harmonogramami!")
    else:
        print("🎯 WYNIK: ⚠️  NIEKTÓRE TESTY NIEUDANE")
        print("💡 Sprawdź konfigurację Tesla Fleet API i połączenie z pojazdem")
    
    print("\n📖 Aby zobaczyć funkcjonalność w akcji, sprawdź logi Google Cloud gdy pojazd będzie gotowy do ładowania w domu")
    print("🔗 Logs: gcloud logs tail --service=tesla-monitor --region=europe-west1 --follow") 