"""
04_terrain_analysis.py

Step 4: Terrain Safety Analysis
  - Slope analysis from LOLA 5m DEM
  - Surface roughness (rolling std of slope)
  - Boulder detection from OHRC imagery (OpenCV blob detection)
  - Solar illumination score (from illumination_fraction.tif)
  - Composite hazard score per pixel

Usage:
  python src/04_terrain_analysis.py

Inputs:
  data/processed/lola_dem_5m.tif
  data/processed/ohrc_radiance.tif
  data/processed/illumination_fraction.tif

Outputs:
  data/processed/slope_map.tif
  data/processed/roughness_map.tif
  data/processed/boulder_density.tif
  data/processed/hazard_score.tif
  data/exports/terrain_stats.json
"""

import os
import sys
import json
import numpy as np
import rasterio
import cv2

sys.path.insert(0, os.path.dirname(__file__))
from utils.dem_utils import compute_slope, compute_roughness
from utils.geo_utils import read_band, save_band

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS   = os.path.join(ROOT, "data", "exports")
os.makedirs(EXPORTS, exist_ok=True)


def detect_boulders_ohrc(ohrc_arr: np.ndarray,
                           pixel_size_m: float = 5.0) -> np.ndarray:
    """
    Detect boulders in OHRC panchromatic imagery using OpenCV blob detector.
    Boulders appear as high-brightness circular features (2–10m radius).

    Parameters
    ----------
    ohrc_arr   : 2D radiance array (float32)
    pixel_size_m : pixel size in metres

    Returns
    -------
    boulder_density : 2D float32 normalised boulder count per 50m²
    """
    # Normalise to 8-bit for OpenCV
    valid = ohrc_arr[np.isfinite(ohrc_arr)]
    if len(valid) == 0:
        print("  [WARNING] OHRC image contains no valid pixels (possible no-overlap). Returning zero boulder density.")
        return np.zeros(ohrc_arr.shape, dtype=np.float32)
        
    vmin, vmax = np.percentile(valid, 2), np.percentile(valid, 98)
    img_8bit = np.clip((ohrc_arr - vmin) / (vmax - vmin + 1e-10) * 255, 0, 255)
    img_8bit = img_8bit.astype(np.uint8)

    # SimpleBlobDetector parameters tuned for lunar boulders
    # cv2 requires: 0 < minArea <= maxArea — clamp to valid range
    min_radius_px = max(1.0, 2.0 / pixel_size_m)   # min 2 m boulder radius
    max_radius_px = max(2.0, 15.0 / pixel_size_m)  # max 15 m boulder radius
    min_area = max(1, int(min_radius_px ** 2 * 3.14))
    max_area = max(min_area + 1, int(max_radius_px ** 2 * 3.14))
    print(f"  Boulder detector: pixel_size={pixel_size_m:.1f}m, "
          f"minArea={min_area}, maxArea={max_area}")

    params = cv2.SimpleBlobDetector_Params()
    params.filterByArea = True
    params.minArea = float(min_area)
    params.maxArea = float(max_area)
    params.filterByCircularity = True
    params.minCircularity = 0.5
    params.filterByConvexity = True
    params.minConvexity = 0.7
    params.filterByInertia = True
    params.minInertiaRatio = 0.4
    params.filterByColor = True
    params.blobColor = 255   # bright boulders

    detector = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(img_8bit)

    # Rasterize boulder positions into a density map
    boulder_density = np.zeros(ohrc_arr.shape, dtype=np.float32)
    window_px = int(50.0 / pixel_size_m)   # 50m window

    for kp in keypoints:
        r, c = int(kp.pt[1]), int(kp.pt[0])
        r0, r1 = max(0, r - window_px), min(ohrc_arr.shape[0], r + window_px)
        c0, c1 = max(0, c - window_px), min(ohrc_arr.shape[1], c + window_px)
        boulder_density[r0:r1, c0:c1] += 1.0

    # Normalise
    if boulder_density.max() > 0:
        boulder_density /= boulder_density.max()

    print(f"  Detected {len(keypoints)} boulder candidates in OHRC.")
    return boulder_density


def compute_hazard_score(slope: np.ndarray,
                          roughness: np.ndarray,
                          boulder_density: np.ndarray,
                          weights: dict = None) -> np.ndarray:
    """
    Composite terrain hazard score [0, 1].
    Higher = more hazardous = worse for landing/traverse.

    Components:
      - Slope score:    normalised slope (0° → 0, 30°+ → 1)
      - Roughness score: normalised roughness
      - Boulder score:   boulder density map

    Parameters
    ----------
    weights : dict with keys 'slope', 'roughness', 'boulder'
              defaults to {'slope': 0.5, 'roughness': 0.3, 'boulder': 0.2}
    """
    if weights is None:
        weights = {"slope": 0.5, "roughness": 0.3, "boulder": 0.2}

    # Normalise slope: 0° → 0, 30° → 1 (capped)
    slope_norm = np.clip(slope / 30.0, 0, 1)

    # Normalise roughness
    r_max = np.nanpercentile(roughness, 98)
    roughness_norm = np.clip(roughness / (r_max + 1e-10), 0, 1)

    hazard = (weights["slope"] * slope_norm +
              weights["roughness"] * roughness_norm +
              weights["boulder"] * boulder_density)

    return np.clip(hazard, 0, 1).astype(np.float32)


def run_terrain_analysis() -> dict:
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 4: Terrain Safety Analysis")
    print("=" * 60)

    lola_path  = os.path.join(PROCESSED, "lola_dem_5m.tif")
    ohrc_path  = os.path.join(PROCESSED, "ohrc_radiance.tif")
    illum_path = os.path.join(PROCESSED, "illumination_fraction.tif")

    if not os.path.exists(lola_path):
        print(f"[ERROR] LOLA DEM not found: {lola_path}")
        return {}

    # ── Load DEM ──────────────────────────────────────────────────────────────
    print("\n[1/4] Loading LOLA DEM...")
    dem, profile = read_band(lola_path)
    pixel_size_m = abs(profile["transform"].a)
    print(f"  DEM shape: {dem.shape}, pixel size: {pixel_size_m:.1f} m")

    # ── Slope ─────────────────────────────────────────────────────────────────
    print("\n[2/4] Computing slope and roughness...")
    slope = compute_slope(dem, pixel_size_m)
    roughness = compute_roughness(slope, window=10)

    n_safe = np.sum(slope < 15)
    print(f"  Slope < 15° (safe for landing): {n_safe:,} pixels "
          f"({100*n_safe/slope.size:.1f}%)")
    print(f"  Max slope: {np.nanmax(slope):.1f}°")

    slope_path = os.path.join(PROCESSED, "slope_map.tif")
    roughness_path = os.path.join(PROCESSED, "roughness_map.tif")
    save_band(slope, profile, slope_path)
    save_band(roughness, profile, roughness_path)
    print(f"  Saved: {slope_path}")

    # ── Boulder Detection ─────────────────────────────────────────────────────
    print("\n[3/4] Detecting boulders in OHRC imagery...")
    if os.path.exists(ohrc_path):
        ohrc, _ = read_band(ohrc_path)
        if np.nanmax(ohrc) == 0:
            print("  [WARNING] OHRC image is blank (all zeros). Proceeding with empty boulder data as per constraints (no synthesized data).")
            boulder_density = np.zeros_like(roughness, dtype=np.float32)
        else:
            boulder_density = detect_boulders_ohrc(ohrc, pixel_size_m)
    else:
        print(f"  [WARNING] OHRC not found at {ohrc_path}. "
              "Proceeding with empty boulder data as per constraints (no synthesized data).")
        boulder_density = np.zeros_like(roughness, dtype=np.float32)

    boulder_path = os.path.join(PROCESSED, "boulder_density.tif")
    save_band(boulder_density, profile, boulder_path)

    # ── Hazard Score ──────────────────────────────────────────────────────────
    print("\n[4/4] Computing composite hazard score...")
    hazard = compute_hazard_score(slope, roughness, boulder_density)
    hazard_path = os.path.join(PROCESSED, "hazard_score.tif")
    save_band(hazard, profile, hazard_path)
    print(f"  Mean hazard score: {np.nanmean(hazard):.3f}")
    print(f"  Saved: {hazard_path}")

    # ── Load illumination fraction ─────────────────────────────────────────────
    if os.path.exists(illum_path):
        illum, _ = read_band(illum_path)
        solar_score = np.clip(illum, 0, 1)
    else:
        print("  [WARNING] Illumination fraction not found. Setting solar score = 0.5")
        solar_score = np.full_like(slope, 0.5)

    solar_path = os.path.join(PROCESSED, "solar_score.tif")
    save_band(solar_score, profile, solar_path)

    # ── Stats Export ──────────────────────────────────────────────────────────
    stats = {
        "scene_pixel_size_m": float(pixel_size_m),
        "total_pixels": int(dem.size),
        "slope": {
            "mean_deg": float(np.nanmean(slope)),
            "max_deg": float(np.nanmax(slope)),
            "pct_below_15deg": float(100 * np.sum(slope < 15) / slope.size),
        },
        "roughness": {
            "mean": float(np.nanmean(roughness)),
            "max": float(np.nanmax(roughness)),
        },
        "hazard": {
            "mean": float(np.nanmean(hazard)),
            "pct_low_hazard": float(100 * np.sum(hazard < 0.3) / hazard.size),
        },
    }

    stats_path = os.path.join(EXPORTS, "terrain_stats.json")
    with open(stats_path, "w", encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Terrain stats: {stats_path}")

    print("\n" + "=" * 60)
    print(" Terrain analysis complete.")
    print(f"  Low-hazard pixels (H<0.3): {stats['hazard']['pct_low_hazard']:.1f}%")
    print("=" * 60)
    print(" Next: run  python src/05_landing_site_selection.py")

    return {
        "slope_map": slope_path,
        "roughness_map": roughness_path,
        "boulder_density": boulder_path,
        "hazard_score": hazard_path,
        "solar_score": solar_path,
    }


if __name__ == "__main__":
    run_terrain_analysis()
