#!/usr/bin/env bash
# Run the Traffic API from the NewAPI folder (copied API code). Run from repo root: ./NewAPI/run_api_local.sh
# Loads .env from NewAPI/, repo root, or supabase and api/ if present.

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEWAPI_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$NEWAPI_DIR"

if [ -f "$NEWAPI_DIR/.env" ]; then
  set -a
  source "$NEWAPI_DIR/.env"
  set +a
  echo "Loaded $NEWAPI_DIR/.env"
fi
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
  echo "Loaded $REPO_ROOT/.env"
fi
if [ -f "$REPO_ROOT/supabase and api/.env" ]; then
  set -a
  source "$REPO_ROOT/supabase and api/.env"
  set +a
  echo "Loaded supabase and api/.env"
fi

if [ -d "$REPO_ROOT/venv" ]; then
  source "$REPO_ROOT/venv/bin/activate"
elif [ -d "$NEWAPI_DIR/venv" ]; then
  source "$NEWAPI_DIR/venv/bin/activate"
fi

echo "Starting API from NewAPI at http://0.0.0.0:8000"
echo "Docs: http://127.0.0.1:8000/docs"
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
