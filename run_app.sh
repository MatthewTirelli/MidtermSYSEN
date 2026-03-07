#!/usr/bin/env bash
# Create venv (if needed), install dependencies, and run the Bar Harbor Traffic Streamlit app.
# Run from project root: ./run_app.sh

set -e
cd "$(dirname "$0")"

VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Installing dependencies from requirements.txt..."
pip install -q -r requirements.txt

# Optional: install pydeck if not present (used by the map)
pip install -q pydeck 2>/dev/null || true

echo ""
echo "Starting Bar Harbor Traffic app..."
echo "Open the URL shown below in your browser (e.g. http://localhost:8501)"
echo ""
streamlit run app/streamlit_app.py "$@"
