# Tesla Controller - Fleet API Edition

Program do kontrolowania pojazdu Tesla używający **Tesla Fleet API** zgodnie z oficjalną dokumentacją Tesla.

## 🚀 Funkcje

- ✅ **Sprawdzanie statusu pojazdu** - bateria, zasięg, temperatura
- ✅ **Zarządzanie ładowaniem** - start/stop, limit, prąd ładowania  
- ✅ **Harmonogramy ładowania** - zaawansowane planowanie z czasem rozpoczęcia i zakończenia
- ✅ **Ładowanie w taryfie nocnej** - automatyczne ładowanie w godzinach off-peak
- ✅ **Interfejs CLI** - łatwy w użyciu interfejs wiersza poleceń
- ✅ **Tryb interaktywny** - menu z opcjami
- ✅ **Tesla Fleet API** - nowoczesne, bezpieczne API

## 📋 Wymagania

### Konfiguracja Tesla Fleet API
- Konto Tesla Developer
- Zarejestrowana aplikacja Fleet API
- Klucze kryptograficzne (prywatny + publiczny)
- Hostowana domena z kluczem publicznym

### Środowisko Python
- Python 3.8+
- Biblioteki z `requirements.txt`

## 🛠️ Instalacja

### 1. Klonowanie repozytorium
```bash
git clone https://github.com/twoja-nazwa/OFF-Peak-tesla-controller.git
cd OFF-Peak-tesla-controller
```

### 2. Instalacja zależności
```bash
pip3 install -r requirements.txt
```

### 3. Konfiguracja Fleet API
Szczegółowy przewodnik: [FLEET_API_SETUP.md](FLEET_API_SETUP.md)

**Krótka wersja:**
1. Wygeneruj klucze kryptograficzne
2. Hostuj klucz publiczny na domenie
3. Zarejestruj aplikację w Tesla Developer Portal
4. Skonfiguruj plik `.env`

### 4. Konfiguracja środowiska
Utwórz plik `.env`:
```bash
# Tesla Fleet API - wymagane
TESLA_CLIENT_ID=twój_client_id
TESLA_CLIENT_SECRET=twój_client_secret
TESLA_DOMAIN=twoja-domena.com
TESLA_PRIVATE_KEY_FILE=private-key.pem
TESLA_PUBLIC_KEY_URL=https://twoja-domena.com/.well-known/appspecific/com.tesla.3p.public-key.pem

# Tesla HTTP Proxy (opcjonalne)
TESLA_HTTP_PROXY_HOST=localhost
TESLA_HTTP_PROXY_PORT=4443
```

## 🚀 Użycie

### Szybki start
```bash
# Sprawdzenie konfiguracji
python3 run.py

# Status pojazdu
python3 cli.py status

# Tryb interaktywny
python3 cli.py interactive
```

### Podstawowe komendy
```bash
# Lista pojazdów
python3 cli.py vehicles

# Ustawienie limitu ładowania
python3 cli.py set-limit 80

# Rozpoczęcie ładowania
python3 cli.py start-charge

# Zatrzymanie ładowania
python3 cli.py stop-charge

# Zaplanowane ładowanie
python3 cli.py schedule-charge 02:00
```

### Harmonogramy ładowania
```bash
# Wyświetlenie harmonogramów
python3 cli.py schedules

# Dodanie harmonogramu nocnego (23:00-07:00)
python3 cli.py add-schedule --start-time 23:00 --end-time 07:00 --days "All"

# Harmonogram weekendowy
python3 cli.py add-schedule --start-time 10:00 --end-time 14:00 --days "Saturday,Sunday"

# Usunięcie harmonogramu
python3 cli.py remove-schedule 1

# Usunięcie wszystkich harmonogramów
python3 cli.py remove-all-schedules --confirm
```

## 📊 Przykłady użycia

### Ładowanie w taryfie nocnej
```python
from tesla_controller import TeslaController, ChargeSchedule

controller = TeslaController()
if controller.connect():
    # Harmonogram nocny (23:00-07:00)
    schedule = ChargeSchedule(
        days_of_week="All",
        start_enabled=True,
        start_time=controller.time_to_minutes("23:00"),
        end_enabled=True,
        end_time=controller.time_to_minutes("07:00")
    )
    controller.add_charge_schedule(schedule)
```

### Monitorowanie pojazdu
```python
status = controller.get_vehicle_status()
print(f"Bateria: {status['battery_level']}%")
print(f"Zasięg: {status['battery_range']} km")
print(f"Status: {status['charging_state']}")
```

Więcej przykładów w pliku [examples.py](examples.py)

## 🔧 Tesla HTTP Proxy (opcjonalne)

Dla podpisanych komend można użyć Tesla HTTP Proxy:

```bash
# Instalacja
go install github.com/teslamotors/vehicle-command/cmd/tesla-http-proxy@latest

# Uruchomienie
tesla-http-proxy -tls-key tls-key.pem -cert tls-cert.pem -port 4443 -key-file private-key.pem -verbose
```

## 📁 Struktura projektu

```
OFF-Peak-tesla-controller/
├── tesla_controller.py          # Główny kontroler (Fleet API)
├── tesla_fleet_api_client.py    # Klient Fleet API
├── cli.py                       # Interfejs CLI
├── run.py                       # Skrypt uruchomieniowy
├── examples.py                  # Przykłady użycia
├── requirements.txt             # Zależności Python
├── FLEET_API_SETUP.md          # Przewodnik konfiguracji
└── .env                        # Konfiguracja (nie commituj!)
```

## 🔒 Bezpieczeństwo

### ⚠️ Nie commituj do repozytorium:
- `.env` - zawiera sekrety API
- `private-key.pem` - klucz prywatny
- `fleet_tokens.json` - tokeny dostępu
- `*.pem` - certyfikaty TLS

### ✅ Bezpieczne do commitowania:
- Kod źródłowy aplikacji
- `public-key.pem` - klucz publiczny (musi być dostępny)
- Dokumentacja

## 🆘 Rozwiązywanie problemów

### Błędy konfiguracji
```bash
# Sprawdzenie wymagań
python3 run.py

# Test połączenia
python3 cli.py status --help
```

### Częste problemy
1. **"Fleet API nie jest zainicjalizowane"** - sprawdź `.env`
2. **"Klucz prywatny nie znaleziony"** - sprawdź ścieżkę do `private-key.pem`
3. **"Public key not accessible"** - zweryfikuj URL klucza publicznego
4. **"Invalid client credentials"** - sprawdź CLIENT_ID i CLIENT_SECRET

## 📚 Dokumentacja

- [Tesla Fleet API Setup](FLEET_API_SETUP.md) - Szczegółowy przewodnik konfiguracji
- [Tesla Developer Portal](https://developer.tesla.com) - Oficjalna dokumentacja
- [Fleet API Docs](https://developer.tesla.com/docs/fleet-api) - Dokumentacja API

## 🤝 Wkład w projekt

1. Fork repozytorium
2. Utwórz branch dla funkcji (`git checkout -b feature/AmazingFeature`)
3. Commit zmian (`git commit -m 'Add some AmazingFeature'`)
4. Push do branch (`git push origin feature/AmazingFeature`)
5. Otwórz Pull Request

## 📄 Licencja

Ten projekt jest licencjonowany na licencji MIT - zobacz plik [LICENSE](LICENSE) dla szczegółów.

## ⚠️ Zastrzeżenia

- Ten projekt nie jest oficjalnie powiązany z Tesla, Inc.
- Używaj na własną odpowiedzialność
- Tesla Fleet API jest jedynym oficjalnie wspieranym sposobem komunikacji
- Stare Owner API (TeslaPy) jest przestarzałe

## 🙏 Podziękowania

- Tesla za udostępnienie Fleet API
- Społeczność Tesla Developer za wsparcie
- Autorzy bibliotek używanych w projekcie

---

**Uwaga:** Ten projekt używa wyłącznie Tesla Fleet API zgodnie z oficjalną dokumentacją Tesla. Nie używa przestarzałego Owner API. 