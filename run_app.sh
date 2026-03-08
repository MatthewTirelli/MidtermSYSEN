#!/usr/bin/env bash
# Run the Bar Harbor Congestion Intelligence Dashboard (Shiny for Python).
# Must be run from the project root: ./run_app.sh

set -e
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# Check we're in the right place
if [ ! -f "app/app.py" ]; then
  echo "Error: app/app.py not found. Run this script from the project root (MidtermSYSEN/)."
  echo "  cd /path/to/MidtermSYSEN"
  echo "  ./run_app.sh"
  exit 1
fi

# Use venv if it exists
if [ -d "venv" ]; then
  source venv/bin/activate
  echo "Using virtual environment: $REPO_ROOT/venv"
else
  echo "Note: No 'venv' found. Using system Python."
  echo "  First time? Create one and install deps:"
  echo "    python3 -m venv venv"
  echo "    source venv/bin/activate"
  echo "    pip install -r requirements.txt"
  echo ""
fi

# Optional: load .env from project root so OLLAMA_API_KEY etc. are set
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
  echo "Loaded .env"
fi

echo "Starting Bar Harbor Congestion Intelligence Dashboard..."
echo "  → http://127.0.0.1:8767"
echo "  (Stop with Ctrl+C)"
echo ""
exec shiny run app/app.py --port 8767 "$@"
