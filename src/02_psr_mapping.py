"""
02_psr_mapping.py

Step 2: Permanently Shadowed Region (PSR) Mapping
  - Load real LOLA 5m DEM
  - Run horizon-based illumination model (100 solar positions)
  - Generate PSR mask (illumination fraction < 0.1%)
  - Detect Doubly Shadowed Craters (DSCs)
  - Export PSR mask, illumination fraction, and DSC GeoJSONs

Usage:
  python src/02_psr_mapping.py

Input:
  data/processed/lola_dem_5m.tif

Outputs:
  data/processed/psr_mask.tif
  data/processed/illumination_fraction.tif
  data/processed/dsc_mask.tif
  data/exports/dsc_locations.geojson
"""

import os
import sys
import json
import numpy as np
import rasterio
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape

sys.path.insert(0, os.path.dirname(__file__))
from utils.dem_utils import (compute_slope, compute_roughness,
                               compute_illumination_fraction, compute_psr_mask,
                               detect_doubly_shadowed_craters)
from utils.geo_utils import read_band, save_band

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS   = os.path.join(ROOT, "data", "exports")
os.makedirs(EXPORTS, exist_ok=True)


def run_psr_mapping(n_sun_positions: int = 100) -> dict:
    """
    Main PSR mapping function.

    Parameters
    ----------
    n_sun_positions : number of solar azimuth positions (100 = ~1h compute on 5m DEM)
                      Reduce to 20 for quick preview.

    Returns dict of output paths.
    """
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 2: PSR Mapping")
    print("=" * 60)

    lola_path = os.path.join(PROCESSED, "lola_dem_5m.tif")
    if not os.path.exists(lola_path):
        print(f"[ERROR] LOLA DEM not found at {lola_path}")
        print("  Run 01_data_ingestion.py first.")
        return {}

    # ── Load DEM ──────────────────────────────────────────────────────────────
    print("\n[1/4] Loading LOLA DEM...")
    dem, profile = read_band(lola_path, band=1)
    pixel_size_m = abs(profile["transform"].a)
    print(f"  Shape: {dem.shape}, Pixel size: {pixel_size_m:.1f} m")
    print(f"  Elevation range: {np.nanmin(dem):.0f} m to {np.nanmax(dem):.0f} m")

    # ── Illumination model ────────────────────────────────────────────────────
    print(f"\n[2/4] Computing illumination fraction ({n_sun_positions} solar positions)...")
    print("  (This may take several minutes for large DEMs at 5m resolution)")
    illum = compute_illumination_fraction(dem, pixel_size_m, n_sun_positions)

    illum_path = os.path.join(PROCESSED, "illumination_fraction.tif")
    save_band(illum, profile, illum_path)
    print(f"  Saved: {illum_path}")

    # ── PSR mask ──────────────────────────────────────────────────────────────
    print("\n[3/4] Generating PSR mask (threshold = 0.1% illumination)...")
    psr_mask = compute_psr_mask(illum, threshold=0.001)
    psr_frac = np.mean(psr_mask) * 100
    print(f"  PSR coverage: {psr_frac:.1f}% of scene")

    psr_path = os.path.join(PROCESSED, "psr_mask.tif")
    psr_profile = profile.copy()
    psr_profile.update({"dtype": "uint8", "count": 1,
                          "compress": "lzw", "nodata": 255})
    with rasterio.open(psr_path, "w", **psr_profile) as dst:
        dst.write(psr_mask, 1)
    print(f"  Saved: {psr_path}")

    # ── DSC Detection ─────────────────────────────────────────────────────────
    print("\n[4/4] Detecting Doubly Shadowed Craters (DSCs)...")
    dsc_mask, dsc_stats = detect_doubly_shadowed_craters(psr_mask, dem, min_area_px=50)
    print(f"  Found {len(dsc_stats)} DSC region(s)")

    dsc_path = os.path.join(PROCESSED, "dsc_mask.tif")
    with rasterio.open(dsc_path, "w", **psr_profile) as dst:
        dst.write(dsc_mask, 1)

    # Export DSC centroids as GeoJSON with lat/lon
    from utils.geo_utils import pixel_to_latlon
    
    # Filter DSCs: area >= 0.01 km² and depth >= 10m, top 10 by area
    filtered_dsc = [s for s in dsc_stats if 
        (s["area_px"] * (pixel_size_m ** 2) / 1e6 >= 0.01) and 
        (s["mean_elevation_m"] - s["min_elevation_m"] >= 10)]
    filtered_dsc = sorted(filtered_dsc, key=lambda x: x["area_px"], reverse=True)[:10]

    geojson_features = []
    for s in filtered_dsc:
        lat, lon = pixel_to_latlon(s["centroid_row"], s["centroid_col"], profile)
        geojson_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "region_id": s["region_id"],
                "area_px": s["area_px"],
                "area_km2": round(s["area_px"] * (pixel_size_m ** 2) / 1e6, 4),
                "mean_elevation_m": round(s["mean_elevation_m"], 1),
                "min_elevation_m": round(s["min_elevation_m"], 1),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
        })

    geojson_path = os.path.join(EXPORTS, "dsc_locations.geojson")
    with open(geojson_path, "w", encoding='utf-8') as f:
        json.dump({"type": "FeatureCollection", "features": geojson_features}, f, indent=2)
    print(f"  Saved DSC locations: {geojson_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" PSR Mapping complete.")
    print(f"  Total PSR area: {np.sum(psr_mask) * pixel_size_m**2 / 1e6:.2f} km²")
    print(f"  Total DSC area: {np.sum(dsc_mask) * pixel_size_m**2 / 1e6:.2f} km²")
    print(f"  DSC regions: {len(dsc_stats)}")
    if dsc_stats:
        best = min(dsc_stats, key=lambda x: x["mean_elevation_m"])
        print(f"  Deepest DSC centroid: row={best['centroid_row']}, col={best['centroid_col']}")
    print("=" * 60)
    print(" Next: run  python src/03_radar_ice_detection.py")

    return {
        "illumination_fraction": illum_path,
        "psr_mask": psr_path,
        "dsc_mask": dsc_path,
        "dsc_geojson": geojson_path,
        "dsc_stats": dsc_stats,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_positions", type=int, default=100,
                        help="Number of solar positions (default 100, use 20 for quick preview)")
    args = parser.parse_args()
    run_psr_mapping(n_sun_positions=args.n_positions)
