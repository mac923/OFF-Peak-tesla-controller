# Tesla Fleet API - Przewodnik konfiguracji

## Przegląd

Tesla Controller używa wyłącznie **Tesla Fleet API** zgodnie z oficjalną dokumentacją Tesla. Fleet API to nowoczesny, bezpieczny sposób komunikacji z pojazdami Tesla, który zastępuje starsze Owner API.

## Wymagania

### 1. Konto Tesla Developer
- Utwórz konto na [developer.tesla.com](https://developer.tesla.com)
- Zweryfikuj email i włącz uwierzytelnianie dwuskładnikowe

### 2. Aplikacja Fleet API
- Zarejestruj aplikację w portalu Tesla Developer
- Otrzymaj `CLIENT_ID` i `CLIENT_SECRET`
- Skonfiguruj domenę aplikacji

### 3. Klucze kryptograficzne
- Klucz prywatny do podpisywania komend
- Klucz publiczny hostowany na domenie

## Krok po kroku

### Krok 1: Generowanie kluczy

```bash
# Generowanie klucza prywatnego
openssl ecparam -name prime256v1 -genkey -noout -out private-key.pem

# Generowanie klucza publicznego
openssl ec -in private-key.pem -pubout -out public-key.pem
```

### Krok 2: Hostowanie klucza publicznego

Klucz publiczny musi być dostępny pod adresem:
```
https://twoja-domena.com/.well-known/appspecific/com.tesla.3p.public-key.pem
```

**Przykład dla GitHub Pages:**
1. Utwórz repozytorium `twoja-nazwa.github.io`
2. Utwórz strukturę katalogów: `.well-known/appspecific/`
3. Umieść `public-key.pem` jako `com.tesla.3p.public-key.pem`

### Krok 3: Rejestracja aplikacji

Wywołaj endpoint rejestracji:
```bash
curl -X POST https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/partner_accounts \
  -H "Authorization: Bearer YOUR_PARTNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "twoja-domena.com"
  }'
```

### Krok 4: Konfiguracja .env

Utwórz plik `.env` w katalogu głównym:

```bash
# Tesla Fleet API - wymagane
TESLA_CLIENT_ID=twój_client_id_z_portalu_developer
TESLA_CLIENT_SECRET=twój_client_secret_z_portalu_developer
TESLA_DOMAIN=twoja-domena.com
TESLA_PRIVATE_KEY_FILE=private-key.pem
TESLA_PUBLIC_KEY_URL=https://twoja-domena.com/.well-known/appspecific/com.tesla.3p.public-key.pem

# Tesla HTTP Proxy (opcjonalne)
TESLA_HTTP_PROXY_HOST=localhost
TESLA_HTTP_PROXY_PORT=4443

# Inne ustawienia (opcjonalne)
TESLA_TIMEOUT=30
```

### Krok 5: Autoryzacja użytkownika

1. Uruchom aplikację - otrzymasz URL autoryzacji
2. Użytkownik musi przejść przez proces OAuth
3. Aplikacja otrzyma kod autoryzacji
4. Kod zostanie wymieniony na token dostępu

## Struktura plików

```
OFF-Peak-tesla-controller/
├── .env                          # Konfiguracja (nie commituj!)
├── private-key.pem              # Klucz prywatny (nie commituj!)
├── tesla_fleet_api_client.py    # Klient Fleet API
├── tesla_controller.py          # Główny kontroler
├── cli.py                       # Interfejs CLI
├── run.py                       # Skrypt uruchomieniowy
└── requirements.txt             # Zależności Python
```

## Bezpieczeństwo

### ⚠️ WAŻNE - Nie commituj:
- `.env` - zawiera sekrety
- `private-key.pem` - klucz prywatny
- `fleet_tokens.json` - tokeny dostępu

### ✅ Commituj:
- `public-key.pem` - klucz publiczny (musi być dostępny)
- Kod źródłowy aplikacji
- Dokumentację

## Testowanie konfiguracji

```bash
# Sprawdzenie wymagań
python3 run.py

# Test połączenia
python3 cli.py status

# Tryb interaktywny
python3 cli.py interactive
```

## Rozwiązywanie problemów

### Błąd: "Fleet API nie jest zainicjalizowane"
- Sprawdź czy wszystkie zmienne w `.env` są ustawione
- Zweryfikuj ścieżkę do `private-key.pem`

### Błąd: "Klucz prywatny nie znaleziony"
- Upewnij się, że `private-key.pem` istnieje
- Sprawdź ścieżkę w `TESLA_PRIVATE_KEY_FILE`

### Błąd: "Public key not accessible"
- Zweryfikuj czy klucz publiczny jest dostępny pod URL
- Sprawdź konfigurację serwera web

### Błąd: "Invalid client credentials"
- Sprawdź `CLIENT_ID` i `CLIENT_SECRET`
- Upewnij się, że aplikacja jest zarejestrowana

## Przydatne linki

- [Tesla Developer Portal](https://developer.tesla.com)
- [Fleet API Documentation](https://developer.tesla.com/docs/fleet-api)
- [Vehicle Commands](https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands)
- [Authentication Guide](https://developer.tesla.com/docs/fleet-api/authentication/overview)

## Wsparcie

W przypadku problemów:
1. Sprawdź logi aplikacji
2. Zweryfikuj konfigurację Fleet API
3. Sprawdź dokumentację Tesla Developer
4. Skontaktuj się z supportem Tesla Developer (jeśli potrzebne)

---

**Uwaga:** Tesla Fleet API jest jedynym oficjalnie wspieranym sposobem komunikacji z pojazdami Tesla. Stare Owner API (TeslaPy) jest przestarzałe i może przestać działać w przyszłości. 