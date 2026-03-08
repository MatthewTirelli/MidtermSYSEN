# New API — code, docs, and run scripts

This folder holds a **copy** of the high-performance Traffic API (GET `/traffic/window`, cached segments, vectorized BPR) plus docs and scripts to run it.

## Contents

### API code (run from this folder)
- **api/** — FastAPI app: `main.py`, `bpr.py`, `schemas.py`, `routers/traffic.py`, `services/supabase_client.py`, `services/traffic_service.py`
- **requirements.txt** — Python dependencies for the API

### Docs
- **TEST_API_LOCALLY.md** — Step-by-step: install deps, set Supabase env, start API, test with curl and /docs
- **ARCHITECTURE_AND_MIGRATION.md** — Why the new API exists, design, migration plan, and app integration steps

### Scripts (run from repo root)
- **run_api_local.sh** — Start the API from this folder (`./NewAPI/run_api_local.sh`)
- **run_dashboard_local_api.sh** — Start the Shiny dashboard pointed at the local API (`./NewAPI/run_dashboard_local_api.sh`)

## Quick start

1. **Install API deps** (once):
   ```bash
   cd NewAPI
   pip install -r requirements.txt
   cd ..
   ```
2. **Set Supabase credentials** in `NewAPI/.env` or `supabase and api/.env`:
   ```
   SUPABASE_URL=https://YOUR_PROJECT.supabase.co
   SUPABASE_ANON_KEY=your_anon_key
   ```
3. **Start the API** (from repo root):
   ```bash
   ./NewAPI/run_api_local.sh
   ```
4. **Start the dashboard** (from repo root):
   ```bash
   ./NewAPI/run_dashboard_local_api.sh
   ```
5. Open **http://127.0.0.1:8766** for the Shiny app.
