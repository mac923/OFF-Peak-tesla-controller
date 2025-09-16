#!/bin/bash

# Skrypt wdrażania Cloud Tesla Monitor do Google Cloud
# Używa Google Cloud Run do uruchamiania kontenera z aplikacją monitorującej Tesla
# ZAKTUALIZOWANY - usuwa problematyczny timeout i używa poprawionej konfiguracji

set -e

# Konfiguracja
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"twoj-project-id"}
REGION=${GOOGLE_CLOUD_REGION:-"europe-west1"}
SERVICE_NAME="tesla-monitor"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🚀 Wdrażanie Tesla Monitor do Google Cloud (z Tesla HTTP Proxy)..."
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Name: $SERVICE_NAME"
echo "⚡ Tesla HTTP Proxy: WŁĄCZONY"

# Sprawdź czy gcloud jest zainstalowane
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI nie jest zainstalowane. Zainstaluj go z https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Sprawdź czy jesteś zalogowany
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Nie jesteś zalogowany do gcloud. Uruchom: gcloud auth login"
    exit 1
fi

# Sprawdź czy PROJECT_ID jest ustawiony
if [ "$PROJECT_ID" = "twoj-project-id" ]; then
    echo "❌ Ustaw zmienną GOOGLE_CLOUD_PROJECT lub PROJECT_ID"
    echo "Przykład: export GOOGLE_CLOUD_PROJECT=my-project-123"
    exit 1
fi

# Ustaw projekt
echo "📋 Ustawianie projektu..."
gcloud config set project $PROJECT_ID

# Włącz wymagane API
echo "🔧 Włączanie wymaganych API..."
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Zaktualizuj konfigurację YAML z właściwym PROJECT_ID
echo "📝 Aktualizacja konfiguracji YAML..."
sed "s/PROJECT_ID/$PROJECT_ID/g" cloud-run-service.yaml > cloud-run-service-updated.yaml

# Buduj obraz Docker dla architektury AMD64 (wymaganej przez Cloud Run)
echo "🏗️  Budowanie obrazu Docker dla AMD64..."
docker build --platform linux/amd64 -t $IMAGE_NAME .

# Wypchnij obraz do Container Registry
echo "📤 Wypychanie obrazu do Container Registry..."
docker push $IMAGE_NAME

# Utwórz bucket dla Storage (jeśli nie istnieje)
BUCKET_NAME="tesla-monitor-data-$PROJECT_ID"
echo "🪣 Tworzenie bucket Storage..."
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://$BUCKET_NAME/ 2>/dev/null || echo "Bucket już istnieje"

# NAPRAWKA: Wdroż używając poprawionej konfiguracji YAML (bez timeout)
echo "🚢 Wdrażanie do Cloud Run z poprawioną konfiguracją..."

# Zaktualizuj obraz w YAML
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s|gcr.io/PROJECT_ID/tesla-monitor|$IMAGE_NAME|g" cloud-run-service-updated.yaml
else
    # Linux
    sed -i "s|gcr.io/PROJECT_ID/tesla-monitor|$IMAGE_NAME|g" cloud-run-service-updated.yaml
fi

# Wdroż usługę
gcloud run services replace cloud-run-service-updated.yaml --region $REGION

# NAPRAWKA: Ustaw uprawnienia Secret Manager dla Cloud Run service account
echo "🔐 Konfiguracja uprawnień Secret Manager..."

# Pobierz numer projektu (potrzebny dla service account)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
CLOUD_RUN_SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

echo "📋 Project Number: $PROJECT_NUMBER"
echo "🤖 Cloud Run Service Account: $CLOUD_RUN_SERVICE_ACCOUNT"

# Nadaj uprawnienia do Secret Manager
echo "🔑 Nadawanie uprawnień secretmanager.secretAccessor..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$CLOUD_RUN_SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

# Ustaw politykę IAM aby usługa była dostępna publicznie
echo "🔓 Ustawianie polityki dostępu..."
gcloud run services add-iam-policy-binding $SERVICE_NAME \
    --region $REGION \
    --member="allUsers" \
    --role="roles/run.invoker"

# Pobierz URL serwisu
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')

# Cleanup
rm -f cloud-run-service-updated.yaml

echo ""
echo "✅ Wdrożenie zakończone pomyślnie!"
echo "🌐 URL serwisu: $SERVICE_URL"
echo "🌐 Health check: $SERVICE_URL/health"
echo "📋 Project ID: $PROJECT_ID"
echo "🪣 Storage Bucket: $BUCKET_NAME"
echo ""
echo "🔧 NOWE FUNKCJONALNOŚCI:"
echo "   ⚡ Tesla HTTP Proxy uruchamiany w kontenerze"
echo "   🔗 Automatyczne generowanie certyfikatów TLS"
echo "   🔄 Zarządzanie harmonogramami ładowania"
echo "   📊 Zwiększono zasoby: 2 CPU, 2Gi RAM"
echo "   🔐 Obsługa Fleet API z podpisanymi komendami"
echo ""
echo "📚 Następne kroki:"
echo "1. Utwórz sekrety OFF Peak API (jeśli jeszcze nie istnieją):"
echo "   gcloud secrets create OFF_PEAK_CHARGE_API_KEY --data-file=-"
echo "   gcloud secrets create OFF_PEAK_CHARGE_API_URL --data-file=-"
echo "2. Sprawdź logi: gcloud logs tail --service=$SERVICE_NAME --region=$REGION"
echo "3. Przetestuj health check: curl $SERVICE_URL/health"
echo "4. Monitoruj aplikację - Tesla proxy uruchamia się automatycznie"
echo ""
echo "⚡ TESLA HTTP PROXY:"
echo "   🔗 Automatycznie uruchamiany w kontenerze na porcie 4443"
echo "   🔐 Self-signed certyfikaty TLS generowane automatycznie"
echo "   📊 Proxy + aplikacja działają w jednym kontenerze"
echo "   🔄 Automatyczne zarządzanie harmonogramami ładowania"
echo ""
echo "🔐 Secret Manager skonfigurowany - aplikacja może odczytać sekrety OFF Peak API"
echo "📖 Dokumentacja: README_AUTOMATYCZNE_HARMONOGRAMY.md" 