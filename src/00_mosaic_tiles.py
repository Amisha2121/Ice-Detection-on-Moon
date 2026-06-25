"""
00_mosaic_tiles.py

Mosaics all available calibrated DFSAR CP (lh/lv) images into a single
regional Pseudo-Stokes GeoTIFF for ice detection.

Handles:
  - GRI  (Ground Range Image)  — single-band float, preferred
  - SRI  (Slant Range Image)   — single-band float
  - SLI  (Single Look Image)   — 2-band complex, SKIPPED
  - Decomposition (odd/evn/vol/hlx) — 1-band float from ndxl products
"""

import os
import glob
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.io import MemoryFile
import sys

sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import reproject_to_lunar_polar

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DFSAR = os.path.join(ROOT, "data", "raw", "dfsar")
PROCESSED = os.path.join(ROOT, "data", "processed")
RES       = 20.0   # 20 m/pixel — good balance of detail vs. memory


def find_best_cp_files():
    """
    Find the best LH and LV calibrated product per orbit.
    Priority: GRI > SRI > SLI (skip SLI — it's complex 2-band).
    """
    # Collect all cp_lh and cp_lv TIFs
    all_lh = glob.glob(os.path.join(RAW_DFSAR, "**", "*cp_lh*.tif"), recursive=True)
    all_lv = glob.glob(os.path.join(RAW_DFSAR, "**", "*cp_lv*.tif"), recursive=True)

    def filter_and_sort(files):
        # Exclude SLI (complex 2-band), prefer GRI then SRI
        gri = [f for f in files if "_gri_" in f.lower()]
        sri = [f for f in files if "_sri_" in f.lower()]
        rest = [f for f in files if "_gri_" not in f.lower()
                                  and "_sri_" not in f.lower()
                                  and "_sli_" not in f.lower()]
        # Verify each is 1-band before including
        chosen = []
        for f in (gri + sri + rest):
            try:
                with rasterio.open(f) as src:
                    if src.count == 1:
                        chosen.append(f)
                    else:
                        print(f"  [SKIP] {os.path.basename(f)} has {src.count} bands (complex/multi)")
            except Exception as e:
                print(f"  [SKIP] {os.path.basename(f)}: {e}")
        return chosen

    lh_files = filter_and_sort(all_lh)
    lv_files = filter_and_sort(all_lv)
    print(f"  Usable LH files: {len(lh_files)}")
    print(f"  Usable LV files: {len(lv_files)}")
    return lh_files, lv_files


def reproject_to_1band(src_path, out_path, band=1):
    """
    Reproject a single band from src_path to lunar polar CRS at RES m/pixel.
    Writes a guaranteed 1-band GeoTIFF.
    """
    reproject_to_lunar_polar(src_path, out_path, resolution_m=RES)
    # If output somehow ended up multi-band, force to 1-band
    with rasterio.open(out_path) as src:
        if src.count > 1:
            data = src.read(band).astype(np.float32)
            prof = src.profile.copy()
            prof.update(count=1, dtype="float32")
            tmp = out_path + ".tmp.tif"
            with rasterio.open(tmp, "w", **prof) as dst:
                dst.write(data, 1)
            os.replace(tmp, out_path)


def safe_merge(file_list):
    """
    Merge a list of 1-band GeoTIFFs; derive bounds automatically from the data.
    Returns (mosaic_array_2d, transform).
    """
    opened = [rasterio.open(f) for f in file_list]
    try:
        mosaic, transform = merge(opened, nodata=0.0, method="first")
    finally:
        for ds in opened:
            ds.close()
    return mosaic[0].astype(np.float32), transform


def build_mosaic():
    os.makedirs(PROCESSED, exist_ok=True)

    print("=== Step 1: Find calibrated CP TIFs ===")
    lh_files, lv_files = find_best_cp_files()

    if not lh_files or not lv_files:
        print("[ERROR] No usable CP lh/lv files found. Check data/raw/dfsar/")
        return

    print("\n=== Step 2: Reproject to Lunar Polar at 20m ===")
    reproj_lh, reproj_lv = [], []

    for i, f in enumerate(lh_files):
        out = os.path.join(PROCESSED, f"temp_reproj_lh_{i}.tif")
        print(f"  LH {i+1}/{len(lh_files)}: {os.path.basename(f)}")
        reproject_to_1band(f, out)
        reproj_lh.append(out)

    for i, f in enumerate(lv_files):
        out = os.path.join(PROCESSED, f"temp_reproj_lv_{i}.tif")
        print(f"  LV {i+1}/{len(lv_files)}: {os.path.basename(f)}")
        reproject_to_1band(f, out)
        reproj_lv.append(out)

    print("\n=== Step 3: Mosaic ===")
    print("  Merging LH...")
    mosaic_lh, trans_lh = safe_merge(reproj_lh)

    print("  Merging LV...")
    mosaic_lv, trans_lv = safe_merge(reproj_lv)

    print(f"  Mosaic shape: {mosaic_lh.shape}")

    print("\n=== Step 4: Compute Pseudo-Stokes ===")
    LH = mosaic_lh
    LV = mosaic_lv

    S0 = LH**2 + LV**2
    S1 = LH**2 - LV**2
    S2 = np.zeros_like(S0)
    S3 = -S1     # CPR = (S0 - S3) / (S0 + S3) will = LV^2/LH^2

    final_path = os.path.join(PROCESSED, "dfsar_regional_stokes.tif")

    with rasterio.open(reproj_lh[0]) as ref:
        prof = ref.profile.copy()

    prof.update({
        "height":    mosaic_lh.shape[0],
        "width":     mosaic_lh.shape[1],
        "transform": trans_lh,
        "count":     4,
        "dtype":     "float32",
        "compress":  "lzw",
        "nodata":    0.0,
    })

    with rasterio.open(final_path, "w", **prof) as dst:
        dst.write(S1, 1)
        dst.write(S2, 2)
        dst.write(S3, 3)
        dst.write(S0, 4)

    print(f"\n✓ Saved regional Stokes: {final_path}")

    # Report extent
    from rasterio.transform import array_bounds
    h, w = mosaic_lh.shape
    left, bottom, right, top = array_bounds(h, w, trans_lh)
    print(f"  Extent (m): W={left:.0f} E={right:.0f} S={bottom:.0f} N={top:.0f}")
    print(f"  Coverage : {(right-left)/1000:.1f} km × {(top-bottom)/1000:.1f} km")

    # Clean up
    for f in reproj_lh + reproj_lv:
        try: os.remove(f)
        except: pass

    print("\n=== Done! ===")
    return final_path


if __name__ == "__main__":
    build_mosaic()
