"""
export_for_dashboard.py

Utility script: copies pipeline outputs from data/processed/ and data/exports/
into dashboard/data/ so the web dashboard can load them directly.

Run after completing all pipeline steps:
  python src/export_for_dashboard.py
"""

import os
import shutil
import json

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORTS   = os.path.join(ROOT, "data", "exports")
DASH_DATA = os.path.join(ROOT, "dashboard", "data")
os.makedirs(DASH_DATA, exist_ok=True)

FILES_TO_COPY = [
    "landing_sites.geojson",
    "dsc_locations.geojson",
    "ice_candidates.geojson",
    "traverse_path.geojson",
    "traverse_waypoints.json",
    "ice_volume_report.json",
    "terrain_stats.json",
    "cpr_histogram.json",
]

print("Exporting pipeline outputs to dashboard/data/...")
for fname in FILES_TO_COPY:
    src = os.path.join(EXPORTS, fname)
    dst = os.path.join(DASH_DATA, fname)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        size = os.path.getsize(dst) / 1024
        print(f"  ✓ {fname}  ({size:.1f} KB)")
    else:
        print(f"  ✗ {fname}  [not found — run pipeline first]")

print("\nDone. Open dashboard/index.html in Chrome to view results.")
