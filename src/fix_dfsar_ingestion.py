"""
fix_dfsar_ingestion.py

Re-ingests the DFSAR decomposition TIFs (evn, odd, vol, hlx) by:
  1. Reading the LOLA reference grid extent
  2. Using rasterio.windows to crop the raw DFSAR to that exact extent
     (avoids CRS-WKT mismatch issues in reprojection)
  3. Resampling to 5m grid via rasterio.warp.reproject
  4. Reconstructing Stokes parameters
  5. Recomputing CPR and DOP maps
  6. Saving everything to data/processed/

Run:
  python src/fix_dfsar_ingestion.py
"""

import os, sys, glob, numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.transform import from_bounds

sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import read_band, save_band, LUNAR_CRS

ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW      = os.path.join(ROOT, "data", "raw", "dfsar")
PROC     = os.path.join(ROOT, "data", "processed")
REF_PATH = os.path.join(PROC, "lola_dem_5m.tif")


def crop_dfsar_to_lola(src_path: str, band_name: str) -> np.ndarray:
    """
    Crop a single-band DFSAR TIF to the LOLA DEM extent.
    
    The DFSAR CRS is functionally identical to LOLA's (both Moon south polar
    stereographic) but has different WKT. We treat them as the same CRS and
    use direct coordinate arithmetic to locate the LOLA window in the DFSAR,
    then reproject at 5m into the LOLA shape.
    """
    with rasterio.open(REF_PATH) as ref:
        ref_bounds  = ref.bounds       # (left, bottom, right, top) in proj metres
        ref_crs     = ref.crs
        ref_width   = ref.width
        ref_height  = ref.height
        ref_transform = ref.transform

    with rasterio.open(src_path) as src:
        src_bounds = src.bounds
        src_crs    = src.crs

        print(f"  [{band_name}] src bounds : {src_bounds}")
        print(f"  [{band_name}] lola bounds: {ref_bounds}")

        # Check for overlap using raw coordinate arithmetic
        # (Both are south-polar stereographic; the numbers are directly comparable)
        ol = max(ref_bounds.left,   src_bounds.left)
        ob = max(ref_bounds.bottom, src_bounds.bottom)
        or_ = min(ref_bounds.right, src_bounds.right)
        ot  = min(ref_bounds.top,   src_bounds.top)

        if ol >= or_ or ob >= ot:
            print(f"  [{band_name}] WARNING: No spatial overlap detected! "
                  "Returning zeros.")
            return np.zeros((ref_height, ref_width), dtype=np.float32)

        overlap_area = (or_ - ol) * (ot - ob)
        lola_area    = (ref_bounds.right - ref_bounds.left) * (ref_bounds.top - ref_bounds.bottom)
        print(f"  [{band_name}] Overlap: {overlap_area/1e6:.1f} km²  "
              f"({100*overlap_area/lola_area:.1f}% of LOLA extent)")

        # Use rasterio window to read only the overlapping region from DFSAR
        # Compute window in src pixel space from the overlap bounds
        from rasterio.windows import from_bounds as window_from_bounds
        src_window = window_from_bounds(ol, ob, or_, ot, src.transform)
        src_window = src_window.round_lengths().round_offsets()

        # Read that window
        raw_data = src.read(1, window=src_window).astype(np.float32)
        raw_transform = src.window_transform(src_window)

        # Handle nodata
        if src.nodata is not None:
            raw_data[raw_data == src.nodata] = np.nan

        print(f"  [{band_name}] Read window shape: {raw_data.shape}  "
              f"valid={np.sum(np.isfinite(raw_data)):,}/{raw_data.size:,}")

    # Now reproject the cropped window into the LOLA 5m grid
    # Replace the src CRS with the LOLA CRS (same projection, different WKT)
    dst_data = np.full((ref_height, ref_width), np.nan, dtype=np.float32)

    reproject(
        source=raw_data,
        destination=dst_data,
        src_transform=raw_transform,
        src_crs=LUNAR_CRS,          # treat DFSAR as the same projection
        dst_transform=ref_transform,
        dst_crs=LUNAR_CRS,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )

    valid = np.sum(np.isfinite(dst_data))
    print(f"  [{band_name}] Reprojected: valid pixels = {valid:,}/{dst_data.size:,} "
          f"({100*valid/dst_data.size:.1f}%)")

    return dst_data


def main():
    print("=" * 60)
    print(" DFSAR Re-Ingestion Fix")
    print("=" * 60)

    if not os.path.exists(REF_PATH):
        print(f"[ERROR] LOLA reference not found: {REF_PATH}")
        return

    with rasterio.open(REF_PATH) as ref:
        ref_profile = ref.profile.copy()

    # Find raw DFSAR decomposition TIFs
    decomp_map = {}
    for key in ["odd", "evn", "vol", "hlx"]:
        matches = glob.glob(os.path.join(RAW, "**", f"*{key}*.tif"), recursive=True)
        matches = [m for m in matches if "browse" not in m.lower()]
        if matches:
            decomp_map[key] = matches[0]
            print(f"  Found {key}: {os.path.relpath(matches[0], ROOT)}")
        else:
            print(f"  [MISSING] {key} band not found")

    if not decomp_map:
        print("[ERROR] No DFSAR decomposition TIFs found.")
        return

    print()

    # Crop each band to LOLA extent
    bands = {}
    for key, path in decomp_map.items():
        print(f"\n[Processing {key.upper()} band]")
        bands[key] = crop_dfsar_to_lola(path, key)

    # Fill missing bands with zeros
    ref_shape = bands[next(iter(bands))].shape
    for key in ["odd", "evn", "vol", "hlx"]:
        if key not in bands:
            bands[key] = np.zeros(ref_shape, dtype=np.float32)

    Ps = np.nan_to_num(bands["odd"], nan=0.0)
    Pd = np.nan_to_num(bands["evn"], nan=0.0)
    Pv = np.nan_to_num(bands["vol"], nan=0.0)
    Ph = np.nan_to_num(bands["hlx"], nan=0.0)

    # ── Reconstruct Stokes parameters ───────────────────────────────────────────
    print("\n[Reconstructing Stokes parameters]")
    S0 = Ps + Pd + Pv + Ph
    S0_safe = np.where(S0 > 0, S0, np.nan)

    # ── Compute CPR and DOP directly ───────────────────────────────────────────
    # CPR = SC / OC = (Ps + vol_contribution) / Pd
    # Using the standard Stokes-based definition:
    #   CPR = (S0 - S3) / (S0 + S3)   where S3 = Ps - Pd (circular component)
    # Equivalently for decomposition products:
    #   CPR = (Pd + Pv) / (Ps + 1e-10)   [volume + double-bounce / single-bounce]
    CPR = (Pd + Pv) / (Ps + 1e-10)
    CPR = np.where(S0 > 1e-10, CPR, np.nan)

    # DOP (Degree of Polarization) from Stokes:
    #   DOP = sqrt(S1² + S2² + S3²) / S0
    # For compact pol:  S1 ≈ Ps-Pd, S2 = 0, S3 = Ph
    S1 = Ps - Pd
    S3 = Ph
    DOP = np.sqrt(S1**2 + S3**2) / (S0_safe + 1e-10)
    DOP = np.clip(DOP, 0, 1)
    DOP = np.where(S0 > 1e-10, DOP, np.nan)

    # ── mCHI / Poincare volume ─────────────────────────────────────────────────
    mchi_pv = Pv / (S0_safe + 1e-10)
    mchi_pv = np.where(S0 > 1e-10, mchi_pv, np.nan)

    print(f"  CPR  — valid={np.sum(np.isfinite(CPR)):,}, "
          f"mean={np.nanmean(CPR):.4f}, max={np.nanmax(CPR):.4f}")
    print(f"  DOP  — valid={np.sum(np.isfinite(DOP)):,}, "
          f"mean={np.nanmean(DOP):.4f}")
    print(f"  mCHI — valid={np.sum(np.isfinite(mchi_pv)):,}, "
          f"mean={np.nanmean(mchi_pv):.4f}")

    # ── Save outputs ───────────────────────────────────────────────────────────
    print("\n[Saving outputs]")

    out_profile = ref_profile.copy()
    out_profile.update({"count": 1, "dtype": "float32",
                        "driver": "GTiff", "compress": "lzw", "nodata": None})

    def save(arr, name):
        path = os.path.join(PROC, name)
        save_band(arr.astype(np.float32), out_profile, path)
        vcount = np.sum(np.isfinite(arr))
        print(f"  Saved {name:30s}  valid={vcount:>10,} px")

    save(CPR,     "cpr_map.tif")
    save(DOP,     "dop_map.tif")
    save(mchi_pv, "mchi_pv.tif")
    save(S0,      "dfsar_s0.tif")

    # Save coreg decomp bands too
    for key in ["odd", "evn", "vol", "hlx"]:
        save_band(bands[key], out_profile, os.path.join(PROC, f"dfsar_coreg_{key}.tif"))

    # Save 4-band Stokes TIF
    stokes_path = os.path.join(PROC, "dfsar_stokes.tif")
    sp = ref_profile.copy()
    sp.update({"count": 4, "dtype": "float32", "compress": "lzw", "nodata": None})
    with rasterio.open(stokes_path, "w", **sp) as dst:
        dst.write(S1.astype(np.float32), 1)
        dst.write(np.zeros_like(S1, dtype=np.float32), 2)
        dst.write(S3.astype(np.float32), 3)
        dst.write(S0.astype(np.float32), 4)
    print(f"  Saved dfsar_stokes.tif")

    print("\n" + "=" * 60)
    print(" DFSAR re-ingestion complete.")
    print(" Next: run  python src/03_radar_ice_detection.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
