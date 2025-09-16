#!/usr/bin/env python3
"""
⚠️  UWAGA: RZECZYWISTY TEST Z POJAZDEM TESLA ⚠️
Ten skrypt rzeczywiście wyśle komendy do pojazdu!
Używaj tylko jeśli jesteś pewien co robisz!
"""

import os
import sys
import json
from dotenv import load_dotenv

# Ładowanie zmiennych środowiskowych
load_dotenv()

# Import naszych modułów
try:
    from tesla_controller import TeslaController, ChargeSchedule
    print("✅ Moduły Tesla Controller załadowane")
except Exception as e:
    print(f"❌ Błąd importu: {e}")
    sys.exit(1)

class RealVehicleScheduleTest:
    """⚠️ RZECZYWISTY test harmonogramów - WYSYŁA KOMENDY DO POJAZDU!"""
    
    def __init__(self):
        print("⚠️" * 20)
        print("🚨 UWAGA: RZECZYWISTY TEST Z POJAZDEM TESLA!")
        print("🚨 Ten skrypt RZECZYWIŚCIE wyśle komendy do pojazdu!")
        print("🚨 Harmonogramy ładowania ZOSTANĄ ZMIENIONE!")
        print("⚠️" * 20)
        
        response = input("\n❓ Czy na pewno chcesz kontynuować? (wpisz 'TAK JESTEM PEWIEN'): ")
        if response != "TAK JESTEM PEWIEN":
            print("❌ Test anulowany dla bezpieczeństwa")
            sys.exit(0)
        
        print("\n🔗 Łączenie z Tesla...")
        try:
            self.tesla_controller = TeslaController()
            if self.tesla_controller.connect():
                print("✅ Połączono z Tesla")
                self.connected = True
            else:
                print("❌ Nie udało się połączyć")
                self.connected = False
        except Exception as e:
            print(f"❌ Błąd połączenia: {e}")
            self.connected = False
    
    def show_current_schedules(self):
        """Pokazuje obecne harmonogramy w pojeździe"""
        print("\n📋 OBECNE HARMONOGRAMY W POJEŹDZIE")
        print("-" * 60)
        
        if not self.connected:
            print("❌ Brak połączenia z Tesla")
            return []
        
        try:
            schedules = self.tesla_controller.get_charge_schedules()
            
            if schedules:
                print(f"📊 Znaleziono {len(schedules)} harmonogramów:")
                for i, schedule in enumerate(schedules, 1):
                    print(f"\n   Harmonogram {i}:")
                    print(f"     ID: {schedule.get('id', 'N/A')}")
                    print(f"     Enabled: {schedule.get('enabled', 'N/A')}")
                    print(f"     Start: {schedule.get('start_time', 'N/A')} min")
                    print(f"     End: {schedule.get('end_time', 'N/A')} min")
                    print(f"     Days: {schedule.get('days_of_week', 'N/A')}")
                    
                    # Konwersja minut na czas
                    if schedule.get('start_time') is not None:
                        start_h = schedule['start_time'] // 60
                        start_m = schedule['start_time'] % 60
                        print(f"     Start time: {start_h:02d}:{start_m:02d}")
                    
                    if schedule.get('end_time') is not None:
                        end_h = schedule['end_time'] // 60
                        end_m = schedule['end_time'] % 60
                        print(f"     End time: {end_h:02d}:{end_m:02d}")
                
                return schedules
            else:
                print("ℹ️  Brak harmonogramów w pojeździe")
                return []
                
        except Exception as e:
            print(f"❌ Błąd pobierania harmonogramów: {e}")
            return []
    
    def add_test_schedule(self):
        """⚠️ RZECZYWIŚCIE dodaje testowy harmonogram do pojazdu!"""
        print("\n➕ DODAWANIE TESTOWEGO HARMONOGRAMU")
        print("-" * 60)
        print("⚠️ TO RZECZYWIŚCIE ZMIENI HARMONOGRAM W TWOIM POJEŹDZIE!")
        
        confirm = input("❓ Czy na pewno dodać testowy harmonogram? (wpisz 'TAK'): ")
        if confirm != "TAK":
            print("❌ Anulowano dodawanie harmonogramu")
            return False
        
        if not self.connected:
            print("❌ Brak połączenia z Tesla")
            return False
        
        try:
            # Tworzenie testowego harmonogramu (2:00-6:00, 16A, codziennie)
            test_schedule = ChargeSchedule(
                enabled=True,
                start_time=120,    # 02:00 (2*60 minut)
                end_time=360,      # 06:00 (6*60 minut)
                days_of_week="All",
                lat=self.tesla_controller.default_latitude,
                lon=self.tesla_controller.default_longitude
            )
            
            print(f"📝 Dodaję harmonogram:")
            print(f"   Czas: 02:00-06:00")
            print(f"   Dni: Codziennie")
            print(f"   Lokalizacja: {test_schedule.lat:.6f}, {test_schedule.lon:.6f}")
            
            # ⚠️ RZECZYWISTE WYWOŁANIE API TESLA!
            result = self.tesla_controller.add_charge_schedule(test_schedule)
            
            if result:
                print("✅ SUKCES: Harmonogram dodany do pojazdu!")
                print("📱 Sprawdź aplikację Tesla - powinien pojawić się nowy harmonogram")
                return True
            else:
                print("❌ BŁĄD: Nie udało się dodać harmonogramu")
                return False
                
        except Exception as e:
            print(f"❌ Błąd dodawania harmonogramu: {e}")
            return False
    
    def remove_schedule_by_id(self, schedule_id: int):
        """⚠️ RZECZYWIŚCIE usuwa harmonogram z pojazdu!"""
        print(f"\n🗑️ USUWANIE HARMONOGRAMU ID: {schedule_id}")
        print("-" * 60)
        print("⚠️ TO RZECZYWIŚCIE USUNIE HARMONOGRAM Z TWOJEGO POJAZDU!")
        
        confirm = input(f"❓ Czy na pewno usunąć harmonogram {schedule_id}? (wpisz 'TAK'): ")
        if confirm != "TAK":
            print("❌ Anulowano usuwanie harmonogramu")
            return False
        
        if not self.connected:
            print("❌ Brak połączenia z Tesla")
            return False
        
        try:
            # ⚠️ RZECZYWISTE WYWOŁANIE API TESLA!
            result = self.tesla_controller.remove_charge_schedule(schedule_id)
            
            if result:
                print(f"✅ SUKCES: Harmonogram {schedule_id} usunięty z pojazdu!")
                print("📱 Sprawdź aplikację Tesla - harmonogram powinien zniknąć")
                return True
            else:
                print(f"❌ BŁĄD: Nie udało się usunąć harmonogramu {schedule_id}")
                return False
                
        except Exception as e:
            print(f"❌ Błąd usuwania harmonogramu: {e}")
            return False
    
    def run_interactive_test(self):
        """Uruchamia interaktywny test z rzeczywistym pojazdem"""
        print("\n🎯 INTERAKTYWNY TEST Z RZECZYWISTYM POJAZDEM TESLA")
        print("=" * 80)
        
        if not self.connected:
            print("❌ Brak połączenia z Tesla - test niemożliwy")
            return False
        
        while True:
            print(f"\n📋 MENU TESTOWE:")
            print("1. 📊 Pokaż obecne harmonogramy")
            print("2. ➕ Dodaj testowy harmonogram (2:00-6:00)")
            print("3. 🗑️ Usuń harmonogram (po ID)")
            print("4. 🚪 Zakończ test")
            
            choice = input("\n❓ Wybierz opcję (1-4): ")
            
            if choice == "1":
                schedules = self.show_current_schedules()
                
            elif choice == "2":
                success = self.add_test_schedule()
                if success:
                    print("\n🎉 Harmonogram dodany! Sprawdź aplikację Tesla na telefonie")
                    
            elif choice == "3":
                schedules = self.show_current_schedules()
                if schedules:
                    try:
                        schedule_id = int(input("\n❓ Podaj ID harmonogramu do usunięcia: "))
                        success = self.remove_schedule_by_id(schedule_id)
                        if success:
                            print("\n🎉 Harmonogram usunięty! Sprawdź aplikację Tesla na telefonie")
                    except ValueError:
                        print("❌ Nieprawidłowe ID harmonogramu")
                else:
                    print("ℹ️ Brak harmonogramów do usunięcia")
                    
            elif choice == "4":
                print("👋 Zakończenie testu")
                break
                
            else:
                print("❌ Nieprawidłowy wybór")
        
        return True

if __name__ == "__main__":
    print("🚨 RZECZYWISTY TEST HARMONOGRAMÓW TESLA")
    print("=" * 80)
    print("⚠️  UWAGA: Ten skrypt rzeczywiście zmieni harmonogramy w Twoim pojeździe!")
    print("⚠️  Używaj tylko jeśli jesteś pewien co robisz!")
    print("⚠️  Zawsze możesz przywrócić harmonogramy ręcznie w aplikacji Tesla")
    
    # Sprawdzenie zmiennych środowiskowych
    required_vars = ['TESLA_CLIENT_ID', 'TESLA_CLIENT_SECRET', 'TESLA_DOMAIN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"\n❌ Brak wymaganych zmiennych środowiskowych: {missing_vars}")
        print("💡 Ustaw je w pliku .env")
        sys.exit(1)
    
    # Uruchomienie testu
    test_suite = RealVehicleScheduleTest()
    if test_suite.connected:
        test_suite.run_interactive_test()
    else:
        print("❌ Nie można uruchomić testu - brak połączenia z Tesla")
    
    print(f"\n📱 Sprawdź aplikację Tesla na telefonie aby zobaczyć zmiany!")
    print(f"📖 Jeśli chcesz przywrócić poprzednie harmonogramy, zrób to ręcznie w aplikacji") 