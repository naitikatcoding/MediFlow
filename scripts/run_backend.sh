#!/usr/bin/env bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR/../Backend"

echo "Starting MediFlow FastAPI Backend Service (Port 8000)..."
if [ -f ".venv/bin/python" ]; then
    .venv/bin/python run.py
else
    python3 run.py
fi
