# 🔧 Tesla HTTP Proxy - Przewodnik

Tesla HTTP Proxy to narzędzie umożliwiające komunikację z nowszymi pojazdami Tesla (2021+) wymagającymi Fleet API z podpisanymi komendami.

## 📋 Wymagania

- Pojazd Tesla z 2021 roku lub nowszy
- Zainstalowany `tesla-http-proxy`
- Certyfikaty TLS i klucz prywatny
- Skonfigurowane Fleet API w portalu Tesla Developer

## 🚀 Szybki start

### 1. Sprawdź instalację
```bash
# Sprawdź czy tesla-http-proxy jest zainstalowany
which tesla-http-proxy

# Sprawdź wersję
tesla-http-proxy --version
```

### 2. Przygotuj certyfikaty
```bash
# Sprawdź czy masz wymagane pliki
ls -la *.pem

# Powinny być:
# - tls-key.pem (klucz TLS)
# - tls-cert.pem (certyfikat TLS) 
# - private-key.pem (klucz prywatny do podpisywania komend)
```

### 3. Uruchom proxy
```bash
tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose
```

### 4. Skonfiguruj program
```bash
# Dodaj do pliku .env
echo "TESLA_HTTP_PROXY_HOST=localhost" >> .env
echo "TESLA_HTTP_PROXY_PORT=4443" >> .env
```

### 5. Wygeneruj token Fleet API
```bash
# Usuń stary token
rm fleet_tokens.json

# Wygeneruj nowy token
python3 generate_token.py
```

## 🔍 Weryfikacja działania

### Sprawdź czy proxy działa
```bash
# Test połączenia
curl -k https://localhost:4443/api/1/vehicles

# Powinno zwrócić błąd autoryzacji (to normalne)
# {"response":null,"error":"Forbidden","error_description":""}
```

### Sprawdź logi proxy
Proxy powinno wyświetlać:
```
[info] Listening on localhost:4443
[debug] Loading cache from /Users/username/.tesla-cache.json...
[debug] Creating proxy
```

### Sprawdź program
Program powinien wyświetlić:
```
Używam Tesla HTTP Proxy: https://localhost:4443
✓ Fleet API klient zainicjalizowany
```

## 📝 Przykład pełnego workflow

### Terminal 1: Uruchom proxy
```bash
cd /path/to/your/certificates
tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose
```

### Terminal 2: Uruchom program
```bash
cd /path/to/tesla-controller
source venv/bin/activate

# Ustaw zmienne proxy (jeśli nie w .env)
export TESLA_HTTP_PROXY_HOST=localhost
export TESLA_HTTP_PROXY_PORT=4443

# Uruchom program
python3 run.py
```

## 🔧 Konfiguracja zaawansowana

### Zmienne środowiskowe
```bash
# W pliku .env
TESLA_HTTP_PROXY_HOST=localhost
TESLA_HTTP_PROXY_PORT=4443

# Opcjonalne - dla zdalnego proxy
TESLA_HTTP_PROXY_HOST=192.168.1.100
TESLA_HTTP_PROXY_PORT=4443
```

### Parametry proxy
```bash
tesla-http-proxy \
  -tls-key tls-key.pem \          # Klucz TLS
  -cert tls-cert.pem \            # Certyfikat TLS
  -port 4443 \                    # Port proxy
  -key-file private-key.pem \     # Klucz prywatny Fleet API
  -verbose \                      # Szczegółowe logi
  -cache /path/to/cache.json      # Opcjonalnie: ścieżka do cache
```

## 📊 Monitorowanie proxy

### Logi proxy
Proxy wyświetla szczegółowe informacje:
```
[info] Received POST request for /api/1/vehicles/VIN/command/set_scheduled_charging
[debug] Executing set_scheduled_charging on VIN
[info] Starting dispatcher service...
[debug] Sending request to https://fleet-api.prd.eu.vn.cloud.tesla.com/...
[debug] Server returned 200: OK
```

### Sprawdzenie procesów
```bash
# Sprawdź czy proxy działa
ps aux | grep tesla-http-proxy

# Sprawdź port
netstat -an | grep 4443
lsof -i :4443
```

## 🛠️ Rozwiązywanie problemów

### ❌ Proxy nie startuje

**Błąd: "bind: address already in use"**
```bash
# Sprawdź co używa portu 4443
lsof -i :4443

# Zabij proces lub użyj innego portu
tesla-http-proxy ... -port 4444
```

**Błąd: "no such file or directory"**
```bash
# Sprawdź ścieżki do certyfikatów
ls -la tls-key.pem tls-cert.pem private-key.pem

# Użyj pełnych ścieżek
tesla-http-proxy -tls-key /full/path/to/tls-key.pem ...
```

### ❌ Program nie łączy się z proxy

**Błąd: "Nie można połączyć z proxy"**
```bash
# Sprawdź czy proxy działa
curl -k https://localhost:4443/api/1/vehicles

# Sprawdź zmienne środowiskowe
echo $TESLA_HTTP_PROXY_HOST
echo $TESLA_HTTP_PROXY_PORT
```

**Błąd SSL**
```bash
# Sprawdź certyfikaty TLS
openssl x509 -in tls-cert.pem -text -noout

# Sprawdź czy klucz pasuje do certyfikatu
openssl rsa -in tls-key.pem -check
```

### ❌ Błędy komend

**Błąd: "expected 17-character VIN"**
- Program automatycznie używa VIN zamiast Fleet API ID
- Sprawdź czy masz najnowszą wersję programu

**Błąd: "Forbidden"**
```bash
# Sprawdź token Fleet API
cat fleet_tokens.json

# Wygeneruj nowy token
python3 generate_token.py
```

**Błąd: "session not found"**
- Proxy automatycznie zarządza sesjami
- Restart proxy może pomóc

## 🔄 Automatyzacja

### Skrypt startowy
```bash
#!/bin/bash
# start_tesla_proxy.sh

cd /path/to/certificates
tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose &

echo "Tesla HTTP Proxy uruchomiony na porcie 4443"
echo "PID: $!"
```

### Systemd service (Linux)
```ini
# /etc/systemd/system/tesla-http-proxy.service
[Unit]
Description=Tesla HTTP Proxy
After=network.target

[Service]
Type=simple
User=tesla
WorkingDirectory=/home/tesla/certificates
ExecStart=/usr/local/bin/tesla-http-proxy -tls-key tls-key.pem -cert tls-cert.pem -port 4443 -key-file private-key.pem
Restart=always

[Install]
WantedBy=multi-user.target
```

### Uruchomienie w tle (macOS/Linux)
```bash
# Uruchom proxy w tle
nohup tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose > proxy.log 2>&1 &

# Sprawdź logi
tail -f proxy.log
```

## 📚 Dodatkowe informacje

### Bezpieczeństwo
- Proxy działa lokalnie na `localhost:4443`
- Używa certyfikatów TLS do szyfrowania
- Klucz prywatny jest używany tylko do podpisywania komend
- Nie przechowuje danych logowania Tesla

### Wydajność
- Proxy automatycznie zarządza sesjami z pojazdem
- Cache sesji przyspiesza kolejne komendy
- Verbose mode może spowolnić działanie

### Kompatybilność
- Działa z pojazdami Tesla 2021+
- Obsługuje wszystkie komendy Fleet API
- Kompatybilny z Tesla Controller

## 🔗 Przydatne linki

- [Tesla Vehicle Command](https://github.com/teslamotors/vehicle-command)
- [Tesla Developer Portal](https://developer.tesla.com/)
- [Fleet API Documentation](https://developer.tesla.com/docs/fleet-api)

---

**Uwaga**: Tesla HTTP Proxy jest narzędziem Tesla Motors. Ten przewodnik opisuje jego użycie z Tesla Controller. 

# Sprawdź czy wszystkie zmienne są ustawione
grep TESLA_ .env 