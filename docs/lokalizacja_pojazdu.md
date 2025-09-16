# Pobieranie Lokalizacji Pojazdu z Tesla Fleet API

## 🎯 KLUCZOWE ODKRYCIE: Parametr `location_data`

### Problem
Tesla Fleet API **NIE zwraca danych lokalizacji** (`latitude`, `longitude`) w standardowym zapytaniu `vehicle_data`. Standardowe zapytanie zwraca tylko ograniczone dane w `drive_state`:

```json
// Standardowe zapytanie - BRAK lokalizacji
"drive_state": {
    "power": 0,
    "shift_state": null,
    "speed": null,
    "timestamp": 1733408444000
}
```

### ✅ Rozwiązanie: Parametr `location_data`

Aby otrzymać dane GPS, **musisz użyć parametru `location_data`** w zapytaniu do Tesla Fleet API:

```python
# ❌ ŹLE - brak danych lokalizacji
vehicle_data = self.fleet_api.get_vehicle_data(vehicle_id)

# ✅ DOBRZE - z danymi lokalizacji
location_data = self.fleet_api.get_vehicle_data(vehicle_id, "location_data")
```

### 📊 Porównanie Odpowiedzi API

#### Standardowe zapytanie (bez lokalizacji):
```json
"drive_state": {
    "power": 0,
    "shift_state": null,
    "speed": null,
    "timestamp": 1733408444000
}
```

#### Z parametrem `location_data` (z lokalizacją):
```json
"drive_state": {
    "gps_as_of": 1733408436,
    "heading": 91,
    "latitude": 52.334213,
    "longitude": 20.937511,
    "native_latitude": 52.334213,
    "native_location_supported": 1,
    "native_longitude": 20.937511,
    "native_type": 1,
    "power": 0,
    "shift_state": null,
    "speed": null,
    "timestamp": 1733408444000
}
```

## 🔧 Implementacja w Kodzie

### Pełna Implementacja:
```python
def get_vehicle_status(self) -> Dict[str, Any]:
    """Pobiera status pojazdu z danymi lokalizacji"""
    
    # 1. Pobierz standardowe dane pojazdu
    vehicle_data = self.fleet_api.get_vehicle_data(vehicle_id)
    
    # 2. Pobierz dane lokalizacji (specjalny parametr!)
    location_data = self.fleet_api.get_vehicle_data(vehicle_id, "location_data")
    
    # 3. Połącz dane jeśli lokalizacja dostępna
    if location_data.get('drive_state', {}).get('latitude') is not None:
        console.print("[green]✓ Otrzymano dane GPS z pojazdu[/green]")
        # Użyj drive_state z location_data dla GPS
        vehicle_data['drive_state'] = location_data.get('drive_state', {})
    else:
        console.print("[yellow]⚠️ Brak danych GPS z API[/yellow]")
    
    # 4. Wyciągnij współrzędne
    drive_state = vehicle_data.get('drive_state', {})
    latitude = drive_state.get('latitude')
    longitude = drive_state.get('longitude')
    
    return {
        'latitude': latitude,
        'longitude': longitude,
        'location_status': self._determine_location_status(drive_state),
        # ... inne dane
    }
```

### Określanie Lokalizacji HOME vs OUTSIDE:
```python
def _determine_location_status(self, drive_state: Dict[str, Any]) -> str:
    """Określa czy pojazd jest w domu czy na zewnątrz"""
    current_lat = drive_state.get('latitude')
    current_lon = drive_state.get('longitude')
    
    if not current_lat or not current_lon:
        # Brak danych GPS - zakładamy HOME gdy używamy .env
        return 'HOME'
    
    # Oblicz odległość od punktu HOME z .env
    home_lat = float(os.getenv('HOME_LATITUDE', '52.334215'))
    home_lon = float(os.getenv('HOME_LONGITUDE', '20.937516'))
    home_radius = float(os.getenv('HOME_RADIUS', '0.001'))  # ~100m
    
    # Proste obliczenie odległości
    lat_diff = abs(current_lat - home_lat)
    lon_diff = abs(current_lon - home_lon)
    distance = (lat_diff ** 2 + lon_diff ** 2) ** 0.5
    
    return 'HOME' if distance <= home_radius else 'OUTSIDE'
```

## 📋 Wymagana Konfiguracja

### Plik .env:
```bash
# Tesla Fleet API
TESLA_CLIENT_ID=twój_client_id
TESLA_CLIENT_SECRET=twój_client_secret
TESLA_DOMAIN=twoja_domena.com

# Lokalizacja domowa dla porównania
HOME_LATITUDE=52.334215
HOME_LONGITUDE=20.937516
HOME_RADIUS=0.001  # ~100 metrów w stopniach
```

## 🔍 Debugowanie i Testowanie

### Debug Różnych Endpointów:
```python
# Test różnych parametrów
def debug_location_endpoints(self, vehicle_id):
    """Testuje różne sposoby pobierania lokalizacji"""
    
    # Próba 1: Standardowe
    standard = self.fleet_api.get_vehicle_data(vehicle_id)
    print("Standardowe:", standard.get('drive_state', {}).keys())
    
    # Próba 2: location_data ✅
    location = self.fleet_api.get_vehicle_data(vehicle_id, "location_data")
    print("Location_data:", location.get('drive_state', {}).keys())
    
    # Próba 3: drive_state
    drive = self.fleet_api.get_vehicle_data(vehicle_id, "drive_state")
    print("Drive_state:", drive.get('drive_state', {}).keys())
```

### Rezultaty Debugowania:
```
Standardowe: ['power', 'shift_state', 'speed', 'timestamp']
Location_data: ['gps_as_of', 'heading', 'latitude', 'longitude', 'native_latitude', 'native_location_supported', 'native_longitude', 'native_type', 'power', 'shift_state', 'speed', 'timestamp']
Drive_state: ['power', 'shift_state', 'speed', 'timestamp']
```

## 🚨 Ważne Uwagi

### Prywatność i Bezpieczeństwo:
- **Tesla ogranicza dostęp do danych lokalizacji** ze względów bezpieczeństwa
- **Parametr `location_data` jest wymagany** - to celowe ograniczenie API
- **Nie wszystkie aplikacje** mogą mieć dostęp do lokalizacji

### Ograniczenia:
- **Dane GPS dostępne tylko gdy pojazd ONLINE**
- **Dokładność** zależy od GPS pojazdu
- **Opóźnienia** w aktualizacji lokalizacji (do kilku minut)

### Fallback Strategy:
```python
def get_vehicle_location_with_fallback(self):
    """Pobiera lokalizację z fallback do .env"""
    try:
        # Próba pobrania z API
        location_data = self.fleet_api.get_vehicle_data(vehicle_id, "location_data")
        drive_state = location_data.get('drive_state', {})
        
        lat = drive_state.get('latitude')
        lon = drive_state.get('longitude')
        
        if lat and lon and lat != 0.0 and lon != 0.0:
            return lat, lon, "GPS"
        else:
            # Fallback do .env
            return self.default_latitude, self.default_longitude, "ENV"
            
    except Exception as e:
        # Fallback do .env
        return self.default_latitude, self.default_longitude, "ENV"
```

## 📖 API Reference

### Tesla Fleet API - vehicle_data Endpoint

**URL:** `GET /api/1/vehicles/{vehicle_tag}/vehicle_data`

**Parametry:**
- `endpoints` (opcjonalny): Lista endpointów do pobrania
  - `"location_data"` - **WYMAGANE dla danych GPS**
  - `"charge_state"` - dane ładowania
  - `"drive_state"` - podstawowe dane jazdy (bez GPS!)
  - `"vehicle_state"` - stan pojazdu

**Przykłady:**
```bash
# Standardowe - bez lokalizacji
GET /api/1/vehicles/{vin}/vehicle_data

# Z lokalizacją - WYMAGANE
GET /api/1/vehicles/{vin}/vehicle_data?endpoints=location_data

# Kombinacja
GET /api/1/vehicles/{vin}/vehicle_data?endpoints=charge_state,location_data
```

## 🎯 Podsumowanie

### ✅ Co Działa:
1. **Parametr `location_data`** zwraca pełne dane GPS
2. **Kombinacja standardowych danych + location_data** zapewnia kompletne informacje
3. **Automatyczne określanie HOME vs OUTSIDE** na podstawie rzeczywistych współrzędnych
4. **Fallback do .env** gdy brak danych GPS

### ❌ Co Nie Działa:
1. **Standardowe zapytanie** - brak danych lokalizacji
2. **Parametr `drive_state`** - nie zawiera GPS
3. **Pojazd offline** - brak danych lokalizacji niezależnie od parametrów

### 🚀 Zalecenia:
1. **Zawsze używaj parametru `location_data`** dla GPS
2. **Implementuj fallback** do konfiguracji z .env
3. **Sprawdzaj czy pojazd jest online** przed pobieraniem lokalizacji
4. **Uwzględnij opóźnienia** w aktualizacji GPS

---

*Dokumentacja zaktualizowana: 2024-12-05*  
*Status: Rozwiązanie przetestowane i działające ✅* 