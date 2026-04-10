# 🕒 Dynamiczny Cloud Scheduler dla Special Charging

## 📋 **ROZWIĄZANIE PROBLEMU**

**Problem:** System Special Charging obliczał optymalny harmonogram (np. 02:19-06:00) i czas wysłania (00:19), ale **nie było mechanizmu uruchamiającego worker o wyznaczonej godzinie**.

**Rozwiązanie:** **Dynamiczne Cloud Scheduler Jobs** - system tworzy tymczasowe Cloud Scheduler jobs na każdą godzinę `send_schedule_at` i `charging_end + 30min`.

---

## 🎯 **ARCHITEKTURA ROZWIĄZANIA**

### **WORKFLOW:**
```
23:00 - Daily check oblicza plan (send_schedule_at=00:19, charging_start=02:19)
23:01 - Tworzy session w Firestore (status=SCHEDULED)
23:02 - Tworzy DWA dynamic jobs:
        • Send job na 00:19
        • Cleanup job na 06:30 (charging_end + 30min)
00:19 - Send job: wybudza pojazd + harmonogram + usuwa siebie
02:19 - Pojazd rozpoczyna ładowanie (Scout ZABLOKOWANY)
06:00 - Ładowanie kończy się
06:30 - Cleanup job: przywraca limit + status COMPLETED + usuwa siebie
06:31 - KONIEC! Zero waste cleanup calls
```

### **KOMPONENTY:**

#### **1. Enhanced Worker Service**
- **Send endpoint:** `/send-special-schedule` - obsługuje wywołania send jobs
- **Cleanup endpoint:** `/cleanup-single-session` - one-shot cleanup dla konkretnej sesji
- **Wake mechanism:** Wybudzanie pojazdu przed wysłaniem harmonogramu
- **Dynamic job management:** Tworzenie i usuwanie scheduler jobs

#### **2. Dynamic Cloud Scheduler Jobs**
- **Send job:** Automatyczne tworzenie podczas planowania harmonogramu
- **Cleanup job:** One-shot cleanup dokładnie charging_end + 30min
- **Cron expression:** Generowany z `send_schedule_at` i `charging_end`
- **Target:** Worker Service endpoints (`/send-special-schedule`, `/cleanup-single-session`)
- **Self-cleaning:** Jobs automatycznie usuwają siebie po wykonaniu

#### **3. ❌ DEPRECATED: Enhanced Cleanup System** 
~~- **Częstotliwość:** Co 30 minut (całodobowo)~~
~~- **Funkcje:** Expired sessions + orphaned dynamic jobs + charge limits~~
~~- **Cloud Scheduler job:** `tesla-special-charging-cleanup`~~

**✅ ZASTĄPIONE PRZEZ:** One-shot cleanup jobs (98% cost savings)

---

## 🔧 **IMPLEMENTACJA**

### **A. Worker Service - Metody:**

#### `_handle_send_special_schedule()`
```python
# Endpoint wywoływany przez send dynamic job
# 1. Wybudza pojazd
# 2. Wysyła harmonogram  
# 3. Usuwa send job (siebie)
```

#### `_handle_cleanup_single_session()`
```python
# Endpoint wywoływany przez cleanup dynamic job
# 1. Przywraca charge limit
# 2. Status ACTIVE -> COMPLETED
# 3. Usuwa cleanup job (siebie)
```

#### `_create_dynamic_scheduler_job(charging_plan, session_id)`
```python
# Tworzy send job
# - Cron expression z send_schedule_at  
# - Target: /send-special-schedule
# - Body: {"session_id": "special_1_20250807_0700"}
```

#### `_create_cleanup_dynamic_scheduler_job(charging_plan, session_id)`
```python
# Tworzy cleanup job
# - Cron expression z charging_end + 30min
# - Target: /cleanup-single-session
# - Body: {"session_id": "special_1_20250807_0700"}
```

#### `_wake_vehicle_for_special_charging(session_id)`
```python
# NOWE! Wybudzanie pojazdu przed wysłaniem harmonogramu
# wake_up_vehicle(use_proxy=True)
```

### **B. Modified Logic - `_process_special_charging_need()`:**

**PRZED:**
```python
if _should_send_schedule_now():
    # Wyślij od razu
else:
    # Tylko loguj "zostanie wysłany za X godzin"
```

**PO:**
```python
if _should_send_schedule_now():
    # Wyślij od razu
else:
    # 1. Utwórz session w Firestore
    # 2. Utwórz send dynamic job
    # 3. Utwórz cleanup dynamic job  
    # 4. Loguj "dynamic jobs utworzone"
```

---

## ⚙️ **KONFIGURACJA**

### **1. Zmienne Środowiskowe (Worker Service):**
```yaml
# cloud-run-service-worker.yaml
env:
- name: GOOGLE_CLOUD_PROJECT
  value: "your-project-id"
- name: GOOGLE_CLOUD_LOCATION  
  value: "europe-west1"
- name: WORKER_SERVICE_URL
  value: "https://tesla-worker-1005200689027.europe-west1.run.app"
```

### **2. Dependencies:**
```txt
# requirements_cloud.txt
google-cloud-scheduler>=2.16.0  # NEEDED!
```

### **3. ❌ DEPRECATED Cloud Scheduler Jobs:**
```bash
# USUŃ stary cleanup job (jeśli istnieje):
gcloud scheduler jobs delete tesla-special-charging-cleanup --location=europe-west1

# Zachowaj tylko daily check:
# A. Istniejący - daily check (23:00)
gcloud scheduler jobs create http tesla-special-charging-daily-check
```

---

## ✅ **SPEŁNIENIE ZAŁOŻEŃ**

### **✅ 1. Wybudzanie pojazdu o wskazanej godzinie:**
```python
def _wake_vehicle_for_special_charging(session_id: str) -> bool:
    # wake_up_vehicle(use_proxy=True)
    # Loguje: "🔄 [SPECIAL] Budzenie pojazdu 0971 dla session special_1_..."
```

### **✅ 2. Harmonogram i limit wysłany:**
```python
# Używa istniejącej logiki _send_special_charging_schedule()
# - Ustawia charge limit
# - Wysyła harmonogram Tesla
# - Aktualizuje session status: SCHEDULED -> ACTIVE
```

### **✅ 3. Scout zablokowany podczas ładowania:**
```python
# Existing: _check_active_special_charging_session()
# Sprawdza czy charging_start <= current_time <= charging_end
# Blokuje normalne OFF PEAK API calls
```

### **✅ 4. One-shot cleanup po zakończeniu:**
```python
# One-shot cleanup dokładnie charging_end + 30min:
# - Wykrywa ACTIVE sessions
# - Przywraca original_charge_limit
# - Status: ACTIVE -> COMPLETED
# - Usuwa cleanup job (siebie)
# - Scout i Worker działają normalnie
```

---

## 🚀 **WDROŻENIE**

### **KROK 1: Wdróż Worker Service**
```bash
# Nowa wersja z one-shot cleanup functionality
./deploy_scout_worker.sh
```

### **KROK 2: Usuń stary cleanup (jeśli istnieje)**
```bash
gcloud scheduler jobs delete tesla-special-charging-cleanup --location=europe-west1
```

### **KROK 3: Test**
```bash
# Manual trigger daily check
curl -X POST https://tesla-worker-1005200689027.europe-west1.run.app/daily-special-charging-check

# Sprawdź logi
gcloud logs read "resource.type=cloud_run_revision" --limit=50 | grep "\[SPECIAL\]"

# Sprawdź dynamic scheduler jobs (powinny być 2 na session)
gcloud scheduler jobs list --location=europe-west1 | grep special-
``` 