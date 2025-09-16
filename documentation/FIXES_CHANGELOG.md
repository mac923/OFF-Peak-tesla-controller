# 🔧 Tesla Monitor - Historia Naprawek i Ulepszeń

**Kompletny changelog wszystkich naprawek i ulepszeń systemu Tesla Monitor w architekturze Scout & Worker.**

---

## 📅 **2025-09-11: NAPRAWKA V2 - Uniwersalne wybudzenie pojazdu offline**

### **Problem:**
Worker wykonywał bezsensowne cykle na pojeździe offline, nie wybudzając go wcześniej.

### **Przyczyna:**
- Naprawka V1 była dodana do `_handle_scout_trigger()` 
- Scout używa endpoint `/run-cycle` zamiast `/scout-trigger`
- Naprawka V1 nigdy się nie wykonała w rzeczywistości

### **Rozwiązanie:**
Dodano uniwersalną logikę do `run_monitoring_cycle()`:
```python
# Jeśli Worker został wywołany a pojazd jest offline → ZAWSZE wybudź pojazd
if not is_online:
    # Łączy z Tesla API, wybudza pojazd Fleet API, czeka 5s, pobiera nowy status
    wake_result = self._wake_vehicle_if_needed(vehicle_vin)
```

### **Korzyści:**
- **Uniwersalne**: Działa z każdym endpoint `/run-cycle`, `/scout-trigger`
- **Proste**: Bez analizowania `reason` od Scout
- **Zawsze skuteczne**: Jeśli Worker działa na offline pojazd → wybudź go

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Wdrożenie:** Scout Function rev tesla-scout-00103-qad, Worker Service rev latest

---

## 📅 **2025-01-09: Nowa sekwencja zarządzania harmonogramami v3.0**

### **Problem:**
Poprzednia sekwencja zawierała niepotrzebne komendy `charge_start`/`charge_stop` i była zbyt skomplikowana.

### **Stara sekwencja (v2.0):**
1. Pobierz harmonogramy → 2. Zatrzymaj ładowanie → 3. Usuń stare → 4. Przygotuj nowe → 5. Sprawdź nakładanie → 6. Wyślij charge_start → 7. Dodaj nowe

### **Nowa sekwencja (v3.0):**
1. Pobierz harmonogramy → 2. Przygotuj nowe → 3. **Dodaj nowe** → 4. **Usuń stare**

### **Eliminowane funkcje:**
- `_detect_current_time_overlap()` - 65 linii
- `_send_charge_start_command()` - 45 linii  
- `_remove_home_schedules_from_tesla()` - logika charge_stop
- `charge_start()`, `charge_stop()`, `start_charging()`, `stop_charging()` - 280 linii

### **Korzyści:**
- **43% mniej punktów awarii** (4 vs 7 kroków)
- **Eliminacja konfliktów** między komendami a harmonogramami
- **Tesla sama zarządza ładowaniem** na podstawie harmonogramów

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Rezultat:** System prostszy, bardziej niezawodny, szybszy

---

## 📅 **2025-01-09: Naprawka HTTP 403 PERMISSION_DENIED dla special charging**

### **Problem:**
Dynamiczne Cloud Scheduler jobs dla special charging zwracały błąd 403 przy wywołaniu endpoints.

### **Przyczyna:**
Dynamiczne jobs tworzone przez Worker Service nie miały autoryzacji OIDC.

### **Rozwiązanie:**
Dodano `oidc_token` z `service_account_email` do funkcji:
- `_create_dynamic_scheduler_job()` (linia ~1165)
- `_create_cleanup_dynamic_scheduler_job()` (linia ~1238)

```python
"oidc_token": {
    "service_account_email": f"{PROJECT_ID}@appspot.gserviceaccount.com"
}
```

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Rezultat:** Special charging jobs działają poprawnie bez błędów autoryzacji

---

## 📅 **2025-01-08: Ulepszenie sekwencji AUTO CHARGE START v2.0**

### **Problem:**
Luka czasowa 3-5 sekund między wysłaniem `charge_start` a dodaniem harmonogramów.

### **Rozwiązanie:**
Odwrócono kolejność - `charge_start` jest wysyłany **PRZED** dodaniem harmonogramów:

```python
# STARA KOLEJNOŚĆ:
# 1. Dodaj harmonogramy → 2. Sprawdź nakładanie → 3. Wyślij charge_start

# NOWA KOLEJNOŚĆ:
# 1. Sprawdź nakładanie → 2. Wyślij charge_start → 3. Dodaj harmonogramy
```

### **Korzyści:**
- **Eliminacja luki czasowej** 3-5 sekund
- **Natychmiastowe rozpoczęcie ładowania** przy nakładających harmonogramach

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Rezultat:** System 3-5 sekund szybszy w rozpoczynaniu ładowania

---

## 📅 **2025-01-08: Naprawka kolizji Scout vs Special Charging**

### **Problem:**
Scout usuwał harmonogramy special charging gdy session była ACTIVE ale przed rozpoczęciem ładowania.

### **Przykład problemu:**
- Session ACTIVE o 03:00, ładowanie 05:00-05:36
- Scout check o 03:XX usuwał harmonogram przed rozpoczęciem ładowania

### **Przyczyna:**
Funkcja `_check_active_special_charging_session()` blokowała tylko sessions w czasie ładowania:
```python
# BŁĘDNA LOGIKA:
charging_start <= current_time <= charging_end
```

### **Rozwiązanie:**
Zmieniono logikę aby blokować **WSZYSTKIE** sessions ACTIVE:
```python
# POPRAWNA LOGIKA:
if status == 'ACTIVE':
    return True  # Zawsze blokuj ACTIVE sessions
```

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Rezultat:** Scout chroni harmonogramy special charging od momentu wysłania przez dynamic job

---

## 📅 **2025-08-05: Nowy mechanizm fallback i harmonogramy Cloud Scheduler**

### **Zmiany:**

#### **1. NOWY FALLBACK MECHANIZM:**
- **Stary:** 15-minutowy slot +12h (duży impact na baterię)
- **Nowy:** 1-minutowy slot ładowania 23:59-00:00

#### **2. HARMONOGRAMY CLOUD SCHEDULER:**
Wszystkie 3 harmonogramy zmieniono ze strefy UTC na Europe/Warsaw:
- `tesla-worker-daily-check` - nocne wybudzenie
- `tesla-scout-location-check` - Scout check  
- `tesla-worker-emergency` - emergency

### **Korzyści:**
- **Pojazd budzony ZAWSZE o północy** czasu warszawskiego niezależnie od pory roku
- **Minimalny 1-minutowy slot** zamiast 15-minutowego przed północą

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Wdrożenie:** Worker Service rewizja tesla-worker-00007-kbx

---

## 📅 **2025-08-01: Centralized token management w Scout & Worker**

### **Problem:**
Scout i Worker miały niezależne systemy zarządzania tokenami Tesla, powodując konflikty refresh tokenów.

### **Rozwiązanie - Architektura hybrydowa v3.1:**
- **Scout normalnie:** Secret Manager bezpośrednio (niskie koszty)
- **Gdy tokeny wygasłe:** Scout → Worker `/refresh-tokens` → Secret Manager
- **Worker:** Centralnie zarządza tokenami

### **Mechanizmy ochronne:**
- **Rate limiting:** 1 próba/min
- **Timeout:** 45s
- **Connection error handling**
- **Cache clearing**

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Rezultat:** Scout już nigdy nie "stoi" z błędami 401 - automatycznie odświeża tokeny

---

## 📅 **2025-08-01: Architektura Scout & Worker na Google Cloud**

### **Wdrożenie:**
- **Scout Function:** https://tesla-scout-74pl3bqokq-ew.a.run.app (Cloud Function, co 15min)
- **Worker Service:** https://tesla-worker-74pl3bqokq-ew.a.run.app (Cloud Run+Docker, on-demand)
- **Cloud Scheduler:** 3 harmonogramy (Scout co 15min, Worker failsafe 00:00 UTC, emergency niedziela 12:00)

### **Korzyści:**
- **96% oszczędność kosztów** (z 6zł na 20 groszy dziennie)
- **Centralne zarządzanie tokenami** przez Worker
- **Tesla connection active, Smart Proxy available**

### **Status:** ✅ WDROŻONE POMYŚLNIE
**Rezultat:** Architektura scout-worker-optimized w pełni operacyjna

---

## 📅 **Starsze naprawki (2024-2025):**

### **🔧 Problem GPS lokalizacji w SCOUT**
**Rozwiązano:** Błędny format parametru `endpoints` - używano kombinacji zamiast pojedynczego `location_data`

### **🔧 Scout Function błędy 408 Request Timeout**
**Rozwiązano:** Implementacja prawidłowego flow Tesla Fleet API - sprawdzanie stanu przed pobieraniem danych

### **🔧 Problem błędu 412 "not supported"**
**Rozwiązano:** Wdrożenie Smart Proxy Mode - Tesla HTTP Proxy uruchamiany on-demand

### **🔧 Pojazd ładował do górnego limitu po usunięciu harmonogramów**
**Rozwiązano:** Dodano `charge_stop` przed usunięciem harmonogramów podczas ładowania

### **🔧 Do pojazdu docierał tylko ostatni harmonogram**
**Rozwiązano:** 
- Obsługa przejścia przez północ (23:00-00:00)
- 3s opóźnienia między harmonogramami  
- Weryfikacja po dodaniu harmonogramów

### **🔧 Problem z pobieraniem harmonogramów z Tesla Fleet API**
**Rozwiązano:** Dodano scope `vehicle_location` w Tesla Developer Portal

---

## 📊 **Podsumowanie ulepszeń:**

### **Architektura:**
- **Scout & Worker:** 96% oszczędność kosztów
- **Centralne zarządzanie tokenów:** Eliminacja konfliktów 401
- **Automatyczne fallback:** Odświeżanie wygasłych tokenów

### **Harmonogramy:**
- **Nowa sekwencja v3.0:** 43% mniej punktów awarii
- **Eliminacja charge commands:** Prostsze zarządzanie
- **Ochrona special charging:** Brak kolizji z Scout

### **Niezawodność:**
- **Uniwersalne wybudzenie:** Zawsze wybudź offline pojazd
- **Smart Proxy Mode:** On-demand Tesla HTTP Proxy
- **Mechanizmy ochronne:** Rate limiting, timeout, error handling

### **Monitoring:**
- **Szczegółowe logowanie:** Łatwiejsze debugowanie
- **Cloud Scheduler:** Prawidłowe strefy czasowe
- **Health checks:** Monitoring stanu systemu

---

**✅ Wszystkie naprawki zostały pomyślnie wdrożone i system Tesla Monitor w architekturze Scout & Worker działa stabilnie z maksymalnymi oszczędnościami kosztów.** 