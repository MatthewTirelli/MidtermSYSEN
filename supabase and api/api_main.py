from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routers import traffic

# Load .env from this directory (supabase and api/) so SUPABASE_URL and SUPABASE_ANON_KEY are set
load_dotenv(Path(__file__).resolve().parent / ".env")


def create_app() -> FastAPI:
    """Application factory for the Bar Harbor Traffic Report API."""
    app = FastAPI(
        title="Bar Harbor Traffic Report",
        version="0.1.0",
        description="FastAPI service exposing road segments and traffic observations (with BPR-derived speed and travel time) from Supabase.",
    )
    app.include_router(traffic.router)
    return app


app = create_app()
