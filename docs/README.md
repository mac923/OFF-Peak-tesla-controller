# 📚 Dokumentacja Tesla Monitor

**Witaj w dokumentacji projektu Tesla Monitor z architekturą Scout & Worker!**

## 🗂️ **Struktura Dokumentacji**

### **📁 architecture/** - Architektura systemu
- [`scout-worker.md`](architecture/scout-worker.md) - Kompletny przewodnik architektury Scout & Worker v3.1
- [`improvements-v3-2.md`](architecture/improvements-v3-2.md) - Ulepszenia architektury v3.2

### **📁 deployment/** - Wdrożenie i konfiguracja
- [`google-cloud.md`](deployment/google-cloud.md) - Przewodnik wdrożenia na Google Cloud
- [`fleet-api-setup.md`](deployment/fleet-api-setup.md) - Konfiguracja Tesla Fleet API

### **📁 api/** - Dokumentacja API
- [`tesla-fleet-api.md`](api/tesla-fleet-api.md) - Tesla Fleet API (oficjalna dokumentacja)
- [`off-peak-api.md`](api/off-peak-api.md) - OFF PEAK CHARGE API
- [`off-peak-readme.md`](api/off-peak-readme.md) - OFF PEAK API README

### **📁 features/** - Funkcjonalności systemu
- [`special-charging.md`](features/special-charging.md) - Special Charging - instrukcja
- [`special-charging-summary.md`](features/special-charging-summary.md) - Podsumowanie Special Charging
- [`dynamic-scheduler.md`](features/dynamic-scheduler.md) - Dynamiczny Cloud Scheduler
- [`one-shot-cleanup.md`](features/one-shot-cleanup.md) - One-shot cleanup implementation
- [`automatic-schedules.md`](features/automatic-schedules.md) - Automatyczne harmonogramy
- [`auto-charge-start.md`](features/auto-charge-start.md) - Wdrożenie auto charge start

### **📁 changelog/** - Historia zmian
- [`fixes-changelog.md`](changelog/fixes-changelog.md) - Historia naprawek i ulepszeń
- [`refactoring-v1.md`](changelog/refactoring-v1.md) - Refactoring v1 - konsolidacja dokumentacji

### **📁 archived/** - Archiwalna dokumentacja
- Stare pliki dokumentacyjne zachowane dla referencji

---

## 🚀 **Szybki Start**

### **Nowi użytkownicy:**
1. Przeczytaj [`README.md`](../README.md) w root projektu
2. Zapoznaj się z [architekturą Scout & Worker](architecture/scout-worker.md)
3. Skonfiguruj [Tesla Fleet API](deployment/fleet-api-setup.md)
4. Wdroż na [Google Cloud](deployment/google-cloud.md)

### **Developerzy:**
1. Sprawdź [strukturę projektu](../README.md#struktura-projektu)
2. Przeczytaj [przewodnik architektury](architecture/scout-worker.md)
3. Zobacz [historię naprawek](changelog/fixes-changelog.md)

### **Operatorzy:**
1. Zapoznaj się z [przewodnikiem wdrożenia](deployment/google-cloud.md)
2. Sprawdź [funkcjonalności systemu](features/)
3. Monitoruj system zgodnie z [architekturą](architecture/scout-worker.md)

---

## 📊 **Kluczowe Informacje**

### **Architektura:**
- **Scout Function**: Sprawdza lokalizację co 15 min (tania)
- **Worker Service**: Pełna logika on-demand (droga, rzadka)
- **Oszczędność kosztów**: 96% vs tradycyjne Cloud Run
- **Token management**: Centralne zarządzanie z fallback mechanism

### **Główne Komponenty:**
```
src/core/           # Tesla Controller + Fleet API Client
src/scout/          # Scout Function (lokalizacja pojazdu)  
src/worker/         # Worker Service (główna logika)
deployment/         # Wdrożenie (Docker, Cloud, Scripts)
tests/             # Testy (unit, integration, e2e)
```

### **Najważniejsze Naprawki:**
- **2025-09-11**: Uniwersalne wybudzenie pojazdu offline
- **2025-01-09**: Nowa sekwencja harmonogramów v3.0 (eliminacja charge commands)
- **2025-08-01**: Centralized token management + architektura Scout & Worker

---

## 🔗 **Przydatne Linki**

- **Główny README**: [`../README.md`](../README.md)
- **Architektura Scout & Worker**: [`architecture/scout-worker.md`](architecture/scout-worker.md)
- **Przewodnik wdrożenia**: [`deployment/google-cloud.md`](deployment/google-cloud.md)
- **Historia naprawek**: [`changelog/fixes-changelog.md`](changelog/fixes-changelog.md)
- **Tesla Fleet API**: [`api/tesla-fleet-api.md`](api/tesla-fleet-api.md)

---

**✅ Dokumentacja jest regularnie aktualizowana. W przypadku pytań sprawdź odpowiedni rozdział lub historię zmian.** 