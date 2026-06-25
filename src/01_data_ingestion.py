"""
01_data_ingestion.py

Step 1 of the Lunar Ice Pipeline:
  - Load real DFSAR SRI GeoTIFF products (PDS4/XML label)
  - Load real OHRC calibrated imagery
  - Load LOLA 5m DEM (Cloud-Optimized GeoTIFF)
  - Reproject everything to Lunar South Polar Stereographic
  - Co-register all layers to the LOLA DEM grid
  - Save processed layers to data/processed/

Usage:
  python src/01_data_ingestion.py

Expects:
  data/raw/dfsar/   → DFSAR SRI GeoTIFFs or XML labels
  data/raw/ohrc/    → OHRC CAL.img or CAL.xml
  data/raw/lola/    → LOLA 5m DEM GeoTIFF
"""

import os
import sys
import glob
import numpy as np
import rasterio
from rasterio.merge import merge
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from utils.geo_utils import (reproject_to_lunar_polar, coregister_to_reference,
                               read_band, save_band, LUNAR_CRS)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DFSAR  = os.path.join(ROOT, "data", "raw", "dfsar")
RAW_OHRC   = os.path.join(ROOT, "data", "raw", "ohrc")
RAW_LOLA   = os.path.join(ROOT, "data", "raw", "lola")
PROCESSED  = os.path.join(ROOT, "data", "processed")

os.makedirs(PROCESSED, exist_ok=True)


def find_dfsar_products(directory: str) -> list:
    """
    Scan the DFSAR directory for raw or derived products.
    Prefers XML label files (PDS4) if present; falls back to direct .tif.
    """
    xml_files = list(set(glob.glob(os.path.join(directory, "**", "*.xml"), recursive=True) +
                         glob.glob(os.path.join(directory, "**", "*.XML"), recursive=True)))
    tif_files = list(set(glob.glob(os.path.join(directory, "**", "*.tif"), recursive=True) +
                         glob.glob(os.path.join(directory, "**", "*.TIF"), recursive=True)))

    # Filter out browse, miscellaneous, geometry, or aux files
    xml_files = [f for f in xml_files if "browse" not in f.lower() and "miscellaneous" not in f.lower() and "geometry" not in f.lower() and ".aux" not in f.lower()]
    tif_files = [f for f in tif_files if "browse" not in f.lower() and "miscellaneous" not in f.lower() and "geometry" not in f.lower() and ".aux" not in f.lower()]

    # Filter/prioritize files containing 'SRI' or 'cp' (circular polarimetry)
    sri_xml = [f for f in xml_files if "SRI" in f or "cp" in f]
    sri_tif = [f for f in tif_files if "SRI" in f or "cp" in f]

    products = []
    if sri_xml:
        products = sri_xml
    elif xml_files:
        products = xml_files
    elif sri_tif:
        products = sri_tif
    else:
        products = tif_files

    if not products:
        print(f"  [WARNING] No DFSAR products found in {directory}")
        print("  Download from: https://pradan.issdc.gov.in/ch2/ → SAR")
    else:
        print(f"  Found {len(products)} DFSAR product(s).")

    return products


def find_ohrc_products(directory: str) -> list:
    """Scan OHRC directory for calibrated products."""
    xml_files = list(set(glob.glob(os.path.join(directory, "**", "*.xml"), recursive=True) +
                         glob.glob(os.path.join(directory, "**", "*.XML"), recursive=True)))
    img_files = list(set(glob.glob(os.path.join(directory, "**", "*.img"), recursive=True) +
                         glob.glob(os.path.join(directory, "**", "*.IMG"), recursive=True)))
    tif_files = list(set(glob.glob(os.path.join(directory, "**", "*.tif"), recursive=True) +
                         glob.glob(os.path.join(directory, "**", "*.TIF"), recursive=True)))

    # Filter out browse, miscellaneous, geometry, or aux files
    xml_files = [f for f in xml_files if "browse" not in f.lower() and "miscellaneous" not in f.lower() and "geometry" not in f.lower() and ".aux" not in f.lower()]
    img_files = [f for f in img_files if "browse" not in f.lower() and "miscellaneous" not in f.lower() and "geometry" not in f.lower() and ".aux" not in f.lower()]
    tif_files = [f for f in tif_files if "browse" not in f.lower() and "miscellaneous" not in f.lower() and "geometry" not in f.lower() and ".aux" not in f.lower()]

    # Filter out metadata files that aren't PDS labels if we have many
    # For OHRC, we want the XML descriptor or direct IMG/TIF
    products = []
    if xml_files:
        products = xml_files
    elif img_files:
        products = img_files
    else:
        products = tif_files

    if not products:
        print(f"  [WARNING] No OHRC products found in {directory}")
        print("  Download from: https://pradan.issdc.gov.in/ch2/ → OHRC")
    else:
        print(f"  Found {len(products)} OHRC product(s).")
    return products


def find_lola_dem(directory: str) -> str | None:
    """Find the LOLA DEM GeoTIFF."""
    candidates = list(set(glob.glob(os.path.join(directory, "**", "*.tif"), recursive=True) +
                          glob.glob(os.path.join(directory, "**", "*.TIF"), recursive=True)))
    if not candidates:
        print(f"  [WARNING] No LOLA DEM found in {directory}")
        print("  Download from: https://pgda.gsfc.nasa.gov/products/78")
        return None
    # Prefer files with 'dem' or 'ldem' in name
    for c in candidates:
        if any(k in c.lower() for k in ["ldem", "dem", "lola"]):
            return c
    return candidates[0]


def read_dfsar_stokes_bands(product_path: str) -> dict | None:
    """
    Open a DFSAR SRI product and return all 4 Stokes bands.
    The product may be opened via its XML label or directly as GeoTIFF.

    Returns dict: {'S0', 'S1', 'S2', 'S3', 'profile'} or None on error.
    """
    try:
        with rasterio.open(product_path) as src:
            print(f"    Bands: {src.count}, CRS: {src.crs}, Shape: {src.shape}")
            if src.count < 4:
                print(f"    [WARNING] Only {src.count} band(s) found. "
                      "Need 4 Stokes bands. Check product type.")
                return None
            bands = src.read([1, 2, 3, 4]).astype(np.float32)
            profile = src.profile.copy()
        return {
            "S1": bands[0], "S2": bands[1],
            "S3": bands[2], "S0": bands[3],
            "profile": profile
        }
    except Exception as e:
        print(f"    [ERROR] Could not open {product_path}: {e}")
        return None


def mosaic_dfsar_products(products: list) -> tuple:
    """
    If multiple DFSAR passes downloaded, mosaic them into a single set
    of Stokes band arrays using average blending in overlap regions.

    Returns (S0, S1, S2, S3, reference_profile)
    """
    from rasterio.merge import merge
    from rasterio.io import MemoryFile

    print(f"  Mosaicking {len(products)} DFSAR products...")
    band_datasets = {b: [] for b in range(1, 5)}

    for p in products:
        try:
            ds = rasterio.open(p)
            if ds.count >= 4:
                for b in range(1, 5):
                    band_datasets[b].append(ds)
        except Exception as e:
            print(f"    [SKIP] {p}: {e}")

    if not band_datasets[1]:
        return None

    # Merge each band separately
    merged_bands = {}
    ref_profile = None
    for b in range(1, 5):
        if band_datasets[b]:
            mosaic, transform = merge(band_datasets[b], indexes=[b],
                                       method="first")
            merged_bands[b] = mosaic[0].astype(np.float32)
            if ref_profile is None:
                ref_profile = band_datasets[b][0].profile.copy()
                ref_profile.update({"transform": transform,
                                     "width": mosaic.shape[2],
                                     "height": mosaic.shape[1]})

    return (merged_bands.get(4), merged_bands.get(1),
            merged_bands.get(2), merged_bands.get(3), ref_profile)


def ingest_lola_dem(lola_path: str, out_path: str) -> str:
    """Reproject LOLA DEM to lunar polar CRS at 5m resolution."""
    print(f"\n[LOLA DEM] Reprojecting: {os.path.basename(lola_path)}")
    reproject_to_lunar_polar(lola_path, out_path, resolution_m=5.0)
    print(f"  Saved: {out_path}")
    return out_path


def ingest_dfsar(products: list, ref_path: str) -> str | None:
    """
    Process DFSAR products:
    1. Detects standard 4-band Stokes or separate decomposition files (odd, evn, vol, hlx)
    2. Reprojects each to lunar polar CRS
    3. Co-registers to LOLA DEM grid
    4. Combines/mosaics to produce a standard 4-band Stokes GeoTIFF (data/processed/dfsar_stokes.tif)
    """
    if not products:
        return None

    # Check if these are separate derived decomposition files
    decomp_types = {"odd": None, "evn": None, "vol": None, "hlx": None}
    for k in decomp_types.keys():
        matches = glob.glob(os.path.join(RAW_DFSAR, "**", f"*{k}*.tif"), recursive=True)
        matches += glob.glob(os.path.join(RAW_DFSAR, "**", f"*{k.upper()}*.TIF"), recursive=True)
        if matches:
            decomp_types[k] = matches[0]

    is_decomp = any(v is not None for v in decomp_types.values())

    if is_decomp:
        print("\n[DFSAR] Processing derived decomposition products...")
        coreg_paths = {}
        for k, p in decomp_types.items():
            if p is not None:
                reproj_out = os.path.join(PROCESSED, f"dfsar_reproj_{k}.tif")
                coreg_out = os.path.join(PROCESSED, f"dfsar_coreg_{k}.tif")
                print(f"  Processing {k.upper()} band: {os.path.basename(p)}")
                reproject_to_lunar_polar(p, reproj_out, resolution_m=5.0, ref_path=ref_path)
                coregister_to_reference(reproj_out, ref_path, coreg_out)
                coreg_paths[k] = coreg_out

        # Read coregistered bands
        with rasterio.open(ref_path) as ref:
            ref_profile = ref.profile.copy()
            shape = (ref.height, ref.width)

        data_bands = {}
        for k in ["odd", "evn", "vol", "hlx"]:
            if k in coreg_paths:
                with rasterio.open(coreg_paths[k]) as src:
                    data_bands[k] = src.read(1).astype(np.float32)
                    # Replace nodata/negative with 0
                    if src.nodata is not None:
                        data_bands[k][data_bands[k] == src.nodata] = 0.0
                    data_bands[k] = np.nan_to_num(data_bands[k], nan=0.0)
                    data_bands[k] = np.clip(data_bands[k], 0.0, None)
            else:
                data_bands[k] = np.zeros(shape, dtype=np.float32)

        Ps = data_bands["odd"]
        Pd = data_bands["evn"]
        Pv = data_bands["vol"]
        Ph = data_bands["hlx"]

        # Reconstruct consistent 4 Stokes parameters:
        # Band 4 (S0) = total power = Ps + Pd + Pv + Ph
        # Band 3 (S3) = circular component: S3 = Ps - Pd - Pv (so CPR = (Pd + Pv)/Ps is high for volume/double bounce)
        # Band 1 (S1) = linear component: S1 = sqrt(clip((S0 * m)^2 - S3^2, 0))
        # Band 2 (S2) = 0.0
        # where m = clip(1.0 - Pv / (S0 + 1e-12), 0, 1)
        S0 = Ps + Pd + Pv + Ph
        S0_safe = S0 + 1e-12
        m = np.clip(1.0 - Pv / S0_safe, 0.0, 1.0)
        S3 = Ps - Pd - Pv
        # Clamp S3 to satisfy Stokes inequality: |S3| <= S0 * m
        S3 = np.clip(S3, -S0 * m, S0 * m)
        S1 = np.sqrt(np.clip((S0 * m)**2 - S3**2, 0.0, None))
        S2 = np.zeros_like(S0)

        final_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
        ref_profile.update({"count": 4, "dtype": "float32", "compress": "lzw", "nodata": None})
        with rasterio.open(final_path, "w", **ref_profile) as dst:
            dst.write(S1, 1)  # S1
            dst.write(S2, 2)  # S2
            dst.write(S3, 3)  # S3
            dst.write(S0, 4)  # S0

        print(f"  Reconstructed Stokes parameters saved to: {final_path}")
        return final_path

    # Check if these are Compact Polarimetry (CP) files (lh, lv)
    cp_types = {"lh": None, "lv": None}
    for k in cp_types.keys():
        matches = glob.glob(os.path.join(RAW_DFSAR, "**", f"*cp_{k}*.tif"), recursive=True)
        if matches:
            cp_types[k] = matches[0]

    if cp_types["lh"] is not None and cp_types["lv"] is not None:
        print("\n[DFSAR] Processing Compact Polarimetry (CP) products...")
        coreg_paths = {}
        for k, p in cp_types.items():
            reproj_out = os.path.join(PROCESSED, f"dfsar_reproj_cp_{k}.tif")
            coreg_out = os.path.join(PROCESSED, f"dfsar_coreg_cp_{k}.tif")
            print(f"  Processing CP {k.upper()} band: {os.path.basename(p)}")
            reproject_to_lunar_polar(p, reproj_out, resolution_m=5.0, ref_path=ref_path)
            coregister_to_reference(reproj_out, ref_path, coreg_out)
            coreg_paths[k] = coreg_out

        with rasterio.open(ref_path) as ref:
            ref_profile = ref.profile.copy()
            shape = (ref.height, ref.width)

        data_bands = {}
        for k in ["lh", "lv"]:
            with rasterio.open(coreg_paths[k]) as src:
                data = src.read(1).astype(np.float32)
                if src.nodata is not None:
                    data[data == src.nodata] = 0.0
                data_bands[k] = np.nan_to_num(data, nan=0.0)

        # Convert amplitude to pseudo-Stokes
        # S0 = LH^2 + LV^2
        # S1 = LH^2 - LV^2
        # S2 = 0
        # S3 = LV^2 - LH^2 = -S1 (so CPR = (S0-S3)/(S0+S3) = LH^2/LV^2)
        LH = data_bands["lh"]
        LV = data_bands["lv"]
        S0 = LH**2 + LV**2
        S1 = LH**2 - LV**2
        S2 = np.zeros_like(S0)
        S3 = -S1

        final_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
        ref_profile.update({"count": 4, "dtype": "float32", "compress": "lzw", "nodata": None})
        with rasterio.open(final_path, "w", **ref_profile) as dst:
            dst.write(S1, 1)
            dst.write(S2, 2)
            dst.write(S3, 3)
            dst.write(S0, 4)

        print(f"  Reconstructed CP pseudo-Stokes parameters saved to: {final_path}")
        return final_path

    else:
        print(f"\n[DFSAR] Processing {len(products)} standard product(s)...")

        reproj_paths = []
        for i, p in enumerate(products):
            out = os.path.join(PROCESSED, f"dfsar_reproj_{i}.tif")
            print(f"  Reprojecting: {os.path.basename(p)}")
            reproject_to_lunar_polar(p, out, resolution_m=5.0, ref_path=ref_path)
            reproj_paths.append(out)

        # Co-register to LOLA DEM
        coreg_paths = []
        for i, p in enumerate(reproj_paths):
            out = os.path.join(PROCESSED, f"dfsar_coreg_{i}.tif")
            print(f"  Co-registering to LOLA grid: {os.path.basename(p)}")
            coregister_to_reference(p, ref_path, out)
            coreg_paths.append(out)

        # Mosaic if multiple passes
        if len(coreg_paths) == 1:
            import shutil
            final_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
            shutil.copy(coreg_paths[0], final_path)
        else:
            # Simple mosaic: take first pixel in overlap regions
            final_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
            from rasterio.merge import merge
            datasets = [rasterio.open(p) for p in coreg_paths]
            mosaic, transform = merge(datasets, method="first")
            profile = datasets[0].profile.copy()
            profile.update({"transform": transform,
                             "width": mosaic.shape[2],
                             "height": mosaic.shape[1],
                             "count": mosaic.shape[0]})
            with rasterio.open(final_path, "w", **profile) as dst:
                dst.write(mosaic)
            for ds in datasets:
                ds.close()

        print(f"  Saved DFSAR Stokes: {final_path}")
        return final_path


def reproject_ohrc_with_gcps(xml_path: str, csv_path: str, dst_path: str, ref_path: str):
    """
    Georeference raw OHRC PDS4 products (.xml/.img) using the associated geometry CSV
    ground coordinates file.  Uses pure rasterio (no osgeo/GDAL bindings required).

    Strategy:
      1. Build GCPs from CSV (Pixel, Scan → projected X, Y in LOLA CRS)
      2. Check if the OHRC footprint overlaps the reference DEM tile
      3. If overlap: warp with rasterio.warp.reproject(gcps=...)
      4. If no overlap: save a blank (zeros) tile so the pipeline can continue
    """
    import pandas as pd
    from pyproj import Transformer
    from rasterio.control import GroundControlPoint
    from rasterio.warp import reproject as rasterio_reproject, Resampling

    os.environ['PROJ_IGNORE_CELESTIAL_BODY'] = 'YES'
    print(f"  [GCP WARP] Georeferencing OHRC via CSV: {os.path.basename(csv_path)}")

    df = pd.read_csv(csv_path)

    # Read reference grid metadata
    with rasterio.open(ref_path) as ref:
        ref_bounds    = ref.bounds
        ref_crs       = ref.crs
        ref_transform = ref.transform
        ref_width     = ref.width
        ref_height    = ref.height
        ref_profile   = ref.profile.copy()

    transformer = Transformer.from_crs("EPSG:4326", ref_crs, always_xy=True)

    # Downsample GCPs (take every 100th point)
    df_sub = df.iloc[::100]

    # Build rasterio GroundControlPoint list
    gcps = []
    for _, r in df_sub.iterrows():
        x, y = transformer.transform(r['Longitude'], r['Latitude'])
        gcps.append(GroundControlPoint(
            row=float(r['Scan']),
            col=float(r['Pixel']),
            x=x,
            y=y,
        ))

    # Check footprint overlap against reference DEM
    xs = [g.x for g in gcps]
    ys = [g.y for g in gcps]
    ohrc_left, ohrc_right  = min(xs), max(xs)
    ohrc_bottom, ohrc_top  = min(ys), max(ys)

    overlap = (ohrc_right  > ref_bounds.left  and
               ohrc_left   < ref_bounds.right and
               ohrc_top    > ref_bounds.bottom and
               ohrc_bottom < ref_bounds.top)

    print(f"  [GCP WARP] OHRC footprint: x=[{ohrc_left:.0f}, {ohrc_right:.0f}]  "
          f"y=[{ohrc_bottom:.0f}, {ohrc_top:.0f}]  m (projected)")
    print(f"  [GCP WARP] LOLA extent  : x=[{ref_bounds.left:.0f}, {ref_bounds.right:.0f}]  "
          f"y=[{ref_bounds.bottom:.0f}, {ref_bounds.top:.0f}]  m")
    print(f"  [GCP WARP] Footprint overlap with LOLA DEM: {overlap}")

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    if not overlap:
        # OHRC swath does not cover the LOLA DEM tile – write a blank tile
        print("  [GCP WARP] No spatial overlap -> writing blank OHRC tile (zeros).")
        blank = np.zeros((ref_height, ref_width), dtype=np.uint8)
        out_profile = ref_profile.copy()
        out_profile.update({"count": 1, "dtype": "uint8",
                             "compress": "lzw", "nodata": 0})
        with rasterio.open(dst_path, "w", **out_profile) as dst:
            dst.write(blank, 1)
        return

    # Overlap exists – warp the PDS4 image onto the LOLA grid
    out_profile = ref_profile.copy()
    out_profile.update({"count": 1, "dtype": "uint8",
                        "compress": "lzw", "nodata": 0})

    with rasterio.open(xml_path) as src:
        with rasterio.open(dst_path, "w", **out_profile) as dst_ds:
            rasterio_reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst_ds, 1),
                gcps=gcps,
                src_crs=ref_crs,
                dst_crs=ref_crs,
                dst_transform=ref_transform,
                resampling=Resampling.bilinear,
            )
    print(f"  [GCP WARP] Saved warped OHRC to: {dst_path}")


def ingest_ohrc(products: list, ref_path: str) -> str | None:
    """
    Process OHRC calibrated imagery:
    1. Reproject to lunar polar CRS (using geometry CSV GCPs if available)
    2. Co-register to LOLA DEM grid
    3. Save single-band radiance GeoTIFF
    """
    if not products:
        return None

    # Check for geometry CSV files in RAW_OHRC recursively
    csv_files = list(set(glob.glob(os.path.join(RAW_OHRC, "**", "*.csv"), recursive=True) +
                         glob.glob(os.path.join(RAW_OHRC, "**", "*.CSV"), recursive=True)))
    has_csv = len(csv_files) > 0

    print(f"\n[OHRC] Processing {len(products)} product(s) (GCPs available: {has_csv})...")
    reproj_paths = []
    for i, p in enumerate(products):
        out = os.path.join(PROCESSED, f"ohrc_reproj_{i}.tif")
        # If we have a geometry CSV file and the product is an XML label, warp with GCPs
        if has_csv and p.lower().endswith(".xml"):
            reproject_ohrc_with_gcps(p, csv_files[0], out, ref_path)
        else:
            print(f"  Reprojecting standard: {os.path.basename(p)}")
            reproject_to_lunar_polar(p, out, resolution_m=5.0, resampling="bilinear", ref_path=ref_path)
        reproj_paths.append(out)

    # Co-register to LOLA
    for i, p in enumerate(reproj_paths):
        out = os.path.join(PROCESSED, f"ohrc_coreg_{i}.tif")
        coregister_to_reference(p, ref_path, out)

    # Mosaic
    final_path = os.path.join(PROCESSED, "ohrc_radiance.tif")
    if len(reproj_paths) == 1:
        import shutil
        shutil.copy(os.path.join(PROCESSED, "ohrc_coreg_0.tif"), final_path)
    else:
        paths = [os.path.join(PROCESSED, f"ohrc_coreg_{i}.tif")
                 for i in range(len(reproj_paths))]
        datasets = [rasterio.open(p) for p in paths if os.path.exists(p)]
        mosaic, transform = merge(datasets, method="first")
        profile = datasets[0].profile.copy()
        profile.update({"transform": transform,
                         "width": mosaic.shape[2],
                         "height": mosaic.shape[1],
                         "count": 1})
        with rasterio.open(final_path, "w", **profile) as dst:
            dst.write(mosaic[:1])
        for ds in datasets:
            ds.close()

    print(f"  Saved OHRC radiance: {final_path}")
    return final_path


def main():
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 1: Data Ingestion")
    print("=" * 60)

    # ── LOLA DEM ──
    lola_raw = find_lola_dem(RAW_LOLA)
    lola_processed = os.path.join(PROCESSED, "lola_dem_5m.tif")
    if lola_raw:
        ingest_lola_dem(lola_raw, lola_processed)
    else:
        print("\n[ERROR] LOLA DEM is required. "
              "Download from https://pgda.gsfc.nasa.gov/products/78\n")
        return

    # ── DFSAR ──
    dfsar_products = find_dfsar_products(RAW_DFSAR)
    dfsar_out = ingest_dfsar(dfsar_products, lola_processed)

    # ── OHRC ──
    ohrc_products = find_ohrc_products(RAW_OHRC)
    ohrc_out = ingest_ohrc(ohrc_products, lola_processed)

    print("\n" + "=" * 60)
    print(" Ingestion complete. Processed files:")
    for f in [lola_processed, dfsar_out, ohrc_out]:
        if f and os.path.exists(f):
            size_mb = os.path.getsize(f) / 1e6
            print(f"  ✓ {os.path.basename(f):40s}  {size_mb:.1f} MB")
        else:
            print(f"  ✗ {f}  [missing — check raw data]")
    print("=" * 60)
    print(" Next: run  python src/02_psr_mapping.py")


if __name__ == "__main__":
    main()
