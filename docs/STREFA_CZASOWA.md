# ⏰ Strefa czasowa w Cloud Tesla Monitor

## 🎯 Kluczowa informacja

**Wszystkie referencje czasowe w aplikacji odnoszą się do CZASU WARSZAWSKIEGO (Europe/Warsaw), niezależnie od lokalizacji serwerów Google Cloud.**

## 📍 Szczegóły implementacji

### Harmonogram monitorowania
- **07:00-23:00** → sprawdzanie co 15 minut (**czas warszawski**)
- **23:00-07:00** → sprawdzanie co 60 minut (**czas warszawski**)
- **00:00** → jednorazowe wybudzenie pojazdu (**czas warszawski**)

### Przykład działania
```
Google Cloud (UTC):    20:08:27
Warszawa (CEST):       22:08:27  ← TO JEST CZAS REFERENCYJNY
Różnica:               +2 godziny (czas letni)
```

## 🔧 Implementacja techniczna

### Biblioteka pytz
```python
import pytz
self.timezone = pytz.timezone('Europe/Warsaw')
warsaw_time = datetime.now(self.timezone)
```

### Automatyczna konwersja
- Google Cloud działa w UTC
- Aplikacja automatycznie konwertuje na czas warszawski
- Obsługa czasu letniego/zimowego jest automatyczna

### Struktura logów
```json
{
  "timestamp": "2025-06-06T22:08:27+02:00",      // Czas warszawski
  "timestamp_utc": "2025-06-06T20:08:27Z",       // Czas UTC (Google Cloud)
  "timezone": "Europe/Warsaw",                   // Strefa czasowa
  "message": "Car ready for schedule"
}
```

## 🌍 Dlaczego to ważne?

### Problem bez strefy czasowej
Bez jednoznacznego określenia strefy czasowej:
- Godzina 07:00 mogłaby oznaczać UTC, lokalny czas serwera, lub czas użytkownika
- Harmonogram mógłby działać nieprzewidywalnie
- Logi byłyby niejednoznaczne

### Rozwiązanie
✅ **Jednoznaczne określenie**: Europe/Warsaw  
✅ **Automatyczna konwersja**: UTC → Warszawa  
✅ **Obsługa DST**: czas letni/zimowy automatycznie  
✅ **Przejrzystość logów**: oba timestampy (lokalny + UTC)  

## 📊 Przykłady działania

### Czas letni (CEST = UTC+2)
```
UTC:      06:00  →  Warszawa: 08:00  →  Interwał: 15 min (dzienne)
UTC:      21:00  →  Warszawa: 23:00  →  Interwał: 60 min (nocne)
UTC:      22:00  →  Warszawa: 00:00  →  Wybudzenie pojazdu
```

### Czas zimowy (CET = UTC+1)
```
UTC:      06:00  →  Warszawa: 07:00  →  Interwał: 15 min (dzienne)
UTC:      22:00  →  Warszawa: 23:00  →  Interwał: 60 min (nocne)
UTC:      23:00  →  Warszawa: 00:00  →  Wybudzenie pojazdu
```

## 🧪 Test strefy czasowej

Uruchom test demonstracyjny:
```bash
python test_timezone.py
```

Wynik pokazuje:
- Aktualny czas UTC vs warszawski
- Różnicę czasową (+1 lub +2 godziny)
- Symulację harmonogramu dla różnych godzin
- Przykład struktury logów z timestampami

## ✅ Podsumowanie

1. **Referencja czasowa**: Europe/Warsaw (czas warszawski)
2. **Harmonogram**: 07:00, 23:00, 00:00 = czas warszawski
3. **Automatyka**: konwersja UTC → Warszawa
4. **DST**: automatyczna obsługa czasu letniego/zimowego
5. **Logi**: podwójny timestamp (lokalny + UTC)
6. **Niezależność**: działa wszędzie, niezależnie od lokalizacji serwerów

**Aplikacja zawsze wie, która jest godzina w Warszawie! 🇵🇱** 