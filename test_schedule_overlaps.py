#!/usr/bin/env python3
"""
Test funkcjonalności rozwiązywania nakładających się harmonogramów ładowania
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cloud_tesla_monitor import CloudTeslaMonitor
from tesla_controller import ChargeSchedule

def create_test_schedule(start_time: int, end_time: int) -> ChargeSchedule:
    """Tworzy testowy harmonogram ładowania"""
    return ChargeSchedule(
        enabled=True,
        start_time=start_time,
        end_time=end_time,
        start_enabled=True,
        end_enabled=True,
        lat=52.334215,
        lon=20.937516,
        days_of_week="All"
    )

def test_no_overlaps():
    """Test: Brak nakładań - harmonogramy powinny zostać bez zmian"""
    print("\n🧪 TEST 1: Brak nakładań")
    print("-" * 50)
    
    # Przygotuj testowe harmonogramy bez nakładań
    schedules = [
        create_test_schedule(12*60, 13*60),      # 12:00-13:00
        create_test_schedule(18*60, 19*60),      # 18:00-19:00  
        create_test_schedule(20*60, 21*60),      # 20:00-21:00
    ]
    
    monitor = CloudTeslaMonitor()
    result = monitor._resolve_schedule_overlaps(schedules, "TEST1234")
    
    # Sprawdź rezultat
    assert len(result) == 3, f"Oczekiwano 3 harmonogramów, otrzymano {len(result)}"
    print(f"✅ SUKCES: {len(result)} harmonogramów bez zmian")
    return True

def test_overlapping_schedules():
    """Test: Nakładające się harmonogramy - pierwszy ma priorytet"""
    print("\n🧪 TEST 2: Nakładające się harmonogramy")
    print("-" * 50)
    
    # Przygotuj testowe harmonogramy z nakładaniami (jak w przykładzie użytkownika)
    schedules = [
        create_test_schedule(12*60, 13*60 + 14),  # 12:00-13:14 (priorytet #1)
        create_test_schedule(11*60, 15*60),       # 11:00-15:00 (priorytet #2, nakłada się z #1)
    ]
    
    monitor = CloudTeslaMonitor()
    result = monitor._resolve_schedule_overlaps(schedules, "TEST1234")
    
    # Sprawdź rezultat - powinien zostać tylko pierwszy harmonogram
    assert len(result) == 1, f"Oczekiwano 1 harmonogram, otrzymano {len(result)}"
    assert result[0].start_time == 12*60, f"Oczekiwano start_time=720, otrzymano {result[0].start_time}"
    assert result[0].end_time == 13*60 + 14, f"Oczekiwano end_time=794, otrzymano {result[0].end_time}"
    
    print(f"✅ SUKCES: Zachowano harmonogram z priorytetem #1 (12:00-13:14)")
    return True

def test_multiple_overlaps():
    """Test: Wiele nakładających się harmonogramów"""
    print("\n🧪 TEST 3: Wiele nakładających się harmonogramów")
    print("-" * 50)
    
    # Przygotuj testowe harmonogramy (jak w przykładzie z dokumentacji)
    schedules = [
        create_test_schedule(13*60, 13*60 + 45),  # 13:00-13:45 (priorytet #1)
        create_test_schedule(13*60, 15*60),       # 13:00-15:00 (priorytet #2, nakłada się z #1)
        create_test_schedule(20*60, 21*60),       # 20:00-21:00 (priorytet #3, bez nakładania)
        create_test_schedule(12*60, 14*60),       # 12:00-14:00 (priorytet #4, nakłada się z #1 i #2)
        create_test_schedule(18*60, 18*60 + 30),  # 18:00-18:30 (priorytet #5, bez nakładania)
    ]
    
    monitor = CloudTeslaMonitor()
    result = monitor._resolve_schedule_overlaps(schedules, "TEST1234")
    
    # Sprawdź rezultat - powinny zostać harmonogramy #1, #3, #5
    assert len(result) == 3, f"Oczekiwano 3 harmonogramy, otrzymano {len(result)}"
    
    # Sprawdź czy zachowano właściwe harmonogramy (w kolejności priorytetów)
    expected_times = [
        (13*60, 13*60 + 45),  # 13:00-13:45 (priorytet #1)
        (20*60, 21*60),       # 20:00-21:00 (priorytet #3)
        (18*60, 18*60 + 30),  # 18:00-18:30 (priorytet #5)
    ]
    
    for i, (exp_start, exp_end) in enumerate(expected_times):
        assert result[i].start_time == exp_start, f"Harmonogram {i+1}: oczekiwano start_time={exp_start}, otrzymano {result[i].start_time}"
        assert result[i].end_time == exp_end, f"Harmonogram {i+1}: oczekiwano end_time={exp_end}, otrzymano {result[i].end_time}"
    
    print(f"✅ SUKCES: Zachowano 3 harmonogramy bez nakładań (priorytety #1, #3, #5)")
    return True

def test_midnight_crossing():
    """Test: Harmonogramy przechodzące przez północ"""
    print("\n🧪 TEST 4: Harmonogramy przechodzące przez północ")
    print("-" * 50)
    
    # Harmonogram przechodzący przez północ (23:30-00:30)
    schedules = [
        create_test_schedule(23*60 + 30, 24*60 + 30),  # 23:30-00:30 (1470 minut)
        create_test_schedule(0*60, 1*60),               # 00:00-01:00 (nakłada się)
    ]
    
    monitor = CloudTeslaMonitor()
    result = monitor._resolve_schedule_overlaps(schedules, "TEST1234")
    
    # Sprawdź rezultat - powinien zostać pierwszy harmonogram
    assert len(result) == 1, f"Oczekiwano 1 harmonogram, otrzymano {len(result)}"
    assert result[0].start_time == 23*60 + 30, f"Oczekiwano start_time=1410, otrzymano {result[0].start_time}"
    
    print(f"✅ SUKCES: Poprawnie obsłużono przejście przez północ")
    return True

def main():
    """Uruchom wszystkie testy"""
    print("🚀 === TEST ROZWIĄZYWANIA NAKŁADAJĄCYCH SIĘ HARMONOGRAMÓW ===")
    
    tests = [
        test_no_overlaps,
        test_overlapping_schedules,
        test_multiple_overlaps,
        test_midnight_crossing,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ BŁĄD w teście {test.__name__}: {e}")
            failed += 1
    
    print(f"\n📊 === WYNIKI TESTÓW ===")
    print(f"✅ Przeszły: {passed}")
    print(f"❌ Niepowodzenia: {failed}")
    print(f"📈 Sukces: {passed}/{passed + failed}")
    
    if failed == 0:
        print("\n🎉 WSZYSTKIE TESTY PRZESZŁY POMYŚLNIE!")
        return True
    else:
        print(f"\n⚠️ NIEKTÓRE TESTY NIEUDANE ({failed}/{passed + failed})")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 