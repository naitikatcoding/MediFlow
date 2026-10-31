#!/usr/bin/env bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR/../Frontend"

echo "Starting MediFlow Next.js Frontend (Port 3000)..."
npm run dev
