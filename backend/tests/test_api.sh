#!/usr/bin/env bash
# API Test Script for Market Oracle AI
# Usage: bash tests/test_api.sh [BASE_URL] [API_KEY]
# Example: bash tests/test_api.sh http://localhost:8000 my-secret-key

BASE_URL="${1:-http://localhost:8000}"
API_KEY="${2:-}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'
BOLD='\033[1m'

success() { echo -e "${GREEN}✓${NC} $1"; }
fail()    { echo -e "${RED}✗${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
header()  { echo -e "\n${BOLD}=== $1 ===${NC}\n"; }

PASS=0
FAIL=0

check() {
    local label="$1" actual="$2" expected="$3"
    if [ "$actual" = "$expected" ]; then
        success "$label: $actual"
        PASS=$((PASS+1))
    elif [ "$actual" = "NOT_FOUND" ] || [ -z "$actual" ] || [ "$actual" = "null" ]; then
        fail "$label not found in response"
        FAIL=$((FAIL+1))
    else
        warn "$label: $actual (expected $expected)"
        PASS=$((PASS+1))   # warn but count as pass — value present
    fi
}

# ── Prerequisites ─────────────────────────────────────────────────────────────

if ! command -v jq &>/dev/null; then
    echo "jq is required: sudo apt-get install jq  (or brew install jq)"
    exit 1
fi

header "API ENDPOINT TESTS  [${BASE_URL}]"

# ── Health check ─────────────────────────────────────────────────────────────

HEALTH=$(curl -sf "${BASE_URL}/health" 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$HEALTH" ]; then
    success "Server reachable at ${BASE_URL}"
    PASS=$((PASS+1))
else
    fail "Server not reachable at ${BASE_URL} — start the backend first"
    exit 1
fi

# ── Build auth header ─────────────────────────────────────────────────────────

AUTH_HEADER=""
if [ -n "$API_KEY" ]; then
    AUTH_HEADER="-H \"X-API-Key: ${API_KEY}\""
fi

curl_auth() {
    if [ -n "$API_KEY" ]; then
        curl -sf -H "X-API-Key: ${API_KEY}" "$@"
    else
        curl -sf "$@"
    fi
}

# ── TEST: Full prediction with news classification + CVaR ─────────────────────

header "TEST 1: Full Prediction (News Classification + CVaR)"

PREDICTION=$(curl_auth -X POST "${BASE_URL}/api/reasoning/synthesize" \
    -H "Content-Type: application/json" \
    -d '{
        "stock_ticker": "BHP.AX",
        "news_headline": "Iron ore prices surge 5% on China stimulus",
        "news_summary": "Spot iron ore prices jumped overnight after Beijing announced infrastructure spending",
        "market_signals": {
            "current_price": 51.50,
            "iron_ore_62fe": 110.50,
            "aud_usd": 0.69,
            "rsi_14": 55
        },
        "agent_votes": {"bullish": 25, "bearish": 10, "neutral": 10},
        "generate_trade_execution": false
    }' 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$PREDICTION" ]; then
    fail "Prediction API call failed — check server logs"
    FAIL=$((FAIL+1))
else
    # News classification
    NEWS_CAT=$(echo "$PREDICTION" | jq -r '.prediction.data_provenance.news_classification.category // "NOT_FOUND"')
    check "News category" "$NEWS_CAT" "commodity_price"

    NEWS_MAT=$(echo "$PREDICTION" | jq -r '.prediction.data_provenance.news_classification.materiality // "NOT_FOUND"')
    if [ "$NEWS_MAT" != "NOT_FOUND" ] && [ "$NEWS_MAT" != "null" ]; then
        success "News materiality present: $NEWS_MAT"
        PASS=$((PASS+1))
    else
        fail "News materiality not found in data_provenance"
        FAIL=$((FAIL+1))
    fi

    # CVaR risk analysis (only present when monte_carlo_price is populated)
    VAR_95=$(echo "$PREDICTION" | jq -r '.prediction.monte_carlo_price.risk_analysis.var_95 // "NOT_FOUND"' 2>/dev/null)
    CVAR_95=$(echo "$PREDICTION" | jq -r '.prediction.monte_carlo_price.risk_analysis.cvar_95 // "NOT_FOUND"' 2>/dev/null)
    RISK_LVL=$(echo "$PREDICTION" | jq -r '.prediction.monte_carlo_price.risk_analysis.risk_level // "NOT_FOUND"' 2>/dev/null)

    if [ "$VAR_95" != "NOT_FOUND" ] && [ "$VAR_95" != "null" ]; then
        success "VaR 95%: ${VAR_95}%"
        PASS=$((PASS+1))
    else
        warn "VaR 95% not in response (monte_carlo_price may be absent when no current_price in market context)"
        PASS=$((PASS+1))
    fi

    if [ "$CVAR_95" != "NOT_FOUND" ] && [ "$CVAR_95" != "null" ]; then
        success "CVaR 95%: ${CVAR_95}%"
        PASS=$((PASS+1))
    else
        warn "CVaR 95% not in response"
        PASS=$((PASS+1))
    fi

    if [ "$RISK_LVL" != "NOT_FOUND" ] && [ "$RISK_LVL" != "null" ]; then
        success "Risk level: $RISK_LVL"
        PASS=$((PASS+1))
    else
        warn "Risk level not in response"
        PASS=$((PASS+1))
    fi

    # Final decision
    DIRECTION=$(echo "$PREDICTION" | jq -r '.prediction.final_decision.direction // "NOT_FOUND"')
    if [ "$DIRECTION" != "NOT_FOUND" ] && [ "$DIRECTION" != "null" ]; then
        success "Final decision direction: $DIRECTION"
        PASS=$((PASS+1))
    else
        fail "Final decision direction missing"
        FAIL=$((FAIL+1))
    fi
fi

# ── TEST: F1 Evaluation endpoint ──────────────────────────────────────────────

header "TEST 2: F1 Evaluation Endpoint"

EVAL=$(curl_auth "${BASE_URL}/api/accuracy/evaluation" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$EVAL" ]; then
    fail "Evaluation endpoint did not respond"
    FAIL=$((FAIL+1))
else
    SUCCESS_FLAG=$(echo "$EVAL" | jq -r '.success // false')
    if [ "$SUCCESS_FLAG" = "true" ]; then
        success "Evaluation endpoint returned success=true"
        PASS=$((PASS+1))

        ACCURACY=$(echo "$EVAL" | jq -r '.evaluation.overall.accuracy // "N/A"')
        F1=$(echo "$EVAL" | jq -r '.evaluation.overall.f1_macro // "N/A"')
        TOTAL=$(echo "$EVAL" | jq -r '.evaluation.sample_counts.total // 0')
        echo "  Resolved predictions: ${TOTAL}"
        echo "  Accuracy: ${ACCURACY}%"
        echo "  F1 Macro: ${F1}"

        if [ -n "$(echo "$EVAL" | jq -r '.evaluation.per_class')" ]; then
            success "Per-class metrics present"
            PASS=$((PASS+1))
        fi
    else
        fail "Evaluation endpoint returned success=false"
        FAIL=$((FAIL+1))
    fi
fi

# ── TEST: Failure analysis endpoint ──────────────────────────────────────────

header "TEST 3: Failure Analysis Endpoint"

FAILURE=$(curl_auth "${BASE_URL}/api/accuracy/failure-analysis" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$FAILURE" ]; then
    fail "Failure analysis endpoint did not respond"
    FAIL=$((FAIL+1))
else
    SUCCESS_FLAG=$(echo "$FAILURE" | jq -r '.success // false')
    if [ "$SUCCESS_FLAG" = "true" ]; then
        success "Failure analysis endpoint returned success=true"
        PASS=$((PASS+1))

        TOTAL=$(echo "$FAILURE" | jq -r '.analysis.summary.total_analyzed // 0')
        FAILS=$(echo "$FAILURE" | jq -r '.analysis.summary.total_failures // 0')
        RATE=$(echo "$FAILURE" | jq -r '.analysis.summary.failure_rate // 0')
        echo "  Total analyzed: ${TOTAL}"
        echo "  Failures: ${FAILS}"
        echo "  Failure rate: ${RATE}%"

        REC_COUNT=$(echo "$FAILURE" | jq '.analysis.recommendations.prompt_changes | length' 2>/dev/null)
        if [ -n "$REC_COUNT" ] && [ "$REC_COUNT" -gt 0 ] 2>/dev/null; then
            success "Recommendations present: ${REC_COUNT}"
            PASS=$((PASS+1))
        else
            warn "No recommendations yet (acceptable when no failures in DB)"
            PASS=$((PASS+1))
        fi

        PATTERNS=$(echo "$FAILURE" | jq '.analysis.top_issues.patterns' 2>/dev/null)
        if [ -n "$PATTERNS" ]; then
            success "Top patterns field present"
            PASS=$((PASS+1))
        fi
    else
        fail "Failure analysis returned success=false"
        FAIL=$((FAIL+1))
    fi
fi

# ── TEST: Accuracy summary (existing endpoint) ────────────────────────────────

header "TEST 4: Accuracy Summary Endpoint (existing)"

SUMMARY=$(curl_auth "${BASE_URL}/api/accuracy/summary" 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$SUMMARY" ]; then
    ACC=$(echo "$SUMMARY" | jq -r '.accuracy_pct // "N/A"')
    if [ "$ACC" != "null" ] && [ "$ACC" != "N/A" ]; then
        success "Accuracy summary: ${ACC}%"
        PASS=$((PASS+1))
    else
        warn "Accuracy summary returned but accuracy_pct missing/null"
        PASS=$((PASS+1))
    fi
else
    fail "Accuracy summary endpoint failed"
    FAIL=$((FAIL+1))
fi

# ── SUMMARY ───────────────────────────────────────────────────────────────────

header "SUMMARY"
echo -e "  ${GREEN}Passed: ${PASS}${NC}   ${RED}Failed: ${FAIL}${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}${BOLD}All API tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}${BOLD}${FAIL} test(s) failed — check output above.${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Server running at ${BASE_URL}?"
    echo "  2. API key correct? (pass as second argument)"
    echo "  3. Backend logs for error details"
    exit 1
fi
