# Ograniczenia Tesla Fleet API - Problemy i Rozwiązania

## 🚫 Problem: Brak Obsługi Usuwania Harmonogramów

### Objaw
```
❌ Błąd API (412): not supported
📍 Żądanie: POST /api/1/vehicles/{VIN}/command/remove_charge_schedule
💥 Nieoczekiwany błąd żądania: 412 Client Error: Precondition Failed
```

### Przyczyna
**Tesla Fleet API nie obsługuje komendy `remove_charge_schedule`** dla większości pojazdów. 

**Błąd 412 "Precondition Failed"** z komunikatem `"not supported"` oznacza, że:
- Komenda nie jest dostępna dla tego typu pojazdu
- Funkcjonalność nie jest implementowana w publicznym Fleet API
- **ROZWIĄZANIE: Tesla HTTP Proxy** obsługuje wszystkie komendy

## ✅ Rozwiązanie: Tesla HTTP Proxy (Zaimplementowane)

### Jak Działa
Tesla HTTP Proxy działa jako lokalny serwer proxy który:
1. **Podpisuje komendy** kluczem prywatnym aplikacji
2. **Przekazuje żądania** do Tesla Fleet API
3. **Obsługuje wszystkie komendy** włącznie z `remove_charge_schedule`

### Konfiguracja w Cloud Tesla Monitor
```bash
# W .env lub zmiennych środowiskowych
TESLA_HTTP_PROXY_HOST=localhost
TESLA_HTTP_PROXY_PORT=4443
```

### Implementacja w Dockerfile
```dockerfile
# Pobierz i zbuduj Tesla HTTP Proxy
FROM golang:1.23-bullseye AS builder
RUN git clone https://github.com/teslamotors/vehicle-command.git /build
WORKDIR /build
RUN go build -o tesla-http-proxy ./cmd/tesla-http-proxy/main.go

# Skopiuj do głównego kontenera
COPY --from=builder /build/tesla-http-proxy /usr/local/bin/tesla-http-proxy
```

### Uruchamianie w startup.sh
```bash
# Generuj certyfikaty TLS
openssl req -x509 -newkey rsa:4096 -keyout tls-key.pem -out tls-cert.pem -days 365 -nodes

# Uruchom Tesla HTTP Proxy w tle
tesla-http-proxy \
    -tls-key tls-key.pem \
    -cert tls-cert.pem \
    -port 4443 \
    -host 127.0.0.1 \
    -key-name "tesla-fleet-api" \
    -keyring-type file \
    -key-file private-key.pem &
```

### Diagnostyka w cloud_tesla_monitor.py
```python
# Automatyczne wykrywanie Tesla HTTP Proxy
proxy_host = os.getenv('TESLA_HTTP_PROXY_HOST')
proxy_port = os.getenv('TESLA_HTTP_PROXY_PORT')
if proxy_host and proxy_port:
    logger.info(f"🔗 Tesla HTTP Proxy skonfigurowane: {proxy_host}:{proxy_port}")
    self._test_tesla_proxy_connection(proxy_host, proxy_port)
else:
    logger.warning("⚠️ Tesla HTTP Proxy NIE jest skonfigurowane")
```

## 🔧 Status Implementacji

### ✅ Co Zostało Naprawione
1. **Tesla HTTP Proxy** - zbudowany i uruchamiany w kontenerze Docker
2. **Automatyczna konfiguracja** - zmienne środowiskowe ustawione w Cloud Run
3. **Diagnostyka połączenia** - test Tesla HTTP Proxy przy starcie aplikacji
4. **Lepsze logowanie błędów** - szczegółowa analiza problemów z usuwaniem
5. **Obsługa błędów** - kontynuacja mimo problemów z usuwaniem

### 🔍 Nowe Logowanie
```
🔧 Inicjalizacja TeslaController...
🔗 Tesla HTTP Proxy skonfigurowane: localhost:4443
🔗 Testuję połączenie z Tesla HTTP Proxy: https://localhost:4443
✅ Tesla HTTP Proxy odpowiada (status: 401)
🔐 Tesla HTTP Proxy wymaga autoryzacji - to normalne
```

### 📊 Proces Zarządzania Harmonogramami
```
[19:02] 🗑️ Usuwanie 2 starych harmonogramów HOME...
🗑️ Próba usunięcia harmonogramu HOME ID: 1750416515
📋 Harmonogram 1750416515: 780-960, enabled=True
🔧 TeslaController używa Tesla HTTP Proxy (URL: https://localhost:4443)
✅ Usunięto harmonogram HOME ID: 1750416515
[19:02] ✅ Pomyślnie usunięto stare harmonogramy HOME
```

## 🚀 Wdrożenie

### Dla Google Cloud Run
1. **Dockerfile** - już zawiera budowanie Tesla HTTP Proxy
2. **startup.sh** - już uruchamia Tesla HTTP Proxy
3. **cloud-run-service.yaml** - już ma zmienne środowiskowe
4. **cloud_tesla_monitor.py** - już testuje połączenie

### Dla Lokalnego Developmentu
```bash
# Ustaw zmienne środowiskowe
export TESLA_HTTP_PROXY_HOST=localhost
export TESLA_HTTP_PROXY_PORT=4443

# Uruchom Tesla HTTP Proxy
tesla-http-proxy -tls-key tls-key.pem -cert tls-cert.pem -port 4443 -key-file private-key.pem &

# Uruchom aplikację
python cloud_tesla_monitor.py
```

## 🎯 Inne Znane Ograniczenia Tesla Fleet API

### 1. Ograniczona Funkcjonalność Komend
- **Rozwiązanie: Tesla HTTP Proxy** - obsługuje wszystkie komendy
- Publiczne Fleet API ma **ograniczony zestup** dostępnych komend
- Wiele funkcji z aplikacji mobilnej **wymaga proxy**

### 2. Wymagania dla Komend
- Większość komend wymaga **wybudzenia pojazdu**
- Niektóre komendy wymagają **specjalnych uprawnień**
- **Scope'y aplikacji** muszą być prawidłowo skonfigurowane

### 3. Problemy z Autoryzacją
```
❌ Błąd API (401): unauthorized
❌ Błąd API (403): forbidden
```

**Rozwiązania:**
- Sprawdź **tokeny dostępu** (refresh_token)
- Zweryfikuj **scope'y aplikacji** w Tesla Developer Portal
- Upewnij się że aplikacja ma uprawnienia **vehicle_cmds** i **vehicle_charging_cmds**

## 📋 Zalecenia

### Dla Programistów
1. **ZAWSZE używaj Tesla HTTP Proxy** dla komend pojazdu
2. **Implementuj fallback rozwiązania** dla błędów autoryzacji
3. **Testuj połączenie z proxy** przy starcie aplikacji
4. **Monitoruj logi** pod kątem błędów proxy

### Dla Użytkowników
1. **Tesla HTTP Proxy jest wymagany** dla pełnej funkcjonalności
2. **Sprawdzaj logi startowe** pod kątem problemów z proxy
3. **Zgłaszaj problemy** gdy proxy nie uruchamia się poprawnie
4. **Upewnij się o certyfikatach TLS** (są generowane automatycznie)

## 🔮 Status i Monitoring

### Sprawdzanie Stanu Tesla HTTP Proxy
```bash
# W kontenerze Docker
curl -k https://localhost:4443/api/1/vehicles
```

### Oczekiwane Odpowiedzi
- **200**: Proxy działa, autoryzacja OK
- **401**: Proxy działa, brak autoryzacji (normalne)
- **Connection refused**: Proxy nie działa

### Typowe Problemy
1. **Proxy nie uruchamia się** - sprawdź klucz prywatny i certyfikaty
2. **Timeout połączenia** - sprawdź port 4443
3. **413 Request Entity Too Large** - sprawdź konfigurację proxy

---

**Data aktualizacji:** 2025-01-25  
**Status:** Problem rozwiązany przez implementację Tesla HTTP Proxy  
**Wersja aplikacji:** Cloud Tesla Monitor v2 z Tesla HTTP Proxy 