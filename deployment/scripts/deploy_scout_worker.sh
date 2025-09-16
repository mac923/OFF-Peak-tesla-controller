#!/bin/bash

# Deploy script dla architektury "Scout & Worker"
# AGRESYWNA OPTYMALIZACJA KOSZTÓW:
# - Scout Function: lekka, tania, częsta (co 15 min)
# - Worker Service: ciężka, droga, rzadka (2-3x dziennie)

set -e

echo "🚀 === WDROŻENIE ARCHITEKTURY SCOUT & WORKER ===="
echo "💰 AGRESYWNA OPTYMALIZACJA KOSZTÓW:"
echo "   🔍 Scout Function: ~1 grosz dziennie (96 wywołań x 0.01 groszy)"
echo "   🔧 Worker Service: ~20 groszy dziennie (4 wywołania x 5 groszy)"
echo "   💵 ŁĄCZNY KOSZT: ~20 groszy dziennie (vs obecne 6 zł)"
echo "   📊 OSZCZĘDNOŚĆ: ~96% redukcja kosztów"
echo ""

# Sprawdź czy PROJECT_ID jest ustawiony
if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    echo "❌ Błąd: Ustaw zmienną GOOGLE_CLOUD_PROJECT"
    echo "Przykład: export GOOGLE_CLOUD_PROJECT=your-project-id"
    exit 1
fi

PROJECT_ID=$GOOGLE_CLOUD_PROJECT
echo "📋 Projekt: $PROJECT_ID"

# Sprawdź czy gcloud jest zalogowany
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Błąd: Zaloguj się do gcloud"
    echo "Wykonaj: gcloud auth login"
    exit 1
fi

echo "✅ Użytkownik zalogowany do gcloud"

# Ustaw domyślny projekt
gcloud config set project $PROJECT_ID

# Włącz wymagane API
echo ""
echo "🔧 Włączanie wymaganych API..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
echo "✅ API włączone"

# Sprawdź czy sekrety istnieją
echo ""
echo "🔐 Sprawdzanie sekretów..."
REQUIRED_SECRETS=(
    "tesla-client-id"
    "tesla-client-secret"
    "tesla-refresh-token"
    "tesla-private-key"
    "OFF_PEAK_CHARGE_API_KEY"
    "WORKER_SERVICE_URL"
)

for secret in "${REQUIRED_SECRETS[@]}"; do
    if gcloud secrets describe $secret >/dev/null 2>&1; then
        echo "✅ Sekret '$secret' istnieje"
    else
        echo "❌ Sekret '$secret' nie istnieje"
        echo "💡 Utwórz sekret: gcloud secrets create $secret --data-file=-"
        exit 1
    fi
done

# === KROK 1: WDROŻENIE SCOUT FUNCTION ===
echo ""
echo "🔍 === WDRAŻANIE SCOUT FUNCTION (LEKKA, TANIA) ==="

# KROK 1.1: Usunięcie przestarzałego kopiowania plików.
# Skrypt będzie teraz wdrażał bezpośrednio z katalogu scout_function_deploy,
# który zawiera już poprawiony main.py i odpowiednie zależności.
#
# usunięto:
# mkdir -p scout_function_deploy
# cp tesla_scout_function.py scout_function_deploy/main.py
# cp requirements_scout.txt scout_function_deploy/requirements.txt

# Wdrażaj Scout Function
echo "🔍 Wdrażanie Scout Function z katalogu 'scout_function_deploy'..."
gcloud functions deploy tesla-scout \
    --gen2 \
    --runtime=python311 \
    --region=europe-west1 \
    --source=scout_function_deploy \
    --entry-point=tesla_scout_main \
    --trigger-http \
    --no-allow-unauthenticated \
    --memory=256MB \
    --timeout=60s \
    --max-instances=1 \
    --min-instances=0 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,HOME_LATITUDE=52.334215,HOME_LONGITUDE=20.937516,HOME_RADIUS=0.03" \
    --service-account="$PROJECT_ID@appspot.gserviceaccount.com"

# Pobierz URL Scout Function
SCOUT_FUNCTION_URL=$(gcloud functions describe tesla-scout --region=europe-west1 --format="value(serviceConfig.uri)")
echo "✅ Scout Function wdrożona: $SCOUT_FUNCTION_URL"

# === KROK 2: WDROŻENIE WORKER SERVICE ===
echo ""
echo "🔧 === WDRAŻANIE WORKER SERVICE (CIĘŻKA, DROGA, RZADKA) ==="

# Buduj obraz Worker (używamy Dockerfile.worker)
echo "🏗️ Budowanie obrazu Worker..."
gcloud builds submit --config=deployment/docker/cloudbuild-worker.yaml .

# Zastąp placeholders w konfiguracji Worker
sed "s/YOUR_PROJECT_ID/$PROJECT_ID/g" deployment/cloud/cloud-run-worker.yaml > cloud-run-service-worker-filled.yaml

# Wdrażaj Worker Service
echo "🔧 Wdrażanie Worker Service..."
gcloud run services replace cloud-run-service-worker-filled.yaml --region=europe-west1

# Pobierz URL Worker Service
WORKER_SERVICE_URL=$(gcloud run services describe tesla-worker --region=europe-west1 --format="value(status.url)")
echo "✅ Worker Service wdrożona: $WORKER_SERVICE_URL"

# === KROK 3: AKTUALIZACJA SCOUT FUNCTION Z URL WORKER ===
echo ""
echo "🔗 Aktualizacja Scout Function z URL Worker Service..."

# KROK 3.1: Usunięcie przestarzałego kopiowania plików przy aktualizacji.
#
# usunięto:
# mkdir -p scout_function_deploy
# cp tesla_scout_function.py scout_function_deploy/main.py
# cp requirements_scout.txt scout_function_deploy/requirements.txt

gcloud functions deploy tesla-scout \
    --gen2 \
    --runtime=python311 \
    --region=europe-west1 \
    --source=src/scout \
    --entry-point=tesla_scout_main \
    --trigger-http \
    --no-allow-unauthenticated \
    --memory=256MB \
    --timeout=60s \
    --max-instances=1 \
    --min-instances=0 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,HOME_LATITUDE=52.334215,HOME_LONGITUDE=20.937516,HOME_RADIUS=0.03,WORKER_SERVICE_URL=$WORKER_SERVICE_URL" \
    --service-account="$PROJECT_ID@appspot.gserviceaccount.com"

echo "✅ Scout Function zaktualizowana z URL Worker Service"

# usunięto:
# rm -rf scout_function_deploy

# === KROK 4: KONFIGURACJA UPRAWNIEŃ ===
echo ""
echo "🔐 Konfiguracja uprawnień..."

# Utwórz service account dla Cloud Scheduler (jeśli nie istnieje)
if ! gcloud iam service-accounts describe tesla-scout-scheduler@$PROJECT_ID.iam.gserviceaccount.com >/dev/null 2>&1; then
    gcloud iam service-accounts create tesla-scout-scheduler \
        --display-name="Tesla Scout Scheduler" \
        --description="Service account for Cloud Scheduler to invoke Scout and Worker"
fi

# Uprawnienia dla Scout Function
gcloud functions add-iam-policy-binding tesla-scout \
    --region=europe-west1 \
    --member="serviceAccount:tesla-scout-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/cloudfunctions.invoker"

# Uprawnienia dla Worker Service
gcloud run services add-iam-policy-binding tesla-worker \
    --member="serviceAccount:tesla-scout-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --region=europe-west1

# Uprawnienia dla Scout Function do wywoływania Worker Service
gcloud run services add-iam-policy-binding tesla-worker \
    --member="serviceAccount:$PROJECT_ID@appspot.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --region=europe-west1

echo "✅ Uprawnienia skonfigurowane"

# === KROK 5: KONFIGURACJA CLOUD SCHEDULER ===
echo ""
echo "📅 Konfiguracja Cloud Scheduler..."

# Zastąp placeholders w konfiguracji scheduler
sed -e "s/YOUR_PROJECT_ID/$PROJECT_ID/g" \
    -e "s|YOUR_SCOUT_FUNCTION_URL|$SCOUT_FUNCTION_URL|g" \
    -e "s|YOUR_WORKER_SERVICE_URL|$WORKER_SERVICE_URL|g" \
    deployment/cloud/scheduler-scout-worker.yaml > cloud-scheduler-scout-worker-filled.yaml

# Utwórz region dla Cloud Scheduler jeśli nie istnieje
gcloud app create --region=europe-west1 2>/dev/null || true

# Usuń istniejące jobs (jeśli istnieją)
gcloud scheduler jobs delete tesla-scout-location-check --location=europe-west1 --quiet 2>/dev/null || true
gcloud scheduler jobs delete tesla-worker-daily-check --location=europe-west1 --quiet 2>/dev/null || true
gcloud scheduler jobs delete tesla-worker-emergency --location=europe-west1 --quiet 2>/dev/null || true

# Utwórz Scout job (główny harmonogram)
echo "🔍 Tworzenie harmonogramu Scout (co 15 min)..."
gcloud scheduler jobs create http tesla-scout-location-check \
    --location=europe-west1 \
    --schedule="*/15 * * * *" \
    --time-zone="UTC" \
    --uri="$SCOUT_FUNCTION_URL" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"trigger":"cloud_scheduler_scout","action":"check_location","frequency":"15min"}' \
    --oidc-service-account-email="tesla-scout-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --max-retry-attempts=2 \
    --max-retry-duration=60s \
    --min-backoff=5s \
    --max-backoff=15s \
    --attempt-deadline=30s \
    --description="Tesla Scout - lekka funkcja sprawdzająca lokalizację (koszt: ~0.01 groszy)"

# Utwórz Worker failsafe job (nocne wybudzenie)
echo "🔧 Tworzenie harmonogramu Worker failsafe (00:00 Europe/Warsaw)..."
gcloud scheduler jobs create http tesla-worker-daily-check \
    --location=europe-west1 \
    --schedule="0 0 * * *" \
    --time-zone="Europe/Warsaw" \
    --uri="$WORKER_SERVICE_URL/run-midnight-wake" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"trigger":"cloud_scheduler_worker_failsafe","action":"midnight_wake_and_check","time":"00:00_Warsaw","force_full_check":true}' \
    --oidc-service-account-email="tesla-scout-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --max-retry-attempts=3 \
    --max-retry-duration=300s \
    --min-backoff=10s \
    --max-backoff=60s \
    --attempt-deadline=120s \
    --description="Tesla Worker - dzienny failsafe i nocne wybudzenie o 00:00 czasu warszawskiego"

# Utwórz Worker emergency job (test tygodniowy)
echo "🔧 Tworzenie harmonogramu Worker emergency (niedziela 12:00 UTC)..."
gcloud scheduler jobs create http tesla-worker-emergency \
    --location=europe-west1 \
    --schedule="0 12 * * 0" \
    --time-zone="UTC" \
    --uri="$WORKER_SERVICE_URL/run-cycle" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"trigger":"cloud_scheduler_worker_emergency","action":"full_check","time":"12:00_UTC_Sunday","force_full_check":true,"reason":"weekly_emergency_test"}' \
    --oidc-service-account-email="tesla-scout-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --max-retry-attempts=2 \
    --max-retry-duration=180s \
    --min-backoff=10s \
    --max-backoff=30s \
    --attempt-deadline=90s \
    --description="Tesla Worker - awaryjne wywołanie pełnej logiki (test tygodniowy)"

echo "✅ Cloud Scheduler jobs utworzone"

# Wyczyść pliki tymczasowe
rm -f cloud-run-service-worker-filled.yaml cloud-scheduler-scout-worker-filled.yaml

echo ""
echo "🎉 === WDROŻENIE SCOUT & WORKER ZAKOŃCZONE POMYŚLNIE ==="
echo ""
echo "💰 AGRESYWNA OPTYMALIZACJA KOSZTÓW AKTYWNA:"
echo "   🔍 Scout Function: Sprawdza lokalizację co 15 min (~1 grosz/dzień)"
echo "   🔧 Worker Service: Pełna logika 2-3x dziennie (~20 groszy/dzień)"
echo "   💵 ŁĄCZNY KOSZT: ~20 groszy dziennie (vs 6 zł poprzednio)"
echo "   📊 OSZCZĘDNOŚĆ: ~96% redukcja kosztów!"
echo ""
echo "🏗️ ARCHITEKTURA:"
echo "   📅 Scout sprawdza lokalizację co 15 min"
echo "   🏠 Gdy pojazd wraca do domu → Scout wywołuje Worker"
echo "   🔧 Worker wykonuje pełną logikę z Tesla HTTP Proxy"
echo "   🌙 Worker failsafe: nocne wybudzenie o 00:00 czasu warszawskiego (Europe/Warsaw)"
echo ""
echo "🔗 ENDPOINTS:"
echo "   Scout Function: $SCOUT_FUNCTION_URL"
echo "   Worker Service: $WORKER_SERVICE_URL"
echo ""
echo "🎯 HARMONOGRAM:"
echo "   🔍 Scout: Co 15 minut (96x dziennie)"
echo "   🔧 Worker: 2-3x gdy Scout wykryje powrót + 1x failsafe"
echo "   🧪 Emergency: Niedziela 12:00 UTC (test)"
echo ""
echo "📊 MONITORING:"
echo "   Scout status: curl $SCOUT_FUNCTION_URL"
echo "   Worker status: curl $WORKER_SERVICE_URL/worker-status"
echo "   Worker health: curl $WORKER_SERVICE_URL/health"
echo ""
echo "🔄 POWRÓT DO STAREJ WERSJI:"
echo "   Jeśli potrzebujesz wrócić do poprzedniej wersji:"
echo "   ./deploy_optimized.sh  # Wdroży poprzednią stabilną wersję"
echo ""
echo "🚀 Architektura Scout & Worker jest gotowa do użycia!" 