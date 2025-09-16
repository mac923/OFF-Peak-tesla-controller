#!/bin/bash

# Startup script dla Tesla Worker Service
# Część architektury "Scout & Worker" dla agresywnej optymalizacji kosztów

echo "🔧 === TESLA WORKER SERVICE STARTUP ==="
echo "💰 Architektura: Scout & Worker (agresywna optymalizacja kosztów)"
echo "🎯 Zadanie: Pełna logika Tesla z proxy (on-demand)"
echo ""

# Sprawdź czy jesteśmy w Worker mode
if [ "$TESLA_WORKER_MODE" != "true" ]; then
    echo "❌ BŁĄD: TESLA_WORKER_MODE nie jest ustawiony na 'true'"
    echo "💡 To jest Worker Service - wymaga TESLA_WORKER_MODE=true"
    exit 1
fi

echo "✅ Worker Mode aktywny"

# Sprawdź dostępność Tesla HTTP Proxy
if command -v tesla-http-proxy >/dev/null 2>&1; then
    echo "✅ Tesla HTTP Proxy dostępny: $(which tesla-http-proxy)"
    export TESLA_PROXY_AVAILABLE=true
else
    echo "⚠️ Tesla HTTP Proxy niedostępny - Worker będzie działać bez proxy"
    export TESLA_PROXY_AVAILABLE=false
fi

# NAPRAWKA: Pobierz private key z Secret Manager przez Python (bo gcloud niedostępny)
if [ -n "$GOOGLE_CLOUD_PROJECT" ] && [ "$TESLA_PROXY_AVAILABLE" = "true" ]; then
    echo "🔐 Pobieranie private key z Secret Manager przez Python..."
    
    python3 -c "
import os
import sys
from google.cloud import secretmanager

try:
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
    secret_name = f'projects/{project_id}/secrets/tesla-private-key/versions/latest'
    
    print('📡 Łączenie z Google Secret Manager...')
    response = client.access_secret_version(request={'name': secret_name})
    
    print('📥 Pobieranie private key...')
    with open('private-key.pem', 'wb') as f:
        f.write(response.payload.data)
    
    os.chmod('private-key.pem', 0o600)
    
    # Weryfikuj czy klucz jest prawidłowy (prime256v1)
    key_size = os.path.getsize('private-key.pem')
    if key_size == 0:
        print('❌ Private key jest pusty')
        sys.exit(1)
    
    with open('private-key.pem', 'r') as f:
        key_content = f.read()
        if 'BEGIN EC PRIVATE KEY' not in key_content and 'BEGIN PRIVATE KEY' not in key_content:
            print('❌ Private key ma nieprawidłowy format')
            sys.exit(1)
    
    print(f'✅ Private key pobrany pomyślnie ({key_size} bajtów)')
    print('🔑 Klucz zweryfikowany - gotowy dla Tesla HTTP Proxy')
    
except Exception as e:
    print(f'❌ Błąd pobierania private key: {e}')
    print('💡 Worker będzie działać bez proxy (tylko monitorowanie)')
    # Utwórz pusty plik żeby aplikacja nie crashowała
    with open('private-key.pem', 'w') as f:
        f.write('')
"
    
    if [ $? -eq 0 ]; then
        echo "✅ Private key gotowy dla Tesla HTTP Proxy"
        export TESLA_PRIVATE_KEY_READY=true
    else
        echo "⚠️ Private key niedostępny - proxy może nie działać"
        export TESLA_PRIVATE_KEY_READY=false
    fi
else
    echo "⚠️ Pomijam pobieranie private key (brak GOOGLE_CLOUD_PROJECT lub proxy niedostępny)"
    export TESLA_PRIVATE_KEY_READY=false
fi

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

# Ustaw zmienne środowiskowe dla proxy
export TESLA_HTTP_PROXY_HOST=${TESLA_HTTP_PROXY_HOST:-localhost}
export TESLA_HTTP_PROXY_PORT=${TESLA_HTTP_PROXY_PORT:-4443}

echo ""
echo "🔧 Konfiguracja Worker Service:"
echo "   Worker Mode: $TESLA_WORKER_MODE"
echo "   Continuous Mode: $CONTINUOUS_MODE"
echo "   Smart Proxy Mode: $TESLA_SMART_PROXY_MODE"
echo "   Proxy Available: $TESLA_PROXY_AVAILABLE"
echo "   Private Key Ready: $TESLA_PRIVATE_KEY_READY"
echo "   Google Sheets Key Ready: $GOOGLE_SHEETS_KEY_READY"
echo "   Proxy Host: $TESLA_HTTP_PROXY_HOST"
echo "   Proxy Port: $TESLA_HTTP_PROXY_PORT"
echo "   Project: $GOOGLE_CLOUD_PROJECT"
echo ""

# Wyświetl informacje o architekturze
echo "🏗️ ARCHITEKTURA SCOUT & WORKER:"
echo "   🔍 Scout Function: Lekka, tania, sprawdza lokalizację co 15 min"
echo "   🔧 Worker Service: Ciężka, droga, pełna logika 2-3x dziennie"
echo "   💰 Optymalizacja kosztów: ~96% redukcja vs poprzednia wersja"
echo ""

# NAPRAWKA: Weryfikuj gotowość systemu przed uruchomieniem Worker
echo "🔍 Weryfikacja gotowości systemu..."

# Sprawdź czy wszystkie komponenty są gotowe
SYSTEM_READY=true

if [ "$TESLA_PROXY_AVAILABLE" = "true" ] && [ "$TESLA_PRIVATE_KEY_READY" != "true" ]; then
    echo "⚠️ Tesla HTTP Proxy dostępny ale private key niegotowy"
    echo "💡 Worker będzie działać w trybie ograniczonym (bez komend)"
fi

if [ "$GOOGLE_SHEETS_KEY_READY" != "true" ]; then
    echo "⚠️ Google Sheets key niegotowy - Special Charging może nie działać"
    echo "💡 Sprawdź czy GOOGLE_SERVICE_ACCOUNT_KEY jest w Secret Manager"
fi

if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    echo "⚠️ GOOGLE_CLOUD_PROJECT nie ustawiony - może brakować sekretów"
    SYSTEM_READY=false
fi

# Sprawdź dostęp do Secret Manager
python3 -c "
from google.cloud import secretmanager
try:
    client = secretmanager.SecretManagerServiceClient()
    print('✅ Google Secret Manager dostępny')
except Exception as e:
    print(f'⚠️ Problem z Secret Manager: {e}')
" 2>/dev/null

if [ "$SYSTEM_READY" = "true" ]; then
    echo "✅ System gotowy do uruchomienia Worker Service"
else
    echo "⚠️ System ma ograniczenia - Worker uruchomi się w trybie fallback"
fi

echo ""

# Uruchom Worker Service w tle
echo "🚀 Uruchamianie Tesla Worker Service..."
python3 cloud_tesla_worker.py &

# Zapisz PID procesu głównego
WORKER_PID=$!
echo "✅ Worker Service uruchomiony (PID: $WORKER_PID)"

# Funkcja cleanup
cleanup() {
    echo ""
    echo "🛑 Otrzymano sygnał zatrzymania - zamykanie Worker Service..."
    
    # Zatrzymaj Worker Service
    if kill -0 $WORKER_PID 2>/dev/null; then
        echo "🛑 Zatrzymywanie Worker Service (PID: $WORKER_PID)..."
        kill -TERM $WORKER_PID
        
        # Czekaj na zakończenie (max 10 sekund)
        for i in {1..10}; do
            if ! kill -0 $WORKER_PID 2>/dev/null; then
                echo "✅ Worker Service zatrzymany"
                break
            fi
            sleep 1
        done
        
        # Jeśli nadal działa, wymuś zatrzymanie
        if kill -0 $WORKER_PID 2>/dev/null; then
            echo "⚠️ Wymuszam zatrzymanie Worker Service..."
            kill -KILL $WORKER_PID
        fi
    fi
    
    echo "✅ Cleanup zakończony"
    exit 0
}

# Obsługa sygnałów
trap cleanup SIGTERM SIGINT

# Czekaj na zakończenie Worker Service
echo "💓 Worker Service działa - oczekuje na wywołania..."
echo "🔗 Endpoints dostępne:"
echo "   GET  /health - Health check"
echo "   GET  /worker-status - Szczegółowy status"
echo "   GET  /get-token - Centralne zarządzanie tokenami Tesla"
echo "   POST /run-cycle - Pełny cykl monitorowania" 
echo "   POST /scout-trigger - Wywołanie od Scout Function"
echo "   POST /refresh-tokens - Wymuszenie odświeżenia tokenów"
echo "   POST /daily-special-charging-check - Special Charging check"
echo "   POST /send-special-schedule-immediate - Natychmiastowe Special Charging"
echo ""

# Główna pętla - czekaj na zakończenie procesu Worker
while kill -0 $WORKER_PID 2>/dev/null; do
    sleep 5
done

# Jeśli Worker Service zakończył się sam
echo "⚠️ Worker Service zakończył się nieoczekiwanie"
exit 1 