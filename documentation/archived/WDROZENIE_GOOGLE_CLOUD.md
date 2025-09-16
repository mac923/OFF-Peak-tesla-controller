# 🌩️ Wdrożenie na Google Cloud z Tesla HTTP Proxy

## Przegląd

Przewodnik krok po kroku wdrażania aplikacji Tesla Controller na Google Cloud Run z obsługą Tesla HTTP Proxy i automatycznym zarządzaniem harmonogramami ładowania.

## 🛠️ Wymagania

### Lokalne narzędzia
- **Docker** - do budowania obrazów
- **Google Cloud SDK** (`gcloud`) - do wdrażania
- **Git** - do pobierania kodu

### Google Cloud
- **Projekt Google Cloud** z włączoną płatnością
- **Uprawnienia Owner/Editor** do projektu
- **Włączone API**:
  - Cloud Run API
  - Container Registry API
  - Cloud Logging API
  - Cloud Storage API
  - Firestore API
  - Secret Manager API

## 📋 Przygotowanie

### 1. Konfiguracja środowiska lokalnego
```bash
# Zaloguj się do Google Cloud
gcloud auth login

# Ustaw projekt
export GOOGLE_CLOUD_PROJECT="twoj-project-id"
gcloud config set project $GOOGLE_CLOUD_PROJECT

# Ustaw region (opcjonalnie)
export GOOGLE_CLOUD_REGION="europe-west1"
```

### 2. Przygotowanie sekretów Fleet API
```bash
# Klucz prywatny Fleet API (wymagany)
gcloud secrets create tesla-private-key --data-file=private-key.pem

# Konfiguracja Tesla Fleet API
gcloud secrets create tesla-client-id --data-string="twoj_client_id"
gcloud secrets create tesla-client-secret --data-string="twoj_client_secret"
gcloud secrets create tesla-domain --data-string="twoja_domena"
gcloud secrets create tesla-public-key-url --data-string="https://twoja_domena/.well-known/appspecific/com.tesla.3p.public-key.pem"

# Lokalizacja domowa
gcloud secrets create home-latitude --data-string="52.334215"
gcloud secrets create home-longitude --data-string="20.937516"
gcloud secrets create home-radius --data-string="0.15"
```

### 3. Przygotowanie sekretów OFF PEAK CHARGE API
```bash
# Klucz API OFF PEAK CHARGE (wymagany dla automatycznych harmonogramów)
gcloud secrets create OFF_PEAK_CHARGE_API_KEY --data-string="twoj_api_key"

# URL API OFF PEAK CHARGE (opcjonalny)
gcloud secrets create OFF_PEAK_CHARGE_API_URL --data-string="https://twoja-domena.com/api/external-calculate"
```

## 🚀 Wdrożenie

### Metoda 1: Automatyczny skrypt (ZALECANA)
```bash
# Pobierz kod
git clone <repo-url>
cd OFF-Peak-tesla-controller

# Ustaw zmienne środowiskowe
export GOOGLE_CLOUD_PROJECT="twoj-project-id"
export GOOGLE_CLOUD_REGION="europe-west1"

# Uruchom wdrożenie
chmod +x deploy_to_cloud.sh
./deploy_to_cloud.sh
```

### Metoda 2: Krok po kroku
```bash
# 1. Włącz wymagane API
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
gcloud services enable secretmanager.googleapis.com

# 2. Buduj obraz Docker
docker build --platform linux/amd64 -t gcr.io/$GOOGLE_CLOUD_PROJECT/tesla-monitor .

# 3. Wypchnij obraz
docker push gcr.io/$GOOGLE_CLOUD_PROJECT/tesla-monitor

# 4. Zaktualizuj konfigurację YAML
sed "s/PROJECT_ID/$GOOGLE_CLOUD_PROJECT/g" cloud-run-service.yaml > cloud-run-service-updated.yaml

# 5. Wdroż do Cloud Run
gcloud run services replace cloud-run-service-updated.yaml --region $GOOGLE_CLOUD_REGION

# 6. Ustaw uprawnienia
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")
CLOUD_RUN_SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:$CLOUD_RUN_SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

# 7. Ustaw dostęp publiczny
gcloud run services add-iam-policy-binding tesla-monitor \
    --region $GOOGLE_CLOUD_REGION \
    --member="allUsers" \
    --role="roles/run.invoker"
```

## 🔍 Weryfikacja

### 1. Sprawdź status wdrożenia
```bash
# Pobierz URL serwisu
SERVICE_URL=$(gcloud run services describe tesla-monitor --platform managed --region $GOOGLE_CLOUD_REGION --format 'value(status.url)')

echo "Service URL: $SERVICE_URL"

# Test health check
curl "$SERVICE_URL/health"
```

### 2. Sprawdź logi uruchomienia
```bash
# Logi w czasie rzeczywistym
gcloud logs tail --service=tesla-monitor --region=$GOOGLE_CLOUD_REGION

# Szukaj specyficznych komunikatów
gcloud logs read --service=tesla-monitor --region=$GOOGLE_CLOUD_REGION --filter="resource.labels.service_name=tesla-monitor" --limit=50
```

### 3. Oczekiwane logi uruchomienia
```
🚀 Uruchamianie Cloud Tesla Monitor z Tesla HTTP Proxy...
🔧 Konfiguracja Tesla HTTP Proxy:
   Host: 0.0.0.0
   Port: 4443
   TLS Key: tls-key.pem
   TLS Cert: tls-cert.pem
   Private Key: private-key.pem
🔄 Uruchamianie Tesla HTTP Proxy...
✅ Tesla HTTP Proxy uruchomiony (PID: 123)
✅ Tesla HTTP Proxy odpowiada poprawnie
🐍 Uruchamianie aplikacji Python...
✅ Aplikacja Python uruchomiona (PID: 456)
🎉 Wszystkie procesy uruchomione!
📊 Tesla HTTP Proxy: https://localhost:4443
🌐 Tesla Monitor: http://localhost:8080
```

## 📊 Monitorowanie

### Dashboard Cloud Run
```bash
# Otwórz dashboard Cloud Run
echo "https://console.cloud.google.com/run/detail/$GOOGLE_CLOUD_REGION/tesla-monitor/metrics?project=$GOOGLE_CLOUD_PROJECT"
```

### Metryki kluczowe
- **CPU utilization** - powinno być < 50% (2 CPU dla proxy + aplikacja)
- **Memory utilization** - powinno być < 80% (2Gi)
- **Request count** - health check co 5 minut
- **Error rate** - powinien być 0%

### Logi aplikacji
```bash
# Filtruj logi Tesla proxy
gcloud logs read --service=tesla-monitor --filter="textPayload:tesla-http-proxy" --limit=20

# Filtruj logi harmonogramów
gcloud logs read --service=tesla-monitor --filter="textPayload:Harmonogram" --limit=20

# Filtruj błędy
gcloud logs read --service=tesla-monitor --filter="severity>=ERROR" --limit=20
```

## 🛡️ Bezpieczeństwo

### Uprawnienia Cloud Run
```bash
# Sprawdź uprawnienia service account
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")
CLOUD_RUN_SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects get-iam-policy $GOOGLE_CLOUD_PROJECT \
    --flatten="bindings[].members" \
    --filter="bindings.members:$CLOUD_RUN_SERVICE_ACCOUNT"
```

### Dostęp do sekretów
```bash
# Sprawdź czy service account ma dostęp do sekretów
gcloud secrets get-iam-policy tesla-private-key
```

### Certyfikaty TLS
- **Self-signed** certyfikaty generowane automatycznie
- **Ważność**: 365 dni
- **CN**: localhost
- **SAN**: DNS:localhost, IP:127.0.0.1

## 🔧 Konfiguracja zaawansowana

### Zwiększenie zasobów
```yaml
# W cloud-run-service.yaml
resources:
  limits:
    cpu: "4"      # Dla większego obciążenia
    memory: "4Gi" # Dla więcej harmonogramów
```

### Skalowanie
```yaml
# W cloud-run-service.yaml
metadata:
  annotations:
    autoscaling.knative.dev/minScale: "1"  # Zawsze 1 instancja
    autoscaling.knative.dev/maxScale: "1"  # Maksymalnie 1 instancja (singleton)
```

### Timeout'y
```yaml
# W cloud-run-service.yaml - health check
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 120  # Więcej czasu na uruchomienie proxy
  periodSeconds: 600       # Sprawdzaj co 10 minut
  timeoutSeconds: 60       # Dłuższy timeout
```

## ❌ Rozwiązywanie problemów

### Tesla HTTP Proxy nie uruchamia się
```bash
# Sprawdź logi uruchomienia
gcloud logs read --service=tesla-monitor --filter="textPayload:Tesla" --limit=10

# Możliwe przyczyny:
# 1. Brak Node.js - sprawdź czy Dockerfile instaluje Node.js
# 2. Brak tesla-http-proxy - sprawdź czy npm install się wykonał
# 3. Brak uprawnień do portu 4443
```

### Aplikacja nie łączy się z proxy
```bash
# Sprawdź czy proxy odpowiada
gcloud logs read --service=tesla-monitor --filter="textPayload:proxy" --limit=10

# Sprawdź zmienne środowiskowe
gcloud run services describe tesla-monitor --region=$GOOGLE_CLOUD_REGION --format="value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)"
```

### Błędy autoryzacji Fleet API
```bash
# Sprawdź sekrety
gcloud secrets versions access latest --secret="tesla-private-key" | head -5
gcloud secrets versions access latest --secret="tesla-client-id"

# Sprawdź logi autoryzacji
gcloud logs read --service=tesla-monitor --filter="textPayload:Autoryzacja OR textPayload:Fleet" --limit=10
```

### Problemy z harmonogramami
```bash
# Sprawdź logi OFF PEAK CHARGE API
gcloud logs read --service=tesla-monitor --filter="textPayload:OFF_PEAK" --limit=10

# Sprawdź sekrety OFF PEAK
gcloud secrets versions access latest --secret="OFF_PEAK_CHARGE_API_KEY"
```

## 🔄 Aktualizacja

### Aktualizacja kodu
```bash
# Pobierz najnowszy kod
git pull

# Ponownie wdroż
./deploy_to_cloud.sh
```

### Aktualizacja sekretów
```bash
# Zaktualizuj sekret
gcloud secrets versions add tesla-private-key --data-file=new-private-key.pem

# Restart serwisu (automatyczny po zmianie sekretów)
gcloud run services update tesla-monitor --region=$GOOGLE_CLOUD_REGION
```

## 📊 Koszty

### Szacunkowe koszty miesięczne
- **Cloud Run**: ~$15-30/miesiąc (2 CPU, 2Gi RAM, zawsze włączony)
- **Cloud Storage**: ~$1-2/miesiąc (logi, stan)
- **Cloud Logging**: ~$0.50-1/miesiąc
- **Secret Manager**: ~$0.30/miesiąc
- **Firestore**: ~$0-1/miesiąc (mały usage)

**Całość**: ~$17-35/miesiąc

### Optymalizacja kosztów
- Użyj **Cloud Run (nie zawsze włączony)** jeśli monitorowanie okresowe
- **Zmniejsz zasoby** jeśli jeden pojazd: 1 CPU, 1Gi RAM
- **Skonfiguruj log retention** na 30 dni zamiast default

---

🎉 **Gratulacje!** Twoja aplikacja Tesla Controller z automatycznym zarządzaniem harmonogramami działa w Google Cloud! ⚡🌩️ 