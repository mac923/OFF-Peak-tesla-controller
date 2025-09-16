#!/bin/bash

# Startup script dla Cloud Tesla Monitor z Tesla HTTP Proxy
# Uruchamia Tesla proxy w tle, a następnie główną aplikację

set -e

echo "🚀 Uruchamianie Cloud Tesla Monitor z Tesla HTTP Proxy..."

# Sprawdź czy certyfikaty TLS istnieją
if [ ! -f "tls-key.pem" ] || [ ! -f "tls-cert.pem" ]; then
    echo "⚠️ Brak certyfikatów TLS - generuję certyfikaty self-signed dla Tesla proxy..."
    
    # Generuj self-signed certyfikat dla localhost
    openssl req -x509 -newkey rsa:4096 -keyout tls-key.pem -out tls-cert.pem -days 365 -nodes \
        -subj "/C=PL/ST=Mazowieckie/L=Warsaw/O=Tesla Monitor/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
    
    echo "✅ Wygenerowano certyfikaty TLS"
fi

# Pobierz klucz prywatny z Secret Manager przez Python
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
    print(f'❌ Błąd pobierania klucza: {e}')
    print('💡 Sprawdź uprawnienia Secret Manager')
"

# Zmienne dla Tesla HTTP Proxy
TESLA_PROXY_PORT=${TESLA_HTTP_PROXY_PORT:-4443}
TESLA_PROXY_HOST=127.0.0.1  # BEZPIECZEŃSTWO: Tylko localhost

echo "🔧 Konfiguracja Tesla HTTP Proxy:"
echo "   Host: $TESLA_PROXY_HOST"
echo "   Port: $TESLA_PROXY_PORT"
echo "   TLS Key: tls-key.pem"
echo "   TLS Cert: tls-cert.pem"
echo "   Private Key: private-key.pem"

# Funkcja czyszczenia przy zamykaniu
cleanup() {
    echo "🛑 Zatrzymywanie procesów..."
    kill $(jobs -p) 2>/dev/null || true
    
    echo "🧹 Czyszczenie plików tymczasowych TLS..."
    # Usuń pliki TLS (są generowane przy każdym starcie)
    rm -f tls-key.pem tls-cert.pem 2>/dev/null || true
    
    # NIE USUWAJ private-key.pem - jest z Secret Manager i może być potrzebny!
    
    exit 0
}
trap cleanup SIGTERM SIGINT

# Uruchom Tesla HTTP Proxy w tle - TYLKO localhost
echo "🔄 Uruchamianie Tesla HTTP Proxy (127.0.0.1 TYLKO)..."
tesla-http-proxy \
    -tls-key tls-key.pem \
    -cert tls-cert.pem \
    -port $TESLA_PROXY_PORT \
    -host $TESLA_PROXY_HOST \
    -key-name "tesla-fleet-api" \
    -keyring-type file \
    -key-file private-key.pem \
    > /tmp/proxy.log 2>&1 &

PROXY_PID=$!
echo "✅ Tesla HTTP Proxy uruchomiony (PID: $PROXY_PID)"

# Poczekaj chwilę żeby proxy się uruchomił
sleep 5

# Sprawdź czy proxy działa
echo "🔍 Sprawdzanie czy Tesla proxy działa..."

# Poczekaj dłużej na uruchomienie proxy
sleep 5

# Sprawdź czy proces proxy nadal działa
if kill -0 $PROXY_PID 2>/dev/null; then
    echo "✅ Tesla HTTP Proxy proces działa (PID: $PROXY_PID)"
else
    echo "❌ Tesla HTTP Proxy proces się zatrzymał!"
    echo "🔍 Sprawdzanie logów proxy..."
    # Pokaż ostatnie logi proxy (jeśli są)
    tail -20 /tmp/proxy.log 2>/dev/null || echo "Brak logów proxy"
fi

# Sprawdź odpowiedź HTTP
if curl -k -s --connect-timeout 10 https://localhost:$TESLA_PROXY_PORT/api/1/vehicles > /dev/null 2>&1; then
    echo "✅ Tesla HTTP Proxy odpowiada poprawnie"
else
    echo "⚠️ Tesla HTTP Proxy może nie odpowiadać - sprawdź logi"
    echo "🔍 Test połączenia curl:"
    curl -k -v --connect-timeout 10 https://localhost:$TESLA_PROXY_PORT/api/1/vehicles 2>&1 | head -5
fi

# Ustaw zmienne środowiskowe dla aplikacji Python
export TESLA_HTTP_PROXY_HOST=localhost
export TESLA_HTTP_PROXY_PORT=$TESLA_PROXY_PORT

echo "🔧 Zmienne środowiskowe dla aplikacji:"
echo "   TESLA_HTTP_PROXY_HOST=$TESLA_HTTP_PROXY_HOST"
echo "   TESLA_HTTP_PROXY_PORT=$TESLA_HTTP_PROXY_PORT"

# Uruchom główną aplikację Python
echo "🐍 Uruchamianie aplikacji Python..."
python cloud_tesla_monitor.py &

PYTHON_PID=$!
echo "✅ Aplikacja Python uruchomiona (PID: $PYTHON_PID)"

echo "🎉 Wszystkie procesy uruchomione!"
echo "📊 Tesla HTTP Proxy: https://localhost:$TESLA_PROXY_PORT"
echo "🌐 Tesla Monitor: http://localhost:$PORT"

# Monitoruj procesy - jeśli któryś się zatrzyma, zatrzymaj wszystkie
while true; do
    # Sprawdź czy Tesla proxy działa
    if ! kill -0 $PROXY_PID 2>/dev/null; then
        echo "❌ Tesla HTTP Proxy się zatrzymał - zatrzymuję aplikację"
        kill $PYTHON_PID 2>/dev/null || true
        exit 1
    fi
    
    # Sprawdź czy aplikacja Python działa
    if ! kill -0 $PYTHON_PID 2>/dev/null; then
        echo "❌ Aplikacja Python się zatrzymała - zatrzymuję proxy"
        kill $PROXY_PID 2>/dev/null || true
        exit 1
    fi
    
    # Poczekaj 30 sekund przed następnym sprawdzeniem
    sleep 30
done 