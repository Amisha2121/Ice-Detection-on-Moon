"""
generate_map_overlays.py
Converts key pipeline rasters (TIF) into PNG images for use as
Leaflet image overlays in the dashboard (no external tile server needed).

Outputs go to dashboard/data/overlays/
"""

import os
import json
import numpy as np
import rasterio
from rasterio.enums import Resampling
from PIL import Image

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC      = os.path.join(ROOT, "data", "processed")
OUT_DIR   = os.path.join(ROOT, "dashboard", "data", "overlays")
os.makedirs(OUT_DIR, exist_ok=True)

TARGET_SIZE = (1024, 1024)   # dashboard overlay resolution

# ── helpers ──────────────────────────────────────────────────────────────────

def load_band(path, band=1, target_size=TARGET_SIZE):
    with rasterio.open(path) as ds:
        data = ds.read(
            band,
            out_shape=(target_size[1], target_size[0]),
            resampling=Resampling.average,
        ).astype(np.float32)
        bounds = ds.bounds
        crs    = ds.crs
    return data, bounds, crs


def norm(arr, lo=None, hi=None):
    lo = np.nanpercentile(arr, 2) if lo is None else lo
    hi = np.nanpercentile(arr, 98) if hi is None else hi
    out = np.clip((arr - lo) / (hi - lo + 1e-9), 0, 1)
    return out


def apply_colormap(norm_arr, colormap):
    """colormap: list of (r,g,b) tuples, 256 entries."""
    idx = (norm_arr * 255).astype(np.uint8)
    cm  = np.array(colormap, dtype=np.uint8)
    rgb = cm[idx]
    return rgb


def turbo_lut():
    """Turbo colormap approximation (256 entries)."""
    t = np.linspace(0, 1, 256)
    r = (0.1357 + t * (4.5974 - t * (42.2  - t * (130.  - t * (150. - t * 58.1))))).clip(0,1)
    g = (0.0914 + t * (2.1856 + t * (4.8052 - t * (14.07 + t * (4.098 - t * 2.194))))).clip(0,1)
    b = (0.1067 + t * (7.456  - t * (43.07  + t * (104.7 - t * (106.5 - t * 37.5))))).clip(0,1)
    return [(int(R*255), int(G*255), int(B*255)) for R,G,B in zip(r,g,b)]


def plasma_lut():
    """Plasma colormap approximation (256 entries)."""
    t = np.linspace(0, 1, 256)
    r = (0.050 + t * (2.74  - t * 1.64)).clip(0,1)
    g = (0.030 + t * (0.15  + t * (2.63 - t * 3.09))).clip(0,1)
    b = (0.527 + t * (1.04  - t * 2.41)).clip(0,1)
    return [(int(R*255), int(G*255), int(B*255)) for R,G,B in zip(r,g,b)]


def save_png(rgb_arr, alpha_arr, out_path):
    """rgb_arr: HxWx3 uint8, alpha_arr: HxW uint8"""
    rgba = np.dstack([rgb_arr, alpha_arr])
    img  = Image.fromarray(rgba, mode="RGBA")
    img.save(out_path, optimize=True)
    kb = os.path.getsize(out_path) / 1024
    print(f"  ✓ {os.path.basename(out_path)}  ({kb:.0f} KB)")


TURBO  = turbo_lut()
PLASMA = plasma_lut()

# ── Layer 1: Moon DEM (greyscale hillshade) ──────────────────────────────────
print("Generating DEM hillshade …")
dem, bounds, crs = load_band(os.path.join(PROC, "lola_dem_5m.tif"))

# Simple hillshade
from scipy.ndimage import uniform_filter
smoothed = uniform_filter(dem, size=3)
gy, gx = np.gradient(smoothed)
slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
aspect    = np.arctan2(-gx, gy)
sun_az, sun_el = np.radians(315), np.radians(45)
hs = (np.cos(sun_el) * np.cos(slope_rad) +
      np.sin(sun_el) * np.sin(slope_rad) * np.cos(sun_az - aspect))
hs = np.clip(hs, 0, 1)

# Blend with elevation tint (blue-grey for moon)
elev_n = norm(dem)
r_ch = (hs * 0.5 * 255).astype(np.uint8)
g_ch = (hs * 0.55 * 255).astype(np.uint8)
b_ch = (hs * 0.7 * 255).astype(np.uint8)
rgb  = np.dstack([r_ch, g_ch, b_ch])
alpha = np.full(dem.shape, 230, dtype=np.uint8)
save_png(rgb, alpha, os.path.join(OUT_DIR, "dem_hillshade.png"))

# ── Layer 2: Illumination / PSR ───────────────────────────────────────────────
print("Generating illumination overlay …")
illum, *_ = load_band(os.path.join(PROC, "illumination_fraction.tif"))
# PSR (dark) → blue; lit → transparent
r_i = np.zeros_like(illum, dtype=np.uint8)
g_i = np.zeros_like(illum, dtype=np.uint8)
b_i = np.full_like(illum, 180, dtype=np.uint8)
alpha_i = ((1 - np.nan_to_num(illum)) * 200).astype(np.uint8)  # dark = opaque blue
rgb_i = np.dstack([r_i, g_i, b_i])
save_png(rgb_i, alpha_i, os.path.join(OUT_DIR, "psr_overlay.png"))

# ── Layer 3: Slope map ────────────────────────────────────────────────────────
print("Generating slope overlay …")
slope, *_ = load_band(os.path.join(PROC, "slope_map.tif"))
sn = norm(slope, 0, 40)
rgb_s  = apply_colormap(sn, PLASMA)
alpha_s = np.full(slope.shape, 180, dtype=np.uint8)
alpha_s[np.isnan(slope)] = 0
save_png(rgb_s, alpha_s, os.path.join(OUT_DIR, "slope_overlay.png"))

# ── Layer 4: Ice probability ──────────────────────────────────────────────────
print("Generating ice probability overlay …")
ice_p, *_ = load_band(os.path.join(PROC, "ice_probability.tif"))
rgb_ip  = apply_colormap(norm(ice_p, 0, 1), TURBO)
# Only show pixels with ice_prob > 0.1 (transparent elsewhere)
alpha_ip = np.where(np.nan_to_num(ice_p) > 0.1,
                    (np.nan_to_num(ice_p) * 230).astype(np.uint8), 0)
save_png(rgb_ip, alpha_ip, os.path.join(OUT_DIR, "ice_prob_overlay.png"))

# ── Layer 5: CPR map ──────────────────────────────────────────────────────────
print("Generating CPR overlay …")
cpr, *_ = load_band(os.path.join(PROC, "cpr_map.tif"))
rgb_cpr  = apply_colormap(norm(cpr, 0.3, 1.5), TURBO)
alpha_cpr = np.where(np.isnan(cpr), 0, 180).astype(np.uint8)
save_png(rgb_cpr, alpha_cpr, os.path.join(OUT_DIR, "cpr_overlay.png"))

# ── Layer 6: Hazard score ─────────────────────────────────────────────────────
print("Generating hazard overlay …")
haz, *_ = load_band(os.path.join(PROC, "hazard_score.tif"))
# Red = high hazard; transparent = safe
r_h = (np.nan_to_num(haz) * 255).astype(np.uint8)
g_h = ((1 - np.nan_to_num(haz)) * 50).astype(np.uint8)
b_h = np.zeros_like(haz, dtype=np.uint8)
alpha_h = np.where(np.nan_to_num(haz) > 0.3, 160, 0).astype(np.uint8)
rgb_h = np.dstack([r_h, g_h, b_h])
save_png(rgb_h, alpha_h, os.path.join(OUT_DIR, "hazard_overlay.png"))

# ── Save bounds metadata ──────────────────────────────────────────────────────
print("Writing bounds metadata …")
meta = {
    "bounds": {
        "west": bounds.left,
        "south": bounds.bottom,
        "east": bounds.right,
        "north": bounds.top
    },
    "crs": "EPSG:32761 (Lunar South Pole Stereographic)",
    "global_basemap": {
        "west": -3000000.0,
        "south": -3000000.0,
        "east": 3000000.0,
        "north": 3000000.0
    },
    "size":   list(TARGET_SIZE),
    "overlays": [
        "dem_hillshade.png",
        "psr_overlay.png",
        "slope_overlay.png",
        "ice_prob_overlay.png",
        "cpr_overlay.png",
        "hazard_overlay.png",
    ]
}
with open(os.path.join(OUT_DIR, "meta.json"), "w") as f:
    json.dump(meta, f, indent=2)
print("  ✓ meta.json")

print("\nAll overlays written to dashboard/data/overlays/")
print(f"Bounds: W={bounds.left:.4f} S={bounds.bottom:.4f} E={bounds.right:.4f} N={bounds.top:.4f}")
