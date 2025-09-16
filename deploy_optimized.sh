#!/bin/bash

# Deploy script dla zoptymalizowanej wersji Tesla Monitor
# Optymalizacja kosztów: Cloud Scheduler + Cloud Run scale-to-zero

set -e

echo "🚀 === WDROŻENIE ZOPTYMALIZOWANEJ WERSJI TESLA MONITOR ==="
echo "💰 Optymalizacja kosztów: Cloud Scheduler + Cloud Run scale-to-zero"
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

# Buduj i wdrażaj obraz
echo ""
echo "🏗️ Budowanie obrazu Docker..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/tesla-monitor:latest .

# Wdrażaj Cloud Run z optymalizacją kosztów
echo ""
echo "🚀 Wdrażanie Cloud Run (tryb zoptymalizowany)..."

# Zastąp YOUR_PROJECT_ID w konfiguracji
sed "s/YOUR_PROJECT_ID/$PROJECT_ID/g" cloud-run-service-optimized.yaml > cloud-run-service-optimized-filled.yaml

# Wdrażaj usługę
gcloud run services replace cloud-run-service-optimized-filled.yaml --region=europe-west1

# Pobierz URL usługi
SERVICE_URL=$(gcloud run services describe tesla-monitor --region=europe-west1 --format="value(status.url)")
echo "✅ Cloud Run wdrożony: $SERVICE_URL"

# Ustaw uprawnienia dla Cloud Scheduler
echo ""
echo "🔐 Konfiguracja uprawnień dla Cloud Scheduler..."

# Utwórz service account dla Cloud Scheduler (jeśli nie istnieje)
if ! gcloud iam service-accounts describe tesla-scheduler@$PROJECT_ID.iam.gserviceaccount.com >/dev/null 2>&1; then
    gcloud iam service-accounts create tesla-scheduler \
        --display-name="Tesla Monitor Scheduler" \
        --description="Service account for Cloud Scheduler to invoke Tesla Monitor"
fi

# Nadaj uprawnienia
gcloud run services add-iam-policy-binding tesla-monitor \
    --member="serviceAccount:tesla-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --region=europe-west1

echo "✅ Uprawnienia skonfigurowane"

# Konfiguruj Cloud Scheduler jobs
echo ""
echo "📅 Konfiguracja Cloud Scheduler jobs..."

# Zastąp placeholders w konfiguracji scheduler
sed -e "s/YOUR_PROJECT_ID/$PROJECT_ID/g" -e "s|YOUR_CLOUD_RUN_URL|$SERVICE_URL|g" cloud-scheduler-jobs.yaml > cloud-scheduler-jobs-filled.yaml

# Utwórz region dla Cloud Scheduler jeśli nie istnieje
gcloud app create --region=europe-west1 2>/dev/null || true

# Usuń istniejące jobs (jeśli istnieją)
gcloud scheduler jobs delete tesla-monitor-day-cycle --location=europe-west1 --quiet 2>/dev/null || true
gcloud scheduler jobs delete tesla-monitor-night-cycle --location=europe-west1 --quiet 2>/dev/null || true
gcloud scheduler jobs delete tesla-monitor-midnight-wake --location=europe-west1 --quiet 2>/dev/null || true

# Utwórz nowe jobs
echo "📅 Tworzenie harmonogramu dziennego (co 15 min, 07:00-22:59 UTC)..."
gcloud scheduler jobs create http tesla-monitor-day-cycle \
    --location=europe-west1 \
    --schedule="0 7-22 * * *" \
    --time-zone="Europe/Warsaw" \
    --uri="$SERVICE_URL/run-cycle" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"trigger":"cloud_scheduler_day","action":"monitoring_cycle","hours":"07:00-22:00_Warsaw"}' \
    --oidc-service-account-email="tesla-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --max-retry-attempts=2 \
    --max-retry-duration=300s \
    --min-backoff-duration=5s \
    --max-backoff-duration=60s \
    --attempt-deadline=60s \
    --description="Tesla Monitor - dzienny cykl monitorowania (07:00-22:00 czasu warszawskiego)"

echo "📅 Tworzenie harmonogramu nocnego cyklu (23:00-06:00 Europe/Warsaw)..."
gcloud scheduler jobs create http tesla-monitor-night-cycle \
    --location=europe-west1 \
    --schedule="0 23,0-6 * * *" \
    --time-zone="Europe/Warsaw" \
    --uri="$SERVICE_URL/run-cycle" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"trigger":"cloud_scheduler_night","action":"monitoring_cycle","hours":"23:00-06:00_Warsaw"}' \
    --oidc-service-account-email="tesla-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --max-retry-attempts=2 \
    --max-retry-duration=300s \
    --min-backoff-duration=10s \
    --max-backoff-duration=30s \
    --attempt-deadline=60s \
    --description="Tesla Monitor - nocny cykl monitorowania (co 60 min)"

echo "📅 Tworzenie harmonogramu nocnego wybudzenia (00:00 Europe/Warsaw)..."
gcloud scheduler jobs create http tesla-monitor-midnight-wake \
    --location=europe-west1 \
    --schedule="0 0 * * *" \
    --time-zone="Europe/Warsaw" \
    --uri="$SERVICE_URL/run-midnight-wake" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"trigger":"cloud_scheduler_midnight","action":"wake_vehicle","time":"00:00_Warsaw"}' \
    --oidc-service-account-email="tesla-scheduler@$PROJECT_ID.iam.gserviceaccount.com" \
    --max-retry-attempts=2 \
    --max-retry-duration=180s \
    --min-backoff-duration=10s \
    --max-backoff-duration=60s \
    --attempt-deadline=120s \
    --description="Tesla Monitor - nocne wybudzenie pojazdu o 00:00 czasu warszawskiego"

echo "✅ Cloud Scheduler jobs utworzone"

# Wyczyść pliki tymczasowe
rm -f cloud-run-service-optimized-filled.yaml cloud-scheduler-jobs-filled.yaml

echo ""
echo "🎉 === WDROŻENIE ZAKOŃCZONE POMYŚLNIE ==="
echo ""
echo "💰 OPTYMALIZACJA KOSZTÓW AKTYWNA:"
echo "   ✅ Cloud Run skaluje do zera między wywołaniami"
echo "   ✅ Harmonogram zarządzany przez Cloud Scheduler"
echo "   ✅ Brak stałych kosztów gdy aplikacja nie jest używana"
echo ""
echo "📊 HARMONOGRAM DZIAŁANIA:"
echo "   🌅 Dzień (07:00-22:00 Warsaw): co godzinę"
echo "   🌙 Noc (23:00-06:00 Warsaw): co godzinę"
echo "   🚗 Wybudzenie pojazdu: 00:00 czasu warszawskiego (codziennie)"
echo ""
echo "🔗 ENDPOINTS:"
echo "   Health check: $SERVICE_URL/health"
echo "   Manual cycle: $SERVICE_URL/run-cycle"
echo "   Midnight wake: $SERVICE_URL/run-midnight-wake"
echo "   Reset state: $SERVICE_URL/reset"
echo "   Reset schedules: $SERVICE_URL/reset-tesla-schedules"
echo ""
echo "📅 ZARZĄDZANIE HARMONOGRAMEM:"
echo "   gcloud scheduler jobs list --location=europe-west1"
echo "   gcloud scheduler jobs pause tesla-monitor-day-cycle --location=europe-west1"
echo "   gcloud scheduler jobs resume tesla-monitor-day-cycle --location=europe-west1"
echo ""
echo "🔍 MONITORING:"
echo "   gcloud run services logs read tesla-monitor --region=europe-west1"
echo "   gcloud scheduler jobs logs list tesla-monitor-day-cycle --location=europe-west1"
echo ""
echo "💡 TRYB CONTINUOUS (wyższe koszty):"
echo "   Ustaw CONTINUOUS_MODE=true w Cloud Run environment variables"
echo ""
echo "🎯 Spodziewana redukcja kosztów: >95% w porównaniu z trybem continuous" 