# Optymalizacja kosztów Cloud Run - Tesla Monitor

## Przegląd

Ten dokument opisuje implementację optymalizacji kosztów dla aplikacji Tesla Monitor w Google Cloud Run, która pozwala na **redukcję kosztów o ponad 95%** w porównaniu z poprzednią implementacją.

## Problem z poprzednią implementacją

### Analiza kosztów (czerwiec 2024)
- **Cloud Run**: 247,62 zł
- **Secret Manager**: 7,00 zł
- **Inne usługi**: 0,00 zł
- **Łącznie**: 254,62 zł

### Źródło wysokich kosztów
Głównym problemem był model działania aplikacji jako **usługi działającej w trybie ciągłym (24/7)**:

1. **Nieskończona pętla**: Aplikacja zawierała `while self.is_running` loop, który utrzymywał kontener przy życiu
2. **Stałe koszty**: Cloud Run naliczał opłaty za każdą sekundę działania instancji
3. **Nieefektywne wykorzystanie**: Przez większość czasu aplikacja "spała" (`time.sleep(60)`), ale kontener pozostawał aktywny

## Nowa architektura (zoptymalizowana)

### Model "On-Demand"
Zmiana z "ciągle działającej usługi" na **"usługę uruchamianą na żądanie"**:

```
Stary model:     [====== APLIKACJA DZIAŁA CIĄGLE ======]
                 ↓ Stałe koszty 24/7

Nowy model:      [APP]---[SLEEP]---[APP]---[SLEEP]---[APP]
                 ↓ Koszty tylko podczas wykonania
```

### Komponenty architektury

#### 1. Cloud Scheduler
- **Harmonogram dzienny**: `0 7-22 * * *` (co godzinę, 07:00-22:00 Europe/Warsaw)
- **Harmonogram nocny**: `0 23,0-6 * * *` (co godzinę, 23:00-06:00 Europe/Warsaw)  
- **Nocne wybudzenie**: `0 0 * * *` (codziennie o 00:00 Europe/Warsaw)

#### 2. Cloud Run (scale-to-zero)
```yaml
annotations:
  autoscaling.knative.dev/minScale: "0"  # KLUCZOWE!
  autoscaling.knative.dev/maxScale: "1"
  run.googleapis.com/timeout: "300"
```

#### 3. Nowe endpointy HTTP
- `POST /run-cycle` - wykonanie cyklu monitorowania
- `POST /run-midnight-wake` - nocne wybudzenie pojazdu
- `GET /health` - sprawdzenie stanu
- `GET /reset` - reset stanu monitorowania

## Implementacja

### 1. Tryby działania aplikacji

#### Tryb Scheduler (domyślny - optymalizacja kosztów)
```python
# Zmienna środowiskowa
CONTINUOUS_MODE=false  # lub brak zmiennej

# Logika
def start_monitoring(self):
    continuous_mode = os.getenv('CONTINUOUS_MODE', 'false').lower() == 'true'
    if continuous_mode:
        self._start_continuous_monitoring()
    else:
        self._start_scheduler_monitoring()  # <- DOMYŚLNIE
```

#### Tryb Continuous (fallback)
```python
# Zmienna środowiskowa
CONTINUOUS_MODE=true

# Zachowuje poprzednią implementację dla kompatybilności
```

### 2. Obsługa wywołań Cloud Scheduler

```python
def _handle_run_cycle(self):
    """Obsługuje wywołanie cyklu monitorowania przez Cloud Scheduler"""
    logger.info("📅 Cloud Scheduler: Rozpoczęcie cyklu monitorowania")
    
    # Wykonaj cykl monitorowania
    self.monitor.run_monitoring_cycle()
    
    # Zwróć odpowiedź JSON
    response = {
        'status': 'cycle_completed',
        'timestamp': warsaw_time.isoformat(),
        'trigger': 'cloud_scheduler'
    }
```

### 3. Zachowanie pełnej funkcjonalności

**Smart Proxy Mode** - zachowany w pełni:
```python
# Tesla HTTP Proxy uruchamiany on-demand dla komend
if self.smart_proxy_mode and self.proxy_available:
    proxy_started = self._start_proxy_on_demand()
    # ... wykonaj komendy Tesla ...
    self._stop_proxy()
```

**Wszystkie funkcje** pozostają bez zmian:
- Automatyczne zarządzanie harmonogramami ładowania
- Integracja z OFF PEAK CHARGE API
- Wykrywanie zmian stanu pojazdu
- Logowanie do Cloud Storage/Firestore

## Wdrożenie

### 1. Automatyczne wdrożenie
```bash
chmod +x deploy_optimized.sh
./deploy_optimized.sh
```

### 2. Manualne kroki

#### Konfiguracja Cloud Run
```bash
# Wdrożenie z scale-to-zero
gcloud run services replace cloud-run-service-optimized.yaml --region=europe-west1
```

#### Utworzenie Cloud Scheduler jobs
```bash
# Harmonogram dzienny
gcloud scheduler jobs create http tesla-monitor-day-cycle \
    --location=europe-west1 \
    --schedule="*/15 7-22 * * *" \
    --uri="$SERVICE_URL/run-cycle" \
    --http-method=POST

# Harmonogram nocny  
gcloud scheduler jobs create http tesla-monitor-night-cycle \
    --location=europe-west1 \
    --schedule="0 23,0-6 * * *" \
    --uri="$SERVICE_URL/run-cycle" \
    --http-method=POST

# Nocne wybudzenie
gcloud scheduler jobs create http tesla-monitor-midnight-wake \
    --location=europe-west1 \
    --schedule="0 0 * * *" \
    --uri="$SERVICE_URL/run-midnight-wake" \
    --http-method=POST
```

## Spodziewane oszczędności

### Analiza kosztów

#### Stary model (continuous)
- **Czas działania**: 24h/dzień × 30 dni = 720 godzin/miesiąc
- **Koszt**: 247,62 zł/miesiąc
- **Koszt na godzinę**: ~0,34 zł/h

#### Nowy model (scheduler)
- **Wywołania dzienne**: 16h × 4 wywołania/h = 64 wywołania/dzień
- **Wywołania nocne**: 8h × 1 wywołanie/h = 8 wywołań/dzień  
- **Łącznie**: 72 wywołania/dzień × 30 dni = 2160 wywołań/miesiąc
- **Czas wykonania**: ~30 sekund/wywołanie = 2160 × 30s = 18 godzin/miesiąc
- **Spodziewany koszt**: 18h × 0,34 zł/h = **~6,12 zł/miesiąc**

### Redukcja kosztów
```
Poprzedni koszt:    247,62 zł/miesiąc
Nowy koszt:         ~6,12 zł/miesiąc
Oszczędności:       241,50 zł/miesiąc (97,5%)
```

## Monitoring i zarządzanie

### Sprawdzanie stanu
```bash
# Status aplikacji
curl https://your-service-url/health

# Logi Cloud Run
gcloud run services logs read tesla-monitor --region=europe-west1

# Logi Cloud Scheduler
gcloud scheduler jobs logs list tesla-monitor-day-cycle --location=europe-west1
```

### Zarządzanie harmonogramem
```bash
# Lista jobs
gcloud scheduler jobs list --location=europe-west1

# Wstrzymanie
gcloud scheduler jobs pause tesla-monitor-day-cycle --location=europe-west1

# Wznowienie
gcloud scheduler jobs resume tesla-monitor-day-cycle --location=europe-west1

# Manualne wywołanie
gcloud scheduler jobs run tesla-monitor-day-cycle --location=europe-west1
```

### Tryb awaryjny (continuous)
W przypadku problemów można szybko przełączyć na tryb continuous:

```bash
# Ustaw zmienną środowiskową
gcloud run services update tesla-monitor \
    --set-env-vars CONTINUOUS_MODE=true \
    --region=europe-west1

# Wyłącz Cloud Scheduler (opcjonalnie)
gcloud scheduler jobs pause tesla-monitor-day-cycle --location=europe-west1
gcloud scheduler jobs pause tesla-monitor-night-cycle --location=europe-west1
```

## Zalety nowej architektury

### 1. Optymalizacja kosztów
- **97,5% redukcja kosztów** Cloud Run
- Brak stałych kosztów między wywołaniami
- Precyzyjna kontrola nad harmonogramem

### 2. Zachowanie funkcjonalności
- **Pełna kompatybilność** z istniejącym kodem
- Smart Proxy Mode działa bez zmian
- Wszystkie funkcje Tesla pozostają aktywne

### 3. Lepsza skalowalność
- Automatyczne skalowanie do zera
- Szybkie cold start (generation 2)
- Elastyczne zarządzanie harmonogramem

### 4. Łatwiejsze zarządzanie
- Harmonogram zarządzany przez Cloud Scheduler
- Możliwość wstrzymania/wznowienia bez zmiany kodu
- Lepsze monitorowanie i debugowanie

## Potencjalne ograniczenia

### 1. Cold start delay
- **Wpływ**: Pierwsze wywołanie może trwać 5-10 sekund dłużej
- **Rozwiązanie**: Użycie generation 2 runtime (już skonfigurowane)

### 2. Utrata stanu między wywołaniami
- **Wpływ**: Brak - stan przechowywany w Cloud Storage/Firestore
- **Rozwiązanie**: Aplikacja już zaprojektowana jako stateless

### 3. Zależność od Cloud Scheduler
- **Wpływ**: Pojedynczy punkt awarii
- **Rozwiązanie**: Tryb continuous jako fallback

## Podsumowanie

Nowa architektura zapewnia:
- **Dramatyczną redukcję kosztów** (>95%)
- **Pełną funkcjonalność** bez regresji
- **Lepszą skalowalność** i zarządzanie
- **Tryb awaryjny** w przypadku problemów

Optymalizacja jest **gotowa do wdrożenia produkcyjnego** i zalecana dla wszystkich instalacji Tesla Monitor w Google Cloud. 