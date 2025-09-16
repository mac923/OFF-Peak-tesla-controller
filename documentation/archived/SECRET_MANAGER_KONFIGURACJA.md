# 🔐 Konfiguracja Google Cloud Secret Manager dla Tesla Monitor

## 🚨 Problem z sekretami - błąd 403

Jeśli widzisz w logach aplikacji błąd:
```
WARNING 2025-06-18T12:33:07.101901Z Nie można odczytać sekretu OFF_PEAK_CHARGE_API_KEY: 403 Permission 'secretmanager.versions.access' denied for resource 'projects/off-peak-tesla-controller/secrets/OFF_PEAK_CHARGE_API_KEY/versions/latest' (or it may not exist).
```

To oznacza że:
1. **Sekrety nie istnieją** w Google Cloud Secret Manager, ALBO
2. **Cloud Run nie ma uprawnień** do odczytu sekretów

## ✅ Rozwiązanie krok po kroku

### 1. 🔑 Utwórz sekrety OFF Peak API

```bash
# Ustaw zmienne
export GOOGLE_CLOUD_PROJECT="off-peak-tesla-controller"  # Twój projekt
export OFF_PEAK_API_KEY="twoj-klucz-api"               # Klucz do OFF Peak API
export OFF_PEAK_API_URL="http://localhost:3000/api/external-calculate"  # URL API

# Utwórz sekret dla klucza API
echo -n "$OFF_PEAK_API_KEY" | gcloud secrets create OFF_PEAK_CHARGE_API_KEY \
    --project=$GOOGLE_CLOUD_PROJECT \
    --data-file=-

# Utwórz sekret dla URL API (opcjonalny)
echo -n "$OFF_PEAK_API_URL" | gcloud secrets create OFF_PEAK_CHARGE_API_URL \
    --project=$GOOGLE_CLOUD_PROJECT \
    --data-file=-
```

### 2. 🤖 Nadaj uprawnienia Cloud Run service account

```bash
# Pobierz numer projektu
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")

# Cloud Run używa domyślnego service account compute
CLOUD_RUN_SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

# Nadaj uprawnienia do odczytu sekretów
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:$CLOUD_RUN_SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

echo "✅ Uprawnienia nadane dla: $CLOUD_RUN_SERVICE_ACCOUNT"
```

### 3. 🔄 Wdroż ponownie aplikację

```bash
# Ponowne wdrożenie z poprawionymi uprawnieniami
./deploy_to_cloud.sh
```

## 📋 Sprawdzenie konfiguracji

### Sprawdź czy sekrety istnieją:
```bash
gcloud secrets list --project=$GOOGLE_CLOUD_PROJECT
```

### Sprawdź uprawnienia service account:
```bash
gcloud projects get-iam-policy $GOOGLE_CLOUD_PROJECT \
    --flatten="bindings[].members" \
    --format='table(bindings.role)' \
    --filter="bindings.members:*compute@developer.gserviceaccount.com"
```

### Sprawdź czy aplikacja odczytuje sekrety:
```bash
# Sprawdź logi aplikacji
gcloud logs tail --service=tesla-monitor --region=europe-west1

# Szukaj komunikatów:
# ✅ "Sekret OFF_PEAK_CHARGE_API_KEY znaleziony"
# ❌ "Sekret OFF_PEAK_CHARGE_API_KEY nie został znaleziony!"
```

## 🔧 Zaktualizowany skrypt wdrażania

Najnowsza wersja `deploy_to_cloud.sh` **automatycznie** konfiguruje uprawnienia Secret Manager podczas wdrażania. Jeśli używasz starszej wersji, zaktualizuj skrypt lub wykonaj manualnie:

```bash
# Manualnie nadaj uprawnienia (jeśli skrypt nie robił tego automatycznie)
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

## 🎯 Co robi aplikacja z sekretami

Aplikacja Tesla Monitor używa tych sekretów do:

1. **OFF_PEAK_CHARGE_API_KEY**: Autoryzacja przy wywołaniach OFF Peak Charge API
2. **OFF_PEAK_CHARGE_API_URL**: URL endpoint'u API (opcjonalny, ma domyślną wartość)

### Kiedy są używane:
- Gdy pojazd spełnia **warunek A**: ONLINE + gotowy do ładowania + w domu
- Po **nocnym wybudzeniu** o 00:00 czasu warszawskiego (jeśli warunek A spełniony)

### Logi sukcesu:
```
[12:33] ✅ Sekret OFF_PEAK_CHARGE_API_KEY znaleziony
[12:33] ✅ Sekret OFF_PEAK_CHARGE_API_URL: http://localhost:3000/api/external-calculate
[12:33] 🚀 ROZPOCZĘCIE _call_off_peak_charge_api - bateria: 75%, VIN: 1234
[12:33] ✅ OFF PEAK CHARGE API - sukces
```

## 🚨 Troubleshooting

### Problem: Sekrety nie istnieją
```bash
# Sprawdź czy sekrety istnieją
gcloud secrets list --project=$GOOGLE_CLOUD_PROJECT

# Jeśli brak, utwórz je
echo -n "twoj-klucz-api" | gcloud secrets create OFF_PEAK_CHARGE_API_KEY --data-file=-
```

### Problem: Brak uprawnień 403
```bash
# Sprawdź service account
gcloud run services describe tesla-monitor --region=europe-west1 --format="value(spec.template.spec.serviceAccountName)"

# Nadaj uprawnienia
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format="value(projectNumber)")
gcloud projects add-iam-policy-binding $GOOGLE_CLOUD_PROJECT \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### Problem: Aplikacja nadal nie może odczytać
```bash
# Restart aplikacji po zmianie uprawnień
gcloud run services update tesla-monitor --region=europe-west1

# Sprawdź logi
gcloud logs tail --service=tesla-monitor --region=europe-west1
```

---

**✅ Po wykonaniu tych kroków aplikacja powinna móc prawidłowo odczytać sekrety i wywołać OFF Peak Charge API.** 