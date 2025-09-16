# API Dokumentacja - External Calculate

## Przegląd

External Calculate API pozwala zewnętrznym klientom na obliczanie optymalnego harmonogramu ładowania pojazdów elektrycznych na podstawie poziomu baterii, zużycia energii, cen prądu i warunków pogodowych.

## Endpoint

```
POST /api/external-calculate
```

## Autoryzacja

API wymaga klucza autoryzacyjnego, który można przekazać na dwa sposoby:

### Opcja 1: Header X-API-Key
```http
X-API-Key: your-api-key-here
```

### Opcja 2: Authorization Bearer
```http
Authorization: Bearer your-api-key-here
```

## Rate Limiting

- **Limit**: 30 zapytań dziennie na klucz API
- **Reset**: Codziennie o północy UTC
- **Headers odpowiedzi**:
  - `X-RateLimit-Limit`: Maksymalny dzienny limit
  - `X-RateLimit-Remaining`: Pozostałe zapytania
  - `X-RateLimit-Reset`: Data/czas resetu (ISO 8601)

## Parametry wejściowe

### Wymagane parametry

| Parametr | Typ | Opis | Przykład |
|----------|-----|------|----------|
| `batteryLevel` | number | Obecny poziom baterii (%) | `65` |
| `batteryCapacity` | number | Pojemność baterii (kWh) | `75` |
| `consumption` | number | Zużycie na 100km (kWh/100km) | `18.5` |
| `dailyMileage` | number | Dzienny przebieg (km) | `120` |

### Opcjonalne parametry

| Parametr | Typ | Opis | Domyślna wartość |
|----------|-----|------|------------------|
| `chargeLimits.optimalUpper` | number | Docelowy górny poziom baterii (0-1) | `0.8` |
| `chargeLimits.optimalLower` | number | Optymalny dolny poziom baterii (0-1) | `0.5` |
| `chargeLimits.emergency` | number | Krytyczny poziom baterii (0-1) | `0.35` |
| `chargeLimits.chargingRate` | number | Moc ładowania (kWh/h) | `11` |

## Przykład żądania

```json
{
  "batteryLevel": 65,
  "batteryCapacity": 75,
  "consumption": 18.5,
  "dailyMileage": 120,
  "chargeLimits": {
    "optimalUpper": 0.8,
    "optimalLower": 0.5,
    "emergency": 0.35,
    "chargingRate": 11
  }
}
```

## Struktura odpowiedzi

### Sukces (HTTP 200)

```json
{
  "success": true,
  "data": {
    "chargingSchedule": [
      {
        "start_time": "2024-01-15T22:00:00.000Z",
        "end_time": "2024-01-15T23:00:00.000Z",
        "charge_amount": 2.75,
        "avg_price": 0.15,
        "cost": 0.41,
        "is_emergency": false
      }
    ],
    "calculatedLimits": {
      "optimalUpper": 0.8,
      "optimalLower": 0.5,
      "emergency": 0.35,
      "chargingRate": 11
    },
    "summary": {
      "totalEnergy": 8.25,
      "totalCost": 1.24,
      "averagePrice": 0.15,
      "scheduledSlots": 3
    },
    "predictions": [
      {
        "date": "2024-01-16",
        "date_formatted": "16.01.2024",
        "starting_level": 85,
        "ending_level": 72,
        "consumption_kwh": 22.2,
        "charging_kwh": 8.25,
        "will_charge": true,
        "is_today": true
      }
    ],
    "userMessages": [
      "Zaplanowano 3 sesje ładowania na łączną energię 8.25 kWh",
      "Średnia cena energii: 0.15 zł/kWh"
    ]
  },
  "meta": {
    "requestId": "req_1705357200000_abc123def",
    "timestamp": "2024-01-15T20:00:00.000Z",
    "processingTime": 1250,
    "version": "1.0.0"
  },
  "rateLimit": {
    "limit": 30,
    "remaining": 29,
    "reset": "2024-01-16T00:00:00.000Z"
  }
}
```

### Opis pól odpowiedzi

#### chargingSchedule
Tablica z harmonogramem ładowania:
- `start_time`: Początek sesji ładowania (ISO 8601)
- `end_time`: Koniec sesji ładowania (ISO 8601)
- `charge_amount`: Ilość energii do naładowania (kWh)
- `avg_price`: Średnia cena energii w tym okresie (zł/kWh)
- `cost`: Koszt ładowania w tym okresie (zł)
- `is_emergency`: Czy to ładowanie awaryjne

#### calculatedLimits
Obliczone limity baterii:
- `optimalUpper`: Docelowy górny poziom (0-1)
- `optimalLower`: Optymalny dolny poziom (0-1)
- `emergency`: Krytyczny poziom (0-1)
- `chargingRate`: Moc ładowania (kWh/h)

#### summary
Podsumowanie harmonogramu:
- `totalEnergy`: Łączna energia do naładowania (kWh)
- `totalCost`: Łączny przewidywany koszt (zł)
- `averagePrice`: Średnia cena energii (zł/kWh)
- `scheduledSlots`: Liczba zaplanowanych sesji

#### predictions
Prognozy na najbliższe dni:
- `date`: Data (YYYY-MM-DD)
- `date_formatted`: Data w formacie polskim
- `starting_level`: Poziom baterii na początku dnia (%)
- `ending_level`: Poziom baterii na końcu dnia (%)
- `consumption_kwh`: Przewidywane zużycie (kWh)
- `charging_kwh`: Przewidywane ładowanie (kWh)
- `will_charge`: Czy będzie ładowanie tego dnia
- `is_today`: Czy to dzisiejszy dzień

#### userMessages
Tablica komunikatów dla użytkownika (po polsku)

## Kody błędów

### HTTP 400 - Bad Request
```json
{
  "error": "Validation error",
  "message": "Błędne dane wejściowe",
  "errors": [
    "batteryLevel musi być liczbą między 0 a 100",
    "consumption musi być liczbą większą od 0"
  ]
}
```

### HTTP 401 - Unauthorized
```json
{
  "error": "Missing API key",
  "message": "Brak klucza API. Podaj klucz w header X-API-Key lub Authorization: Bearer <key>"
}
```

```json
{
  "error": "Invalid API key",
  "message": "Nieprawidłowy klucz API"
}
```

### HTTP 405 - Method Not Allowed
```json
{
  "error": "Method not allowed",
  "message": "Tylko metoda POST jest obsługiwana"
}
```

### HTTP 429 - Too Many Requests
```json
{
  "error": "Rate limit exceeded",
  "message": "Przekroczono limit 30 zapytań dziennie",
  "rateLimit": {
    "limit": 30,
    "remaining": 0,
    "reset": "2024-01-16T00:00:00.000Z"
  }
}
```

### HTTP 500 - Internal Server Error
```json
{
  "error": "Internal server error",
  "message": "Wystąpił błąd podczas przetwarzania żądania"
}
```

## Przykład użycia (cURL)

```bash
curl -X POST https://your-domain.com/api/external-calculate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "batteryLevel": 65,
    "batteryCapacity": 75,
    "consumption": 18.5,
    "dailyMileage": 120
  }'
```

## Przykład użycia (JavaScript)

```javascript
const response = await fetch('/api/external-calculate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key-here'
  },
  body: JSON.stringify({
    batteryLevel: 65,
    batteryCapacity: 75,
    consumption: 18.5,
    dailyMileage: 120,
    chargeLimits: {
      optimalUpper: 0.8,
      optimalLower: 0.5,
      emergency: 0.35,
      chargingRate: 11
    }
  })
});

const data = await response.json();

if (data.success) {
  console.log('Harmonogram ładowania:', data.data.chargingSchedule);
  console.log('Podsumowanie:', data.data.summary);
} else {
  console.error('Błąd:', data.error);
}
```

## Konfiguracja środowiska

W pliku `.env` lub `.env.local` należy ustawić:

```env
# Klucze API dla zewnętrznych klientów (oddzielone przecinkami)
VALID_API_KEYS=client1-key,client2-key,client3-key

# Klucz do API cen energii Pstryk.pl (używany wewnętrznie)
ENERGY_API_KEY=your-pstryk-api-key
```

## Uwagi bezpieczeństwa

1. **Klucze API** - Przechowuj klucze w bezpieczny sposób i nie udostępniaj ich publicznie
2. **HTTPS** - Zawsze używaj HTTPS w środowisku produkcyjnym
3. **Rate Limiting** - Rate limiter działa w pamięci serwera, więc resetuje się przy restarcie
4. **Logowanie** - API loguje podstawowe informacje o żądaniach (bez wrażliwych danych)

## Wsparcie

W przypadku problemów technicznych lub pytań dotyczących integracji, skontaktuj się z zespołem deweloperskim. 