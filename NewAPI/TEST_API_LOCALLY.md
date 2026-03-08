# Test the Traffic API locally

## 1. Install dependencies

From the repo root (or from `supabase and api`):

```bash
cd "supabase and api"
pip install -r requirements.txt
```

(Or use a venv: `python3 -m venv venv` then `source venv/bin/activate` before `pip install`.)

## 2. Set Supabase credentials

Create a file `.env` in the repo root **or** in `supabase and api/` with:

```
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
```

Or export in the shell:

```bash
export SUPABASE_URL="https://YOUR_PROJECT.supabase.co"
export SUPABASE_ANON_KEY="your_anon_key"
```

## 3. Start the API

From the repo root (using the script in this folder):

```bash
./NewAPI/run_api_local.sh
```

Or from the `supabase and api` folder:

```bash
cd "supabase and api"
./run_api_local.sh
# Or manually (after loading .env if you use one):
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

You should see something like: `Uvicorn running on http://0.0.0.0:8000`.

## 4. Test the endpoints

**Health check:**

```bash
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok"}`

**Segments (cached at startup):**

```bash
curl http://127.0.0.1:8000/segments
```

Expected: JSON array of road segments (or `[]` if Supabase isn't configured).

**Traffic window (main new endpoint):**

```bash
curl "http://127.0.0.1:8000/traffic/window?date=2025-03-04&start_hour=18&end_hour=19"
```

Expected: JSON array of objects with `segment_id`, `mean_flow_vph`, `mean_speed_kmh`, `mean_travel_time_sec`, `vc_ratio`.

## 5. Optional: interactive docs

Open in a browser:

- **Swagger UI:** http://127.0.0.1:8000/docs  
- **ReDoc:** http://127.0.0.1:8000/redoc  

Use "Try it out" on `GET /traffic/window` and set `date`, `start_hour`, `end_hour`.

## Troubleshooting

- **503 on /segments or /traffic/window:** Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` and restart the API.
- **Empty `[]` from /traffic/window:** That date/hour may have no data in Supabase; try another date or hour (e.g. `date=2025-03-03&start_hour=0&end_hour=1`).
- **Port 8000 in use:** Run on another port, e.g. `uvicorn api.main:app --host 0.0.0.0 --port 8001`, and use `http://127.0.0.1:8001` in the steps above.
