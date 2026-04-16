#!/bin/bash
# Market Oracle AI — Push to main if unpushed commits exist
# Triggers Railway (backend) + Vercel (frontend) auto-deploy pipelines

UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')

if [ "$UNPUSHED" -gt 0 ]; then
  echo "Auto-deploy: pushing $UNPUSHED commit(s) to origin/main..."
  git push origin main
  echo "Deploy triggered: Railway (backend) + Vercel (frontend) will build automatically."
else
  echo "Auto-deploy: nothing to push."
fi

exit 0
