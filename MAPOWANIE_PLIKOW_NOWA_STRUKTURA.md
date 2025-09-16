# 📋 Mapowanie Plików - Obecna → Nowa Struktura

**Data:** 2025-09-16  
**Cel:** Szczegółowe mapowanie wszystkich plików z obecnej struktury do proponowanej nowej struktury

---

## 🔄 **MAPOWANIE PLIKÓW PYTHON**

### **📁 src/core/ (Główne komponenty)**
```
tesla_controller.py                → src/core/tesla_controller.py
tesla_fleet_api_client.py         → src/core/tesla_fleet_api_client.py
```

### **📁 src/scout/ (Scout Function)**
```
tesla_scout_function.py           → src/scout/scout_function.py
scout_function_deploy/main.py     → src/scout/scout_main.py
scout_function_deploy/requirements.txt → src/scout/requirements.txt
```

### **📁 src/worker/ (Worker Service)**
```
cloud_tesla_worker.py             → src/worker/worker_service.py
cloud_tesla_monitor.py            → src/worker/monitor.py
requirements_cloud.txt            → src/worker/requirements.txt
```

### **📁 src/cli/ (Command Line Interface)**
```
cli.py                            → src/cli/cli.py
run.py                            → src/cli/run.py
```

### **📁 src/utils/ (Utilities)**
```
generate_token.py                 → src/utils/generate_token.py
```

### **📁 Pliki pozostające w root**
```
main.py                           → main.py (entry point)
setup.py                          → setup.py (setup script)
requirements.txt                  → requirements.txt (główne deps)
```

---

## 🧪 **MAPOWANIE TESTÓW**

### **📁 tests/integration/ (Testy integracyjne Scout & Worker)**
```
test_token_architecture.py       → tests/integration/test_token_architecture.py
test_token_refresh_fallback.py   → tests/integration/test_token_refresh_fallback.py
test_worker_startup_sequence.py  → tests/integration/test_worker_startup_sequence.py
test_worker_token_fix.py         → tests/integration/test_worker_token_fix.py
```

### **📁 tests/e2e/ (Testy end-to-end)**
```
test_special_charging.py         → tests/e2e/test_special_charging.py
```

---

## 🚀 **MAPOWANIE DEPLOYMENT**

### **📁 deployment/docker/**
```
Dockerfile.worker                 → deployment/docker/Dockerfile.worker
startup_worker.sh                 → deployment/docker/startup_worker.sh
```

### **📁 deployment/cloud/**
```
cloud-run-service-worker.yaml    → deployment/cloud/cloud-run-worker.yaml
cloud-scheduler-scout-worker.yaml → deployment/cloud/scheduler-scout-worker.yaml
cloud-scheduler-special-charging.yaml → deployment/cloud/scheduler-special.yaml
```

### **📁 deployment/scripts/**
```
deploy_scout_worker.sh            → deployment/scripts/deploy_scout_worker.sh
```

### **📁 deployment/templates/**
```
env_example.txt                   → deployment/templates/.env.template
```

---

## 📚 **MAPOWANIE DOKUMENTACJI**

### **📁 docs/architecture/**
```
documentation/SCOUT_WORKER_ARCHITECTURE.md → docs/architecture/scout-worker.md
documentation/OPTYMALIZACJA_KOSZTOW_CLOUD_RUN.md → docs/architecture/cost-optimization.md
```

### **📁 docs/deployment/**
```
documentation/DEPLOYMENT_GUIDE.md → docs/deployment/google-cloud.md
documentation/FLEET_API_SETUP.md  → docs/deployment/fleet-api-setup.md
```

### **📁 docs/api/**
```
documentation/API Tesla - documentation.md → docs/api/tesla-fleet-api.md
documentation/OFF_PEAK_CHARGE_API_DOCUMENTATION.md → docs/api/off-peak-api.md
documentation/OFF_PEAK_CHARGE_API_README.md → docs/api/off-peak-readme.md
```

### **📁 docs/changelog/**
```
documentation/FIXES_CHANGELOG.md  → docs/changelog/fixes-changelog.md
REFACTORING_SUMMARY_v1.md         → docs/changelog/refactoring-v1.md
```

### **📁 docs/ (główne)**
```
README.md                         → docs/README.md (overview dokumentacji)
documentation/README.md           → docs/project-overview.md
documentation/QUICKSTART.md       → docs/quickstart.md
```

### **📁 docs/archived/ (archiwalne)**
```
documentation/archived/           → docs/archived/ (całość)
```

### **📁 Dokumentacja specjalistyczna (do przeglądu)**
```
ARCHITECTURE_IMPROVEMENTS_v3_2.md → docs/architecture/improvements-v3-2.md
IMPLEMENTACJA_DYNAMICZNY_SCHEDULER.md → docs/features/dynamic-scheduler.md  
INSTRUKCJA_SPECIAL_CHARGING.md    → docs/features/special-charging.md
ONE_SHOT_CLEANUP_IMPLEMENTATION.md → docs/features/one-shot-cleanup.md
PODSUMOWANIE_SPECIAL_CHARGING.md  → docs/features/special-charging-summary.md
README_AUTOMATYCZNE_HARMONOGRAMY.md → docs/features/automatic-schedules.md
WDROZENIE_AUTO_CHARGE_START.md    → docs/features/auto-charge-start.md
```

---

## 🔐 **MAPOWANIE SEKRETÓW**

### **📁 secrets/ (Git ignore)**
```
.env                              → secrets/.env
private-key.pem                   → secrets/private-key.pem
fleet_tokens.json                 → secrets/fleet_tokens.json
tesla-sheets-key.json            → secrets/tesla-sheets-key.json
vehicle_command_private_key.pem   → secrets/vehicle_command_private_key.pem
vehicle_command_public_key.pem    → secrets/vehicle_command_public_key.pem
public_key.pem                    → secrets/public_key.pem
```

---

## 📁 **MAPOWANIE POZOSTAŁYCH KATALOGÓW**

### **📁 dokumentacja/ (stary katalog)**
```
dokumentacja/                     → USUNĄĆ (duplikat documentation/)
```

### **📁 scout_function_deploy/ (stary katalog)**
```
scout_function_deploy/            → USUNĄĆ (przeniesione do src/scout/)
```

---

## 🔧 **PLIKI KONFIGURACYJNE ROOT**

### **Pozostają w root:**
```
.gitignore                        → .gitignore (aktualizacja dla secrets/)
.gcloudignore                     → .gcloudignore  
.dockerignore                     → .dockerignore
requirements.txt                  → requirements.txt
setup.py                          → setup.py
main.py                           → main.py
README.md                         → README.md (główny)
```

---

## 📊 **STATYSTYKI MIGRACJI**

### **Pliki do przeniesienia:**
- **Python:** 15 plików → 5 katalogów w src/
- **Testy:** 5 plików → 2 katalogi w tests/  
- **Deployment:** 6 plików → 4 katalogi w deployment/
- **Dokumentacja:** ~30 plików → 5 katalogów w docs/
- **Sekrety:** 7 plików → 1 katalog secrets/

### **Katalogi do utworzenia:**
- `src/` + 5 podkatalogów
- `deployment/` + 4 podkatalogi  
- `tests/` + 3 podkatalogi
- `docs/` + 5 podkatalogów
- `secrets/`
- `examples/`
- `tools/`

### **Pliki wymagające aktualizacji import paths:**
```python
# Przykłady zmian import:
from tesla_controller import TeslaController
→ from src.core.tesla_controller import TeslaController

from tesla_fleet_api_client import TeslaFleetAPIClient  
→ from src.core.tesla_fleet_api_client import TeslaFleetAPIClient
```

### **Pliki wymagające aktualizacji ścieżek:**
- `Dockerfile.worker` - ścieżki do plików Python
- `deploy_scout_worker.sh` - ścieżki do konfiguracji
- `startup_worker.sh` - ścieżki do skryptów
- Wszystkie testy - import paths

---

## ⚙️ **SKRYPT MIGRACJI (Pseudokod)**

```bash
#!/bin/bash
# migrate_structure.sh

# 1. Utwórz nowe katalogi
mkdir -p src/{core,scout,worker,cli,utils}
mkdir -p deployment/{docker,cloud,scripts,templates}  
mkdir -p tests/{unit,integration,e2e}
mkdir -p docs/{architecture,deployment,api,changelog,archived}
mkdir -p secrets examples tools

# 2. Przenieś pliki Python
mv tesla_controller.py src/core/
mv tesla_fleet_api_client.py src/core/
mv tesla_scout_function.py src/scout/scout_function.py
# ... etc

# 3. Przenieś deployment files
mv Dockerfile.worker deployment/docker/
mv deploy_scout_worker.sh deployment/scripts/
# ... etc

# 4. Przenieś dokumentację
mv documentation/SCOUT_WORKER_ARCHITECTURE.md docs/architecture/scout-worker.md
# ... etc

# 5. Przenieś sekrety
mv .env secrets/ 2>/dev/null || true
mv *.pem secrets/ 2>/dev/null || true
# ... etc

# 6. Aktualizuj .gitignore
echo "secrets/*" >> .gitignore
echo "!secrets/.gitkeep" >> .gitignore

# 7. Utwórz .gitkeep files
touch secrets/.gitkeep examples/.gitkeep tools/.gitkeep
```

---

## ✅ **PLAN WALIDACJI**

### **1. Walidacja struktury:**
```bash
# Sprawdź czy wszystkie pliki zostały przeniesione
find . -name "*.py" -not -path "./venv/*" | wc -l  # Powinna być ta sama liczba
```

### **2. Walidacja importów:**
```bash
# Test importów w każdym module
python -c "from src.core.tesla_controller import TeslaController"
```

### **3. Walidacja deployment:**
```bash
# Test czy Dockerfile nadal działa
docker build -f deployment/docker/Dockerfile.worker .
```

### **4. Walidacja testów:**
```bash
# Uruchom wszystkie testy
python -m pytest tests/
```

---

**✅ To mapowanie zapewni systematyczną migrację wszystkich plików do nowej, lepiej zorganizowanej struktury projektu.** 