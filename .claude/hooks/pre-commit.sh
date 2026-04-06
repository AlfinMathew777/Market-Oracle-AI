#!/bin/bash
# Market Oracle AI — Pre-commit hook
# Runs before every commit. Exit 2 = BLOCK. Exit 0 = allow.

set -e

echo "Running pre-commit checks..."

# 1. Python type/syntax check (backend)
STAGED_PY=$(git diff --cached --name-only | grep "\.py$" || true)
if [ -n "$STAGED_PY" ]; then
  echo "Checking Python files..."
  python3 -m py_compile $STAGED_PY || { echo "BLOCKED: Python syntax error"; exit 2; }
fi

# 2. Secret scan — block hardcoded keys
STAGED_ALL=$(git diff --cached --name-only || true)
if [ -n "$STAGED_ALL" ]; then
  if git diff --cached | grep -qE '(sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|password\s*=\s*["\x27][^"\x27]{6,})'; then
    echo "BLOCKED: Possible hardcoded secret detected in staged files"
    exit 2
  fi
fi

# 3. JS/TS lint (frontend staged files only)
STAGED_JS=$(git diff --cached --name-only | grep -E "\.(js|ts|jsx|tsx)$" || true)
if [ -n "$STAGED_JS" ] && command -v npx &>/dev/null; then
  cd frontend 2>/dev/null || true
  npx eslint $STAGED_JS --quiet 2>/dev/null || { echo "BLOCKED: ESLint errors"; exit 2; }
  cd .. 2>/dev/null || true
fi

echo "Pre-commit checks passed."
exit 0
