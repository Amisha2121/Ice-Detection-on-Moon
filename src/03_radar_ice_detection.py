"""
03_radar_ice_detection.py

Step 3: Radar-based Subsurface Ice Detection
  - Load real DFSAR Stokes bands (from processed/dfsar_stokes.tif)
  - Apply Lee speckle filter
  - Compute CPR, DOP
  - Run m-chi decomposition
  - Apply ice thresholds: CPR > 1 AND DOP < 0.13 AND inside PSR
  - Generate ice probability map
  - Export ice candidate GeoJSON for dashboard

Usage:
  python src/03_radar_ice_detection.py

Inputs:
  data/processed/dfsar_stokes.tif   (4-band: S1, S2, S3, S0)
  data/processed/psr_mask.tif

Outputs:
  data/processed/cpr_map.tif
  data/processed/dop_map.tif
  data/processed/mchi_rgb.tif
  data/processed/ice_probability.tif
  data/exports/ice_candidates.geojson
"""

import os
import sys
import json
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

sys.path.insert(0, os.path.dirname(__file__))
from utils.radar_utils import (lee_filter, compute_cpr, compute_dop,
                                 mchi_decomposition, compute_ice_probability)
from utils.geo_utils import read_band, save_band, pixel_to_latlon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS   = os.path.join(ROOT, "data", "exports")
os.makedirs(EXPORTS, exist_ok=True)


def load_stokes_bands(dfsar_path: str) -> dict:
    """
    Load 4 Stokes bands from DFSAR SRI GeoTIFF.
    Band order: B1=S1, B2=S2, B3=S3, B4=S0 (total power)
    """
    with rasterio.open(dfsar_path) as src:
        profile = src.profile.copy()
        bands = src.read([1, 2, 3, 4]).astype(np.float32)

    S1, S2, S3, S0 = bands[0], bands[1], bands[2], bands[3]

    # Do NOT set nodata to NaN here because scipy.ndimage.uniform_filter 
    # uses a running sum that propagates NaNs across the entire image!
    # We will mask out the zero/nodata values after filtering.

    print(f"  Loaded DFSAR: shape={S0.shape}, "
          f"S0 range=[{np.nanmin(S0):.3e}, {np.nanmax(S0):.3e}]")
    return {"S0": S0, "S1": S1, "S2": S2, "S3": S3, "profile": profile}


def run_ice_detection() -> dict:
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 3: Radar Ice Detection")
    print("=" * 60)

    dfsar_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
    psr_path   = os.path.join(PROCESSED, "psr_mask.tif")

    if not os.path.exists(dfsar_path):
        print(f"[ERROR] DFSAR not found: {dfsar_path}")
        print("  Run 01_data_ingestion.py first.")
        return {}

    if not os.path.exists(psr_path):
        print(f"[WARNING] PSR mask not found: {psr_path}")
        print("  Run 02_psr_mapping.py first. Proceeding without PSR constraint.")
        psr_mask = None
    else:
        psr_mask, _ = read_band(psr_path)
        psr_mask = psr_mask.astype(np.uint8)
        # After loading Stokes we need stokes shape — load shape early for check
        with rasterio.open(dfsar_path) as _src:
            _stokes_shape = (_src.height, _src.width)
        if psr_mask.shape != _stokes_shape:
            print(f"  [WARNING] PSR mask shape {psr_mask.shape} != DFSAR shape {_stokes_shape}")
            print("  Reprojecting PSR mask to match DFSAR grid...")
            import rasterio.warp as _warp
            from rasterio.enums import Resampling as _RS
            with rasterio.open(psr_path) as _psrc, rasterio.open(dfsar_path) as _dsrc:
                _psr_reproj = np.zeros(_stokes_shape, dtype=np.uint8)
                _warp.reproject(
                    source=_psrc.read(1).astype(np.uint8),
                    destination=_psr_reproj,
                    src_transform=_psrc.transform,
                    src_crs=_psrc.crs,
                    dst_transform=_dsrc.transform,
                    dst_crs=_dsrc.crs,
                    resampling=_RS.nearest
                )
            psr_mask = _psr_reproj
            print(f"  PSR mask reprojected to {psr_mask.shape}")

    # ── Load Stokes ───────────────────────────────────────────────────────────
    print("\n[1/5] Loading Stokes bands from DFSAR...")
    stokes = load_stokes_bands(dfsar_path)
    S0, S1, S2, S3 = stokes["S0"], stokes["S1"], stokes["S2"], stokes["S3"]
    profile = stokes["profile"]

    # Check if DFSAR stokes bands are empty/all NaNs (no overlap situation)
    valid_count = np.sum(np.isfinite(S0) & (S0 > 0))
    if valid_count == 0:
        print("\n  [WARNING] DFSAR Stokes bands contain no valid overlapping pixels in the target DEM tile.")
        print("  Proceeding with empty radar data as per constraints (no synthesized data).")

    # ── Lee Speckle Filter ────────────────────────────────────────────────────
    print("\n[2/5] Applying Lee speckle filter (5×5 window)...")
    S0_f = lee_filter(S0, window=5)
    S1_f = lee_filter(S1, window=5)
    S2_f = lee_filter(S2, window=5)
    S3_f = lee_filter(S3, window=5)
    print("  Filter applied.")

    # ── CPR ───────────────────────────────────────────────────────────────────
    print("\n[3/5] Computing CPR and DOP...")
    cpr = compute_cpr(S0_f, S3_f, filter_window=0)  # already filtered
    dop = compute_dop(S0_f, S1_f, S2_f, S3_f)

    cpr_valid = cpr[np.isfinite(cpr)]
    dop_valid = dop[np.isfinite(dop)]
    
    if len(cpr_valid) > 0:
        cpr_min = np.nanmin(cpr_valid)
        cpr_max = np.nanmax(cpr_valid)
        cpr_mean = np.nanmean(cpr_valid)
    else:
        cpr_min, cpr_max, cpr_mean = 0.0, 0.0, 0.0
        
    if len(dop_valid) > 0:
        dop_min = np.nanmin(dop_valid)
        dop_max = np.nanmax(dop_valid)
        dop_mean = np.nanmean(dop_valid)
    else:
        dop_min, dop_max, dop_mean = 0.0, 0.0, 0.0

    print(f"  CPR — min={cpr_min:.3f}, max={cpr_max:.3f}, mean={cpr_mean:.3f}")
    print(f"  DOP — min={dop_min:.3f}, max={dop_max:.3f}, mean={dop_mean:.3f}")

    cpr_path = os.path.join(PROCESSED, "cpr_map.tif")
    dop_path = os.path.join(PROCESSED, "dop_map.tif")
    save_band(cpr, profile, cpr_path)
    save_band(dop, profile, dop_path)
    print(f"  Saved: {cpr_path}")
    print(f"  Saved: {dop_path}")

    # ── m-chi decomposition ───────────────────────────────────────────────────
    print("\n[4/5] Running m-chi decomposition...")
    mchi = mchi_decomposition(S0_f, S1_f, S2_f, S3_f)

    # Save false-colour RGB as 3-band GeoTIFF
    mchi_path = os.path.join(PROCESSED, "mchi_rgb.tif")
    rgb_profile = profile.copy()
    rgb_profile.update({"count": 3, "dtype": "uint8"})
    with rasterio.open(mchi_path, "w", **rgb_profile) as dst:
        rgb = mchi["rgb"]
        dst.write(rgb[:, :, 0], 1)  # Pd → Red
        dst.write(rgb[:, :, 1], 2)  # Pv → Green (volume/ice indicator)
        dst.write(rgb[:, :, 2], 3)  # Ps → Blue

    # Save volume scattering (Pv) as its own band
    pv_path = os.path.join(PROCESSED, "mchi_pv.tif")
    save_band(mchi["Pv"], profile, pv_path)
    print(f"  Saved m-chi RGB: {mchi_path}")

    # ── Ice Probability Map ───────────────────────────────────────────────────
    print("\n[5/5] Generating ice probability map...")
    if psr_mask is None:
        psr_mask = np.ones_like(cpr, dtype=np.uint8)  # if no PSR, use all pixels

    ice_prob = compute_ice_probability(cpr, dop, psr_mask)

    # Hard ice mask: strict thresholds matching BAH problem statement
    # CPR > 1.0  (volume/double-bounce dominance — characteristic of ice)
    # DOP < 0.13 (depolarised return — water ice is a volume scatterer)
    # inside PSR (or entire swath if PSR mask unavailable)
    ice_mask = ((cpr > 1.0) & (dop < 0.13) & (psr_mask == 1)).astype(np.uint8)

    n_ice = np.sum(ice_mask)
    print(f"  Ice pixels (CPR>1 & DOP<0.13 & in PSR): {n_ice:,}")

    ice_prob_path = os.path.join(PROCESSED, "ice_probability.tif")
    ice_mask_path = os.path.join(PROCESSED, "ice_mask.tif")
    save_band(ice_prob, profile, ice_prob_path)

    prob_profile = profile.copy()
    prob_profile.update({"dtype": "uint8"})
    with rasterio.open(ice_mask_path, "w", **prob_profile) as dst:
        dst.write(ice_mask, 1)

    print(f"  Saved ice probability: {ice_prob_path}")

    # ── Export Ice Candidates as GeoJSON ─────────────────────────────────────
    print("\n  Exporting top ice candidate zones to GeoJSON...")
    # Find local maxima in ice_prob as candidate points
    from scipy.ndimage import maximum_filter, label as ndlabel

    high_prob = (ice_prob > 0.7).astype(np.uint8)
    local_max = (ice_prob == maximum_filter(ice_prob, size=20)) & (ice_prob > 0.7)

    features = []
    rows, cols = np.where(local_max)
    # Sort by probability descending
    probs = ice_prob[rows, cols]
    order = np.argsort(probs)[::-1]

    for idx in order[:50]:   # top 50 candidates
        r, c = int(rows[idx]), int(cols[idx])
        lat, lon = pixel_to_latlon(r, c, profile)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "ice_probability": round(float(ice_prob[r, c]), 4),
                "cpr": round(float(cpr[r, c]) if np.isfinite(cpr[r, c]) else 0, 4),
                "dop": round(float(dop[r, c]) if np.isfinite(dop[r, c]) else 0, 4),
                "in_psr": int(psr_mask[r, c]),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
        })

    geojson_path = os.path.join(EXPORTS, "ice_candidates.geojson")
    with open(geojson_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
    print(f"  Saved ice candidates: {geojson_path}")

    # ── Export CPR Histogram ──────────────────────────────────────────────────
    print("\n  Exporting CPR histogram data for dashboard...")
    cpr_in_psr = cpr[psr_mask == 1]
    hist, bin_edges = np.histogram(cpr_in_psr, bins=50, range=(0, 3))
    
    hist_data = {
        "x": [float((bin_edges[i] + bin_edges[i+1])/2) for i in range(len(hist))],
        "y": [int(v) for v in hist]
    }
    with open(os.path.join(EXPORTS, "cpr_histogram.json"), "w") as f:
        json.dump(hist_data, f, indent=2)

    print("\n" + "=" * 60)
    print(" Ice detection complete.")
    print(f"  Total ice pixels: {n_ice:,}")
    print(f"  Ice-covered area: {n_ice * (abs(profile['transform'].a)**2) / 1e6:.3f} km²")
    print(f"  Top ice candidates exported: {len(features)}")
    print("=" * 60)
    print(" Next: run  python src/04_terrain_analysis.py")

    return {
        "cpr_map": cpr_path,
        "dop_map": dop_path,
        "mchi_rgb": mchi_path,
        "ice_probability": ice_prob_path,
        "ice_mask": ice_mask_path,
        "ice_candidates_geojson": geojson_path,
    }


if __name__ == "__main__":
    run_ice_detection()
