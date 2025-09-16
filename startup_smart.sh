#!/bin/bash

# Smart Startup Script dla Cloud Tesla Monitor
# Uruchamia aplikację BEZ proxy, ale proxy może być uruchomiony on-demand

set -e

echo "🚀 Smart Cloud Tesla Monitor - uruchamianie..."

# Pobierz klucz prywatny z Secret Manager (potrzebny dla proxy)
echo "🔑 Pobieranie klucza prywatnego z Secret Manager..."
python -c "
import os
from google.cloud import secretmanager

try:
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ.get('GOOGLE_CLOUD_PROJECT')
    secret_name = f'projects/{project_id}/secrets/tesla-private-key/versions/latest'
    response = client.access_secret_version(request={'name': secret_name})
    
    with open('private-key.pem', 'wb') as f:
        f.write(response.payload.data)
    
    os.chmod('private-key.pem', 0o600)
    print('✅ Klucz prywatny pobrany z Secret Manager')
    
except Exception as e:
    print(f'⚠️ Błąd pobierania klucza: {e}')
    print('💡 Aplikacja będzie działać bez proxy (tylko monitoring)')
    # Utwórz pusty plik żeby aplikacja nie crashowała
    with open('private-key.pem', 'w') as f:
        f.write('')
"

# Funkcja sprawdzająca czy tesla-http-proxy jest dostępny
check_proxy_available() {
    if command -v tesla-http-proxy >/dev/null 2>&1; then
        echo "✅ tesla-http-proxy jest dostępny"
        return 0
    else
        echo "❌ tesla-http-proxy nie jest dostępny"
        return 1
    fi
}

# Sprawdź czy proxy jest dostępny
if check_proxy_available; then
    echo "🔧 Tesla HTTP Proxy jest dostępny - można używać komend"
    export TESLA_PROXY_AVAILABLE="true"
else
    echo "⚠️ Tesla HTTP Proxy nie jest dostępny - tylko monitoring"
    export TESLA_PROXY_AVAILABLE="false"
fi

# Ustaw zmienne środowiskowe dla aplikacji
export TESLA_HTTP_PROXY_HOST="localhost"
export TESLA_HTTP_PROXY_PORT="${TESLA_HTTP_PROXY_PORT:-4443}"
export TESLA_SMART_PROXY_MODE="true"  # Nowy tryb smart proxy

echo "🔧 Konfiguracja Smart Proxy:"
echo "   Proxy available: $TESLA_PROXY_AVAILABLE"
echo "   Host: $TESLA_HTTP_PROXY_HOST"
echo "   Port: $TESLA_HTTP_PROXY_PORT"
echo "   Smart mode: $TESLA_SMART_PROXY_MODE"

# Funkcja czyszczenia
cleanup() {
    echo "🛑 Zatrzymywanie procesów..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Uruchom główną aplikację Python
echo "🐍 Uruchamianie aplikacji Python..."
python cloud_tesla_monitor.py &

PYTHON_PID=$!
echo "✅ Aplikacja Python uruchomiona (PID: $PYTHON_PID)"

echo "🎉 Smart Tesla Monitor uruchomiony!"
echo "🌐 Tesla Monitor: http://localhost:$PORT"
echo "💡 Proxy uruchamiany on-demand gdy potrzebne komendy"

# Monitoruj proces aplikacji
while true; do
    if ! kill -0 $PYTHON_PID 2>/dev/null; then
        echo "❌ Aplikacja Python się zatrzymała"
        exit 1
    fi
    
    sleep 30
done 