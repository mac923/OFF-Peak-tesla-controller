# NAPRAWKA: Warunek B Offline - Poprawki Scout Function

## Wykryte Problemy

### 🚨 **PROBLEM #1: KRYTYCZNY - Reset zmiennej trigger_worker**

**Lokalizacja:** 
- `scout_function_deploy/main.py` linia 1148
- `tesla_scout_function.py` linia 758

**Opis:**
Scout poprawnie wykrywał Warunek B offline i ustawiał `trigger_worker = True`, ale następnie zmienna była resetowana na `False` w sekcji inicjalizacji głównej logiki.

**Przed naprawką:**
```python
# Sekcja offline (1080-1088)
if was_at_home and not was_charging_ready and was_online and vehicle_state == 'offline':
    trigger_worker = True  # ← USTAWIONE
    reason = "Warunek B - pojazd OFFLINE, wybudzenie i sprawdzenie stanu"

# Główna logika (1147-1148) 
trigger_worker = False  # ← RESETOWANE!
reason = ""
```

**Po naprawce:**
```python
# NAPRAWKA: Nie resetuj trigger_worker jeśli został już ustawiony w sekcji offline
if 'trigger_worker' not in locals():
    trigger_worker = False
if 'reason' not in locals() or not reason:
    reason = ""
```

### 🚨 **PROBLEM #2: POWAŻNY - Brak zapisu stanu offline**

**Lokalizacja:**
- `scout_function_deploy/main.py` linie 1198-1200
- `tesla_scout_function.py` - brakowało całkowicie

**Opis:**
Stan offline nie był zapisywany do Firestore, co powodowało że:
- Firestore zawierało stale `online=True` dla pojazdu offline
- Przy następnym sprawdzeniu Scout ponownie wykrywał "przejście offline"
- Mogło prowadzić do wielokrotnego wywoływania Warunku B

**Przed naprawką:**
```python
if vehicle_state == 'online':  # ← TYLKO DLA ONLINE!
    save_current_state(db, vin, location_data, current_at_home)
# Brak obsługi offline
```

**Po naprawce:**
```python
if vehicle_state == 'online':
    save_current_state(db, vin, location_data, current_at_home)
    logger.info(f"💾 [SCOUT] Stan pojazdu zapisany po sprawdzeniu warunków A/B")
elif vehicle_state == 'offline' and last_state and last_state.get('online', False):
    # NAPRAWKA: Zapisz stan offline TYLKO gdy pojazd przechodzi z online na offline
    # Unikamy marnowania zasobów przy każdym sprawdzeniu offline co 15 min
    offline_state_data = {
        'vin': vin,
        'latitude': None,
        'longitude': None,
        'at_home': current_at_home,
        'last_check': location_data['timestamp'],
        'updated_at': firestore.SERVER_TIMESTAMP,
        'online': False,  # KLUCZOWE: Zapisz że pojazd jest offline
        'battery_level': 0,
        'charging_state': 'Unknown',
        'is_charging_ready': False,
        'vehicle_state': 'offline'
    }
    doc_ref = db.collection('tesla_scout_state').document(vin)
    doc_ref.set(offline_state_data)
```

## Wprowadzone Naprawki

### ✅ **NAPRAWKA #1: Warunki inicjalizacji zmiennych**
- Zmienne `trigger_worker` i `reason` nie są resetowane jeśli zostały już ustawione
- Dodano logowanie debug dla potwierdzenia zachowania wartości

### ✅ **NAPRAWKA #2: Inteligentny zapis stanu offline**
- Stan offline zapisywany TYLKO przy przejściu `online → offline`
- Unikanie marnowania zasobów przy każdym sprawdzeniu co 15 min
- Prawidłowe ustawienie `online=False` w Firestore

### ✅ **NAPRAWKA #3: Dodatkowe logowanie debug**
- Potwierdzenie ustawienia `trigger_worker=True` w sekcji offline
- Logowanie zachowania zmiennej po inicjalizacji
- Śledzenie zapisu stanu offline

## Oczekiwane Rezultaty

### 🎯 **Warunek B Offline będzie działał poprawnie:**
1. Scout wykryje przejście `online → offline` w trakcie Warunku B
2. Ustawi `trigger_worker = True` i `reason = "Warunek B - pojazd OFFLINE..."`
3. Zmienne **NIE BĘDĄ** resetowane w głównej logice
4. Worker Service zostanie wywołany z `/run-cycle`
5. Worker wybudzi pojazd i sprawdzi stan ładowania

### 🎯 **Prawidłowe zarządzanie stanem:**
1. Stan offline zostanie zapisany do Firestore przy przejściu
2. Kolejne sprawdzenia offline nie będą generować niepotrzebnych zapisów
3. Warunek A będzie poprawnie wykrywany po powrocie online

### 🎯 **Logi potwierdzające działanie:**
```
😴 [SCOUT] WARUNEK B OFFLINE - trigger_worker=True, reason='Warunek B - pojazd OFFLINE, wybudzenie i sprawdzenie stanu'
🔍 [DEBUG] Po inicjalizacji: trigger_worker zachowany jako True
📡 [SCOUT] Wywołuję Worker Service: Warunek B - pojazd OFFLINE, wybudzenie i sprawdzenie stanu
✅ [SCOUT] Worker Service wywołany pomyślnie
💾 [SCOUT] Stan offline zapisany po przejściu online→offline
```

## Pliki Zmodyfikowane

1. **scout_function_deploy/main.py**
   - Naprawka inicjalizacji zmiennych (linie 1147-1156)
   - Dodanie zapisu stanu offline (linie 1201-1220)
   - Dodatkowe logowanie debug

2. **tesla_scout_function.py**
   - Naprawka inicjalizacji zmiennych (linie 757-767)
   - Dodanie całej sekcji zapisu stanu (linie 817-844)
   - Dodatkowe logowanie debug

## Data Naprawy
2025-08-17

## Weryfikacja
Po wdrożeniu, Warunek B offline powinien poprawnie wywoływać Worker Service, co zostanie potwierdzone w logach obu serwisów. 