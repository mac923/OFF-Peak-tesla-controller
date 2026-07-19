#!/bin/bash
# Smoke test po deployu architektury Scout & Worker.
# Użycie: ./smoke_test_deploy.sh [WORKER_URL]
# Bez argumentu odczytuje URL z gcloud.

set -u

REGION="europe-west1"
FAILED=0

WORKER_URL="${1:-}"
if [ -z "$WORKER_URL" ]; then
    WORKER_URL=$(gcloud run services describe tesla-worker --region=$REGION --format="value(status.url)" 2>/dev/null)
fi
if [ -z "$WORKER_URL" ]; then
    echo "❌ Nie można ustalić URL Worker Service (podaj jako argument)"
    exit 1
fi

echo "🔍 Smoke test Worker: $WORKER_URL"

# Worker wymaga autoryzacji OIDC (celowo: --no-allow-unauthenticated)
ID_TOKEN=$(gcloud auth print-identity-token 2>/dev/null)
if [ -z "$ID_TOKEN" ]; then
    echo "❌ Nie można wygenerować identity tokena (gcloud auth print-identity-token)"
    exit 1
fi

check() {
    local name="$1" url="$2" expected="$3"
    local code
    code=$(curl -s -o /tmp/smoke_body -w "%{http_code}" --max-time 30 \
        -H "Authorization: Bearer $ID_TOKEN" "$url")
    if [ "$code" = "$expected" ]; then
        echo "✅ $name (HTTP $code)"
    else
        echo "❌ $name: HTTP $code (oczekiwano $expected)"
        head -c 300 /tmp/smoke_body; echo
        FAILED=1
    fi
}

# 1. Health check
check "GET /health" "$WORKER_URL/health" "200"

# 2. Token dla Scout
check "GET /get-token" "$WORKER_URL/get-token" "200"
if grep -q '"access_token"' /tmp/smoke_body 2>/dev/null; then
    echo "✅ /get-token zwraca access_token"
else
    echo "❌ /get-token bez access_token w odpowiedzi"
    FAILED=1
fi

# 3. Scout Function — stan wdrożenia
SCOUT_STATE=$(gcloud functions describe tesla-scout --region=$REGION --format="value(state)" 2>/dev/null)
if [ "$SCOUT_STATE" = "ACTIVE" ]; then
    echo "✅ Scout Function: ACTIVE"
else
    echo "❌ Scout Function state: ${SCOUT_STATE:-brak}"
    FAILED=1
fi

# 4. Zdeprecjonowany duplikat joba special-charging nie powinien istnieć
if gcloud scheduler jobs describe tesla-special-charging-daily-check --location=$REGION >/dev/null 2>&1; then
    echo "⚠️ Job tesla-special-charging-daily-check nadal istnieje (duplikat midnight-wake) — usuń:"
    echo "   gcloud scheduler jobs delete tesla-special-charging-daily-check --location=$REGION"
    FAILED=1
else
    echo "✅ Brak zdeprecjonowanego joba tesla-special-charging-daily-check"
fi

echo
if [ "$FAILED" = "0" ]; then
    echo "🎉 SMOKE TEST PASSED"
else
    echo "🚨 SMOKE TEST FAILED"
fi
exit $FAILED
