#!/usr/bin/env bash
# Run the Shiny dashboard (app/app.py) so it uses the LOCAL Bar Harbor Traffic API (http://localhost:8000).
# Works when run from repo root: ./NewAPI/run_dashboard_local_api.sh
# Start the local API first (e.g. ./NewAPI/run_api_local.sh).

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export TRAFFIC_API_BASE_URL="http://localhost:8000"

if [ -d "venv" ]; then
  source venv/bin/activate
fi

echo "Starting Shiny dashboard (app/app.py → local API at $TRAFFIC_API_BASE_URL)"
echo "Make sure the API is running: ./NewAPI/run_api_local.sh"
echo ""
shiny run app/app.py --port 8766 "$@"
