#!/usr/bin/env bash
# Run the Streamlit dashboard so it pulls from the published Bar Harbor Traffic Report API.
# That API is deployed (e.g. Posit Connect) and reads from Supabase (nnbhantltvdwqphzyvev.supabase.co).
# No local API needed.

set -e
cd "$(dirname "$0")"

# Published FastAPI (uses https://nnbhantltvdwqphzyvev.supabase.co)
export TRAFFIC_API_BASE_URL="https://connect.systems-apps.com/content/4579a545-541d-412e-93d4-b35ef9cbca66"

# Activate venv if it exists
if [ -d "venv" ]; then
  source venv/bin/activate
fi

echo "Starting dashboard (API: published Bar Harbor Traffic Report → Supabase)"
streamlit run app/streamlit_app.py "$@"
