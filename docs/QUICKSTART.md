# 🚀 Szybki Start - Tesla Controller

Ten przewodnik pomoże Ci szybko uruchomić Tesla Controller i rozpocząć kontrolowanie swojego pojazdu.

## ⚡ Instalacja w 4 krokach

### 1. Pobierz i przygotuj projekt
```bash
# Sklonuj repozytorium
git clone <repository-url>
cd OFF-Peak-tesla-controller

# Sprawdź czy masz Python 3.8+
python3 --version
```

### 2. Utwórz środowisko wirtualne
```bash
# Utwórz środowisko wirtualne
python3 -m venv venv

# Aktywuj środowisko wirtualne
source venv/bin/activate  # Na macOS/Linux
# lub
venv\Scripts\activate     # Na Windows
```

### 3. Automatyczna instalacja
```bash
# Uruchom skrypt instalacyjny
python3 setup.py
```

Skrypt automatycznie:
- ✅ Zainstaluje wszystkie wymagane biblioteki
- ✅ Utworzy plik konfiguracyjny `.env`
- ✅ Przetestuje instalację

### 4. Pierwsze uruchomienie
```bash
# Uruchom główne menu
python3 run.py
```

## 🔐 Pierwsza autoryzacja

Przy pierwszym uruchomieniu:

1. **Program otworzy przeglądarkę** z stroną logowania Tesla
2. **Zaloguj się** swoimi danymi Tesla (email + hasło + 2FA)
3. **Po zalogowaniu** zostaniesz przekierowany na stronę błędu "Page not found" - to normalne!
4. **Skopiuj cały URL** z paska adresu (zaczyna się od `https://auth.tesla.com/void/callback`)
5. **Wklej URL w terminalu** i naciśnij Enter

✅ **Token zostanie zapisany** - nie będziesz musiał się logować ponownie!

## 🎯 Pierwsze kroki

### Sprawdź status pojazdu
```bash
python3 cli.py status
```

### Ustaw ładowanie nocne (taryfa G12)
```bash
# Limit ładowania na 90%
python3 cli.py set-limit 90

# Harmonogram nocny 23:00-07:00
python3 cli.py add-schedule --start-time 23:00 --end-time 07:00 --days All
```

### Tryb interaktywny (najłatwiejszy)
```bash
python3 cli.py interactive
```

## 📱 Najczęściej używane komendy

| Komenda | Opis |
|---------|------|
| `source venv/bin/activate` | Aktywuj środowisko wirtualne |
| `python3 run.py` | Główne menu programu |
| `python3 cli.py status` | Status pojazdu |
| `python3 cli.py start-charge` | Rozpocznij ładowanie |
| `python3 cli.py stop-charge` | Zatrzymaj ładowanie |
| `python3 cli.py set-limit 80` | Ustaw limit na 80% |
| `python3 cli.py interactive` | Tryb interaktywny |

## 🌙 Konfiguracja ładowania nocnego

### Dla taryfy G12 (23:00-07:00)
```bash
python3 cli.py add-schedule --start-time 23:00 --end-time 07:00 --days All
python3 cli.py set-limit 90
```

### Dla dni roboczych (23:00-06:00)
```bash
python3 cli.py add-schedule --start-time 23:00 --end-time 06:00 --days Weekdays
```

### Weekendowe ładowanie (10:00-14:00)
```bash
python3 cli.py add-schedule --start-time 10:00 --end-time 14:00 --days Saturday,Sunday
```

## 🛠️ Rozwiązywanie problemów

### ❌ "Błąd podczas łączenia z Tesla API"
```bash
# Usuń cache i spróbuj ponownie
rm tesla_cache.json
python3 cli.py status
```

### ❌ "Pojazd jest offline"
- To normalne - program automatycznie obudzi pojazd
- Może potrwać 1-2 minuty

### ❌ "ModuleNotFoundError: No module named 'click'"
```bash
# Aktywuj środowisko wirtualne i zainstaluj zależności
source venv/bin/activate
pip install -r requirements.txt
```

### ❌ "Nie znaleziono adresu email"
```bash
# Sprawdź plik .env
cat .env

# Lub ustaw email ręcznie
echo "TESLA_EMAIL=twoj_email@example.com" > .env
```

### ❌ "403 Tesla Vehicle Command Protocol required"

**To oznacza, że masz nowszy pojazd Tesla (2021+) wymagający Fleet API!**

## 🚗 Nowsze pojazdy Tesla - Tesla HTTP Proxy

Jeśli widzisz błąd `403 Tesla Vehicle Command Protocol required`, Twój pojazd wymaga **Fleet API z podpisanymi komendami**. Najłatwiejszym rozwiązaniem jest użycie **Tesla HTTP Proxy**.

### 🔧 Szybka konfiguracja proxy

#### 1. Sprawdź czy masz tesla-http-proxy
```bash
which tesla-http-proxy
```

#### 2. Sprawdź certyfikaty
```bash
# Upewnij się, że masz te pliki:
ls -la *.pem
# Powinny być: tls-key.pem, tls-cert.pem, private-key.pem
```

#### 3. Uruchom proxy (w osobnym terminalu)
```bash
tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose
```

#### 4. Skonfiguruj program do używania proxy
```bash
# Dodaj do pliku .env
echo "TESLA_HTTP_PROXY_HOST=localhost" >> .env
echo "TESLA_HTTP_PROXY_PORT=4443" >> .env
```

#### 5. Wygeneruj token Fleet API
```bash
python3 generate_token.py
```

Skrypt przeprowadzi Cię przez proces:
1. Otworzy URL w przeglądarce
2. Zaloguj się do Tesla
3. Skopiuj kod z URL po przekierowaniu
4. Wklej kod w terminalu

#### 6. Uruchom program z proxy
```bash
# Terminal 1: Proxy (zostaw uruchomiony)
tesla-http-proxy -tls-key tls-key.pem -cert tls-cert.pem -port 4443 -key-file private-key.pem -verbose

# Terminal 2: Program
source venv/bin/activate
python3 run.py
```

### ✅ Weryfikacja działania

Program powinien wyświetlić:
```
Używam Tesla HTTP Proxy: https://localhost:4443
✓ Fleet API klient zainicjalizowany
```

W logach proxy zobaczysz:
```
[info] Received POST request for /api/1/vehicles/VIN/command/...
[debug] Executing command on VIN
```

### 🔄 Workflow dla nowszych pojazdów

```bash
# 1. Uruchom proxy (zostaw w tle)
tesla-http-proxy -tls-key tls-key.pem -cert tls-cert.pem -port 4443 -key-file private-key.pem -verbose &

# 2. Ustaw zmienne proxy
export TESLA_HTTP_PROXY_HOST=localhost
export TESLA_HTTP_PROXY_PORT=4443

# 3. Uruchom program
source venv/bin/activate
python3 run.py
```

### 🆘 Problemy z proxy

**Proxy nie odpowiada:**
```bash
# Sprawdź czy działa
ps aux | grep tesla-http-proxy
curl -k https://localhost:4443/api/1/vehicles
```

**Token wygasł:**
```bash
# Wygeneruj nowy token
python3 generate_token.py
```

**Błąd VIN:**
- Program automatycznie używa VIN zamiast Fleet API ID
- Jeśli nadal błąd, sprawdź czy proxy jest uruchomiony

## 📊 Co możesz sprawdzić?

Program pokazuje:
- 🔋 **Poziom baterii** i zasięg
- ⚡ **Status ładowania** i prąd
- 🌡️ **Temperatury** wewnętrzną i zewnętrzną
- 🚗 **Przebieg** i status pojazdu
- ⏰ **Harmonogramy** ładowania
- 📍 **Lokalizację** pojazdu

## 🎮 Tryb interaktywny

Najłatwiejszy sposób korzystania:

```bash
python3 cli.py interactive
```

Menu pozwala na:
1. ✅ Sprawdzenie statusu
2. ⚡ Zarządzanie ładowaniem
3. ⏰ Tworzenie harmonogramów
4. 🔧 Ustawienia pojazdu

## 💡 Wskazówki

- **Zawsze aktywuj środowisko wirtualne** przed uruchomieniem
- **Używaj trybu interaktywnego** - jest najłatwiejszy
- **Ustaw harmonogram nocny** - zaoszczędzisz na prądzie
- **Nie budź pojazdu zbyt często** - oszczędzaj baterię 12V
- **Sprawdzaj status przed podróżą** - upewnij się o zasięgu

## 🆘 Potrzebujesz pomocy?

1. **Sprawdź pełną dokumentację**: `README.md`
2. **Zobacz przykłady**: `python3 examples.py`
3. **Pomoc CLI**: `python3 cli.py --help`
4. **Sprawdź logi** w terminalu

---

**Gotowe!** 🎉 Teraz możesz kontrolować swój pojazd Tesla z linii poleceń! 