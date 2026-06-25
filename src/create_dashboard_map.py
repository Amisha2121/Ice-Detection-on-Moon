"""
create_dashboard_map.py

Creates two key PNG images for the dashboard:
1. global_basemap.png  — full south-polar context (±3000 km), real Clementine data
2. dem_hillshade.png   — 5m LOLA DEM hillshade of the Shackleton 16km tile, real data

These are exported to dashboard/data/overlays/
"""

import os, json
import numpy as np
import cv2
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from scipy.ndimage import uniform_filter

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC     = os.path.join(ROOT, "data", "processed")
RAW_LOLA = os.path.join(ROOT, "data", "raw", "lola")
SRC_IMG  = os.path.join(ROOT, "moon_global.png")
OUT_DIR  = os.path.join(ROOT, "dashboard", "data", "overlays")
os.makedirs(OUT_DIR, exist_ok=True)

# South Pole Stereographic CRS
MOON_CRS   = "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=1737400 +b=1737400 +units=m +no_defs"
MOON_LONLAT= "+proj=longlat +a=1737400 +b=1737400 +no_defs"

# ── 1. Global Basemap ─────────────────────────────────────────────────────────
def create_global_basemap(out_path, radius_km=2500, size=(2048, 2048)):
    """
    Reproject the Clementine global equirectangular Moon map to
    South Pole Stereographic. Produces a greyscale PNG covering ±radius_km.
    """
    if not os.path.exists(SRC_IMG):
        print(f"  [SKIP] {SRC_IMG} not found.")
        return

    print(f"  Reading Clementine global map …")
    img = cv2.imread(SRC_IMG, cv2.IMREAD_COLOR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, c = img.shape

    radius = radius_km * 1000.0
    dst_bounds    = (-radius, -radius, radius, radius)
    dst_transform = from_bounds(*dst_bounds, size[1], size[0])

    src_transform = from_bounds(-180, -90, 180, 90, w, h)

    dst_bands = np.zeros((c, size[0], size[1]), dtype=np.uint8)
    print(f"  Reprojecting {w}×{h} → {size[1]}×{size[0]} …")
    for b in range(c):
        reproject(
            source=img[:, :, b],
            destination=dst_bands[b],
            src_transform=src_transform,
            src_crs=MOON_LONLAT,
            dst_transform=dst_transform,
            dst_crs=MOON_CRS,
            resampling=Resampling.bilinear,
        )

    out = np.dstack([dst_bands[0], dst_bands[1], dst_bands[2]])
    out = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)

    # Make outside-moon area dark space color
    mask_black = np.all(out == [0, 0, 0], axis=-1)
    out[mask_black] = [8, 10, 14]

    # Apply mild contrast stretch
    grey = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    p2, p98 = np.percentile(grey[grey > 14], [2, 98])
    out_f = (out.astype(np.float32) - p2) / (p98 - p2 + 1e-5)
    out_u = np.clip(out_f * 255, 0, 255).astype(np.uint8)
    out_u[mask_black] = [8, 10, 14]

    cv2.imwrite(out_path, out_u)
    print(f"  ✓ global_basemap.png  ({os.path.getsize(out_path)//1024} KB)")
    return (-radius, -radius, radius, radius)


# ── 2. DEM Hillshade ─────────────────────────────────────────────────────────
def create_dem_hillshade(dem_path, out_path, size=(1024, 1024)):
    """
    Render a hillshaded version of the LOLA DEM at maximum quality.
    Uses the Sun angle approximation for the south polar region (~1.5° above horizon).
    """
    with rasterio.open(dem_path) as ds:
        dem   = ds.read(1).astype(np.float32)
        prof  = ds.profile
        bounds = ds.bounds
        px_m  = abs(ds.transform.a)

    # Fill nodata
    nodata = prof.get("nodata", None)
    if nodata is not None:
        dem[dem == nodata] = np.nan
    # Simple linear interpolation for small NaN holes
    from scipy.ndimage import uniform_filter, generic_filter
    mask = np.isnan(dem)
    if mask.any():
        # Fill with local mean
        dem_filled = dem.copy()
        dem_filled[mask] = 0.0
        local_mean = uniform_filter(dem_filled, size=5)
        dem[mask] = local_mean[mask]

    # Sobel gradients
    dz_dx = cv2.Sobel(dem, cv2.CV_64F, 1, 0, ksize=3) / (8 * px_m)
    dz_dy = cv2.Sobel(dem, cv2.CV_64F, 0, 1, ksize=3) / (8 * px_m)

    # Sun at 1.5° above horizon, azimuth 315°
    sun_alt = 1.5 * np.pi / 180
    sun_az  = 315.0 * np.pi / 180

    lx = -np.sin(sun_az) * np.cos(sun_alt)
    ly = -np.cos(sun_az) * np.cos(sun_alt)
    lz =  np.sin(sun_alt)

    # Surface normal
    norm = np.sqrt(dz_dx**2 + dz_dy**2 + 1.0)
    nx = -dz_dx / norm
    ny = -dz_dy / norm
    nz =  1.0   / norm

    hillshade = (lx * nx + ly * ny + lz * nz)
    hillshade = np.clip(hillshade, 0, 1)

    # Scale to uint8
    hs_u8 = (hillshade * 255).astype(np.uint8)

    # Resize to target size
    hs_resized = cv2.resize(hs_u8, (size[1], size[0]), interpolation=cv2.INTER_LINEAR)

    # Apply a subtle blue-grey tint for a "lunar" look
    b = np.clip(hs_resized.astype(np.float32) * 0.75, 0, 255).astype(np.uint8)
    g = np.clip(hs_resized.astype(np.float32) * 0.80, 0, 255).astype(np.uint8)
    r = hs_resized
    out_bgr = cv2.merge([b, g, r])

    cv2.imwrite(out_path, out_bgr)
    print(f"  ✓ dem_hillshade.png  ({os.path.getsize(out_path)//1024} KB)")
    return bounds


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print(" Dashboard Map Builder")
    print("=" * 55)

    # Global basemap
    print("\n[1/2] Building global basemap …")
    g_out = os.path.join(OUT_DIR, "global_basemap.png")
    g_bounds = create_global_basemap(g_out, radius_km=2500, size=(2048, 2048))
    if g_bounds is None:
        g_bounds = (-2500000, -2500000, 2500000, 2500000)

    # DEM hillshade (overwrite existing)
    print("\n[2/2] Building DEM hillshade …")
    dem_path = os.path.join(PROC, "lola_dem_5m.tif")
    if not os.path.exists(dem_path):
        print(f"  [ERROR] {dem_path} not found.")
        return

    hs_out  = os.path.join(OUT_DIR, "dem_hillshade.png")
    l_bounds = create_dem_hillshade(dem_path, hs_out)

    # Update meta.json
    meta_path = os.path.join(OUT_DIR, "meta.json")
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception:
        meta = {}

    meta["bounds"] = {
        "west":  l_bounds.left,
        "south": l_bounds.bottom,
        "east":  l_bounds.right,
        "north": l_bounds.top,
    }
    meta["global_basemap"] = {
        "west":  g_bounds[0],
        "south": g_bounds[1],
        "east":  g_bounds[2],
        "north": g_bounds[3],
    }
    with open(meta_path, "w", encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    print(f"\n  ✓ meta.json updated")

    print("\n" + "=" * 55)
    print(f"  Local DEM  : W={l_bounds.left:.0f} S={l_bounds.bottom:.0f} E={l_bounds.right:.0f} N={l_bounds.top:.0f} m")
    print(f"  Global map : ±{abs(g_bounds[0])/1000:.0f} km radius")
    print("=" * 55)


if __name__ == "__main__":
    main()
