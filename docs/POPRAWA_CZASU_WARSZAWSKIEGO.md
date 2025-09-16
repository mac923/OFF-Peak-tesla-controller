# Poprawa obsługi czasu warszawskiego w harmonogramie

## Problem

Aplikacja Tesla Controller używała harmonogramu z zadaniem zaplanowanym na godzinę 00:00, ale nie było jasne czy to jest 00:00 UTC czy 00:00 czasu warszawskiego. Użytkownik wskazał, że godziny były pomyślane w kontekście czasu warszawskiego, ale implementacja mogła działać w UTC.

## Główna zmiana

### Zadanie o północy
**Przed:**
```python
schedule.every().day.at("00:00").do(self.run_midnight_wake_check)
```

**Po:**
```python
schedule.every().day.at("00:00", "Europe/Warsaw").do(self.run_midnight_wake_check)
```

### Wymagania
Dodano do `requirements.txt`:
```
# Scheduling and timezone handling
schedule>=1.2.0
pytz>=2023.3
```

## Weryfikacja

### Prawidłowe działanie
1. **Interwały monitorowania** - funkcja `_get_monitoring_schedule_interval()` już prawidłowo używa `self._get_warsaw_time()`:
   - 07:00-23:00 (czas warszawski): co 15 minut
   - 23:00-07:00 (czas warszawski): co 60 minut

2. **Nocne wybudzenie** - funkcja `run_midnight_wake_check()` już używa `self._get_warsaw_time()` dla logowania.

3. **Wszystkie pozostałe operacje** - używają `self._get_warsaw_time()` do logowania i operacji czasowych.

## Rezultat

Teraz zadanie nocnego wybudzenia pojazdu będzie uruchamiane dokładnie o 00:00 czasu warszawskiego (Europe/Warsaw), a nie UTC. Oznacza to, że:

- **Zimą** (UTC+1): zadanie wykona się o 01:00 UTC
- **Latem** (UTC+2): zadanie wykona się o 02:00 UTC

## Konsekwencje dla Google Cloud

Aplikacja działająca na Google Cloud Run będzie teraz prawidłowo interpretować godziny w kontekście czasu warszawskiego, niezależnie od strefy czasowej serwera.

## Biblioteka schedule

Używamy funkcjonalności `schedule.every().day.at("HH:MM", "timezone")` z biblioteki `schedule>=1.2.0`, która wspiera strefy czasowe poprzez `pytz`.

Dokumentacja: https://schedule.readthedocs.io/en/stable/timezones.html

## Testowanie

Aby zweryfikować poprawność działania, sprawdź logi aplikacji o godzinach granicznych:
- 23:00-01:00 (zmiana z 15-minutowego na 60-minutowy interwał)
- 07:00-09:00 (zmiana z 60-minutowego na 15-minutowy interwał)
- 00:00 (wykonanie zadania nocnego wybudzenia)

Wszystkie te operacje powinny następować według czasu warszawskiego, nie UTC. 