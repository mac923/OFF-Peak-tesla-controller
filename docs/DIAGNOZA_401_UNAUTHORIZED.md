# Diagnoza błędu 401 Unauthorized - Tesla Fleet API

## Zidentyfikowana przyczyna

**Główny problem:** Brak prawidłowego procesu uwierzytelniania OAuth2 dla Tesla Fleet API.

### Szczegóły błędu:
```
✗ Błąd odświeżania tokenu: 401 Client Error: Unauthorized for url: https://auth.tesla.com/oauth2/v3/token
Błąd pobierania pojazdów: Brak ważnego tokenu dostępu
```

## Możliwe przyczyny:

### 1. **Wygasły lub nieważny token**
- Token w `fleet_tokens.json` może być wygasły
- Token został unieważniony przez Tesla
- Refresh token jest nieprawidłowy

### 2. **Nieprawidłowa konfiguracja OAuth2**
- CLIENT_ID/CLIENT_SECRET nie pasują do zarejestrowanej aplikacji
- Brak zgody użytkownika (consent) dla wymaganych scope'ów
- Aplikacja nie została poprawnie zarejestrowana w Tesla Developer Portal

### 3. **Problemy z regionem**
- Używanie tokenu z jednego regionu w innym
- Nieprawidłowy URL autoryzacji dla regionu

### 4. **Problemy z kluczami kryptograficznymi**
- Klucz prywatny nie pasuje do klucza publicznego
- Nieprawidłowe podpisywanie komend

## Kroki rozwiązania:

### Krok 1: Sprawdzenie konfiguracji
```bash
# Sprawdź plik .env - czy wszystkie wartości są poprawne
grep TESLA_ .env
```

### Krok 2: Regeneracja tokenów
```bash
# Usuń stare tokeny
rm fleet_tokens.json

# Wygeneruj nowe tokeny
python3 generate_token.py
```

### Krok 3: Sprawdzenie rejestracji aplikacji
1. Sprawdź czy aplikacja jest zarejestrowana w Tesla Developer Portal
2. Sprawdź czy domena jest poprawnie skonfigurowana  
3. Sprawdź czy klucz publiczny jest dostępny pod odpowiednim URL

### Krok 4: Test tokenów
```bash
# Test tokenu przez curl
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "https://fleet-api.prd.eu.vn.cloud.tesla.com/api/1/vehicles"
```

### Krok 5: Sprawdzenie scope'ów
Upewnij się że token ma wymagane scope'y:
- `openid`
- `offline_access` 
- `vehicle_device_data`
- `vehicle_cmds`
- `vehicle_charging_cmds`

## Zalecane działania:

### Opcja A: Pełna regeneracja (ZALECANE)
1. Usuń plik `fleet_tokens.json`
2. Uruchom `python3 generate_token.py`
3. Przejdź przez pełny proces OAuth2
4. Przetestuj nowe tokeny

### Opcja B: Sprawdzenie istniejących tokenów
1. Sprawdź ważność tokenu przez API Tesla
2. Sprawdź czy refresh token jest prawidłowy
3. Spróbuj manualnie odświeżyć token

### Opcja C: Sprawdzenie konfiguracji
1. Zweryfikuj CLIENT_ID i CLIENT_SECRET
2. Sprawdź czy domena jest poprawnie skonfigurowana
3. Sprawdź dostępność klucza publicznego

## Logi debugowe:

Aby uzyskać więcej informacji o błędzie, dodaj do kodu:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Uwaga bezpieczeństwa:

**NIE UDOSTĘPNIAJ** tokenów, CLIENT_SECRET ani kluczy prywatnych w logach lub publicznie.

## Następne kroki:

1. **Najpierw spróbuj Opcji A** - pełna regeneracja tokenów
2. Jeśli nie pomoże, sprawdź konfigurację aplikacji w Tesla Developer Portal
3. W ostateczności skontaktuj się z Tesla Developer Support

---

**Status:** 📋 Diagnoza - wymagane działanie użytkownika
**Priorytet:** 🔴 Wysoki - blokuje funkcjonalność
**Przewidywany czas rozwiązania:** 15-30 minut 