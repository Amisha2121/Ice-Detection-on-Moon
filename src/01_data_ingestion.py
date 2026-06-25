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
import re
import xml.etree.ElementTree as ET
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.control import GroundControlPoint
from rasterio.warp import reproject as rasterio_reproject, Resampling, transform_bounds
from pyproj import Transformer
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from utils.geo_utils import (reproject_to_lunar_polar, coregister_to_reference,
                               read_band, save_band, LUNAR_CRS)
from utils.dfsar_meta import write_dfsar_meta

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DFSAR  = os.path.join(ROOT, "data", "raw", "dfsar")
RAW_OHRC   = os.path.join(ROOT, "data", "raw", "ohrc")
RAW_LOLA   = os.path.join(ROOT, "data", "raw", "lola")
PROCESSED  = os.path.join(ROOT, "data", "processed")

os.makedirs(PROCESSED, exist_ok=True)


def _parse_dfsar_corners(xml_path: str) -> dict | None:
    """
    Extract the 4 corner lat/lon coordinates from a DFSAR PDS4 XML label.
    Returns dict with keys: ul_lat, ul_lon, ur_lat, ur_lon, ll_lat, ll_lon, lr_lat, lr_lon
    or None if parsing fails.
    """
    try:
        with open(xml_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        def _find(tag):
            m = re.search(rf'<isda:{tag}[^>]*>([^<]+)<', content)
            return float(m.group(1)) if m else None
        corners = {
            'ul_lat': _find('upper_left_latitude'),
            'ul_lon': _find('upper_left_longitude'),
            'ur_lat': _find('upper_right_latitude'),
            'ur_lon': _find('upper_right_longitude'),
            'll_lat': _find('lower_left_latitude'),
            'll_lon': _find('lower_left_longitude'),
            'lr_lat': _find('lower_right_latitude'),
            'lr_lon': _find('lower_right_longitude'),
        }
        if any(v is None for v in corners.values()):
            return None
        return corners
    except Exception as e:
        print(f"  [DFSAR] Could not parse corners from {os.path.basename(xml_path)}: {e}")
        return None


def _corners_to_lola_crs(corners: dict, ref_crs) -> tuple:
    """
    Convert DFSAR lat/lon corner dict to projected coords in the LOLA CRS.
    Returns (min_x, min_y, max_x, max_y) in the reference CRS.
    """
    import os as _os
    old = _os.environ.get('PROJ_IGNORE_CELESTIAL_BODY')
    _os.environ['PROJ_IGNORE_CELESTIAL_BODY'] = 'YES'
    try:
        t = Transformer.from_crs('EPSG:4326', ref_crs, always_xy=True)
        pts = [
            (corners['ul_lon'], corners['ul_lat']),
            (corners['ur_lon'], corners['ur_lat']),
            (corners['ll_lon'], corners['ll_lat']),
            (corners['lr_lon'], corners['lr_lat']),
        ]
        xs = [t.transform(lon, lat)[0] for lon, lat in pts]
        ys = [t.transform(lon, lat)[1] for lon, lat in pts]
        return min(xs), min(ys), max(xs), max(ys)
    finally:
        if old is None:
            _os.environ.pop('PROJ_IGNORE_CELESTIAL_BODY', None)
        else:
            _os.environ['PROJ_IGNORE_CELESTIAL_BODY'] = old


def reproject_dfsar_with_gcps(xml_path: str, dst_path: str, ref_path: str) -> bool:
    """
    Warp a raw DFSAR PDS4 product onto the LOLA reference grid using 4-corner
    GCPs derived from the PDS4 XML label's corner lat/lon fields.

    This mirrors reproject_ohrc_with_gcps() — the .dat/.xml files have no
    embedded CRS so rasterio would return an identity matrix; instead we read
    the real footprint from the label and build proper GCPs.

    Returns True on success, False if corners could not be parsed.
    """
    corners = _parse_dfsar_corners(xml_path)
    if corners is None:
        print(f"  [DFSAR GCP WARP] No corner coords in {os.path.basename(xml_path)} "
              f"— falling back to blind reproject")
        return False

    with rasterio.open(ref_path) as ref:
        ref_bounds    = ref.bounds
        ref_crs       = ref.crs
        ref_transform = ref.transform
        ref_width     = ref.width
        ref_height    = ref.height
        ref_profile   = ref.profile.copy()

    # Project corners to LOLA CRS
    import os as _os
    old = _os.environ.get('PROJ_IGNORE_CELESTIAL_BODY')
    _os.environ['PROJ_IGNORE_CELESTIAL_BODY'] = 'YES'
    try:
        t = Transformer.from_crs('EPSG:4326', ref_crs, always_xy=True)
        def _proj(lat, lon):
            return t.transform(lon, lat)  # returns (x, y)
        ul_x, ul_y = _proj(corners['ul_lat'], corners['ul_lon'])
        ur_x, ur_y = _proj(corners['ur_lat'], corners['ur_lon'])
        ll_x, ll_y = _proj(corners['ll_lat'], corners['ll_lon'])
        lr_x, lr_y = _proj(corners['lr_lat'], corners['lr_lon'])
    finally:
        if old is None:
            _os.environ.pop('PROJ_IGNORE_CELESTIAL_BODY', None)
        else:
            _os.environ['PROJ_IGNORE_CELESTIAL_BODY'] = old

    # Real footprint in LOLA CRS
    dfsar_xs = [ul_x, ur_x, ll_x, lr_x]
    dfsar_ys = [ul_y, ur_y, ll_y, lr_y]
    dfsar_minx, dfsar_maxx = min(dfsar_xs), max(dfsar_xs)
    dfsar_miny, dfsar_maxy = min(dfsar_ys), max(dfsar_ys)

    print(f"  [DFSAR GCP WARP] Real footprint (XML corners):")
    print(f"    UL ({corners['ul_lat']:.3f}°, {corners['ul_lon']:.3f}°)  "
          f"UR ({corners['ur_lat']:.3f}°, {corners['ur_lon']:.3f}°)")
    print(f"    LL ({corners['ll_lat']:.3f}°, {corners['ll_lon']:.3f}°)  "
          f"LR ({corners['lr_lat']:.3f}°, {corners['lr_lon']:.3f}°)")
    print(f"  [DFSAR GCP WARP] Projected x=[{dfsar_minx:.0f}, {dfsar_maxx:.0f}]  "
          f"y=[{dfsar_miny:.0f}, {dfsar_maxy:.0f}]  m")
    print(f"  [DFSAR GCP WARP] LOLA DEM  x=[{ref_bounds.left:.0f}, {ref_bounds.right:.0f}]  "
          f"y=[{ref_bounds.bottom:.0f}, {ref_bounds.top:.0f}]  m")

    overlap = (dfsar_maxx > ref_bounds.left  and dfsar_minx < ref_bounds.right and
               dfsar_maxy > ref_bounds.bottom and dfsar_miny < ref_bounds.top)
    print(f"  [DFSAR GCP WARP] Spatial overlap with LOLA DEM: {overlap}")

    if not overlap:
        print("  [DFSAR GCP WARP] No overlap — skipping this granule.")
        return False

    # Build 4 GCPs: map pixel corners → projected coordinates
    with rasterio.open(xml_path) as src:
        h, w = src.height, src.width
        src_count = src.count

    # GCPs: (row, col) in pixel space → (x, y) in LOLA CRS
    gcps = [
        GroundControlPoint(row=0,     col=0,   x=ul_x, y=ul_y),
        GroundControlPoint(row=0,     col=w-1, x=ur_x, y=ur_y),
        GroundControlPoint(row=h-1,   col=0,   x=ll_x, y=ll_y),
        GroundControlPoint(row=h-1,   col=w-1, x=lr_x, y=lr_y),
    ]

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    out_profile = ref_profile.copy()
    out_profile.update({'count': 1, 'dtype': 'float32',
                        'compress': 'lzw', 'nodata': 0.0})

    with rasterio.open(xml_path) as src:
        with rasterio.open(dst_path, 'w', **out_profile) as dst_ds:
            rasterio_reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst_ds, 1),
                gcps=gcps,
                src_crs=ref_crs,
                dst_crs=ref_crs,
                dst_transform=ref_transform,
                resampling=Resampling.bilinear,
                SRC_METHOD='NO_GEOTRANSFORM',
            )
    print(f"  [DFSAR GCP WARP] Saved warped product to: {os.path.basename(dst_path)}")
    return True


def find_dfsar_products(directory: str) -> list:
    """
    Scan the DFSAR directory for raw data XML labels (PDS4 _r0b_ or _d_cp_ products).
    Returns only the data XML files (not geometry XMLs).
    Falls back to .tif files if no XMLs found.
    """
    # Data XMLs: contain 'r0b' or match CP naming; exclude geometry folder
    xml_files = glob.glob(os.path.join(directory, '**', '*.xml'), recursive=True)
    xml_files = [f for f in xml_files
                 if 'geometry' not in f.lower()
                 and 'browse' not in f.lower()
                 and '.aux' not in f.lower()]

    tif_files = list(set(glob.glob(os.path.join(directory, '**', '*.tif'), recursive=True) +
                         glob.glob(os.path.join(directory, '**', '*.TIF'), recursive=True)))
    tif_files = [f for f in tif_files if 'geometry' not in f.lower()
                 and 'browse' not in f.lower() and '.aux' not in f.lower()]

    products = xml_files if xml_files else tif_files

    if not products:
        print(f"  [WARNING] No DFSAR products found in {directory}")
        print("  Download from: https://pradan.issdc.gov.in/ch2/ → SAR")
    else:
        print(f"  Found {len(products)} DFSAR product(s) (data XMLs preferred over TIFs).")

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


def _check_dfsar_overlap(product_path: str, ref_path: str) -> bool:
    """
    Check whether a DFSAR product footprint intersects the LOLA DEM tile.
    Uses XML corner lat/lons (real georeferencing) rather than the pixel-grid
    bounds rasterio returns when the file has no CRS (which is meaningless).
    """
    # Prefer XML-based check for real footprint
    corners = _parse_dfsar_corners(product_path)
    if corners is not None:
        with rasterio.open(ref_path) as ref:
            ref_bounds = ref.bounds
            ref_crs    = ref.crs
        minx, miny, maxx, maxy = _corners_to_lola_crs(corners, ref_crs)
        overlap = (maxx > ref_bounds.left and minx < ref_bounds.right and
                   maxy > ref_bounds.bottom and miny < ref_bounds.top)
        print(f"  [DFSAR] XML footprint: lat=[{min(corners['ul_lat'],corners['ll_lat']):.3f}, "
              f"{max(corners['ur_lat'],corners['lr_lat']):.3f}]  "
              f"lon=[{min(corners['ul_lon'],corners['ll_lon']):.3f}, "
              f"{max(corners['ur_lon'],corners['lr_lon']):.3f}]")
        print(f"  [DFSAR] Projected x=[{minx:.0f}, {maxx:.0f}]  y=[{miny:.0f}, {maxy:.0f}]  m")
        print(f"  [DFSAR] LOLA DEM  x=[{ref_bounds.left:.0f}, {ref_bounds.right:.0f}]  "
              f"y=[{ref_bounds.bottom:.0f}, {ref_bounds.top:.0f}]  m")
        print(f"  [DFSAR] Real spatial overlap: {overlap}")
        if not overlap:
            print("  [DFSAR] *** THIS GRANULE DOES NOT COVER YOUR LOLA DEM TILE — will skip")
        return overlap
    else:
        # No XML corners — fall through (file likely a .tif without CRS, will produce blank data)
        print(f"  [DFSAR] WARNING: No corner lat/lon in {os.path.basename(product_path)} "
              f"— cannot verify overlap. File may lack georeferencing.")
        return False


def _find_decomp_tifs() -> dict:
    """Locate odd/evn/vol/hlx decomposition GeoTIFFs (ndxl polarimetric products)."""
    decomp = {}
    for key in ["odd", "evn", "vol", "hlx"]:
        matches = glob.glob(os.path.join(RAW_DFSAR, "**", f"*{key}*.tif"), recursive=True)
        matches += glob.glob(os.path.join(RAW_DFSAR, "**", f"*{key.upper()}*.TIF"), recursive=True)
        matches = [m for m in matches if "browse" not in m.lower()]
        if matches:
            decomp[key] = matches[0]
    return decomp


def _find_cp_tifs() -> dict:
    """Locate compact-polarimetry LH/LV amplitude pairs."""
    cp = {"lh": None, "lv": None}
    for key in cp:
        matches = glob.glob(os.path.join(RAW_DFSAR, "**", f"*cp_{key}*.tif"), recursive=True)
        matches += glob.glob(os.path.join(RAW_DFSAR, "**", f"*cp_{key}*.TIF"), recursive=True)
        matches = [m for m in matches if "browse" not in m.lower() and "_sli_" not in m.lower()]
        if matches:
            cp[key] = matches[0]
    return cp


def _save_stokes_tif(ref_profile: dict, S1, S2, S3, S0) -> str:
    final_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
    profile = ref_profile.copy()
    profile.update({"count": 4, "dtype": "float32", "compress": "lzw", "nodata": None})
    with rasterio.open(final_path, "w", **profile) as dst:
        dst.write(S1.astype(np.float32), 1)
        dst.write(S2.astype(np.float32), 2)
        dst.write(S3.astype(np.float32), 3)
        dst.write(S0.astype(np.float32), 4)
    return final_path


def _stokes_from_decomposition(data_bands: dict, ref_profile: dict) -> str:
    Ps = data_bands["odd"]
    Pd = data_bands["evn"]
    Pv = data_bands["vol"]
    Ph = data_bands["hlx"]

    S0 = Ps + Pd + Pv + Ph
    S0_safe = S0 + 1e-12
    m = np.clip(1.0 - Pv / S0_safe, 0.0, 1.0)
    S3 = np.clip(Ps - Pd - Pv, -S0 * m, S0 * m)
    S1 = np.sqrt(np.clip((S0 * m) ** 2 - S3 ** 2, 0.0, None))
    S2 = np.zeros_like(S0)
    return _save_stokes_tif(ref_profile, S1, S2, S3, S0)


def _stokes_from_compact_pol(LH, LV, ref_profile: dict) -> str:
    """Derive Stokes from LH/LV compact-pol amplitudes (two independent channels)."""
    S0 = LH ** 2 + LV ** 2
    S1 = LH ** 2 - LV ** 2
    S2 = np.zeros_like(S0)
    S3 = -S1
    return _save_stokes_tif(ref_profile, S1, S2, S3, S0)


def _synthesize_demo_stokes(amp: np.ndarray) -> tuple:
    """
    OFFLINE UI DEMO ONLY — not a physical measurement.
    Do not use for science outputs or judge presentations.
    """
    S0 = amp ** 2
    if np.max(S0) <= 0:
        zeros = np.zeros_like(S0)
        return zeros, zeros, zeros, zeros
    p90 = np.percentile(S0[S0 > 0], 90)
    S3 = S0 * (0.5 - 0.6 * np.clip(S0 / p90, 0, 1.5))
    S1 = S0 * 0.05
    S2 = np.zeros_like(S0)
    return S1, S2, S3, S0


def _ingest_decomposition_products(ref_path: str, ref_profile: dict) -> str | None:
    decomp = _find_decomp_tifs()
    if not any(decomp.values()):
        return None

    print("\n[DFSAR] Processing polarimetric decomposition products (odd/evn/vol/hlx)...")
    coreg_paths = {}
    for key, path in decomp.items():
        reproj_out = os.path.join(PROCESSED, f"dfsar_reproj_{key}.tif")
        coreg_out = os.path.join(PROCESSED, f"dfsar_coreg_{key}.tif")
        print(f"  {key.upper()}: {os.path.basename(path)}")
        reproject_to_lunar_polar(path, reproj_out, resolution_m=5.0, ref_path=ref_path)
        coregister_to_reference(reproj_out, ref_path, coreg_out)
        coreg_paths[key] = coreg_out

    shape = (ref_profile["height"], ref_profile["width"])
    data_bands = {}
    for key in ["odd", "evn", "vol", "hlx"]:
        if key in coreg_paths:
            with rasterio.open(coreg_paths[key]) as src:
                data = src.read(1).astype(np.float32)
                if src.nodata is not None:
                    data[data == src.nodata] = 0.0
                data_bands[key] = np.clip(np.nan_to_num(data, nan=0.0), 0.0, None)
        else:
            data_bands[key] = np.zeros(shape, dtype=np.float32)

    final_path = _stokes_from_decomposition(data_bands, ref_profile)
    print(f"  Reconstructed Stokes from decomposition saved to: {final_path}")
    return final_path


def _ingest_compact_pol_products(ref_path: str, ref_profile: dict) -> str | None:
    cp = _find_cp_tifs()
    if not (cp["lh"] and cp["lv"]):
        return None

    print("\n[DFSAR] Processing compact-polarimetry LH/LV products...")
    data_bands = {}
    for key, path in cp.items():
        reproj_out = os.path.join(PROCESSED, f"dfsar_reproj_cp_{key}.tif")
        coreg_out = os.path.join(PROCESSED, f"dfsar_coreg_cp_{key}.tif")
        print(f"  CP {key.upper()}: {os.path.basename(path)}")
        reproject_to_lunar_polar(path, reproj_out, resolution_m=5.0, ref_path=ref_path)
        coregister_to_reference(reproj_out, ref_path, coreg_out)
        with rasterio.open(coreg_out) as src:
            data = src.read(1).astype(np.float32)
            if src.nodata is not None:
                data[data == src.nodata] = 0.0
            data_bands[key] = np.nan_to_num(data, nan=0.0)

    final_path = _stokes_from_compact_pol(data_bands["lh"], data_bands["lv"], ref_profile)
    print(f"  Reconstructed CP Stokes (LH/LV) saved to: {final_path}")
    return final_path


def _ingest_standard_stokes_products(products: list, ref_path: str, ref_profile: dict) -> str | None:
    """Handle pre-computed 4-band Stokes GeoTIFFs."""
    stokes_products = []
    for p in products:
        try:
            with rasterio.open(p) as src:
                if src.count >= 4:
                    stokes_products.append(p)
        except Exception:
            continue

    if not stokes_products:
        return None

    print(f"\n[DFSAR] Processing {len(stokes_products)} standard 4-band Stokes product(s)...")
    reproj_paths = []
    for i, p in enumerate(stokes_products):
        out = os.path.join(PROCESSED, f"dfsar_reproj_{i}.tif")
        print(f"  Reprojecting: {os.path.basename(p)}")
        reproject_to_lunar_polar(p, out, resolution_m=5.0, ref_path=ref_path)
        reproj_paths.append(out)

    coreg_paths = []
    for i, p in enumerate(reproj_paths):
        out = os.path.join(PROCESSED, f"dfsar_coreg_{i}.tif")
        coregister_to_reference(p, ref_path, out)
        coreg_paths.append(out)

    final_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
    if len(coreg_paths) == 1:
        import shutil
        shutil.copy(coreg_paths[0], final_path)
    else:
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

    print(f"  Saved standard Stokes product: {final_path}")
    return final_path


def ingest_dfsar(products: list, ref_path: str, synthetic_demo: bool = False) -> str | None:
    """
    Process DFSAR products into a 4-band Stokes GeoTIFF co-registered to the LOLA grid.

    Priority:
      1. Polarimetric decomposition TIFs (odd/evn/vol/hlx)
      2. Compact-pol LH+LV pair
      3. Native 4-band Stokes GeoTIFFs
      4. Single-band PDS4 amplitude: XML GCP warp only; no Stokes unless --synthetic-demo

    Writes data/processed/dfsar_ingestion_meta.json documenting the source.
    """
    stokes_path = os.path.join(PROCESSED, "dfsar_stokes.tif")
    limitation = (
        "Available DFSAR product is single-band amplitude only. "
        "CPR and DOP ice detection require multi-channel polarimetry "
        "(decomposition odd/evn/vol/hlx, compact-pol LH+LV, or full-pol Stokes). "
        "Re-download the ndxl decomposition or LH/LV pair for this pass from PRADAN."
    )

    if not products:
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="none",
            synthetic=False,
            cpr_dop_detection_valid=False,
            limitation_message="No DFSAR products found in data/raw/dfsar/",
        )
        if os.path.exists(stokes_path):
            os.remove(stokes_path)
        return None

    with rasterio.open(ref_path) as ref:
        ref_profile = ref.profile.copy()

    result = _ingest_decomposition_products(ref_path, ref_profile)
    if result:
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="decomposition",
            synthetic=False,
            cpr_dop_detection_valid=True,
            limitation_message=None,
        )
        return result

    result = _ingest_compact_pol_products(ref_path, ref_profile)
    if result:
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="compact_pol_lh_lv",
            synthetic=False,
            cpr_dop_detection_valid=True,
            limitation_message=None,
        )
        return result

    result = _ingest_standard_stokes_products(products, ref_path, ref_profile)
    if result:
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="stokes_4band",
            synthetic=False,
            cpr_dop_detection_valid=True,
            limitation_message=None,
        )
        return result

    # ── Single-band PDS4 products: XML GCP warp (real georeferencing fix) ─────
    print(f"\n[DFSAR] Checking {len(products)} product footprint(s) against LOLA DEM tile...")
    overlapping = [p for p in products if _check_dfsar_overlap(p, ref_path)]

    if not overlapping:
        print("!" * 70)
        print("  [DFSAR] NO products overlap the LOLA DEM tile.")
        print("  Pipeline will run but ice detection will produce zero pixels.")
        print("!" * 70)
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="none",
            synthetic=False,
            cpr_dop_detection_valid=False,
            limitation_message="DFSAR swath does not overlap the LOLA DEM tile.",
        )
        if os.path.exists(stokes_path):
            os.remove(stokes_path)
        return None

    print(f"  {len(overlapping)}/{len(products)} product(s) overlap — warping amplitude via XML GCPs...")
    warped_paths = []
    for i, p in enumerate(overlapping):
        dst = os.path.join(PROCESSED, f"dfsar_coreg_{i}.tif")
        if reproject_dfsar_with_gcps(p, dst, ref_path):
            warped_paths.append(dst)

    if not warped_paths:
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="amplitude_only",
            synthetic=False,
            cpr_dop_detection_valid=False,
            limitation_message=limitation,
        )
        if os.path.exists(stokes_path):
            os.remove(stokes_path)
        return None

    if len(warped_paths) == 1:
        with rasterio.open(warped_paths[0]) as src:
            amp = src.read(1).astype(np.float32)
            if src.nodata is not None:
                amp[amp == src.nodata] = 0.0
            amp = np.nan_to_num(amp, nan=0.0)
    else:
        datasets = [rasterio.open(p) for p in warped_paths]
        mosaic, _ = merge(datasets, method="first")
        for ds in datasets:
            ds.close()
        amp = np.nan_to_num(mosaic[0].astype(np.float32), nan=0.0)

    amp_path = os.path.join(PROCESSED, "dfsar_amplitude_coreg.tif")
    amp_profile = ref_profile.copy()
    amp_profile.update({"count": 1, "dtype": "float32", "compress": "lzw", "nodata": 0.0})
    with rasterio.open(amp_path, "w", **amp_profile) as dst:
        dst.write(amp, 1)
    print(f"  Saved co-registered amplitude (reference only): {amp_path}")

    valid = int(np.sum(amp > 0))
    print(f"  Valid amplitude pixels: {valid:,}")

    if synthetic_demo:
        print("\n" + "!" * 70)
        print("  *** SYNTHETIC DEMO MODE — NOT REAL ICE DETECTION ***")
        print("  Stokes bands are formula-generated for UI testing only.")
        print("  Do not present these results as Chandrayaan-2 measurements.")
        print("!" * 70 + "\n")
        S1, S2, S3, S0 = _synthesize_demo_stokes(amp)
        final_path = _save_stokes_tif(ref_profile, S1, S2, S3, S0)
        write_dfsar_meta(
            PROCESSED,
            polarimetry_source="synthetic_demo",
            synthetic=True,
            cpr_dop_detection_valid=False,
            limitation_message=(
                "SYNTHETIC DEMO: Stokes invented from single-band amplitude. "
                "Ice pixels are not spacecraft measurements."
            ),
        )
        print(f"  [DEMO] Synthetic Stokes saved to: {final_path}")
        return final_path

    print("\n" + "!" * 70)
    print("  [DFSAR] Single-band amplitude only — cannot derive CPR/DOP.")
    print(f"  {limitation}")
    print("  Proceeding without Stokes file (will not synthesize values).")
    print("  Pass --synthetic-demo only for offline UI testing.")
    print("!" * 70 + "\n")

    if os.path.exists(stokes_path):
        os.remove(stokes_path)

    write_dfsar_meta(
        PROCESSED,
        polarimetry_source="amplitude_only",
        synthetic=False,
        cpr_dop_detection_valid=False,
        limitation_message=limitation,
        amplitude_reference=amp_path,
    )
    return None


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
                SRC_METHOD='NO_GEOTRANSFORM',
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


def main(synthetic_demo: bool = False):
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
    dfsar_out = ingest_dfsar(dfsar_products, lola_processed, synthetic_demo=synthetic_demo)

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
    import argparse
    parser = argparse.ArgumentParser(description="Lunar Ice Pipeline — Step 1")
    parser.add_argument(
        "--synthetic-demo",
        action="store_true",
        help="Generate formula-based Stokes from single-band amplitude for UI testing only "
             "(never use for science or judge presentations)",
    )
    args = parser.parse_args()
    main(synthetic_demo=args.synthetic_demo)
