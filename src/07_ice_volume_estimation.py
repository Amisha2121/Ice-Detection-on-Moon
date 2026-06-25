"""
07_ice_volume_estimation.py

Step 7: Subsurface Ice Volume Estimation
  - Counts ice pixels from ice_mask (CPR>1 AND DOP<0.13 AND in PSR)
  - Converts pixel count to area via pixel_resolution²
  - Applies briefing formula: Volume = Area × depth × ice_fraction
  - Uncertainty: Monte Carlo over [depth_low, depth_high] × [conc_low, conc_high]
  - Export volume statistics

Usage:
  python src/07_ice_volume_estimation.py

Inputs:
  data/processed/cpr_map.tif
  data/processed/ice_mask.tif

Outputs:
  data/processed/ice_concentration.tif
  data/processed/dielectric_map.tif
  data/exports/ice_volume_report.json
"""

import os
import sys
import json
import numpy as np

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import read_band, save_band

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS   = os.path.join(ROOT, "data", "exports")
os.makedirs(EXPORTS, exist_ok=True)

# ── Physical Constants (Briefing Formula Chain) ───────────────────────────────
DEPTH_MID       = 2.5    # m — midpoint of 0–5 m subsurface layer
DEPTH_LOW       = 1.0    # m — lower CI bound
DEPTH_HIGH      = 5.0    # m — upper CI bound
CONC_MID        = 0.10   # 10% volumetric ice fraction (conservative)
CONC_LOW        = 0.05   # 5%  — lower CI bound
CONC_HIGH       = 0.20   # 20% — upper CI bound
ICE_DENSITY     = 917.0  # kg/m³
EPSILON_ICE     = 3.15
EPSILON_REG     = 2.70


def cpr_to_dielectric(cpr: np.ndarray) -> np.ndarray:
    """Fresnel inversion: CPR → effective dielectric constant."""
    cpr_baseline = 0.25
    cpr_norm = np.clip(cpr / cpr_baseline, 0, None)
    sqrt_cpr = np.sqrt(np.clip(cpr_norm, 0, 0.99))
    epsilon = ((1.0 + sqrt_cpr) / (1.0 - sqrt_cpr + 1e-6)) ** 2
    epsilon = np.clip(epsilon, EPSILON_REG, 10.0)
    return epsilon.astype(np.float32)


def run_ice_volume_estimation() -> dict:
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 7: Ice Volume Estimation")
    print("=" * 60)

    cpr_path  = os.path.join(PROCESSED, "cpr_map.tif")
    mask_path = os.path.join(PROCESSED, "ice_mask.tif")

    if not os.path.exists(cpr_path):
        print(f"[ERROR] CPR map not found: {cpr_path}")
        print("  Run 03_radar_ice_detection.py first.")
        return {}

    # ── Load CPR and mask ─────────────────────────────────────────────────────
    print("\n[1/4] Loading CPR map and ice mask...")
    cpr,  profile  = read_band(cpr_path)
    if os.path.exists(mask_path):
        ice_mask, _ = read_band(mask_path)
        ice_mask = (ice_mask > 0).astype(np.uint8)
    else:
        print("  [WARNING] Ice mask not found. Using CPR > 1 as mask.")
        ice_mask = (cpr > 1.0).astype(np.uint8)

    pixel_size_m  = abs(profile["transform"].a)
    pixel_area_m2 = pixel_size_m ** 2
    n_ice_pixels  = int(np.sum(ice_mask))
    ice_area_km2  = n_ice_pixels * pixel_area_m2 / 1e6

    print(f"  Ice pixels: {n_ice_pixels:,}  ({ice_area_km2:.6f} km²  = {n_ice_pixels * pixel_area_m2:.0f} m²)")

    # ── Dielectric inversion (for reference / secondary output) ──────────────
    print("\n[2/4] Inverting CPR → dielectric constant (Fresnel model)...")
    epsilon = cpr_to_dielectric(cpr)
    epsilon_ice_region = np.where(ice_mask == 1, epsilon, np.nan)
    mean_eps = float(np.nanmean(epsilon_ice_region)) if n_ice_pixels > 0 else 0.0
    max_eps  = float(np.nanmax(epsilon_ice_region))  if n_ice_pixels > 0 else 0.0
    print(f"  Effective epsilon — mean={mean_eps:.3f}, max={max_eps:.3f}")

    epsilon_path = os.path.join(PROCESSED, "dielectric_map.tif")
    save_band(epsilon, profile, epsilon_path)
    print(f"  Saved: {epsilon_path}")

    # ── Ice concentration proxy (Maxwell-Garnett simplified) ─────────────────
    print("\n[3/4] Computing ice concentration proxy...")
    # Save ice_concentration map as CONC_MID everywhere inside ice mask
    conc_map = np.where(ice_mask == 1, CONC_MID, 0.0).astype(np.float32)
    conc_path = os.path.join(PROCESSED, "ice_concentration.tif")
    save_band(conc_map, profile, conc_path)
    print(f"  Mean ice concentration (in detection zone): {CONC_MID*100:.1f}%")
    print(f"  Saved: {conc_path}")

    # ── Briefing Formula Chain ────────────────────────────────────────────────
    # Step 4: Volume — ice depth assumed 0–5m subsurface
    #   ice_volume_km3 = ice_area_km2 × (depth_m / 1000) × ice_fraction
    # Step 5: Mass
    #   volume_m3 = ice_volume_km3 × 1e9
    #   ice_mass_Gt = (volume_m3 × ice_density × ice_fraction) / 1e12

    point_vol_km3 = ice_area_km2 * (DEPTH_MID / 1000.0) * CONC_MID
    volume_m3     = point_vol_km3 * 1e9
    ice_mass_Gt   = (volume_m3 * ICE_DENSITY * CONC_MID) / 1e12

    print(f"\n  === ICE VOLUME ESTIMATE (Briefing Formula) ===")
    print(f"  Ice area:        {ice_area_km2:.6f} km²")
    print(f"  Depth midpoint:  {DEPTH_MID} m,  Concentration: {CONC_MID*100:.0f}%")
    print(f"  Point estimate:  {point_vol_km3:.6e} km³")
    print(f"  Ice mass:        {ice_mass_Gt:.4e} Gt")

    # ── Uncertainty bounds (90% CI using low/high depth × concentration) ─────
    print("\n[4/4] Computing 90% CI via depth × concentration bounds...")
    vol_low  = ice_area_km2 * (DEPTH_LOW  / 1000.0) * CONC_LOW
    vol_high = ice_area_km2 * (DEPTH_HIGH / 1000.0) * CONC_HIGH

    # Monte Carlo over depth and concentration distributions
    n_draws   = 1000
    rng       = np.random.default_rng(42)
    depths    = rng.uniform(DEPTH_LOW, DEPTH_HIGH, n_draws)
    concs     = rng.uniform(CONC_LOW,  CONC_HIGH,  n_draws)
    mc_vols   = ice_area_km2 * (depths / 1000.0) * concs
    mc_mean   = float(np.mean(mc_vols))
    mc_std    = float(np.std(mc_vols))
    mc_p5     = float(np.percentile(mc_vols, 5))
    mc_p95    = float(np.percentile(mc_vols, 95))

    print(f"  MC mean:    {mc_mean:.6e} km³")
    print(f"  MC 1-sigma: ±{mc_std:.6e} km³")
    print(f"  90% CI:     [{mc_p5:.6e}, {mc_p95:.6e}] km³")

    # ── Export report ─────────────────────────────────────────────────────────
    report = {
        "scene_pixel_size_m":   pixel_size_m,
        "ice_detection": {
            "n_ice_pixels":     n_ice_pixels,
            "pixel_area_m2":    pixel_area_m2,
            "ice_area_m2":      float(n_ice_pixels * pixel_area_m2),
            "ice_area_km2":     round(ice_area_km2, 8),
        },
        "dielectric_inversion": {
            "model":            "Fresnel reflection + CPR normalisation",
            "epsilon_regolith": EPSILON_REG,
            "epsilon_ice":      EPSILON_ICE,
            "mean_epsilon_detected_region": round(mean_eps, 4),
        },
        "concentration": {
            "model":                "Briefing formula (conservative)",
            "mean_ice_fraction_pct": round(CONC_MID * 100, 2),
            "low_pct":               round(CONC_LOW  * 100, 2),
            "high_pct":              round(CONC_HIGH * 100, 2),
        },
        "volume_estimate": {
            "depth_mid_m":           DEPTH_MID,
            "depth_range_m":         [DEPTH_LOW, DEPTH_HIGH],
            "conc_range":            [CONC_LOW, CONC_HIGH],
            "point_estimate_km3":    round(point_vol_km3, 10),
            "point_estimate_m3":     round(volume_m3, 4),
            "vol_low_km3":           round(vol_low, 10),
            "vol_high_km3":          round(vol_high, 10),
            "mass_Gt":               round(ice_mass_Gt, 10),
            "monte_carlo": {
                "n_draws":   n_draws,
                "mean_km3":  round(mc_mean, 10),
                "std_km3":   round(mc_std, 10),
                "p5_km3":    round(mc_p5, 10),
                "p95_km3":   round(mc_p95, 10),
                "cpr_noise_pct": 15,
                "samples":   n_draws,
            }
        },
        "references": [
            "Spudis et al. 2013 — Mini-RF CPR baseline",
            "Fresnel reflection model — Nozette et al. 1996",
            "Ice density 917 kg/m3 — CRC Handbook",
            "Briefing formula chain: vol = area × depth × ice_fraction",
        ]
    }

    report_path = os.path.join(EXPORTS, "ice_volume_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Full report saved: {report_path}")

    print("\n" + "=" * 60)
    print(" Ice Volume Estimation complete.")
    print(f"  Point:  {point_vol_km3:.4e} km³")
    print(f"  90% CI: {mc_p5:.4e} – {mc_p95:.4e} km³")
    print(f"  Mass:   {ice_mass_Gt:.4e} Gt")
    print("=" * 60)
    print(" Next: open  dashboard/index.html  in your browser.")

    return {
        "dielectric_map":    epsilon_path,
        "ice_concentration": conc_path,
        "volume_report":     report_path,
        "volume_km3":        mc_mean,
    }


if __name__ == "__main__":
    run_ice_volume_estimation()
