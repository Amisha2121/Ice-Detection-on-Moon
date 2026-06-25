"""
05_landing_site_selection.py

Step 5: Multi-Criteria Landing Site Selection
  - Combines ice proximity, terrain safety, solar illumination, flatness
  - Generates a composite suitability score per pixel
  - Identifies top candidate landing ellipses (3×4 km)
  - Ranks and exports as GeoJSON for dashboard

Usage:
  python src/05_landing_site_selection.py

Inputs:
  data/processed/ice_probability.tif
  data/processed/hazard_score.tif
  data/processed/solar_score.tif
  data/processed/slope_map.tif
  data/processed/psr_mask.tif

Outputs:
  data/processed/landing_suitability.tif
  data/exports/landing_sites.geojson
"""

import os
import sys
import json
import numpy as np
import rasterio
from scipy.ndimage import (maximum_filter, label as nd_label,
                            gaussian_filter, distance_transform_edt)

sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import read_band, save_band, pixel_to_latlon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS   = os.path.join(ROOT, "data", "exports")
os.makedirs(EXPORTS, exist_ok=True)

# ── Scoring weights (5-criteria per briefing) ────────────────────────────────
# 1. Slope safety   2. Hazard   3. Ice proximity   4. Illumination   5. Comms
WEIGHTS = {
    "slope":        0.25,
    "hazard":       0.25,
    "ice_prox":     0.30,   # highest — ice access is primary goal
    "illumination": 0.15,
    "comm":         0.05,
}

ICE_PROX_DECAY_KM = 2.0   # exponential decay half-distance for ice proximity


def compute_ice_proximity_score(ice_mask: np.ndarray,
                                 pixel_size_m: float = 5.0) -> np.ndarray:
    """
    Exponential-decay proximity score: exp(-d / ICE_PROX_DECAY_KM).
    Landing sites near ice deposits score highly (briefing formula).
    """
    if np.sum(ice_mask) == 0:
        print("  [WARNING] No ice pixels found. Proximity score is zero everywhere.")
        return np.zeros_like(ice_mask, dtype=np.float32)

    dist_px = distance_transform_edt(1 - ice_mask)
    dist_km = dist_px * pixel_size_m / 1000.0
    # Exponential decay: exp(-d / decay_km); closer = higher score
    proximity = np.exp(-dist_km / ICE_PROX_DECAY_KM)
    return proximity.astype(np.float32)


def compute_suitability(ice_prob: np.ndarray,
                         hazard: np.ndarray,
                         solar: np.ndarray,
                         slope: np.ndarray,
                         psr_mask: np.ndarray,
                         pixel_size_m: float = 5.0) -> np.ndarray:
    """
    5-criteria composite landing suitability score [0, 1].

    Criteria (per briefing):
      1. Slope score       — lower slope is better (< 5° ideal)
      2. Hazard score      — lower roughness/boulders is better
      3. Ice proximity     — exponential decay from nearest ice pixel
      4. Illumination      — solar fraction for power generation
      5. Comms visibility  — always 1.0 (assumed; no comms map available)

    Landing sites OUTSIDE the PSR (for solar power) but close to ice.
    """
    # 1. Slope score — < 5° ideal, 0 at 10°+
    slope_score = np.clip(1.0 - slope / 10.0, 0, 1)

    # 2. Hazard score
    hazard_score = np.clip(1.0 - hazard, 0, 1)

    # 3. Ice proximity (exponential decay)
    ice_prox_score = compute_ice_proximity_score(ice_prob, pixel_size_m)

    # 4. Illumination score (solar fraction)
    illum_score = np.clip(solar, 0, 1)

    # 5. Comm visibility (assume 1.0 everywhere — no comm map available)
    comm_score = np.ones_like(slope, dtype=np.float32)

    score = (WEIGHTS["slope"]        * slope_score +
             WEIGHTS["hazard"]       * hazard_score +
             WEIGHTS["ice_prox"]     * ice_prox_score +
             WEIGHTS["illumination"] * illum_score +
             WEIGHTS["comm"]         * comm_score)

    # Hard constraints: must be outside PSR, slope < 15°
    score = np.where((psr_mask == 0) & (slope < 15.0), score, 0.0)

    return np.clip(score, 0, 1).astype(np.float32)


def find_landing_candidates(suitability: np.ndarray,
                              profile: dict,
                              top_n: int = 3,
                              min_sep_px: int = 200) -> list:
    """
    Find top-N distinct landing site candidates using local maxima
    with minimum separation constraint.

    Returns list of dicts with pixel coords and scores.
    """
    # Smooth before finding peaks
    smooth = gaussian_filter(suitability.astype(np.float64), sigma=5)
    local_max = (smooth == maximum_filter(smooth, size=min_sep_px // 2))
    candidates_mask = local_max & (suitability > 0.3)

    rows, cols = np.where(candidates_mask)
    scores = suitability[rows, cols]
    order = np.argsort(scores)[::-1]

    selected = []
    for idx in order:
        r, c = int(rows[idx]), int(cols[idx])

        # Check minimum separation from already-selected sites
        too_close = False
        for s in selected:
            dist = np.sqrt((r - s["row"])**2 + (c - s["col"])**2)
            if dist < min_sep_px:
                too_close = True
                break

        if not too_close:
            selected.append({"row": r, "col": c,
                               "score": float(suitability[r, c])})
        if len(selected) >= top_n:
            break

    return selected


def run_landing_site_selection() -> dict:
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 5: Landing Site Selection")
    print("=" * 60)

    # ── Load inputs ───────────────────────────────────────────────────────────
    required = {
        "ice_mask":        os.path.join(PROCESSED, "ice_mask.tif"),
        "hazard_score":    os.path.join(PROCESSED, "hazard_score.tif"),
        "slope_map":       os.path.join(PROCESSED, "slope_map.tif"),
    }

    for name, path in required.items():
        if not os.path.exists(path):
            print(f"[ERROR] Missing: {path}")
            print(f"  Run previous pipeline steps first.")
            return {}

    print("\n[1/3] Loading terrain layers...")
    ice_mask, profile = read_band(required["ice_mask"])
    ice_mask = ice_mask.astype(np.uint8)
    
    ice_prob_path = os.path.join(PROCESSED, "ice_probability.tif")
    if os.path.exists(ice_prob_path):
        ice_prob, _ = read_band(ice_prob_path)
    else:
        ice_prob = np.zeros_like(ice_mask, dtype=np.float32)
        
    hazard, _         = read_band(required["hazard_score"])
    slope, _          = read_band(required["slope_map"])
    pixel_size_m      = abs(profile["transform"].a)

    solar_path = os.path.join(PROCESSED, "solar_score.tif")
    solar = read_band(solar_path)[0] if os.path.exists(solar_path) else np.full_like(slope, 0.3)

    psr_path = os.path.join(PROCESSED, "psr_mask.tif")
    psr_mask = read_band(psr_path)[0].astype(np.uint8) if os.path.exists(psr_path) else np.zeros_like(slope, dtype=np.uint8)

    print(f"  Scene: {ice_mask.shape}, pixel size: {pixel_size_m:.1f} m")

    # ── Align all layers to ice_mask grid ─────────────────────────────────────
    import rasterio.warp as _warp
    from rasterio.enums import Resampling as _RS

    def _align(arr, src_path, ref_profile):
        """Reproject arr (loaded from src_path) to match ref_profile grid."""
        if arr.shape == (ref_profile["height"], ref_profile["width"]):
            return arr
        with rasterio.open(src_path) as _src:
            out = np.zeros((ref_profile["height"], ref_profile["width"]), dtype=np.float32)
            _warp.reproject(
                source=arr.astype(np.float32),
                destination=out,
                src_transform=_src.transform,
                src_crs=_src.crs,
                dst_transform=ref_profile["transform"],
                dst_crs=ref_profile["crs"],
                resampling=_RS.bilinear
            )
        return out

    def _align_mask(arr, src_path, ref_profile):
        out = _align(arr.astype(np.float32), src_path, ref_profile)
        return (out > 0.5).astype(np.uint8)

    if hazard.shape != ice_mask.shape:
        print(f"  Reprojecting hazard {hazard.shape} → {ice_mask.shape}")
        hazard = _align(hazard, required["hazard_score"], profile)

    if slope.shape != ice_mask.shape:
        print(f"  Reprojecting slope {slope.shape} → {ice_mask.shape}")
        slope = _align(slope, required["slope_map"], profile)

    if solar.shape != ice_mask.shape:
        solar = np.full(ice_mask.shape, 0.3, dtype=np.float32)

    if psr_mask.shape != ice_mask.shape:
        print(f"  Reprojecting PSR mask {psr_mask.shape} → {ice_mask.shape}")
        psr_mask = _align_mask(psr_mask, psr_path, profile)

    # ── Suitability map ───────────────────────────────────────────────────────
    print("\n[2/3] Computing landing suitability map...")
    suitability = compute_suitability(ice_mask, hazard, solar, slope,
                                       psr_mask, pixel_size_m)
    suit_path = os.path.join(PROCESSED, "landing_suitability.tif")
    save_band(suitability, profile, suit_path)
    print(f"  Max suitability score: {np.nanmax(suitability):.4f}")
    print(f"  Saved: {suit_path}")

    # ── Find candidates ───────────────────────────────────────────────────────
    print("\n[3/3] Selecting top landing site candidates...")
    candidates = find_landing_candidates(suitability, profile, top_n=3,
                                          min_sep_px=int(5000 / pixel_size_m))

    if not candidates:
        print("  [WARNING] No valid landing sites found. Try relaxing constraints.")
        return {"suitability_map": suit_path, "landing_sites": []}

    # ── Enrich each candidate with additional metrics ─────────────────────────
    from scipy.spatial import cKDTree
    ice_coords = np.column_stack(np.where(ice_mask))
    if len(ice_coords) > 0:
        ice_tree = cKDTree(ice_coords)
    else:
        ice_tree = None

    features = []
    for rank, c in enumerate(candidates, 1):
        r, c_col = c["row"], c["col"]
        lat, lon = pixel_to_latlon(r, c_col, profile)

        # Compute distance to nearest ice pixel
        if ice_tree is not None:
            dist_px, _ = ice_tree.query([r, c_col])
            dist_to_ice = (dist_px * pixel_size_m) / 1000.0
        else:
            dist_to_ice = -1.0

        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "rank": rank,
                "suitability_score": round(c["score"], 4),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "slope_deg": round(float(slope[r, c_col]), 2),
                "hazard_score": round(float(hazard[r, c_col]), 4),
                "solar_fraction": round(float(solar[r, c_col]), 4),
                "ice_probability_nearby": round(float(ice_prob[r, c_col]), 4),
                "distance_to_ice_m": round(float(dist_to_ice), 0),
                "label": f"LS-{rank}",
                "rationale": (
                    f"Rank {rank}: score={c['score']:.3f}, "
                    f"slope={slope[r,c_col]:.1f}°, "
                    f"distance to ice={dist_to_ice/1000:.2f} km"
                ),
            }
        }
        features.append(feature)
        print(f"\n  Landing Site {rank} (score={c['score']:.4f}):")
        print(f"    Lat/Lon: {lat:.4f}°, {lon:.4f}°")
        print(f"    Slope: {slope[r,c_col]:.1f}°, Hazard: {hazard[r,c_col]:.3f}")
        print(f"    Distance to ice: {dist_to_ice/1000:.2f} km")

    geojson_path = os.path.join(EXPORTS, "landing_sites.geojson")
    with open(geojson_path, "w", encoding='utf-8') as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
    print(f"\n  Saved landing sites: {geojson_path}")

    print("\n" + "=" * 60)
    print(f" Landing Site Selection complete. Top {len(features)} sites identified.")
    print("=" * 60)
    print(" Next: run  python src/06_rover_traverse.py")

    return {"suitability_map": suit_path,
            "landing_sites_geojson": geojson_path,
            "candidates": candidates}


if __name__ == "__main__":
    run_landing_site_selection()
