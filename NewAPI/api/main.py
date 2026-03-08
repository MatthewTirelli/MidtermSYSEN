"""
Bar Harbor Traffic Report API. High-performance: window filtering, cached segments, vectorized BPR.
Run from NewAPI/: uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from pathlib import Path
from dotenv import load_dotenv
# Load .env from NewAPI/ or from repo root / supabase and api
_newapi = Path(__file__).resolve().parent.parent
load_dotenv(_newapi / ".env")
load_dotenv(_newapi.parent / ".env")
load_dotenv(_newapi.parent / "supabase and api" / ".env")

from contextlib import asynccontextmanager

from fastapi import FastAPI

from routers import traffic


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm in-memory road_segments cache at startup for fast /segments and BPR lookups."""
    from services.supabase_client import warm_segment_cache
    warm_segment_cache()
    yield


app = FastAPI(
    title="Bar Harbor Traffic Report API",
    description="Traffic metrics per segment for a time window; segments from Supabase.",
    lifespan=lifespan,
)

app.include_router(traffic.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
