# 🔧 NAPRAWKA: Problem HTTP 403 w architekturze Scout & Worker

## 🚨 **PROBLEM ZIDENTYFIKOWANY - 2025-09-05**

### **Objawy:**
```
DEFAULT 2025-09-05T03:45:02.205344Z ⚠️ [SCOUT] Token in fleet-tokens expired or expiring in <5 min
DEFAULT 2025-09-05T03:45:02.248255Z 💡 [SCOUT] Próbuję odświeżyć tokeny przez Worker Service
WARNING 2025-09-05T03:45:02.857161Z [httpRequest.requestMethod: POST] [httpRequest.status: 403]
DEFAULT 2025-09-05T03:45:03.102544Z ❌ [SCOUT] Worker nie może odświeżyć tokenów: HTTP 403
```

### **Przyczyna:**
Scout Function nie wysyłał **Google Cloud Identity Token** w nagłówkach autoryzacji przy wywołaniach Worker Service.

---

## ✅ **ROZWIĄZANIE WDROŻONE**

### **1. Dodanie obsługi Google Cloud Identity Token w Scout Function**

**Plik:** `scout_function_deploy/main.py`

#### **A. Dodano importy:**
```python
# Google Cloud Identity Token dla autoryzacji Worker Service
from google.auth.transport.requests import Request
from google.oauth2 import id_token
```

#### **B. Nowa funkcja generowania tokenów:**
```python
def get_google_cloud_identity_token(target_audience: str) -> Optional[str]:
    """
    Generuje Google Cloud Identity Token dla autoryzacji wywołań do Cloud Run
    
    Args:
        target_audience: URL serwisu Cloud Run (np. Worker Service URL)
    
    Returns:
        Identity token jako string lub None w przypadku błędu
    """
    try:
        # Wygeneruj Identity Token dla docelowego serwisu
        auth_req = Request()
        token = id_token.fetch_id_token(auth_req, target_audience)
        
        logger.info(f"✅ [AUTH] Wygenerowano Identity Token dla: {target_audience}")
        return token
        
    except Exception as e:
        logger.error(f"❌ [AUTH] Błąd generowania Identity Token: {e}")
        return None
```

#### **C. Aktualizacja funkcji `trigger_worker_refresh_tokens()`:**
```python
# NAPRAWKA: Generuj Google Cloud Identity Token dla autoryzacji
identity_token = get_google_cloud_identity_token(worker_url)
if not identity_token:
    logger.error("❌ [SCOUT] Nie można wygenerować Identity Token dla Worker Service")
    return {"success": False, "message": "Identity token generation failed", "details": {}}

# Przygotuj nagłówki z autoryzacją
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {identity_token}"
}

# Wywołaj Worker z timeoutem i autoryzacją
response = requests.post(
    refresh_url,
    json=payload,
    timeout=45,
    headers=headers
)
```

#### **D. Aktualizacja funkcji `trigger_worker_service()`:**
```python
# Generuj Google Cloud Identity Token dla autoryzacji
identity_token = get_google_cloud_identity_token(worker_url)
if not identity_token:
    logger.error("❌ [SCOUT] Nie można wygenerować Identity Token dla Worker Service")
    return False

# Przygotuj nagłówki z autoryzacją
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {identity_token}"
}

response = requests.post(
    f"{worker_url.rstrip('/')}/run-cycle",
    json=payload,
    timeout=60,
    headers=headers
)
```

### **2. Aktualizacja wymagań Scout Function**

**Plik:** `scout_function_deploy/requirements.txt`
```
functions-framework==3.*
google-cloud-firestore==2.*
google-cloud-secret-manager==2.*
google-auth==2.*  # ← DODANO
requests==2.*
pytz==2023.*
```

### **3. Naprawka błędu w Worker Service**

**Problem:** Błędne wcięcie metody `__init__` w klasie `WorkerHealthCheckHandler` powodowało błąd 404 dla endpointu `/refresh-tokens`.

**Naprawka w:** `cloud_tesla_worker.py`
```python
class WorkerHealthCheckHandler(BaseHTTPRequestHandler):
    """
    Handler dla Worker Service - rozszerza funkcjonalność o obsługę wywołań od Scout
    """
    
    def __init__(self, monitor_instance, worker_instance, *args, **kwargs):  # ← POPRAWIONO WCIĘCIE
        self.monitor = monitor_instance
        self.worker = worker_instance
        super().__init__(*args, **kwargs)
```

---

## 🚀 **WDROŻENIE**

### **1. Scout Function:**
```bash
gcloud functions deploy tesla-scout \
    --gen2 \
    --runtime=python311 \
    --region=europe-west1 \
    --source=scout_function_deploy \
    --entry-point=tesla_scout_main \
    --trigger-http \
    --no-allow-unauthenticated \
    --memory=256MB \
    --timeout=60s \
    --max-instances=1 \
    --min-instances=0 \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=off-peak-tesla-controller,HOME_LATITUDE=52.334215,HOME_LONGITUDE=20.937516,HOME_RADIUS=0.03" \
    --service-account="off-peak-tesla-controller@appspot.gserviceaccount.com"
```

### **2. Worker Service:**
```bash
gcloud builds submit --config=cloudbuild-worker.yaml .
sed "s/YOUR_PROJECT_ID/off-peak-tesla-controller/g" cloud-run-service-worker.yaml > cloud-run-service-worker-filled.yaml
gcloud run services replace cloud-run-service-worker-filled.yaml --region=europe-west1
```

---

## ✅ **WERYFIKACJA NAPRAWKI**

### **Przed naprawką:**
```
WARNING 2025-09-05T07:01:13.557115Z The request was not authenticated.
❌ [SCOUT] Worker nie może odświeżyć tokenów: HTTP 403
```

### **Po naprawce:**
```
INFO 2025-09-05T07:10:34.486652Z POST /refresh-tokens - Odśwież tokeny Tesla
✅ [AUTH] Wygenerowano Identity Token dla: https://tesla-worker-1005200689027.europe-west1.run.app
✅ Scout Function działa poprawnie z autoryzacją
```

### **Test manualny:**
```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -H "Content-Type: application/json" \
     -d '{"test": "manual_after_fix"}' \
     https://tesla-scout-74pl3bqokq-ew.a.run.app/

# Rezultat: {"status":"success", ...}
```

---

## 🎯 **REZULTAT**

✅ **Problem HTTP 403 ROZWIĄZANY**  
✅ **Scout Function może odświeżać tokeny przez Worker Service**  
✅ **Autoryzacja Google Cloud Identity Token działa poprawnie**  
✅ **Architektura Scout & Worker w pełni operacyjna**  
✅ **Mechanizm fallback tokenów przywrócony**  

### **Korzyści:**
- **Bezpieczeństwo:** Zachowane wymaganie autoryzacji Worker Service
- **Zgodność:** Implementacja zgodna z Google Cloud best practices
- **Niezawodność:** Automatyczne odświeżanie tokenów działa 24/7
- **Koszt:** Zachowana optymalizacja kosztów Scout & Worker

**Data wdrożenia:** 2025-09-05  
**Status:** ✅ NAPRAWIONE I PRZETESTOWANE 