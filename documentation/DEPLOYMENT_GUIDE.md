# 🚀 Przewodnik Wdrożenia Tesla Monitor na Google Cloud

**Kompletny przewodnik wdrażania systemu Tesla Monitor w architekturze Scout & Worker na Google Cloud Platform.**

---

## 📋 Wymagania

### 1. Konto Google Cloud
- Aktywne konto Google Cloud z włączoną płatnością
- Utworzony projekt Google Cloud
- Zainstalowane Google Cloud SDK (`gcloud`)

### 2. Konfiguracja Tesla Fleet API
- Zarejestrowana aplikacja w Tesla Developer Portal
- Wygenerowane klucze prywatny i publiczny
- Skonfigurowana domena z dostępnym kluczem publicznym

### 3. Narzędzia lokalne
- Docker
- Git
- Bash (Linux/macOS) lub WSL (Windows)

### 4. API OFF PEAK CHARGE (opcjonalne)
- Klucz API do OFF PEAK CHARGE API
- URL endpoint API (jeśli inny niż domyślny)

---

## 🔧 Przygotowanie środowiska

### 1. Konfiguracja Google Cloud
```bash
# Zaloguj się do Google Cloud
gcloud auth login

# Ustaw domyślny projekt
export GOOGLE_CLOUD_PROJECT="twoj-project-id"
gcloud config set project $GOOGLE_CLOUD_PROJECT

# Ustaw region (zalecany: Europe West 1)
export GOOGLE_CLOUD_REGION="europe-west1"
gcloud config set run/region $GOOGLE_CLOUD_REGION
```

### 2. Włączenie wymaganych API
```bash
# Włącz wszystkie wymagane API
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

---

## 🔐 Konfiguracja Secret Manager

### 1. Sekrety Tesla Fleet API
```bash
# Klucz prywatny Fleet API (wymagany)
gcloud secrets create tesla-private-key --data-file=private-key.pem

# Konfiguracja Tesla Fleet API
gcloud secrets create tesla-client-id --data-string="twoj_client_id"
gcloud secrets create tesla-client-secret --data-string="twoj_client_secret"
gcloud secrets create tesla-domain --data-string="twoja_domena.com"
gcloud secrets create tesla-public-key-url --data-string="https://twoja_domena.com/.well-known/appspecific/com.tesla.3p.public-key.pem"

# Tokeny Tesla (będą zarządzane automatycznie przez Worker)
gcloud secrets create fleet-tokens --data-string='{}'
```

### 2. Lokalizacja domowa
```bash
# Współrzędne domowe (wymagane dla Scout)
gcloud secrets create home-latitude --data-string="52.334215"
gcloud secrets create home-longitude --data-string="20.937516"
gcloud secrets create home-radius --data-string="0.001"
```

### 3. Sekrety OFF PEAK CHARGE API (opcjonalne)
```bash
# Klucz API OFF PEAK CHARGE
gcloud secrets create OFF_PEAK_CHARGE_API_KEY --data-string="twoj_api_key"

# URL API OFF PEAK CHARGE (opcjonalny)
gcloud secrets create OFF_PEAK_CHARGE_API_URL --data-string="https://twoja-domena.com/api/external-calculate"
```

### 4. Konfiguracja uprawnień
```bash
# Pobierz numer projektu
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")

# Nadaj uprawnienia domyślnemu service account
CLOUD_RUN_SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:$CLOUD_RUN_SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

echo "✅ Uprawnienia Secret Manager nadane dla: $CLOUD_RUN_SERVICE_ACCOUNT"
```

---

## 🏗️ Wdrożenie Architektury Scout & Worker

### Metoda 1: Automatyczny skrypt (ZALECANA)
```bash
# Pobierz kod
git clone <repo-url>
cd OFF-Peak-tesla-controller

# Ustaw zmienne środowiskowe
export GOOGLE_CLOUD_PROJECT="twoj-project-id"
export GOOGLE_CLOUD_REGION="europe-west1"

# Uruchom wdrożenie Scout & Worker
chmod +x deploy_scout_worker.sh
./deploy_scout_worker.sh
```

### Metoda 2: Wdrożenie manualne

#### Krok 1: Wdrożenie Worker Service
```bash
# Zbuduj obraz Worker
docker build --platform linux/amd64 -f Dockerfile.worker -t gcr.io/$GOOGLE_CLOUD_PROJECT/tesla-worker .

# Wypchnij obraz
docker push gcr.io/$GOOGLE_CLOUD_PROJECT/tesla-worker

# Wdroż Worker Service
gcloud run deploy tesla-worker \
    --image gcr.io/$GOOGLE_CLOUD_PROJECT/tesla-worker \
    --platform managed \
    --region $GOOGLE_CLOUD_REGION \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --timeout 900 \
    --concurrency 1 \
    --max-instances 1 \
    --min-instances 0
```

#### Krok 2: Wdrożenie Scout Function
```bash
# Pobierz URL Worker Service
WORKER_URL=$(gcloud run services describe tesla-worker --region=$GOOGLE_CLOUD_REGION --format="value(status.url)")

# Wdroż Scout Function
gcloud functions deploy tesla-scout \
    --runtime python39 \
    --source scout_function_deploy \
    --entry-point tesla_scout_main \
    --trigger-http \
    --allow-unauthenticated \
    --memory 256MB \
    --timeout 540 \
    --set-env-vars "WORKER_SERVICE_URL=$WORKER_URL"
```

#### Krok 3: Konfiguracja Cloud Scheduler
```bash
# Pobierz URL Scout Function
SCOUT_URL=$(gcloud functions describe tesla-scout --region=$GOOGLE_CLOUD_REGION --format="value(httpsTrigger.url)")

# Scout co 15 minut
gcloud scheduler jobs create http tesla-scout-location-check \
    --schedule="*/15 * * * *" \
    --time-zone="Europe/Warsaw" \
    --uri="$SCOUT_URL" \
    --http-method=POST

# Worker failsafe - nocne wybudzenie
gcloud scheduler jobs create http tesla-worker-daily-check \
    --schedule="0 0 * * *" \
    --time-zone="Europe/Warsaw" \
    --uri="$WORKER_URL/run-cycle" \
    --http-method=POST

# Emergency backup - niedziela 12:00
gcloud scheduler jobs create http tesla-worker-emergency \
    --schedule="0 12 * * 0" \
    --time-zone="Europe/Warsaw" \
    --uri="$WORKER_URL/run-cycle" \
    --http-method=POST
```

---

## ✅ Weryfikacja wdrożenia

### 1. Test Worker Service
```bash
# Pobierz URL Worker
WORKER_URL=$(gcloud run services describe tesla-worker --region=$GOOGLE_CLOUD_REGION --format="value(status.url)")

# Test health check
curl -X GET "$WORKER_URL/health"

# Test endpointu tokenów
curl -X GET "$WORKER_URL/get-token"

# Oczekiwana odpowiedź:
# {
#   "status": "success",
#   "access_token": "eyJ...",
#   "remaining_minutes": 1439,
#   "architecture": {
#     "type": "centralized_token_management"
#   }
# }
```

### 2. Test Scout Function
```bash
# Pobierz URL Scout
SCOUT_URL=$(gcloud functions describe tesla-scout --region=$GOOGLE_CLOUD_REGION --format="value(httpsTrigger.url)")

# Test Scout Function
curl -X POST "$SCOUT_URL"

# Sprawdź logi Scout
gcloud functions logs read tesla-scout --limit=20

# Szukaj komunikatów:
# ✅ [SCOUT] Token Tesla otrzymany (ważny przez 1439 min)
# 🏗️ [SCOUT] Centralne zarządzanie tokenami przez Worker
```

### 3. Test architektury tokenów
```bash
# Uruchom test weryfikacyjny
python3 test_token_architecture.py --worker-url $WORKER_URL

# Oczekiwany wynik:
# ✅ Worker Health Check
# ✅ Worker Token Endpoint  
# ✅ Token Validity
# ✅ Multiple Token Requests
# ✅ Worker Status Endpoint
# 🎉 WSZYSTKIE TESTY PRZESZŁY
```

### 4. Test fallback mechanism
```bash
# Test mechanizmu fallback
python3 test_token_refresh_fallback.py

# Oczekiwany wynik:
# ✅ PASS Worker Endpoint
# ✅ PASS Scout Fallback  
# ✅ PASS Rate Limiting
# ✅ PASS Cache Clearing
# 🎉 WSZYSTKIE TESTY PRZESZŁY
```

---

## 📊 Monitoring i logowanie

### Logi Worker Service
```bash
# Sprawdź logi Worker
gcloud run services logs read tesla-worker --region=$GOOGLE_CLOUD_REGION --limit=50

# Szukaj komunikatów:
# ✅ [WORKER] Token Tesla udostępniony Scout
# 🔍➡️🔧 [WORKER] Otrzymano wywołanie od Scout Function
# ✅ [WORKER] Cykl zakończony pomyślnie
```

### Logi Scout Function
```bash
# Sprawdź logi Scout
gcloud functions logs read tesla-scout --limit=50

# Szukaj komunikatów:
# 📡 [SCOUT] Pobieram token Tesla z Worker lub Secret Manager
# ✅ [SCOUT] Token Tesla otrzymany (ważny przez 1439 min)
# 🏠 [SCOUT] Pojazd w domu -> wywołuję Worker
```

### Logi Cloud Scheduler
```bash
# Sprawdź wykonania harmonogramów
gcloud scheduler jobs list --location=$GOOGLE_CLOUD_REGION

# Szczegóły konkretnego job
gcloud scheduler jobs describe tesla-scout-location-check --location=$GOOGLE_CLOUD_REGION
```

---

## 🔧 Konfiguracja zmiennych środowiskowych

### Worker Service
Worker automatycznie pobiera konfigurację z Secret Manager. Sprawdź czy sekrety są poprawnie skonfigurowane:

```bash
# Sprawdź sekrety
gcloud secrets list --filter="name:tesla OR name:OFF_PEAK OR name:home OR name:fleet-tokens"

# Sprawdź wartość sekretu (ostrożnie - pokazuje zawartość!)
gcloud secrets versions access latest --secret="tesla-client-id"
```

### Scout Function
Scout używa zmiennych środowiskowych:

```bash
# Sprawdź konfigurację Scout
gcloud functions describe tesla-scout --region=$GOOGLE_CLOUD_REGION --format="value(environmentVariables)"

# Zaktualizuj WORKER_SERVICE_URL jeśli potrzeba
gcloud functions deploy tesla-scout \
    --source scout_function_deploy \
    --set-env-vars "WORKER_SERVICE_URL=$WORKER_URL"
```

---

## 🚨 Rozwiązywanie problemów

### Problem: Błąd 403 Secret Manager
```bash
# Sprawdź czy sekrety istnieją
gcloud secrets list

# Sprawdź uprawnienia service account
gcloud projects get-iam-policy $GOOGLE_CLOUD_PROJECT \
    --flatten="bindings[].members" \
    --format='table(bindings.role)' \
    --filter="bindings.members:*compute@developer.gserviceaccount.com"

# Nadaj uprawnienia jeśli brak
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### Problem: Scout nie może połączyć się z Worker
```bash
# Sprawdź czy Worker działa
curl -X GET "$WORKER_URL/health"

# Sprawdź czy Scout ma poprawny URL Worker
gcloud functions describe tesla-scout --format="value(environmentVariables.WORKER_SERVICE_URL)"

# Zaktualizuj URL jeśli potrzeba
WORKER_URL=$(gcloud run services describe tesla-worker --region=$GOOGLE_CLOUD_REGION --format="value(status.url)")
gcloud functions deploy tesla-scout \
    --source scout_function_deploy \
    --set-env-vars "WORKER_SERVICE_URL=$WORKER_URL"
```

### Problem: Błędy autoryzacji Tesla API 401
```bash
# Sprawdź czy tokeny są aktualne
curl -X GET "$WORKER_URL/get-token"

# Sprawdź logi Worker
gcloud run services logs read tesla-worker --limit=20

# Zresetuj tokeny jeśli potrzeba (wymaga ponownej autoryzacji)
python3 generate_token.py
gcloud secrets versions add fleet-tokens --data-file=fleet_tokens.json
```

### Problem: Wysokie koszty
```bash
# Sprawdź czy Worker skaluje do zera
gcloud run services describe tesla-worker --region=$GOOGLE_CLOUD_REGION --format="value(spec.template.metadata.annotations)"

# Sprawdź częstotliwość wywołań
gcloud scheduler jobs list --location=$GOOGLE_CLOUD_REGION

# Sprawdź metryki kosztów
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=tesla-worker" --limit=100
```

---

## 💰 Optymalizacja kosztów

### Aktualne koszty architektury Scout & Worker:
- **Scout Function**: ~1 grosz/dzień (96 wywołań × 0.01gr)
- **Worker Service**: ~20 groszy/dzień (2-3 wywołania × 5-10gr)
- **Cloud Scheduler**: ~3 grosze/miesiąc (3 harmonogramy)
- **Secret Manager**: ~1 grosz/miesiąc (10 sekretów)

**TOTAL: ~21 groszy/dzień (~6.30 zł/miesiąc)**

### Porównanie z tradycyjną architekturą:
- **Tradycyjne Cloud Run**: ~150-300 groszy/dzień
- **Scout & Worker**: ~21 groszy/dzień
- **Oszczędności**: 85-90%

---

## 🎯 Checklist wdrożenia

- [ ] Google Cloud projekt skonfigurowany
- [ ] Wszystkie wymagane API włączone
- [ ] Sekrety Tesla Fleet API utworzone w Secret Manager
- [ ] Uprawnienia Secret Manager nadane service account
- [ ] Worker Service wdrożony i działa
- [ ] Scout Function wdrożona z poprawnym WORKER_SERVICE_URL
- [ ] Cloud Scheduler harmonogramy skonfigurowane
- [ ] Test architektury tokenów przeszedł pomyślnie
- [ ] Test fallback mechanism działa
- [ ] Monitoring i logi działają prawidłowo
- [ ] Koszty są na oczekiwanym poziomie (~21 groszy/dzień)

---

**✅ Po wykonaniu wszystkich kroków architektura Scout & Worker jest gotowa do użycia z maksymalnymi oszczędnościami kosztów i pełną funkcjonalnością Tesla Monitor.** 