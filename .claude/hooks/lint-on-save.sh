#!/bin/bash
# Market Oracle AI — Lint on save
# Auto-formats JS/TS files after Claude writes/edits them.
# Called by PostToolUse hook with file path on stdin (JSON).

FILE=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE" ]; then exit 0; fi

# Only format JS/TS/CSS files
if echo "$FILE" | grep -qE "\.(js|ts|jsx|tsx|css|scss)$"; then
  if command -v npx &>/dev/null && [ -f "frontend/package.json" ]; then
    npx prettier --write "$FILE" --log-level silent 2>/dev/null || true
  fi
fi

exit 0
