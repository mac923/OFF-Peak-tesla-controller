# NAPRAWKA: Cloud Scheduler Timezone - Nocne sprawdzenie o 00:00 czasu warszawskiego

## 🔍 PROBLEM WYKRYTY

Aplikacja wykonywała nocne sprawdzenie o godzinie **2:00 czasu warszawskiego** zamiast **00:00 czasu warszawskiego**.

### Przyczyna
Cloud Scheduler jobs były skonfigurowane z `--time-zone="UTC"` zamiast `--time-zone="Europe/Warsaw"`.

**Efekt:**
- 00:00 UTC = 2:00 czasu warszawskiego (zimą) lub 1:00 (latem)
- Pojazd był budzony o niewłaściwej porze

### Logi błędne
```
INFO 2025-08-13T00:00:15.852275Z [02:00] ✅ VIN=0971, bateria=79%, ładowanie=gotowe, lokalizacja=HOME
INFO 2025-08-13T00:00:15.852295Z Tesla Monitor: Midnight status check completed
INFO 2025-08-13T00:00:15.889376Z [02:00] ✅ nocne sprawdzenie - VIN=0971, bateria=79%, ładowanie=gotowe, lokalizacja=HOME
```

## ✅ ROZWIĄZANIE WDROŻONE

### 1. Aktualizacja deploy_scout_worker.sh

**Przed:**
```bash
--time-zone="UTC"
--message-body='{"trigger":"cloud_scheduler_worker_failsafe","action":"midnight_wake_and_check","time":"00:00_UTC","force_full_check":true}'
--description="Tesla Worker - dzienny failsafe i nocne wybudzenie (koszt: ~kilka groszy)"
```

**Po:**
```bash
--time-zone="Europe/Warsaw"
--message-body='{"trigger":"cloud_scheduler_worker_failsafe","action":"midnight_wake_and_check","time":"00:00_Warsaw","force_full_check":true}'
--description="Tesla Worker - dzienny failsafe i nocne wybudzenie o 00:00 czasu warszawskiego"
```

### 2. Aktualizacja deploy_optimized.sh

**Przed:**
```bash
--time-zone="UTC"
--message-body='{"trigger":"cloud_scheduler_midnight","action":"wake_vehicle","time":"00:00_UTC"}'
--description="Tesla Monitor - nocne wybudzenie pojazdu (00:00 UTC)"
```

**Po:**
```bash
--time-zone="Europe/Warsaw"
--message-body='{"trigger":"cloud_scheduler_midnight","action":"wake_vehicle","time":"00:00_Warsaw"}'
--description="Tesla Monitor - nocne wybudzenie pojazdu o 00:00 czasu warszawskiego"
```

### 3. Aktualizacja dokumentacji

- **OPTYMALIZACJA_KOSZTOW_CLOUD_RUN.md**: Harmonogramy zaktualizowane na Europe/Warsaw
- **Komunikaty końcowe**: Wszystkie skrypty deploy informują o czasie warszawskim

## 🎯 REZULTAT

Po wdrożeniu poprawek:
- Nocne sprawdzenie będzie wykonywane dokładnie o **00:00 czasu warszawskiego**
- Niezależnie od pory roku (czas zimowy/letni) 
- Zgodnie z intencją użytkownika

### Oczekiwane logi po naprawce
```
INFO 2025-08-13T22:00:15.852275Z [00:00] ✅ VIN=0971, bateria=79%, ładowanie=gotowe, lokalizacja=HOME
INFO 2025-08-13T22:00:15.852295Z Tesla Monitor: Midnight status check completed
INFO 2025-08-13T22:00:15.889376Z [00:00] ✅ nocne sprawdzenie - VIN=0971, bateria=79%, ładowanie=gotowe, lokalizacja=HOME
```

## 📋 PLIKI ZMODYFIKOWANE

1. **deploy_scout_worker.sh** - Cloud Scheduler timezone dla Worker failsafe
2. **deploy_optimized.sh** - Cloud Scheduler timezone dla wszystkich harmonogramów
3. **documentation/OPTYMALIZACJA_KOSZTOW_CLOUD_RUN.md** - Aktualizacja dokumentacji

## 🚀 WDROŻENIE

**UWAGA:** Zmiany są gotowe w kodzie, ale **NIE zostały jeszcze wdrożone na Google Cloud**.

Aby wdrożyć poprawki:
```bash
# Dla architektury Scout & Worker
./deploy_scout_worker.sh

# Lub dla architektury standardowej
./deploy_optimized.sh
```

## ✅ WERYFIKACJA

Po wdrożeniu sprawdź logi aplikacji około północy czasu warszawskiego:
- Nocne sprawdzenie powinno wystąpić o 00:00 (nie o 02:00)
- Logi powinny pokazywać `[00:00]` zamiast `[02:00]`

## 📚 ZGODNOŚĆ Z PAMIĘCIĄ

Ta naprawka jest zgodna z pamięcią o fallback mechanizmie - pojazd będzie budzony **ZAWSZE o północy czasu warszawskiego** niezależnie od pory roku, zgodnie z architekturą Scout & Worker.

---

## 🔋 DODATKOWA NAPRAWKA: Special Charging Slot Selection

### 🔍 PROBLEM WYKRYTY W SPECIAL CHARGING

Aplikacja nie potrafiła znaleźć odpowiedniego slotu ładowania gdy standardowy slot kolidował z peak hours:

```
INFO 2025-08-12T22:01:14.893407Z 🔍 [SPECIAL] Najpóźniejszy możliwy start: 04:15
INFO 2025-08-12T22:01:14.893531Z 🔍 [SPECIAL] Sprawdzam slot 04:00-06:15 (start za 4.0h przed target)
INFO 2025-08-12T22:01:14.893545Z ⚠️ [SPECIAL] Slot 04:00-06:15 koliduje z peak hours 06:00-10:00
ERROR 2025-08-12T22:01:14.893582Z ❌ [SPECIAL] Nie znaleziono optymalnego slotu dla 2.2h ładowania
```

### ✅ ROZWIĄZANIE: Hierarchia Strategii Wyboru Slotu

Zaimplementowano 4-poziomową hierarchię strategii:

#### **STRATEGIA 1: Slot Optymalny** (najlepszy)
- Slot unikający w 100% peak hours
- Standardowy safety buffer 1.5h
- Przykład: 02:00-04:15 (unika peak hours 06:00-10:00)

#### **STRATEGIA 2: Slot Wcześniejszy** (dobry)
- Wcześniejsze sloty unikające peak hours
- Opcje: 22:00-01:00, 03:45-06:00, poprzedni wieczór
- Przykład: 03:45-06:00 (kończy przed peak hours)

#### **STRATEGIA 3: Minimalna Kolizja** (akceptowalny)
- Maksymalnie 50% czasu ładowania w peak hours
- Przykład: 05:00-07:15 (1.25h kolizji z 2.25h)

#### **STRATEGIA 4: Fallback** (ostateczność)
- Zapewnia docelowy poziom baterii mimo kolizji
- Minimalny buffer 0.5h zamiast 1.5h
- Przykład: 04:00-06:15 (gwarantuje target time)

### 🎯 REZULTAT NAPRAWKI SPECIAL CHARGING

Po wdrożeniu dla scenariusza z logów (2.2h ładowania, target 06:30):

**Oczekiwany wybór - STRATEGIA 2:**
```
✅ [SPECIAL] STRATEGIA 2: Używam wcześniejszy slot: 03:45-06:00 (unika peak hours)
```

**Lub w przypadku braku lepszych opcji - STRATEGIA 4:**
```
🚨 [SPECIAL] STRATEGIA 4 (FALLBACK): Wymuszam slot zapewniający target time: 04:00-06:15
🚨 [SPECIAL] Kolizja z peak hours: 0.25h (11.1%)
🚨 [SPECIAL] UZASADNIENIE: Zapewnia docelowy poziom baterii na czas!
```

### 📋 PLIKI ZMODYFIKOWANE (Special Charging)

1. **cloud_tesla_worker.py** - Nowa implementacja `_find_optimal_charging_slot()` z hierarchią strategii
2. **Nowe funkcje**:
   - `_find_slot_avoiding_peak_hours()` - STRATEGIA 1
   - `_find_earlier_slot()` - STRATEGIA 2  
   - `_find_minimal_collision_slot()` - STRATEGIA 3
   - `_create_fallback_slot()` - STRATEGIA 4
   - `_calculate_peak_collision()` - Oblicza kolizję z peak hours 