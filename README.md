# OFF-Peak Tesla Controller

Zaawansowany system zarządzania ładowaniem pojazdu Tesla z integracją z OFF-Peak Charge API i Google Cloud Platform.

## 📋 Opis projektu

OFF-Peak Tesla Controller to kompleksowy system automatycznego zarządzania harmonogramami ładowania pojazdu Tesla, zoptymalizowany pod kątem kosztów energii i wykorzystania odnawialnych źródeł energii.

### 🏗️ Architektura

System wykorzystuje **Scout & Worker Architecture** na Google Cloud Platform:

- **Scout Function**: Lekka funkcja Cloud Function uruchamiana co 15 minut, monitorująca lokalizację pojazdu
- **Worker Service**: Główny serwis Cloud Run obsługujący zarządzanie harmonogramami i komunikację z Tesla API
- **Cloud Scheduler**: Harmonogramy uruchamiające system w określonych godzinach
- **Secret Manager**: Centralne zarządzanie tokenami Tesla API

### 🚀 Główne funkcjonalności

- ✅ **Automatyczne zarządzanie harmonogramami** ładowania Tesla
- ✅ **Integracja z OFF-Peak Charge API** dla optymalnych godzin ładowania
- ✅ **Wykrywanie lokalizacji pojazdu** (dom vs inne lokalizacje)
- ✅ **Special Charging** - jednorazowe sesje ładowania
- ✅ **Optymalizacja kosztów** - 96% redukcja kosztów Cloud (z 6zł na 20 groszy dziennie)
- ✅ **Automatyczne wybudzanie** uśpionych pojazdów
- ✅ **Fallback mechanizmy** zapewniające niezawodność
- ✅ **Kompleksowe logowanie** i monitoring

### 🔧 Technologie

- **Python 3.9+** - główny język programowania
- **Tesla Fleet API** - komunikacja z pojazdem Tesla
- **Google Cloud Platform** - infrastruktura chmurowa
- **Docker** - konteneryzacja aplikacji
- **OFF-Peak Charge API** - optymalizacja harmonogramów ładowania

## 📁 Struktura projektu

```
OFF-Peak-tesla-controller/
├── cloud_tesla_monitor.py      # Główna logika monitorowania
├── cloud_tesla_worker.py       # Worker Service na Cloud Run
├── tesla_controller.py         # Kontroler Tesla API
├── tesla_fleet_api_client.py   # Klient Tesla Fleet API
├── scout_function_deploy/      # Scout Function (Cloud Function)
├── documentation/              # Dokumentacja techniczna
├── deploy_*.sh                # Skrypty wdrożeniowe
├── test_*.py                  # Testy systemowe
└── requirements*.txt          # Zależności Python
```

## 🚀 Szybki start

### Wymagania wstępne

1. **Konto Tesla Developer** z dostępem do Fleet API
2. **Google Cloud Platform** z włączonymi usługami:
   - Cloud Run
   - Cloud Functions
   - Cloud Scheduler
   - Secret Manager
3. **OFF-Peak Charge API** - dostęp do API

### Instalacja

1. **Klonowanie repozytorium**:
```bash
git clone https://github.com/[username]/OFF-Peak-tesla-controller.git
cd OFF-Peak-tesla-controller
```

2. **Konfiguracja środowiska**:
```bash
cp env_example.txt .env
# Edytuj .env z własnymi danymi
```

3. **Instalacja zależności**:
```bash
pip install -r requirements.txt
```

4. **Wdrożenie na Google Cloud**:
```bash
./deploy_scout_worker.sh
```

## 📖 Dokumentacja

- [📋 Architektura Scout & Worker](README_SCOUT_WORKER_ARCHITECTURE.md)
- [⚙️ Automatyczne harmonogramy](README_AUTOMATYCZNE_HARMONOGRAMY.md)
- [🔧 Konfiguracja Fleet API](documentation/FLEET_API_SETUP.md)
- [☁️ Wdrożenie na Google Cloud](documentation/CLOUD_DEPLOYMENT.md)
- [🔐 Bezpieczeństwo](documentation/BEZPIECZENSTWO_RAPORT_FINAL.md)

## 🔄 Najważniejsze naprawki i ulepszenia

System przeszedł przez liczne iteracje i ulepszenia:

- **V3.0**: Eliminacja komend charge_start/charge_stop (43% mniej punktów awarii)
- **V2.0**: Uniwersalne wybudzenie pojazdów offline
- **Hybrid Token Architecture**: Automatyczne odświeżanie tokenów Tesla API
- **Special Charging**: System jednorazowych sesji ładowania
- **Smart Proxy Mode**: On-demand Tesla HTTP Proxy

## 🧪 Testy

System zawiera kompleksowe testy:

```bash
# Test połączenia z Tesla API
python test_scout_connection.py

# Test harmonogramów
python test_harmonogram_integration.py

# Test Special Charging
python test_special_charging.py
```

## 📊 Monitoring i logi

System zapewnia szczegółowe logowanie:
- Google Cloud Logging
- Strukturyzowane logi JSON
- Metryki wydajności
- Alerty błędów

## 🤝 Wkład w projekt

1. Fork repozytorium
2. Utwórz branch dla swojej funkcjonalności (`git checkout -b feature/nazwa-funkcjonalności`)
3. Commit zmian (`git commit -m 'Dodaj nową funkcjonalność'`)
4. Push do brancha (`git push origin feature/nazwa-funkcjonalności`)
5. Utwórz Pull Request

## 📄 Licencja

Ten projekt jest licencjonowany na licencji MIT - szczegóły w pliku [LICENSE](LICENSE).

## ⚠️ Disclaimer

Ten projekt jest nieoficjalnym narzędziem do zarządzania pojazdem Tesla. Użyj na własną odpowiedzialność. Autor nie ponosi odpowiedzialności za jakiekolwiek uszkodzenia lub problemy wynikające z użycia tego oprogramowania.

## 📞 Kontakt

W przypadku pytań lub problemów, utwórz Issue w tym repozytorium.

---

**Status projektu**: 🟢 Aktywnie rozwijany | **Wersja**: 3.2 | **Ostatnia aktualizacja**: Wrzesień 2025 