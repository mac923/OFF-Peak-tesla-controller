# 🔋 Tesla Special Charging - Instrukcja Wdrożenia

Kompletny przewodnik implementacji systemu zarządzania wyjątkowymi potrzebami naładowania pojazdu Tesla przez Google Sheets.

## 📋 **KROK 1: Przygotowanie Google Sheets**

### A. Stwórz arkusz kalkulacyjny:
1. Przejdź do: https://sheets.google.com
2. Kliknij: "Utwórz nowy arkusz kalkulacyjny"
3. Nazwij arkusz: **"Tesla Special Charging"**

### B. Struktura arkusza:

Utwórz nagłówki w pierwszym wierszu:

| **A1: Data** | **B1: Godzina** | **C1: Docelowy %** | **D1: Status** | **E1: Utworzono** | **F1: Ostatnia aktualizacja** |
|--------------|-----------------|-------------------|----------------|-------------------|-------------------------------|

### C. Przykładowe dane (wiersze 2-4):

```
Data        Godzina    Docelowy %    Status     Utworzono           Ostatnia aktualizacja
2024-01-22  07:00      85            ACTIVE     2024-01-20 14:30    
2024-01-25  15:30      95            PLANNED    2024-01-20 16:45    
2024-01-28  08:00      90            ACTIVE     2024-01-21 10:15    
```

### D. Udostępnij arkusz:
1. Kliknij **"Udostępnij"** (prawy górny róg)
2. Ustaw: **"Wszyscy użytkownicy z linkiem" → "Przeglądający"**
3. **Skopiuj link** - będzie potrzebny w konfiguracji

---

## 🔑 **KROK 2: Konfiguracja Google Service Account**

### A. Utwórz Service Account:
```bash
gcloud iam service-accounts create tesla-special-charging \
  --display-name="Tesla Special Charging Google Sheets" \
  --description="Service Account for Tesla Special Charging Google Sheets API"
```

### B. Wygeneruj klucz:
```bash
gcloud iam service-accounts keys create tesla-sheets-key.json \
  --iam-account=tesla-special-charging@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### C. Dodaj Service Account do arkusza:
1. Otwórz plik `tesla-sheets-key.json`
2. Skopiuj adres email `client_email` (np. `tesla-special-charging@projekt.iam.gserviceaccount.com`)
3. W Google Sheets kliknij **"Udostępnij"**
4. Dodaj ten email z uprawnieniami **"Przeglądający"**

---

## 🔧 **KROK 3: Konfiguracja Google Cloud Secrets**

### A. Zapisz URL arkusza:
```bash
gcloud secrets create GOOGLE_SHEETS_URL \
  --data="https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit#gid=0"
```

### B. Zapisz klucz Service Account:
```bash
gcloud secrets create GOOGLE_SERVICE_ACCOUNT_KEY \
  --data-file=tesla-sheets-key.json
```

### C. Przyznaj dostęp Worker Service:
```bash
# Dla GOOGLE_SHEETS_URL
gcloud secrets add-iam-policy-binding GOOGLE_SHEETS_URL \
  --member="serviceAccount:YOUR_PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Dla GOOGLE_SERVICE_ACCOUNT_KEY  
gcloud secrets add-iam-policy-binding GOOGLE_SERVICE_ACCOUNT_KEY \
  --member="serviceAccount:YOUR_PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 🚀 **KROK 4: Wdrożenie Worker Service**

### A. Zaktualizuj konfigurację Worker Service:

Edytuj `cloud-run-service-worker.yaml` i dodaj nowe zmienne środowiskowe:

```yaml
# Dodaj po istniejących zmiennych środowiskowych:
- name: GOOGLE_SHEETS_URL
  valueFrom:
    secretKeyRef:
      name: GOOGLE_SHEETS_URL
      key: latest

- name: GOOGLE_SERVICE_ACCOUNT_KEY
  valueFrom:
    secretKeyRef:
      name: GOOGLE_SERVICE_ACCOUNT_KEY
      key: latest
```

### B. Wdroż Worker Service:
```bash
./deploy_scout_worker.sh
```

### C. Sprawdź czy działa:
```bash
# Test Worker Service health
curl https://YOUR_WORKER_SERVICE_URL/health

# Test nowego endpoint
curl -X POST https://YOUR_WORKER_SERVICE_URL/daily-special-charging-check \
  -H "Content-Type: application/json" \
  -d '{"trigger":"manual_test"}'
```

---

## ⏰ **KROK 5: Konfiguracja Cloud Scheduler**

### A. Wdroż nowy harmonogram:
```bash
# Zastąp YOUR_PROJECT_ID i YOUR_WORKER_SERVICE_URL
gcloud scheduler jobs create http tesla-special-charging-daily-check \
  --schedule="0 23 * * *" \
  --time-zone="Europe/Warsaw" \
  --uri="YOUR_WORKER_SERVICE_URL/daily-special-charging-check" \
  --http-method=POST \
  --headers="Content-Type=application/json" \
  --message-body='{"trigger":"cloud_scheduler_special_charging","action":"daily_special_charging_check"}' \
  --oidc-service-account-email="YOUR_PROJECT_ID@appspot.gserviceaccount.com"
```

### B. Sprawdź harmonogram:
```bash
gcloud scheduler jobs list --location=europe-west1
```

### C. Test harmonogramu:
```bash
gcloud scheduler jobs run tesla-special-charging-daily-check --location=europe-west1
```

---

## 🧪 **KROK 6: Test systemu**

### A. Dodaj test do Google Sheets:
1. Otwórz swój arkusz Google Sheets
2. Dodaj nowy wiersz:
   ```
   Data: 2024-01-22 (jutrzejsza data)
   Godzina: 07:00
   Docelowy %: 85
   Status: ACTIVE
   ```

### B. Wykonaj manual test:
```bash
# Test daily check
curl -X POST https://YOUR_WORKER_SERVICE_URL/daily-special-charging-check \
  -H "Content-Type: application/json" \
  -d '{"trigger":"manual_test","action":"daily_special_charging_check"}'
```

### C. Sprawdź logi:
```bash
# Worker Service logs
gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=tesla-worker" \
  --limit=50 --format='value(textPayload)' | grep -i special

# Cloud Scheduler logs
gcloud logs read "resource.type=cloud_scheduler_job" --limit=10
```

---

## 📊 **KROK 7: Monitorowanie i weryfikacja**

### A. Sprawdź Firestore (special charging sessions):
```bash
# Za pomocą gcloud firestore
gcloud firestore collections list

# Sprawdź sessions
gcloud firestore documents list special_charging_sessions --limit=5
```

### B. Sprawdź logi aplikacji:
```bash
# Szukaj wpisów SPECIAL w logach
gcloud logs read --limit=100 --format='value(textPayload)' | grep "\[SPECIAL\]"
```

### C. Sprawdź harmonogramy Tesla:
- Otwórz aplikację mobilną Tesla
- Przejdź do: **Ładowanie → Harmonogramy ładowania**
- Sprawdź czy pojawiły się nowe harmonogramy

---

## 🎯 **KROK 8: Jak używać systemu**

### A. Planowanie wyjątkowego ładowania:

1. **Otwórz Google Sheets**
2. **Dodaj nowy wiersz:**
   - **Data:** Kiedy potrzebujesz naładowany samochód (YYYY-MM-DD)
   - **Godzina:** O której godzinie (HH:MM)  
   - **Docelowy %:** Ile procent baterii (50-100)
   - **Status:** `ACTIVE` (system będzie obsługiwać)

### B. Przykłady użycia:

```
# Wyjazd służbowy jutro rano
Data: 2024-01-22  Godzina: 07:00  Docelowy %: 85  Status: ACTIVE

# Długa podróż w weekend  
Data: 2024-01-25  Godzina: 15:30  Docelowy %: 95  Status: ACTIVE

# Planowany wyjazd na przyszłą niedzielę
Data: 2024-01-28  Godzina: 08:00  Status: PLANNED (zmień na ACTIVE bliżej daty)
```

### C. Statusy wierszy:
- **`ACTIVE`** - System aktywnie obsługuje tę potrzebę
- **`PLANNED`** - Zaplanowane na przyszłość (nie aktywne)
- **`COMPLETED`** - Zakończone (system aktualizuje automatycznie)
- **`CANCELLED`** - Anulowane (jeśli chcesz anulować)

---

## ⚡ **Jak działa system**

### Automatyczny workflow:

1. **23:00 codziennie** - System sprawdza Google Sheets
2. **Znajduje potrzeby** na najbliższe 48h ze statusem `ACTIVE`
3. **Oblicza optymalny harmonogram** unikając godzin peak (6:00-10:00, 19:00-22:00)
4. **W odpowiednim czasie** (2h przed ładowaniem):
   - Zwiększa charge limit w pojeździe (jeśli potrzeba)
   - Wysyła harmonogram ładowania do Tesla
   - Zapisuje session w Firestore
5. **Po zakończeniu ładowania**:
   - Przywraca oryginalny charge limit
   - Aktualizuje status w Google Sheets na `COMPLETED`

### Zabezpieczenia:
- **Blokuje normalne OFF PEAK API** podczas special charging
- **Cleanup expired sessions** automatycznie
- **Fallback mechanisms** w przypadku błędów
- **Peak hours avoidance** - unika drogich godzin energii
- **Safety buffer** - 1.5h dodatkowy czas ładowania

---

## 🚨 **Rozwiązywanie problemów**

### A. Google Sheets nie działa:
```bash
# Sprawdź czy sekrety są dostępne
gcloud secrets versions access latest --secret="GOOGLE_SHEETS_URL"
gcloud secrets versions access latest --secret="GOOGLE_SERVICE_ACCOUNT_KEY"

# Sprawdź uprawnienia Service Account w arkuszu
```

### B. Harmonogramy nie są wysyłane:
```bash
# Sprawdź logi special charging
gcloud logs read --limit=100 | grep -i "special\|SPECIAL"

# Sprawdź czy Tesla HTTP Proxy działa
curl https://YOUR_WORKER_SERVICE_URL/worker-status
```

### C. Pojazd nie ładuje się:
- Sprawdź czy pojazd jest w domu i podłączony
- Sprawdź charge limit w aplikacji Tesla
- Sprawdź harmonogramy w aplikacji Tesla
- Sprawdź logi Firestore sessions

---

## 🎉 **Gotowe!**

System Tesla Special Charging jest teraz w pełni funkcjonalny! 

**Najważniejsze korzyści:**
- ✅ Prosty interfejs Google Sheets  
- ✅ Automatyczne planowanie harmonogramów
- ✅ Unikanie drogich godzin energii
- ✅ Inteligentne zarządzanie charge limits
- ✅ Zabezpieczenia przed konfliktami
- ✅ Monitoring i cleanup automatyczny

**Przykład sukcesu:**
```
21.01 19:00 - Dodajesz do Sheets: "85% na 22.01 07:00"
21.01 23:00 - System planuje ładowanie 01:00-05:12
21.01 23:01 - Wysyła harmonogram do pojazdu  
22.01 01:00 - Pojazd rozpoczyna ładowanie
22.01 05:12 - Ładowanie kończy się (85% baterii)
22.01 07:00 - Gotowy do wyjazdu! 🚗⚡
``` 