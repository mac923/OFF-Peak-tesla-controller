# 🚀 NOWA FUNKCJONALNOŚĆ: Automatyczne zarządzanie harmonogramami ładowania

## ✨ Co nowego?

Aplikacja Tesla Controller została rozszerzona o **automatyczne zarządzanie harmonogramami ładowania**! System teraz:

1. **🔍 Wykrywa** gdy pojazd jest gotowy do ładowania w domu
2. **📞 Wywołuje** API OFF PEAK CHARGE dla optymalnego harmonogramu
3. **🔄 Porównuje** nowy harmonogram z poprzednim
4. **🗑️ Usuwa** stare harmonogramy HOME z Tesla
5. **➕ Dodaje** nowe harmonogramy z API OFF PEAK CHARGE

## 🛠️ Szybkie uruchomienie

### 1. Zainstaluj Tesla HTTP Proxy
```bash
npm install -g tesla-http-proxy
```

### 2. Uruchom proxy
```bash
tesla-http-proxy \
  -tls-key tls-key.pem \
  -cert tls-cert.pem \
  -port 4443 \
  -key-file private-key.pem \
  -verbose
```

### 3. Zaktualizuj konfigurację
```bash
# Dodaj do pliku .env
echo "TESLA_HTTP_PROXY_HOST=localhost" >> .env
echo "TESLA_HTTP_PROXY_PORT=4443" >> .env
```

### 4. Uruchom aplikację
```bash
python3 cloud_tesla_monitor.py
```

## 🎯 Co zobaczysz w logach?

### Pierwszy harmonogram (nowy)
```
[14:30] ✅ VIN=ABC123, bateria=65%, ładowanie=gotowe, lokalizacja=HOME
[14:30] 🔄 Wywołuję OFF PEAK CHARGE API
[14:30] ✅ OFF PEAK CHARGE API - sukces
[14:30] 📋 Harmonogram dla ABC123: PIERWSZY (hash: 1a2b3c4d...)
[14:30] 🔧 Rozpoczęto zarządzanie harmonogramami Tesla
[14:30] ✅ Pomyślnie zaktualizowano harmonogramy Tesla
```

### Harmonogram bez zmian
```
[15:30] ✅ VIN=ABC123, bateria=70%, ładowanie=gotowe, lokalizacja=HOME
[15:30] 🔄 Wywołuję OFF PEAK CHARGE API
[15:30] ✅ OFF PEAK CHARGE API - sukces
[15:30] 📋 Harmonogram dla ABC123: IDENTYCZNY (hash: 1a2b3c4d...)
[15:30] 📋 Harmonogram IDENTYCZNY - nie wykonuję zmian w Tesla
```

### Harmonogram się zmienił
```
[16:30] ✅ VIN=ABC123, bateria=75%, ładowanie=gotowe, lokalizacja=HOME
[16:30] 🔄 Wywołuję OFF PEAK CHARGE API
[16:30] ✅ OFF PEAK CHARGE API - sukces
[16:30] 📋 Harmonogram dla ABC123: RÓŻNY (hash: 5e6f7g8h...)
[16:30] 🔧 Rozpoczęto zarządzanie harmonogramami Tesla
[16:30] 🗑️ Usunięto 2/2 harmonogramów HOME
[16:30] ✅ Dodano 3/3 harmonogramów do Tesla
[16:30] ✅ Pomyślnie zaktualizowano harmonogramy Tesla
```

## 🔧 Rozwiązywanie problemów

### ❌ "Nie można połączyć się z Tesla API"
```bash
# Sprawdź proxy
curl -k https://localhost:4443/api/1/vehicles

# Sprawdź czy proxy działa
ps aux | grep tesla-http-proxy
```

### ❌ "OFF PEAK CHARGE API failed"
```bash
# Sprawdź sekrety (dla Google Cloud)
gcloud secrets versions access latest --secret="OFF_PEAK_CHARGE_API_KEY"
```

### ❌ "Brak harmonogramów HOME"
```bash
# Zwiększ promień wyszukiwania
export HOME_RADIUS=0.2
```

## 🛡️ Bezpieczeństwo

✅ **Usuwa tylko harmonogramy HOME** - nie wpływa na harmonogramy w innych lokalizacjach  
✅ **Porównuje hash'e** - aktualizuje tylko gdy rzeczywiście się zmienił  
✅ **Szczegółowe logowanie** - pełna historia operacji  
✅ **Obsługa błędów** - bezpieczne rollback przy problemach  

## 📖 Pełna dokumentacja

Szczegółowa dokumentacja: [`documentation/AUTOMATYCZNE_ZARZADZANIE_HARMONOGRAMAMI.md`](documentation/AUTOMATYCZNE_ZARZADZANIE_HARMONOGRAMAMI.md)

## 🚀 Test funkcjonalności

1. **Ustaw pojazd w stanie gotowym do ładowania w domu**
2. **Uruchom monitor**: `python3 cloud_tesla_monitor.py`
3. **Obserwuj logi** - powinieneś zobaczyć automatyczne zarządzanie harmonogramami
4. **Sprawdź harmonogramy w aplikacji Tesla** - nowe harmonogramy powinny być widoczne

## 💡 Wskazówki

- **Pierwsza aktywacja**: System zawsze zaktualizuje harmonogramy przy pierwszym wykryciu
- **Identyczne harmonogramy**: System nie wykonuje zbędnych operacji
- **Różne harmonogramy**: System automatycznie zastąpi stare harmonogramy nowymi
- **Lokalizacja HOME**: Konfiguruj `HOME_LATITUDE`, `HOME_LONGITUDE`, `HOME_RADIUS` dokładnie

---

🎉 **Gratulacje!** Twoja Tesla będzie teraz automatycznie ładowana w najtańszych godzinach! 🔋⚡ 