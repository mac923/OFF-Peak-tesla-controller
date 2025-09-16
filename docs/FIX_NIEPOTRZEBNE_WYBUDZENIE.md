# NAPRAWKA: Niepotrzebne wybudzenie pojazdu

## Problem

W logach aplikacji zauważono niepotrzebne wybudzenie pojazdu mimo że był już gotowy do ładowania:

1. **17:10:50** - Pojazd online, `charging_ready=False` → Uruchomiono przypadek B
2. **17:25:51** - Pojazd online, `charging_ready=True` → Warunek A spełniony ("Car ready for schedule")
3. **17:40:52** - Pojazd offline → System wybudził pojazd (błędnie!)

## Przyczyna

W funkcji `_handle_condition_a()` brakło logiki kończenia aktywnego przypadku B gdy pojazd stanie się gotowy do ładowania.

**Przed naprawką:**
```python
def _handle_condition_a(self, status):
    # ... logowanie ...
    # Nie kończymy monitorowania - pojazd może zmienić stan!  ← BŁĄD!
```

**Po naprawce:**
```python
def _handle_condition_a(self, status):
    # ... logowanie ...
    # NAPRAWKA: Zakończ aktywny przypadek B jeśli pojazd stał się gotowy
    if vehicle_vin in self.active_cases:
        # Usuń przypadek B - pojazd jest gotowy
        del self.active_cases[vehicle_vin]
```

## Rozwiązanie

Dodano logikę kończenia przypadku B w momencie gdy pojazd stanie się gotowy do ładowania (warunek A).

## Efekt

✅ **Przed:** Pojazd był budzony niepotrzebnie gdy przechodził w offline mimo gotowości  
✅ **Po:** Przypadek B jest kończony gdy pojazd stanie się gotowy → brak niepotrzebnego budzenia

## Nowe logi

Po naprawce w logach pojawi się:
```
Tesla Monitor: Monitoring case B terminated - car ready for charging
✅ Zakończono przypadek B - pojazd gotowy do ładowania
```

Data naprawy: 2025-01-17 