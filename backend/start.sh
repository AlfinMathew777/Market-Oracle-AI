#!/bin/bash
cd "$(dirname "$0")"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8:replace
exec python -B -Xutf8 -m uvicorn server:app --host 0.0.0.0 --port 8001
