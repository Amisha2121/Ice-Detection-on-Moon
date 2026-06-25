"""
check_accuracy.py  –  Summarise pipeline output quality metrics.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import read_band

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
EXP  = os.path.join(ROOT, "data", "exports")

print("=" * 60)
print(" PIPELINE ACCURACY / DATA-QUALITY SUMMARY")
print("=" * 60)

# ── Ice Detection ─────────────────────────────────────────────
ice,      _ = read_band(os.path.join(PROC, "ice_mask.tif"))
ice_prob, _ = read_band(os.path.join(PROC, "ice_probability.tif"))
cpr,      _ = read_band(os.path.join(PROC, "cpr_map.tif"))
dop,      _ = read_band(os.path.join(PROC, "dop_map.tif"))

valid_cpr = cpr[np.isfinite(cpr)]
valid_dop = dop[np.isfinite(dop)]

print("\n[ICE DETECTION]")
print(f"  CPR valid pixels  : {len(valid_cpr):>10,} / {cpr.size:,}  ({100*len(valid_cpr)/cpr.size:.1f}% coverage)")
if len(valid_cpr):
    print(f"  CPR range         : {valid_cpr.min():.3f} – {valid_cpr.max():.3f}  (mean={valid_cpr.mean():.3f})")
    print(f"  CPR > 1.0 pixels  : {int(np.sum(valid_cpr > 1.0)):>10,}  (ice-like threshold)")
print(f"  DOP valid pixels  : {len(valid_dop):>10,}  (mean={valid_dop.mean():.3f})" if len(valid_dop) else "  DOP: no valid pixels")
print(f"  Ice mask flagged  : {int(np.sum(ice)):>10,} px  (AND of CPR+DOP+PSR)")
print(f"  Ice prob > 0.5    : {int(np.sum(ice_prob > 0.5)):>10,} px")
print(f"  Ice prob > 0.3    : {int(np.sum(ice_prob > 0.3)):>10,} px")
print(f"  Ice prob > 0.1    : {int(np.sum(ice_prob > 0.1)):>10,} px")
print(f"  Ice prob max      : {np.nanmax(ice_prob):.3f}")

# ── PSR / DSC ─────────────────────────────────────────────────
illum, _ = read_band(os.path.join(PROC, "illumination_fraction.tif"))
# ── PSR / DSC ─────────────────────────────────────────────────
illum, _ = read_band(os.path.join(PROC, "illumination_fraction.tif"))
dsc,   _ = read_band(os.path.join(PROC, "dsc_mask.tif"))

print("\n[PERMANENTLY SHADOWED REGIONS]")
print(f"  PSR (illum=0)     : {int(np.sum(illum == 0)):>10,} px  ({100*np.sum(illum==0)/illum.size:.2f}%)")
print(f"  Near-PSR (<0.05)  : {int(np.sum(illum < 0.05)):>10,} px  ({100*np.sum(illum<0.05)/illum.size:.2f}%)")
print(f"  Illum range       : {illum.min():.3f} – {illum.max():.3f}")
print(f"  DSC craters found : {int(dsc.max()):>10,}")

# ── Terrain ───────────────────────────────────────────────────
slope,   _ = read_band(os.path.join(PROC, "slope_map.tif"))
hazard,  _ = read_band(os.path.join(PROC, "hazard_score.tif"))
roughness, _ = read_band(os.path.join(PROC, "roughness_map.tif"))

print("\n[TERRAIN ANALYSIS]")
print(f"  DEM pixels        : {slope.size:>10,}  ({int(slope.shape[0])}x{int(slope.shape[1])} @ 5 m/px)")
print(f"  Slope mean/max    : {np.nanmean(slope):.1f}° / {np.nanmax(slope):.1f}°")
print(f"  Safe (<15°)       : {100*np.sum(slope<15)/slope.size:.1f}%")
print(f"  Slope < 5°        : {100*np.sum(slope<5)/slope.size:.1f}%  (very flat)")
print(f"  Roughness mean    : {np.nanmean(roughness):.3f} deg-std")
print(f"  Low-hazard (H<0.3): {100*np.sum(hazard<0.3)/hazard.size:.1f}%")

# ── Landing Sites ─────────────────────────────────────────────
ls_path = os.path.join(EXP, "landing_sites.geojson")
if os.path.exists(ls_path):
    with open(ls_path) as f:
        ls = json.load(f)
    feats = ls.get("features", [])
    print(f"\n[LANDING SITES]  {len(feats)} candidates")
    for feat in feats:
        p = feat["properties"]
        coord = feat["geometry"]["coordinates"]
        label = p.get('label', f"LS-{p.get('rank', '?')}")
        print(f"  {label}: lat={coord[1]:.4f} lon={coord[0]:.4f}  "
              f"score={p['suitability_score']:.4f}  slope={p['slope_deg']:.1f}deg  hazard={p['hazard_score']:.3f}")

# ── Volume ────────────────────────────────────────────────────
vol_path = os.path.join(EXP, "ice_volume_report.json")
if os.path.exists(vol_path):
    with open(vol_path) as f:
        vol = json.load(f)
    vest = vol.get("volume_estimate", {})
    mc = vest.get("monte_carlo", {})
    print(f"\n[ICE VOLUME ESTIMATE]")
    print(f"  Point estimate    : {vest.get('point_estimate_km3', 0.0):.6f} km3")
    print(f"  90% CI            : [{mc.get('p5_km3', 0.0):.6f}, {mc.get('p95_km3', 0.0):.6f}] km3")

# ── Overlap analysis ─────────────────────────────────────────
print("\n[DATA OVERLAP ANALYSIS]")
psr_mask  = illum < 0.05
cpr_valid = np.isfinite(cpr)
both = psr_mask & cpr_valid
print(f"  PSR area          : {int(np.sum(psr_mask)):>10,} px")
print(f"  CPR valid area    : {int(np.sum(cpr_valid)):>10,} px")
print(f"  PSR & CPR overlap : {int(np.sum(both)):>10,} px  <- KEY for ice detection")
if np.sum(both) > 0 and len(valid_cpr) > 0:
    cpr_in_psr = cpr[both]
    print(f"  CPR in PSR zones  : mean={cpr_in_psr.mean():.3f}  max={cpr_in_psr.max():.3f}")
    print(f"  CPR>1.0 in PSR    : {int(np.sum(cpr_in_psr > 1.0)):>10,} px  (possible ice)")

print("\n" + "=" * 60)
