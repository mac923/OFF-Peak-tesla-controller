# 🔧 NAPRAWKA: Problem HTTP 403 dla Special Charging Dynamic Jobs

## 🚨 **PROBLEM ZIDENTYFIKOWANY - 2025-01-09**

### **Objawy:**
```
INFO 2025-09-05T23:00:00.814678582Z special-charging-special_2_20250906_0700 scheduled at 23:00:00.807908Z
WARNING 2025-09-05T23:00:01.826428Z [httpRequest.status: 403] [httpRequest.latency: 0 ms] 
ERROR 2025-09-05T23:00:01.998830515Z "status":"PERMISSION_DENIED", "targetType":"HTTP", "url":"https://tesla-worker-74pl3bqokq-ew.a.run.app/send-special-schedule"
```

### **Przyczyna:**
Dynamiczne Cloud Scheduler jobs tworzone przez Worker Service **nie miały skonfigurowanej autoryzacji OIDC** do wywołania Cloud Run Worker Service endpoints:
- `/send-special-schedule` 
- `/cleanup-single-session`

### **Szczegóły problemu:**
1. **Daily check o 23:00** - pomyślnie utworzył dynamic job `special-charging-special_2_20250906_0700`
2. **Dynamic job o 01:00** - otrzymał HTTP 403 PERMISSION_DENIED przy próbie wywołania Worker Service
3. **Brak autoryzacji OIDC** - dynamic jobs nie miały `oidc_token` w konfiguracji `http_target`

---

## ✅ **ROZWIĄZANIE WDROŻONE**

### **1. Dodanie autoryzacji OIDC do dynamic send jobs**

**Plik:** `cloud_tesla_worker.py`
**Funkcja:** `_create_dynamic_scheduler_job()` (linia ~1157-1170)

```python
# PRZED naprawką:
"http_target": {
    "uri": f"{WORKER_SERVICE_URL}/send-special-schedule",
    "http_method": scheduler_v1.HttpMethod.POST,
    "headers": {"Content-Type": "application/json"},
    "body": json.dumps({...}).encode()
}

# PO naprawce:
"http_target": {
    "uri": f"{WORKER_SERVICE_URL}/send-special-schedule",
    "http_method": scheduler_v1.HttpMethod.POST,
    "headers": {"Content-Type": "application/json"},
    "body": json.dumps({...}).encode(),
    # ✅ NAPRAWKA: Dodanie autoryzacji OIDC
    "oidc_token": {
        "service_account_email": f"{PROJECT_ID}@appspot.gserviceaccount.com"
    }
}
```

### **2. Dodanie autoryzacji OIDC do cleanup jobs**

**Plik:** `cloud_tesla_worker.py`
**Funkcja:** `_create_cleanup_dynamic_scheduler_job()` (linia ~1230-1243)

```python
# PRZED naprawką:
"http_target": {
    "uri": f"{WORKER_SERVICE_URL}/cleanup-single-session",
    "http_method": scheduler_v1.HttpMethod.POST,
    "headers": {"Content-Type": "application/json"},
    "body": json.dumps({...}).encode()
}

# PO naprawce:
"http_target": {
    "uri": f"{WORKER_SERVICE_URL}/cleanup-single-session", 
    "http_method": scheduler_v1.HttpMethod.POST,
    "headers": {"Content-Type": "application/json"},
    "body": json.dumps({...}).encode(),
    # ✅ NAPRAWKA: Dodanie autoryzacji OIDC
    "oidc_token": {
        "service_account_email": f"{PROJECT_ID}@appspot.gserviceaccount.com"
    }
}
```

### **3. Service Account używany:**
```
{PROJECT_ID}@appspot.gserviceaccount.com
```
Czyli dla projektu `off-peak-tesla-controller`:
```
off-peak-tesla-controller@appspot.gserviceaccount.com
```

---

## 🎯 **REZULTAT**

### **Przed naprawką:**
- ❌ Dynamic jobs otrzymywały HTTP 403 PERMISSION_DENIED
- ❌ Special charging nie działało o wyznaczonych godzinach
- ❌ Jobs były tworzone ale nie mogły wywołać Worker Service

### **Po naprawce:**
- ✅ Dynamic jobs mają autoryzację OIDC z service account
- ✅ Special charging będzie działać o wyznaczonych godzinach
- ✅ Pełna kompatybilność z Cloud Run authentication

---

## 📅 **WDROŻENIE**

**Data:** 2025-01-09
**Metoda:** Deploy Worker Service z poprawionymi funkcjami autoryzacji
**Komenda:** `./deploy_scout_worker.sh`

**Test:** Następny special charging job powinien działać poprawnie bez błędów 403.

---

## 🔍 **WERYFIKACJA**

Sprawdź logi Cloud Scheduler dla następnego dynamic job:
```bash
# Sprawdź czy job wykonuje się bez błędu 403
gcloud logging read "resource.type=cloud_scheduler_job AND jsonPayload.jobName:special-charging" --limit=10
```

Oczekiwany rezultat: **HTTP 200** zamiast **HTTP 403**. 