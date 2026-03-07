# Who Accesses the Public API (Supabase)?

## Summary

| Component | Accesses Supabase REST? | How |
|-----------|-------------------------|-----|
| **FastAPI** (`supabase_client.py`) | **Yes** | Reads `SUPABASE_URL` and `SUPABASE_ANON_KEY` from **environment** (`.env` when run locally). Calls `https://<SUPABASE_URL>/rest/v1/road_segments` and `.../traffic_observations` with `apikey` and `Authorization: Bearer <key>` headers. |
| **Streamlit app** | **No** | Only calls the **FastAPI** (GET /segments, GET /observations). It never talks to Supabase directly. |

So the only code that hits the “public” Supabase REST API is the **FastAPI**, and it does so using **server-side env vars**.

---

## Why the App Might Not Work When Using the “Published” API

1. **The app doesn’t call Supabase**  
   It only calls the FastAPI (e.g. `https://connect.systems-apps.com/.../` or `http://127.0.0.1:8000`). So the app only works if that FastAPI responds with data.

2. **The published FastAPI needs credentials**  
   When the FastAPI is deployed (e.g. Posit Connect), it must have **SUPABASE_URL** and **SUPABASE_ANON_KEY** set in **that deployment’s** environment. If they’re missing or wrong there, the FastAPI will return 503 or empty data, and the app will get nothing.

3. **Local vs deployed**  
   - **Local:** You have `.env` in `supabase and api/`, so the FastAPI can read Supabase and the app (pointed at localhost) works.  
   - **Deployed:** If the deployment doesn’t have those env vars set, the published API can’t read Supabase, so the app can’t get data when pointed at the published API.

---

## Fix: Let the App Pull from Supabase Directly

If you add a **“Load from Supabase”** (or similar) option in the Streamlit app so it calls Supabase REST itself (with URL + anon key from env or config), then:

- The app no longer depends on the **deployed** FastAPI having Supabase credentials.
- You only need the anon key available where the **app** runs (e.g. env var or Streamlit secrets). The anon key is intended for client/public use (with RLS and rate limits).

The app already has BPR logic; it would need to fetch `road_segments` and `traffic_observations` from Supabase (with a limit on observations), then apply BPR and use the result like it does for the FastAPI.
