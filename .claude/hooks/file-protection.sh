#!/bin/bash
# Market Oracle AI — Block Claude from editing protected files
# Called by PreToolUse hook before Edit/Write/MultiEdit

FILE=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE" ]; then exit 0; fi

# Normalise Windows backslashes
FILE=$(echo "$FILE" | tr '\\' '/')

if echo "$FILE" | grep -qE '\.env$|backend/aussieintel\.db|railway\.toml|vercel\.json'; then
  echo "BLOCKED: $FILE is a protected file — edit manually if intended"
  exit 2
fi

exit 0
