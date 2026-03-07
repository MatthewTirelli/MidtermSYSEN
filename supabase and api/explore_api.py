#!/usr/bin/env python3
"""
Call the Bar Harbor Traffic Report API and print a short summary.
Run the API first (uvicorn api_main:app --reload), then in another terminal:
  cd "supabase and api" && python explore_api.py
Or point at a deployed API:
  python explore_api.py https://your-connect-url.com
"""

import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def main():
    print(f"Using API base: {BASE}\n")
    with httpx.Client(timeout=30.0) as client:
        # Segments
        try:
            r = client.get(f"{BASE.rstrip('/')}/segments")
            r.raise_for_status()
            segments = r.json()
            print(f"GET /segments  -> {len(segments)} segments")
            if segments:
                s = segments[0]
                print(f"  First: segment_id={s.get('segment_id')}, road_class={s.get('road_class')}, "
                      f"length_m={s.get('length_m')}, capacity_vph={s.get('capacity_vph')}")
        except Exception as e:
            print(f"GET /segments  -> ERROR: {e}")

        # Observations (with BPR speed/travel_time)
        try:
            r = client.get(f"{BASE.rstrip('/')}/observations")
            r.raise_for_status()
            obs = r.json()
            print(f"\nGET /observations -> {len(obs)} observations")
            if obs:
                o = obs[0]
                print(f"  First: segment_id={o.get('segment_id')}, timestamp={o.get('timestamp')}, "
                      f"flow_vph={o.get('flow_vph')}, speed_kmh={o.get('speed_kmh')}, "
                      f"travel_time_sec={o.get('travel_time_sec')}")
        except Exception as e:
            print(f"GET /observations -> ERROR: {e}")

    print("\nInteractive docs: open in browser -> " f"{BASE.rstrip('/')}/docs")


if __name__ == "__main__":
    main()
