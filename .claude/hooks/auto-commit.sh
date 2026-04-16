#!/bin/bash
# Market Oracle AI — Auto-commit after every Claude file change
# Called by PostToolUse hook after lint-on-save.sh

git add -A && git diff --cached --quiet || git commit -m "claude: auto-commit $(date +%H:%M:%S)" --no-verify
exit 0
