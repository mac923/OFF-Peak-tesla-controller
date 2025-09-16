#!/bin/bash

# Smart Deployment Script dla Cloud Tesla Monitor z Tesla HTTP Proxy Smart Mode
# Uruchamia aplikację z proxy on-demand

set -e

echo "🚀 === SMART WDROŻENIE CLOUD TESLA MONITOR (PROXY ON-DEMAND) ==="

# Sprawdź czy jesteś w odpowiednim katalogu
if [ ! -f "cloud_tesla_monitor.py" ]; then
    echo "❌ Błąd: Nie znaleziono pliku cloud_tesla_monitor.py"
    echo "💡 Uruchom skrypt z katalogu głównego projektu"
    exit 1
fi

# Konfiguracja projektu Google Cloud
PROJECT_ID="off-peak-tesla-controller"
REGION="europe-west1"
SERVICE_NAME="tesla-monitor"
REPOSITORY="cloud-run-source-deploy"

echo "📋 Konfiguracja Smart Deployment:"
echo "   Projekt: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Serwis: $SERVICE_NAME"
echo "   Repozytorium: $REPOSITORY"
echo "   Mode: Smart Proxy (on-demand)"

# Sprawdź czy gcloud jest skonfigurowane
if ! gcloud auth list --filter=status=ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Błąd: Brak aktywnej autoryzacji gcloud"
    echo "💡 Uruchom: gcloud auth login"
    exit 1
fi

# Ustaw aktywny projekt
echo "🔧 Ustawianie aktywnego projektu..."
gcloud config set project $PROJECT_ID

# Włącz wymagane API
echo "🔧 Sprawdzanie API Google Cloud..."
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet
gcloud services enable artifactregistry.googleapis.com --quiet

# Sprawdź czy repozytorium Artifact Registry istnieje
echo "🔍 Sprawdzanie repozytorium Artifact Registry..."
if ! gcloud artifacts repositories describe $REPOSITORY --location=$REGION --quiet > /dev/null 2>&1; then
    echo "❌ Repozytorium $REPOSITORY nie istnieje w $REGION"
    echo "💡 Utwórz je przez: gcloud artifacts repositories create $REPOSITORY --repository-format=docker --location=$REGION"
    exit 1
fi

# Zbuduj i wyślij obraz (używając Smart Dockerfile)
IMAGE_URL="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE_NAME:smart-$(date +%s)"

echo "🏗️ Budowanie Smart obrazu Docker (z Tesla HTTP Proxy on-demand)..."
echo "   Obraz: $IMAGE_URL"

# Użyj Smart Dockerfile z platformą amd64
docker build --platform linux/amd64 -f Dockerfile.smart -t $IMAGE_URL .
docker push $IMAGE_URL

if [ $? -ne 0 ]; then
    echo "❌ Błąd budowania obrazu Docker"
    exit 1
fi

echo "✅ Smart obraz Docker zbudowany pomyślnie"

# Aktualizuj konfigurację Cloud Run z nowym obrazem
echo "🔧 Aktualizowanie konfiguracji Smart Cloud Run..."
sed "s|image: .*|image: $IMAGE_URL|" cloud-run-service-smart.yaml > cloud-run-service-temp.yaml

# Wdróż serwis Cloud Run
echo "🚀 Wdrażanie Smart Monitor na Cloud Run..."
gcloud run services replace cloud-run-service-temp.yaml --region=$REGION

if [ $? -ne 0 ]; then
    echo "❌ Błąd wdrażania na Cloud Run"
    rm -f cloud-run-service-temp.yaml
    exit 1
fi

# Wyczyść plik tymczasowy
rm -f cloud-run-service-temp.yaml

# Pobierz URL serwisu
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo ""
echo "🎉 === SMART WDROŻENIE ZAKOŃCZONE POMYŚLNIE ==="
echo ""
echo "✅ Smart Tesla Monitor wdrożony z funkcjami:"
echo "   🔧 Monitoring pojazdu (zawsze działa)"
echo "   🚀 Tesla HTTP Proxy on-demand (dla komend)"
echo "   📊 Automatyczne zarządzanie harmonogramami"
echo "   🔄 Fallback dla pustych harmonogramów OFF PEAK"
echo "   📍 Poprawne filtrowanie harmonogramów HOME"
echo ""
echo "📊 Informacje o wdrożeniu:"
echo "   🌐 URL serwisu: $SERVICE_URL"
echo "   🖼️  Obraz: $IMAGE_URL"
echo "   📅 Data: $(date)"
echo "   🔧 Mode: Smart Proxy (on-demand)"
echo ""
echo "🔍 Sprawdź status aplikacji:"
echo "   curl $SERVICE_URL/health"
echo ""
echo "📋 Sprawdź logi Smart Proxy:"
echo "   gcloud logging read 'resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\"' --limit=50 --region=$REGION"
echo ""
echo "💡 UWAGA: Smart Proxy Mode"
echo "   ✅ Aplikacja startuje bez proxy (stabilność)"
echo "   🚀 Proxy uruchamiany on-demand (gdy potrzebne komendy)"
echo "   🔄 Graceful degradation (monitoring zawsze działa)"
echo "   ⚡ Automatyczne zatrzymywanie proxy po komendach" 