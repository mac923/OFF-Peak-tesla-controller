# 🔧 NAPRAWKA: Problem z end_enabled=False w harmonogramach ładowania

## 📋 **PROBLEM**

Worker Service wysyłał harmonogramy ładowania do Tesla z błędnym parametrem `end_enabled=False`, co powodowało:

### **Objawy:**
- **W logach:** Harmonogram 12:00-16:17 wysłany pomyślnie
- **W aplikacji Tesla:** 12:00 (active) - 16:15 (non-active)
- **Rzeczywisty efekt:** Ładowanie od 12:00 bez czasu zakończenia

### **Przyczyna:**
Worker Service w `cloud_tesla_worker.py` nie ustawiał `end_enabled=True` przy tworzeniu `ChargeSchedule`, używając domyślnej wartości `False` z definicji klasy.

## 🔧 **ROZWIĄZANIE**

### **Naprawione pliki:**
- `cloud_tesla_worker.py` - linie 1485 i 1442

### **Zmiany w kodzie:**

**1. Funkcja `_send_tesla_charging_schedule` (linia 1485):**
```python
# PRZED (BŁĘDNE):
charge_schedule = ChargeSchedule(
    enabled=True,
    start_time=start_minutes,
    end_time=end_minutes,
    start_enabled=True,
    # end_enabled=False (domyślna wartość) # ❌ BŁĄD
    lat=home_lat,
    lon=home_lon,
    days_of_week="All"
)

# PO NAPRAWCE (POPRAWNE):
charge_schedule = ChargeSchedule(
    enabled=True,
    start_time=start_minutes,
    end_time=end_minutes,
    start_enabled=True,
    end_enabled=True,  # ✅ NAPRAWKA: kończyć ładowanie o określonym czasie
    lat=home_lat,
    lon=home_lon,
    days_of_week="All"
)
```

**2. Funkcja `_convert_charging_plan_to_tesla_schedule` (linia 1442):**
```python
# Analogiczna naprawka w drugiej funkcji
charge_schedule = ChargeSchedule(
    enabled=True,
    start_time=start_minutes,
    end_time=end_minutes,
    start_enabled=True,
    end_enabled=True,  # ✅ NAPRAWKA: kończyć ładowanie o określonym czasie
    lat=home_lat,
    lon=home_lon,
    days_of_week=sched.get("days_of_week", "All")
)
```

## ✅ **WERYFIKACJA**

### **Test przed naprawką:**
- **Wysłane:** 12:00-16:17
- **Tesla App:** 12:00 (active) - 16:15 (non-active)
- **Efekt:** Ładowanie bez końca

### **Test po naprawce:**
- **Wysłane:** 15:51-19:51  
- **Tesla App:** 15:51 (active) - 19:51 (active) ✅
- **Efekt:** Ładowanie z prawidłowym czasem końca

## 🎯 **STATUS**

✅ **NAPRAWKA WDROŻONA** na produkcję (rewizja tesla-worker-00031-vm2)  
✅ **TESTY POTWIERDZONE** - harmonogramy wysyłane z `end_enabled=True`  
✅ **GŁÓWNA APLIKACJA** (`cloud_tesla_monitor.py`) już była prawidłowa  

## 📚 **NAUKA**

**Problem wynikał z różnicy między:**
- **CLI** (`cli.py`) - prawidłowo ustawia `end_enabled=True` gdy podany `end_time`
- **Główna aplikacja** (`cloud_tesla_monitor.py`) - prawidłowo ustawia `end_enabled=True` 
- **Worker Service** (`cloud_tesla_worker.py`) - zapomniał ustawić `end_enabled=True`

**Definicja klasy `ChargeSchedule`:**
```python
@dataclass
class ChargeSchedule:
    end_enabled: bool = False  # Domyślnie False!
```

**Lekcja:** Zawsze jawnie ustawiać `end_enabled=True` gdy harmonogram ma czas końca. 