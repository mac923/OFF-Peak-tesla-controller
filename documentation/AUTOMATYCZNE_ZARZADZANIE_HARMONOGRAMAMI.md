# 🔋 Automatyczne zarządzanie harmonogramami ładowania

## Przegląd

Nowa funkcjonalność aplikacji Tesla Controller umożliwia automatyczne zarządzanie harmonogramami ładowania na podstawie danych z API OFF PEAK CHARGE. System porównuje harmonogramy i aktualizuje je tylko wtedy, gdy się zmieniły.

## ⚙️ Jak to działa

### 1. Wykrycie warunków ładowania
Aplikacja wykrywa warunek A (pojazd gotowy do ładowania w domu):
- Pojazd jest ONLINE
- `is_charging_ready = true`
- Lokalizacja = HOME

### 2. Wywołanie API OFF PEAK CHARGE
Gdy wykryje warunek A:
- Wywołuje API OFF PEAK CHARGE z danymi pojazdu
- Pobiera optymalny harmonogram ładowania

### 3. Porównanie harmonogramów
System porównuje nowy harmonogram z poprzednim:
- Generuje hash MD5 z kluczowych danych harmonogramu
- Porównuje z hash'em z poprzedniej próby
- Jeśli hash jest identyczny → nic nie robi
- Jeśli hash jest różny → przechodzi do aktualizacji

### 4. Zarządzanie harmonogramami Tesla
Gdy harmonogram jest różny:
1. **Pobiera** wszystkie harmonogramy z pojazdu Tesla
2. **Filtruje** harmonogramy HOME (w okolicy domowej lokalizacji)
3. **Usuwa** wszystkie stare harmonogramy HOME
4. **Konwertuje** harmonogramy z API OFF PEAK CHARGE do formatu Tesla
5. **Dodaje** nowe harmonogramy do pojazdu

## 🛠️ Wymagania

### Tesla HTTP Proxy
Nowa funkcjonalność wymaga Tesla HTTP Proxy dla wysyłania komend do pojazdu:

```bash
# Instalacja tesla-http-proxy
npm install -g tesla-http-proxy

# Uruchomienie proxy
tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose
```

### Konfiguracja zmiennych środowiskowych
```bash
# W pliku .env
TESLA_HTTP_PROXY_HOST=localhost
TESLA_HTTP_PROXY_PORT=4443

# Lokalizacja domowa (dla filtrowania harmonogramów HOME)
HOME_LATITUDE=52.334215
HOME_LONGITUDE=20.937516
HOME_RADIUS=0.15
```

### Sekrety Google Cloud (opcjonalne)
```bash
# Jeśli używasz Google Cloud Secret Manager
gcloud secrets create tesla-http-proxy-host --data="localhost"
gcloud secrets create tesla-http-proxy-port --data="4443"
```

## 📋 Konfiguracja harmonogramów

### Format danych wejściowych (API OFF PEAK CHARGE)
```json
{
  "success": true,
  "data": {
    "chargingSchedule": [
      {
        "start_time": "2024-01-15T22:00:00.000Z",
        "end_time": "2024-01-15T23:00:00.000Z",
        "charge_amount": 2.75
      },
      {
        "start_time": "2024-01-16T01:00:00.000Z",
        "end_time": "2024-01-16T03:00:00.000Z",
        "charge_amount": 5.5
      }
    ]
  }
}
```

### Format danych wyjściowych (Tesla)
System automatycznie konwertuje harmonogram na format Tesla:
- **Czas**: Konwersja z UTC na czas warszawski
- **Minuty**: Konwersja na minuty od północy
- **Dni tygodnia**: Ustawiane na "All" (wszystkie dni)
- **Lokalizacja**: Ustawiana na HOME (z konfiguracji)
- **Tryb**: Harmonogram ciągły (nie jednorazowy)

## 🔍 Logowanie i monitorowanie

### Logi operacji
```
[14:30] 🔄 Harmonogram RÓŻNY - rozpoczynam zarządzanie harmonogramami Tesla
[14:30] 📋 Pobieranie obecnych harmonogramów HOME...
[14:30] 📍 Znaleziono 2 harmonogramów HOME z 3 całkowitych
[14:30] 🗑️ Usuwanie 2 starych harmonogramów HOME...
[14:30] 🗑️ Usunięto harmonogram HOME ID: 123
[14:30] 🗑️ Usunięto harmonogram HOME ID: 124
[14:30] 🔄 Konwersja harmonogramów z API OFF PEAK CHARGE...
[14:30] 📅 Harmonogram #1: 22:00-23:00 (1320-1380 min), 2.75 kWh
[14:30] 📅 Harmonogram #2: 01:00-03:00 (60-180 min), 5.5 kWh
[14:30] ✅ Skonwertowano 2 harmonogramów z API OFF PEAK CHARGE
[14:30] ➕ Dodawanie 2 nowych harmonogramów...
[14:30] ✅ Dodano harmonogram #1: 22:00-23:00
[14:30] ✅ Dodano harmonogram #2: 01:00-03:00
[14:30] ✅ Pomyślnie zaktualizowano harmonogramy Tesla
```

### Logi gdy harmonogram jest identyczny
```
[14:30] 📋 Harmonogram dla ABC123: IDENTYCZNY (hash: 1a2b3c4d...)
[14:30] 📋 Harmonogram IDENTYCZNY - nie wykonuję zmian w Tesla
```

### Logi błędów
```
[14:30] ❌ Błąd aktualizacji harmonogramów Tesla
[14:30] ❌ Nie można połączyć się z Tesla API
[14:30] ❌ Błąd usuwania harmonogramu HOME ID: 123
```

## 🎯 Korzyści

### ✅ Optymalizacja energii
- Automatyczne wykorzystanie najtańszych godzin ładowania
- Ładowanie zgodnie z cenami energii w czasie rzeczywistym

### ✅ Oszczędność czasu
- Brak konieczności ręcznego ustawiania harmonogramów
- Automatyczna aktualizacja gdy zmienią się warunki

### ✅ Minimalizacja niepotrzebnych operacji
- Aktualizacja tylko gdy harmonogram rzeczywiście się zmienił
- Porównanie hash'ów zamiast pełnych danych

### ✅ Dokładne logowanie
- Szczegółowe logi wszystkich operacji
- Możliwość debugowania problemów
- Śledzenie historii zmian

## 🛡️ Bezpieczeństwo

### Filtrowanie harmonogramów HOME
- Usuwa tylko harmonogramy w okolicy domowej lokalizacji
- Nie wpływa na harmonogramy w innych lokalizacjach (praca, podróże)
- Configurowalne parametry lokalizacji

### Obsługa błędów
- Rollback przy nieudanej operacji
- Szczegółowe logowanie błędów
- Timeout'y dla operacji API

### Walidacja danych
- Sprawdzanie poprawności danych z API OFF PEAK CHARGE
- Walidacja czasów ładowania
- Sprawdzanie dostępności pojazdu

## 🔧 Rozwiązywanie problemów

### Błąd: "Nie można połączyć się z Tesla API"
```bash
# Sprawdź czy Tesla HTTP Proxy działa
curl -k https://localhost:4443/api/1/vehicles

# Sprawdź zmienne środowiskowe
echo $TESLA_HTTP_PROXY_HOST
echo $TESLA_HTTP_PROXY_PORT
```

### Błąd: "Brak harmonogramów HOME"
```bash
# Sprawdź konfigurację lokalizacji
echo $HOME_LATITUDE
echo $HOME_LONGITUDE
echo $HOME_RADIUS

# Zwiększ promień wyszukiwania
export HOME_RADIUS=0.2
```

### Błąd: "OFF PEAK CHARGE API failed"
```bash
# Sprawdź sekrety Google Cloud
gcloud secrets versions access latest --secret="OFF_PEAK_CHARGE_API_KEY"
gcloud secrets versions access latest --secret="OFF_PEAK_CHARGE_API_URL"
```

## 📊 Przykład kompletnego workflow

```
1. [14:30] ✅ VIN=ABC123, bateria=65%, ładowanie=gotowe, lokalizacja=HOME
2. [14:30] 🔄 Wywołuję OFF PEAK CHARGE API
3. [14:30] ✅ OFF PEAK CHARGE API - sukces
4. [14:30] 📋 Harmonogram dla ABC123: RÓŻNY (hash: 1a2b3c4d...)
5. [14:30] 🔧 Rozpoczęto zarządzanie harmonogramami Tesla dla ABC123
6. [14:30] 📋 Pobieranie obecnych harmonogramów HOME...
7. [14:30] 📍 Znaleziono 2 harmonogramów HOME z 3 całkowitych
8. [14:30] 🗑️ Usuwanie 2 starych harmonogramów HOME...
9. [14:30] 🗑️ Usunięto 2/2 harmonogramów HOME
10. [14:30] 🔄 Konwersja harmonogramów z API OFF PEAK CHARGE...
11. [14:30] ✅ Skonwertowano 2 harmonogramów z API OFF PEAK CHARGE
12. [14:30] ➕ Dodawanie 2 nowych harmonogramów...
13. [14:30] ✅ Dodano 2/2 harmonogramów do Tesla
14. [14:30] ✅ Pomyślnie zaktualizowano harmonogramy Tesla
```

## 🚀 Testowanie

### Test manualny
```bash
# Uruchom monitor z debugowaniem
python3 cloud_tesla_monitor.py --debug

# W osobnym terminalu - wymuś warunek A
curl -X POST http://localhost:8080/test/condition-a
```

### Test automatyczny
```bash
# Uruchom testy jednostkowe
python3 -m pytest tests/test_schedule_management.py -v
```

## 📈 Przyszłe rozszerzenia

### Planowane funkcjonalności
- [ ] Obsługa wielu lokalizacji (dom, praca, etc.)
- [ ] Integracja z prognozą pogody
- [ ] Optymalizacja na podstawie planów podróży
- [ ] Powiadomienia push o zmianach harmonogramu
- [ ] Dashboard web do zarządzania harmonogramami 