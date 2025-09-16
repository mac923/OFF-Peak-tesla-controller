# External Calculate API

Prosty backend/API w Next.js do obliczania optymalnego harmonogramu ładowania pojazdów elektrycznych dla zewnętrznych klientów.

## 🚀 Szybki start

### 1. Konfiguracja środowiska

Skopiuj i skonfiguruj zmienne środowiskowe:

```bash
# Utwórz plik konfiguracyjny
cp .env.example .env.local

# Edytuj .env.local i ustaw:
# VALID_API_KEYS=your-api-keys-here
# ENERGY_API_KEY=your-energy-api-key
```

### 2. Instalacja zależności

```bash
npm install
```

### 3. Uruchomienie

```bash
# Środowisko deweloperskie
npm run dev

# Produkcja
npm run build
npm start
```

### 4. Test API

```bash
curl -X POST http://localhost:3000/api/external-calculate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "batteryLevel": 65,
    "batteryCapacity": 75,
    "consumption": 18.5,
    "dailyMileage": 120
  }'
```

## 📋 Funkcjonalności

### ✅ Co jest zaimplementowane

- **✅ Import modułu calculate.js** - API korzysta z funkcji `calculateOptimalChargingSchedule` z `lib/calculations/index.js`
- **✅ Endpoint REST API** - `POST /api/external-calculate`
- **✅ Walidacja API key** - Klucze konfigurowane via `VALID_API_KEYS` env variable
- **✅ Rate limiting** - 30 zapytań dziennie na klucz API (in-memory)
- **✅ Walidacja danych wejściowych** - Sprawdzanie wszystkich wymaganych parametrów
- **✅ Obsługa błędów** - Szczegółowe komunikaty błędów w języku polskim
- **✅ Dokumentacja API** - Kompletna dokumentacja w `docs/API_DOCUMENTATION.md`
- **✅ Testy jednostkowe** - Pełny zestaw testów w `tests/external-calculate.test.js`
- **✅ Konfiguracja środowiska** - Instrukcje w `docs/ENVIRONMENT_SETUP.md`

### 🔧 Funkcje API

1. **Obliczenia harmonogramu ładowania**
   - Import i wykonanie logiki z `calculate.js`
   - Zwraca optymalny harmonogram ładowania
   - Uwzględnia ceny energii i warunki pogodowe

2. **System autoryzacji**
   - Weryfikacja kluczy API z env
   - Obsługa headerów `X-API-Key` i `Authorization: Bearer`
   - Bezpieczne logowanie (bez kluczy w logach)

3. **Rate limiting**
   - 30 zapytań dziennie na klucz
   - In-memory implementation z Map()
   - Automatyczne czyszczenie starych wpisów
   - Nagłówki HTTP z informacją o limitach

4. **Walidacja i obsługa błędów**
   - Walidacja wszystkich parametrów wejściowych
   - Szczegółowe komunikaty błędów po polsku
   - Różne kody statusu HTTP (400, 401, 405, 429, 500)

## 📁 Struktura plików

```
├── pages/api/
│   └── external-calculate.js     # Główny endpoint API
├── lib/calculations/
│   ├── index.js                  # Eksport funkcji obliczeniowych
│   ├── core.js                   # Logika podstawowych obliczeń
│   ├── weather.js                # Dane pogodowe
│   ├── pricing.js                # Ceny energii
│   └── scheduling.js             # Harmonogramowanie
├── tests/
│   └── external-calculate.test.js # Testy API
├── docs/
│   ├── API_DOCUMENTATION.md      # Dokumentacja API
│   ├── ENVIRONMENT_SETUP.md      # Konfiguracja środowiska
│   └── API_README.md             # Ten plik
├── jest.config.js               # Konfiguracja testów
└── jest.setup.js               # Setup testów
```

## 🧪 Testowanie

```bash
# Uruchom wszystkie testy
npm test

# Testy w trybie watch
npm run test:watch

# Testy z coverage
npm run test:coverage
```

### Przykłady testów

- ✅ Walidacja metod HTTP
- ✅ Autoryzacja i klucze API
- ✅ Walidacja danych wejściowych
- ✅ Rate limiting
- ✅ Pomyślne odpowiedzi
- ✅ Obsługa błędów

## 📖 Dokumentacja

### Szczegółowa dokumentacja API
👉 [API_DOCUMENTATION.md](./API_DOCUMENTATION.md)

### Konfiguracja środowiska
👉 [ENVIRONMENT_SETUP.md](./ENVIRONMENT_SETUP.md)

## 🔒 Bezpieczeństwo

### Klucze API
- Konfigurowane via zmienne środowiskowe
- Minimum 20 znaków długości
- Obsługa wielu kluczy (oddzielone przecinkami)
- Bezpieczne logowanie (bez wyświetlania kluczy)

### Rate limiting
- 30 zapytań dziennie na klucz
- Reset o północy UTC
- Nagłówki HTTP z informacją o limitach
- Możliwość rozszerzenia o Redis

### Walidacja
- Sprawdzanie wszystkich parametrów wejściowych
- Szczegółowe komunikaty błędów
- Sanityzacja danych wejściowych

## 🚀 Deployment

### Vercel (zalecane)

```bash
# Deploy na Vercel
npm install -g vercel
vercel

# Ustaw zmienne środowiskowe w Vercel Dashboard
```

### Inne platformy

1. **Heroku**
   ```bash
   heroku config:set VALID_API_KEYS=key1,key2
   heroku config:set ENERGY_API_KEY=your-key
   ```

2. **DigitalOcean/AWS/Azure**
   - Skonfiguruj zmienne środowiskowe zgodnie z dokumentacją platformy

## 🐛 Troubleshooting

### Częste problemy

**Błąd: "Missing API key"**
- Sprawdź plik `.env.local`
- Upewnij się że `VALID_API_KEYS` jest ustawione
- Restart serwera po zmianie zmiennych

**Błąd: "Invalid API key"**
- Sprawdź czy klucz jest na liście `VALID_API_KEYS`
- Usuń spacje i ukryte znaki z kluczy

**Rate limit nie działa**
- In-memory rate limiter resetuje się przy restarcie
- W produkcji rozważ Redis

### Logi debugowania

API loguje informacje pomocne w debugowaniu:

```
=== API EXTERNAL CALCULATE ===
API Key: abc123def4...
Parametry: { batteryLevel: 65, ... }
=== API RESPONSE ===
Status: 200 OK
Scheduled slots: 3
Rate limit remaining: 27
```

## 🔧 Rozszerzenia

### Możliwe ulepszenia

1. **Redis rate limiting** - Dla środowiska produkcyjnego
2. **Websocket API** - Dla real-time aktualizacji
3. **Webhooks** - Powiadomienia o zmianach cen
4. **GraphQL endpoint** - Bardziej elastyczne zapytania
5. **API versioning** - `/api/v1/external-calculate`
6. **Middleware autoryzacji** - Centralizacja logiki auth
7. **Monitoring** - Integracja z Sentry/DataDog

### Dodanie Redis rate limitingu

```javascript
// Przykład Redis implementation
const redis = require('redis');
const client = redis.createClient(process.env.REDIS_URL);

async function checkRateLimitRedis(apiKey) {
  const key = `rate_limit:${apiKey}:${new Date().toDateString()}`;
  const current = await client.get(key);
  
  if (current >= 30) {
    return { allowed: false, remaining: 0 };
  }
  
  await client.multi()
    .incr(key)
    .expire(key, 86400) // 24 hours
    .exec();
    
  return { allowed: true, remaining: 30 - (current + 1) };
}
```

## 📞 Wsparcie

W przypadku problemów:

1. Sprawdź dokumentację w folderze `docs/`
2. Uruchom testy: `npm test`
3. Sprawdź logi aplikacji
4. Skontaktuj się z zespołem deweloperskim

---

**Status**: ✅ Gotowe do użycia  
**Wersja**: 1.0.0  
**Ostatnia aktualizacja**: 2024-01-15 