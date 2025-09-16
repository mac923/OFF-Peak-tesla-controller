# Problem z klasyfikacją lokalizacji pojazdu - ROZWIĄZANE

## Zidentyfikowany problem

**Błąd:** Nieprawidłowa wartość `HOME_RADIUS` w pliku `.env` powodowała błędną klasyfikację lokalizacji.

### Szczegóły problemu:

**Przed poprawką:**
```env
HOME_LATITUDE=52.334215  # Warszawa
HOME_LONGITUDE=20.937516 # Warszawa  
HOME_RADIUS=100.0        # ❌ BŁĄD: 100 stopni = ~11,000 km!
```

**Lokalizacja pojazdu:** `50.195550, 21.268254` (około 240 km od Warszawy)

**Dlaczego pokazywało "HOME":**
- Kod interpretuje `HOME_RADIUS` jako **stopnie geograficzne**, nie metry
- `HOME_RADIUS=100.0` oznaczało promień **100 stopni** = około **11,000 kilometrów**
- Praktycznie cała Europa mieściła się w tym promieniu

## Zastosowane rozwiązanie

**Po poprawce:**
```env
HOME_LATITUDE=52.334215  # Warszawa  
HOME_LONGITUDE=20.937516 # Warszawa
HOME_RADIUS=0.001        # ✅ POPRAWNE: ~100 metrów
```

### Wyjaśnienie jednostek:

- **1 stopień szerokości geograficznej** ≈ 111 km
- **0.001 stopnia** ≈ 111 metrów  
- **0.001 stopnia** to rozsądny promień dla określenia lokalizacji "HOME"

## Weryfikacja rozwiązania

**Obecne współrzędne pojazdu:** `50.195550, 21.268254`
**Współrzędne HOME:** `52.334215, 20.937516`

**Obliczenie odległości:**
```python
lat_diff = abs(50.195550 - 52.334215) = 2.138665
lon_diff = abs(21.268254 - 20.937516) = 0.330738
distance = √(2.138665² + 0.330738²) = 2.164 stopni ≈ 240 km
```

**Wynik:** `2.164 > 0.001` → **OUTSIDE** ✅ (prawidłowo)

## Test rezultatu

Po zmianie i ponownym uruchomieniu programu, lokalizacja powinna być poprawnie klasyfikowana jako:

**Oczekiwany wynik:**
```
╭─────────────────────────────── 🌍 Lokalizacja ───────────────────────────────╮
│                                                                               │
│ Lokalizacja: OUTSIDE                                                          │
│ Współrzędne: 50.195550, 21.268254                                            │
│                                                                               │
╰───────────────────────────────────────────────────────────────────────────────╯
```

## Konfiguracja promieniu dla różnych przypadków

**Zalecane wartości `HOME_RADIUS`:**

- **Garaż/dom:** `0.0001` (≈ 11 metrów)
- **Podwórko/posesja:** `0.0005` (≈ 55 metrów)  
- **Dzielnica:** `0.001` (≈ 111 metrów) - **domyślne**
- **Miasto:** `0.01` (≈ 1.1 km)

## Uwagi techniczne

1. **Kod używa prostego obliczenia odległości** - wystarczające dla małych odległości
2. **Dla większej precyzji** można by użyć wzoru haversine, ale nie jest to potrzebne
3. **Tesla Fleet API** może ograniczać dostęp do danych lokalizacji ze względów prywatności

---

**Status:** ✅ **ROZWIĄZANE**  
**Akcja:** Poprawiono `HOME_RADIUS` z `100.0` na `0.001`  
**Test:** Uruchom ponownie `python3 cli.py status` aby zweryfikować 