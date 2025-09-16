#!/bin/bash

# Skrypt wdrożenia Cloud Tesla Monitor BEZ Tesla HTTP Proxy
# Ten wariant powinien działać stabilnie i pozwolić na wdrożenie naprawek

set -e

echo "🚀 === WDROŻENIE CLOUD TESLA MONITOR (BEZ PROXY) ==="

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

echo "📋 Konfiguracja wdrożenia:"
echo "   Projekt: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Serwis: $SERVICE_NAME"
echo "   Repozytorium: $REPOSITORY"

# Sprawdź czy gcloud jest skonfigurowane
if ! gcloud auth list --filter=status=ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Błąd: Brak aktywnej autoryzacji gcloud"
    echo "💡 Uruchom: gcloud auth login"
    exit 1
fi

# Ustaw aktywny projekt
echo "🔧 Ustawianie aktywnego projektu..."
gcloud config set project $PROJECT_ID

# Włącz wymagane API (jeśli jeszcze nie są włączone)
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

# Zbuduj i wyślij obraz (używając prostego Dockerfile)
IMAGE_URL="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE_NAME:$(date +%s)"

echo "🏗️ Budowanie obrazu Docker (BEZ Tesla HTTP Proxy)..."
echo "   Obraz: $IMAGE_URL"

# Użyj prostego Dockerfile z platformą amd64
docker build --platform linux/amd64 -f Dockerfile.simple -t $IMAGE_URL .
docker push $IMAGE_URL

if [ $? -ne 0 ]; then
    echo "❌ Błąd budowania obrazu Docker"
    exit 1
fi

echo "✅ Obraz Docker zbudowany pomyślnie"

# Aktualizuj konfigurację Cloud Run z nowym obrazem
echo "🔧 Aktualizowanie konfiguracji Cloud Run..."
sed "s|image: .*|image: $IMAGE_URL|" cloud-run-service-simple.yaml > cloud-run-service-temp.yaml

# Wdróż serwis Cloud Run
echo "🚀 Wdrażanie na Cloud Run..."
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
echo "🎉 === WDROŻENIE ZAKOŃCZONE POMYŚLNIE ==="
echo ""
echo "✅ Naprawki wdrożone:"
echo "   🔧 Filtrowanie harmonogramów HOME (latitude/longitude)"
echo "   🔄 Fallback dla pustych harmonogramów OFF PEAK"
echo "   📊 Wykrywanie pustych harmonogramów (0 sesji/kWh)"
echo ""
echo "📊 Informacje o wdrożeniu:"
echo "   🌐 URL serwisu: $SERVICE_URL"
echo "   🖼️  Obraz: $IMAGE_URL"
echo "   📅 Data: $(date)"
echo ""
echo "🔍 Sprawdź status aplikacji:"
echo "   curl $SERVICE_URL/health"
echo ""
echo "📋 Sprawdź logi:"
echo "   gcloud logging read 'resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE_NAME\"' --limit=50 --region=$REGION"
echo ""
echo "💡 UWAGA: Ta wersja NIE używa Tesla HTTP Proxy"
echo "   - Zmniejszone zużycie zasobów"
echo "   - Większa stabilność wdrożenia"
echo "   - Wszystkie naprawki funkcjonalności są aktywne" 