#!/usr/bin/env bash
set -e

# Change directory to project root
cd "$(dirname "$0")"

# Kill any existing server running on this port/app
pkill -f "uvicorn results_backend.app:app" 2>/dev/null || true

# Set environment variables for Single Operator Test mode
export FINS_OPERATOR_MODE=SINGLE
export FINS_MODE=TEST
export FINS_DB="$PWD/runtime/single_test.sqlite3"

# Verify virtual environment exists
if [ ! -f ".venv_mac/bin/python3" ]; then
    echo "Virtualenv .venv_mac/bin/python3 not found!"
    exit 1
fi

echo "=========================================================="
echo " Starting FINS 2026 Server (Single Operator / Test Mode)  "
echo " Database: $FINS_DB"
echo " Dashboard: http://127.0.0.1:8765"
echo " TV Graphics: http://127.0.0.1:8765/broadcast_tvg/?program=1"
echo "=========================================================="

exec .venv_mac/bin/python3 -m uvicorn results_backend.app:app --host 0.0.0.0 --port 8765
