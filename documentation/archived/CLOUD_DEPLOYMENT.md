# 🚀 Wdrożenie Tesla Monitor w Google Cloud

Ten przewodnik opisuje jak wdrożyć inteligentny system monitorowania pojazdu Tesla w Google Cloud z wykorzystaniem Cloud Run.

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

## 🔧 Konfiguracja początkowa

### 1. Przygotowanie środowiska Google Cloud

```bash
# Zaloguj się do Google Cloud
gcloud auth login

# Ustaw domyślny projekt
gcloud config set project TWOJ_PROJECT_ID

# Włącz wymagane API
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
```

### 2. Przygotowanie plików Tesla

Upewnij się, że masz następujące pliki w katalogu projektu:
- `private-key.pem` - klucz prywatny Tesla Fleet API
- `fleet_tokens.json` - tokeny dostępu (opcjonalnie)
- `.env` - zmienne środowiskowe (dla testów lokalnych)

## 🚢 Wdrożenie automatyczne

### Opcja 1: Użyj skryptu wdrażania

```bash
# Ustaw zmienne środowiskowe
export GOOGLE_CLOUD_PROJECT="twoj-project-id"
export GOOGLE_CLOUD_REGION="europe-west1"

# Uruchom skrypt wdrażania
./deploy_to_cloud.sh
```

### Opcja 2: Wdrożenie manualne

```bash
# 1. Zbuduj obraz Docker
docker build -t gcr.io/TWOJ_PROJECT_ID/tesla-monitor .

# 2. Wypchnij obraz do Container Registry
docker push gcr.io/TWOJ_PROJECT_ID/tesla-monitor

# 3. Wdroż do Cloud Run
gcloud run deploy tesla-monitor \
    --image gcr.io/TWOJ_PROJECT_ID/tesla-monitor \
    --platform managed \
    --region europe-west1 \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --timeout 3600 \
    --concurrency 1 \
    --max-instances 1
```

## ⚙️ Konfiguracja zmiennych środowiskowych

Po wdrożeniu ustaw zmienne środowiskowe Tesla:

```bash
gcloud run services update tesla-monitor --region europe-west1 \
  --set-env-vars TESLA_CLIENT_ID=twoj_client_id \
  --set-env-vars TESLA_CLIENT_SECRET=twoj_client_secret \
  --set-env-vars TESLA_DOMAIN=twoja_domena.com \
  --set-env-vars TESLA_PRIVATE_KEY_FILE=private-key.pem \
  --set-env-vars TESLA_PUBLIC_KEY_URL=https://twoja_domena.com/.well-known/appspecific/com.tesla.3p.public-key.pem \
  --set-env-vars HOME_LATITUDE=52.334215 \
  --set-env-vars HOME_LONGITUDE=20.937516 \
  --set-env-vars HOME_RADIUS=100
```

### Wymagane zmienne środowiskowe:

| Zmienna | Opis | Przykład |
|---------|------|----------|
| `TESLA_CLIENT_ID` | Client ID z Tesla Developer Portal | `abc123...` |
| `TESLA_CLIENT_SECRET` | Client Secret z Tesla Developer Portal | `def456...` |
| `TESLA_DOMAIN` | Twoja domena | `example.com` |
| `TESLA_PRIVATE_KEY_FILE` | Ścieżka do klucza prywatnego | `private-key.pem` |
| `TESLA_PUBLIC_KEY_URL` | URL klucza publicznego | `https://example.com/.well-known/...` |
| `HOME_LATITUDE` | Szerokość geograficzna domu | `52.334215` |
| `HOME_LONGITUDE` | Długość geograficzna domu | `20.937516` |
| `HOME_RADIUS` | Promień domu w metrach | `100` |

## 📊 Monitorowanie i logi

### Sprawdzanie logów

```bash
# Logi w czasie rzeczywistym
gcloud logs tail --service=tesla-monitor

# Logi z ostatniej godziny
gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=tesla-monitor" --limit=50 --format=json
```

### Health Check

Aplikacja udostępnia endpoint zdrowia:
```bash
curl https://TWOJ_SERVICE_URL/health
```

Odpowiedź:
```json
{
  "status": "healthy",
  "is_running": true,
  "active_cases": 0,
  "timestamp": "2024-01-15T10:30:00"
}
```

## 🔍 Logika monitorowania

System działa zgodnie z następującą logiką:

### Harmonogram sprawdzania (CZAS WARSZAWSKI - Europe/Warsaw):
- **07:00-23:00**: sprawdzanie co 15 minut
- **23:00-07:00**: sprawdzanie co 60 minut
- **00:00**: jednorazowe wybudzenie pojazdu i sprawdzenie stanu

**⚠️ WAŻNE**: Wszystkie godziny odnoszą się do **czasu warszawskiego (Europe/Warsaw)**, niezależnie od tego, gdzie hostowana jest aplikacja w Google Cloud. System automatycznie konwertuje czas UTC (używany przez Google Cloud) na czas warszawski.

### Warunki logowania:

#### ✅ Warunek A
**Gdy**: pojazd ONLINE + `is_charging_ready=true` + lokalizacja HOME
**Akcja**: Log "Car ready for schedule" z poziomem baterii

#### ✅ Warunek B
**Gdy**: pojazd ONLINE + lokalizacja HOME + `is_charging_ready=false` (pierwszy raz)
**Akcja**: 
1. Monitoruj do przejścia w stan OFFLINE
2. Po OFFLINE → log "Car ready for checking status"
3. Wybudź pojazd → log "Car was awaken"
4. Sprawdź status po wybudzeniu

#### ✅ Nocne wybudzenie
**Gdy**: codziennie o godzinie 00:00 **czasu warszawskiego**
**Akcja**: 
1. Wybudź pojazd → log "Midnight wake-up initiated"
2. Sprawdź status po wybudzeniu → log "Midnight status check completed" z danymi

#### ❌ Pozostałe przypadki
**Gdy**: pojazd OFFLINE lub lokalizacja ≠ HOME lub przypadek B już trwa
**Akcja**: Brak logowania (zgodnie z wymaganiami minimalnego logowania)

## 🗄️ Przechowywanie danych

### Google Cloud Storage
- **Bucket**: `tesla-monitor-data-TWOJ_PROJECT_ID`
- **Plik stanu**: `monitoring_state.json` - aktywne przypadki monitorowania

### Google Cloud Firestore
- **Kolekcja**: `tesla_monitor_logs` - szczegółowe logi zdarzeń

## ⏰ Strefa czasowa

### Konfiguracja czasu warszawskiego
Aplikacja jest skonfigurowana do pracy w **strefie czasowej Europe/Warsaw** niezależnie od lokalizacji serwerów Google Cloud:

- **Harmonogram monitorowania**: wszystkie godziny (07:00, 23:00, 00:00) odnoszą się do czasu warszawskiego
- **Logowanie zdarzeń**: każdy log zawiera timestamp w czasie warszawskim + UTC
- **Automatyczna konwersja**: system automatycznie konwertuje czas UTC (Google Cloud) na czas warszawski
- **Obsługa czasu letniego/zimowego**: biblioteka `pytz` automatycznie obsługuje przejścia DST

### Przykład logów z czasem:
```json
{
  "timestamp": "2024-01-15T10:30:00+01:00",
  "timestamp_utc": "2024-01-15T09:30:00Z",
  "timezone": "Europe/Warsaw",
  "message": "Car ready for schedule"
}
```

## 🔧 Rozwiązywanie problemów

### Problem: Aplikacja nie startuje
```bash
# Sprawdź logi
gcloud logs read "resource.type=cloud_run_revision" --limit=10

# Sprawdź zmienne środowiskowe
gcloud run services describe tesla-monitor --region=europe-west1
```

### Problem: Brak połączenia z Tesla API
1. Sprawdź poprawność `TESLA_CLIENT_ID` i `TESLA_CLIENT_SECRET`
2. Upewnij się, że klucz publiczny jest dostępny pod `TESLA_PUBLIC_KEY_URL`
3. Sprawdź czy plik `private-key.pem` jest w kontenerze

### Problem: Nieprawidłowa lokalizacja
1. Sprawdź `HOME_LATITUDE` i `HOME_LONGITUDE`
2. Dostosuj `HOME_RADIUS` jeśli potrzeba
3. Tesla Fleet API może nie udostępniać lokalizacji ze względów prywatności

## 📈 Skalowanie i koszty

### Konfiguracja zasobów:
- **CPU**: 1 vCPU
- **Pamięć**: 512Mi
- **Instancje**: 1 (singleton)
- **Timeout**: 3600s (1 godzina)

### Szacunkowe koszty miesięczne:
- **Cloud Run**: ~$5-10 (przy ciągłym działaniu)
- **Cloud Storage**: ~$0.50 (dla logów i stanu)
- **Cloud Logging**: ~$1-2 (w zależności od ilości logów)

## 🔒 Bezpieczeństwo

### Zalecenia:
1. **Nie commituj** plików `.env`, `private-key.pem`, `fleet_tokens.json`
2. Używaj **Google Secret Manager** dla wrażliwych danych
3. Regularnie **rotuj klucze** Tesla Fleet API
4. Monitoruj **logi dostępu** do aplikacji

### Konfiguracja Secret Manager (opcjonalnie):

```bash
# Utwórz sekrety
gcloud secrets create tesla-client-secret --data-file=-
gcloud secrets create tesla-private-key --data-file=private-key.pem

# Nadaj uprawnienia Cloud Run
gcloud secrets add-iam-policy-binding tesla-client-secret \
    --member="serviceAccount:TWOJ_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

## 📞 Wsparcie

W przypadku problemów:
1. Sprawdź logi aplikacji
2. Zweryfikuj konfigurację Tesla Fleet API
3. Upewnij się, że wszystkie wymagane API są włączone
4. Sprawdź limity i kwoty Google Cloud

---

**Uwaga**: System został zaprojektowany jako inteligentny monitor z minimalnym logowaniem - loguje tylko gdy to rzeczywiście potrzebne, zgodnie z określonymi warunkami. 