# Bar Harbor Traffic Report API

FastAPI service that reads road segments and traffic observations from Supabase and applies the BPR formula to compute speed and travel time for observations.

## Endpoints

- **`GET /segments`** — Returns all rows from the Supabase `road_segments` table (passthrough).
- **`GET /observations`** — Returns traffic observations from Supabase with BPR-derived `speed_kmh` and `travel_time_sec` added.

## Environment

Set before running or deploying:

- `SUPABASE_URL` — e.g. `https://your-project.supabase.co`
- `SUPABASE_ANON_KEY` — your Supabase anon/public key

Copy `.env.example` to `.env` and fill in values (do not commit `.env`).

## Run locally

From this directory (`supabase and api/`):

```bash
pip install -r requirements.txt
uvicorn api_main:app --reload
```

API docs at http://localhost:8000/docs.

## Deploy to Posit Connect (flat)

From the project root:

```bash
rsconnect deploy fastapi -n <saved-server-name> --entrypoint api_main:app "supabase and api/"
```

Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the Connect dashboard or via `--environment` when deploying.
