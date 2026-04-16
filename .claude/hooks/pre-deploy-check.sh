#!/bin/bash
# Pre-deployment safety checks for Market Oracle AI
# Called by deploy-agent before any git push to staging/production
# Exits 2 to block the deploy if any check fails.

set -e

echo "=== Market Oracle AI Pre-Deploy Checks ==="

# 1. Uncommitted changes
echo -n "[ ] Checking for uncommitted changes... "
if [[ -n $(git status --porcelain) ]]; then
    echo "FAIL"
    echo "ERROR: Uncommitted changes detected. Commit or stash before deploying."
    git status --short
    exit 2
fi
echo "OK"

# 2. Run tests
echo -n "[ ] Running pytest... "
if ! cd backend && python -m pytest tests/ -q --tb=no 2>&1; then
    echo "FAIL"
    echo "ERROR: Tests failed. Fix before deploying."
    exit 2
fi
echo "OK"

# 3. Check we're on the right branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "[ ] Current branch: $CURRENT_BRANCH"

# 4. Check backend starts (syntax check only — fast)
echo -n "[ ] Syntax check backend... "
if ! cd backend && python3 -c "import server" 2>&1; then
    echo "FAIL"
    echo "ERROR: Backend has import errors. Fix before deploying."
    exit 2
fi
echo "OK"

echo ""
echo "=== All pre-deploy checks passed ==="
echo "Branch: $CURRENT_BRANCH"
echo "Ready to deploy."
exit 0
