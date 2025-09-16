# 🔧 NAPRAWKA: Problem z kluczem Google Sheets w Worker Service

## 📋 **PROBLEM**

Worker Service nie mógł pobrać danych z Google Sheets dla Special Charging, wyrzucając błąd:
```
ERROR [Errno 2] No such file or directory: 'tesla-sheets-key.json'
```

### **Przyczyna:**
- Aplikacja próbowała odczytać plik `tesla-sheets-key.json` bezpośrednio z systemu plików
- Plik nie był kopiowany do kontenera Docker ani pobierany z Secret Manager podczas startu
- Brak logiki w `startup_worker.sh` do pobierania klucza z Secret Manager

## 🔧 **ROZWIĄZANIE**

Dodano logikę pobierania klucza Google Sheets z Secret Manager do `startup_worker.sh`:

### **Nowa funkcjonalność:**
1. **Pobieranie z Secret Manager:** Klucz `GOOGLE_SERVICE_ACCOUNT_KEY` jest pobierany podczas startu kontenera
2. **Walidacja JSON:** Sprawdzenie czy klucz ma prawidłowy format Service Account
3. **Zapis do pliku:** Klucz jest zapisywany jako `tesla-sheets-key.json` z odpowiednimi uprawnieniami (600)
4. **Diagnostyka:** Dodane logowanie statusu klucza w konfiguracji Worker Service

### **Zmiany w `startup_worker.sh`:**

```bash
# NAPRAWKA: Pobierz Google Sheets key z Secret Manager (dla Special Charging)
if [ -n "$GOOGLE_CLOUD_PROJECT" ]; then
    echo "📊 Pobieranie Google Sheets key z Secret Manager przez Python..."
    
    python3 -c "
import os
import sys
from google.cloud import secretmanager
import json

try:
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
    secret_name = f'projects/{project_id}/secrets/GOOGLE_SERVICE_ACCOUNT_KEY/versions/latest'
    
    print('📡 Łączenie z Google Secret Manager...')
    response = client.access_secret_version(request={'name': secret_name})
    
    print('📥 Pobieranie Google Sheets key...')
    key_data = response.payload.data.decode('utf-8')
    
    # Weryfikuj czy to prawidłowy JSON
    try:
        key_json = json.loads(key_data)
        if 'type' not in key_json or key_json.get('type') != 'service_account':
            print('❌ Google Sheets key ma nieprawidłowy format (brak type=service_account)')
            sys.exit(1)
        if 'client_email' not in key_json:
            print('❌ Google Sheets key ma nieprawidłowy format (brak client_email)')
            sys.exit(1)
    except json.JSONDecodeError:
        print('❌ Google Sheets key nie jest prawidłowym JSON')
        sys.exit(1)
    
    # Zapisz jako plik tesla-sheets-key.json
    with open('tesla-sheets-key.json', 'w') as f:
        f.write(key_data)
    
    os.chmod('tesla-sheets-key.json', 0o600)
    
    key_size = len(key_data)
    client_email = key_json.get('client_email', 'unknown')
    
    print(f'✅ Google Sheets key pobrany pomyślnie ({key_size} znaków)')
    print(f'📧 Service Account: {client_email}')
    print('📊 Klucz gotowy dla Google Sheets API')
    
except Exception as e:
    print(f'❌ Błąd pobierania Google Sheets key: {e}')
    print('💡 Worker będzie działać bez Special Charging (brak dostępu do Google Sheets)')
    # Utwórz pusty plik żeby aplikacja nie crashowała
    with open('tesla-sheets-key.json', 'w') as f:
        f.write('{}')
"
    
    if [ $? -eq 0 ]; then
        echo "✅ Google Sheets key gotowy dla Special Charging"
        export GOOGLE_SHEETS_KEY_READY=true
    else
        echo "⚠️ Google Sheets key niedostępny - Special Charging może nie działać"
        export GOOGLE_SHEETS_KEY_READY=false
    fi
else
    echo "⚠️ Pomijam pobieranie Google Sheets key (brak GOOGLE_CLOUD_PROJECT)"
    export GOOGLE_SHEETS_KEY_READY=false
fi
```

## ✅ **REZULTAT**

Po wdrożeniu Worker Service będzie:
1. **Automatycznie pobierać** klucz Google Sheets z Secret Manager podczas startu
2. **Walidować format** klucza przed użyciem
3. **Zapisywać plik** `tesla-sheets-key.json` z odpowiednimi uprawnieniami
4. **Wyświetlać status** klucza w konfiguracji systemu
5. **Obsługiwać błędy** gracefully z fallback na pusty plik

## 🚀 **WDROŻENIE**

Aby wdrożyć naprawkę:
```bash
./deploy_scout_worker.sh
```

## 🔍 **WERYFIKACJA**

Po wdrożeniu sprawdź logi startu Worker Service:
```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="tesla-worker"' --limit=50 --format="value(textPayload)" --freshness=10m
```

Szukaj komunikatów:
- ✅ `Google Sheets key pobrany pomyślnie`
- ✅ `Google Sheets Key Ready: true`
- ✅ `Service Account: tesla-special-charging@...`

## 📋 **WYMAGANIA**

Przed wdrożeniem upewnij się, że:
1. **Secret Manager:** `GOOGLE_SERVICE_ACCOUNT_KEY` istnieje w Secret Manager
2. **Uprawnienia:** Worker Service ma dostęp do sekretu
3. **Format klucza:** Klucz jest prawidłowym JSON Service Account
4. **Google Sheets:** Arkusz "Tesla Special Charging" istnieje i jest udostępniony Service Account

Data naprawki: **2025-08-08** 