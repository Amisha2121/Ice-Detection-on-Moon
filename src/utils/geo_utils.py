"""
geo_utils.py
Geospatial utilities: reprojection, co-registration, grid alignment,
and coordinate transforms for lunar south polar data.
"""

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.enums import Resampling as RS
import os

# ── Lunar South Polar Stereographic CRS ──────────────────────────────────────
# ESRI:104903 / IAU 2015 Moon polar stereographic (south)
LUNAR_SOUTH_POLAR_WKT = """
PROJCRS["GCS_Moon_2000_South_Pole_Stereographic",
    BASEGEOGCRS["GCS_Moon_2000",
        DATUM["D_Moon_2000",
            ELLIPSOID["Moon_2000_IAU_IAG",1737400,0]],
        PRIMEM["Reference_Meridian",0],
        ANGLEUNIT["Degree",0.0174532925199433]],
    CONVERSION["South_Pole_Stereographic",
        METHOD["Polar Stereographic (variant A)",ID["EPSG",9810]],
        PARAMETER["Latitude of natural origin",-90,ANGLEUNIT["Degree",0.0174532925199433]],
        PARAMETER["Longitude of natural origin",0,ANGLEUNIT["Degree",0.0174532925199433]],
        PARAMETER["Scale factor at natural origin",1,SCALEUNIT["unity",1]],
        PARAMETER["False easting",0,LENGTHUNIT["Metre",1]],
        PARAMETER["False northing",0,LENGTHUNIT["Metre",1]]],
    CS[Cartesian,2],
        AXIS["(E)",east,ORDER[1],LENGTHUNIT["Metre",1]],
        AXIS["(N)",north,ORDER[2],LENGTHUNIT["Metre",1]]]
"""

LUNAR_CRS = CRS.from_wkt(LUNAR_SOUTH_POLAR_WKT)


def reproject_to_lunar_polar(src_path: str, dst_path: str,
                              resolution_m: float = 5.0,
                              resampling: str = "bilinear",
                              ref_path: str = None) -> dict:
    """
    Reproject any raster to Lunar South Polar Stereographic at given resolution.
    If ref_path is provided, matches the reference grid (extent, resolution, CRS).

    Parameters
    ----------
    src_path : path to input GeoTIFF / PDS4 XML label
    dst_path : path for output GeoTIFF
    resolution_m : target pixel size in metres (default 5 m)
    resampling : 'bilinear', 'nearest', 'cubic'
    ref_path : path to reference GeoTIFF to match

    Returns
    -------
    dict with 'transform', 'crs', 'shape', 'nodata'
    """
    rs_map = {
        "bilinear": Resampling.bilinear,
        "nearest": Resampling.nearest,
        "cubic": Resampling.cubic,
    }
    rs = rs_map.get(resampling, Resampling.bilinear)

    if ref_path and os.path.exists(ref_path):
        with rasterio.open(ref_path) as ref:
            dst_crs = ref.crs
            dst_transform = ref.transform
            dst_width = ref.width
            dst_height = ref.height
    else:
        dst_crs = LUNAR_CRS
        with rasterio.open(src_path) as src:
            src_crs = src.crs if src.crs else LUNAR_CRS
            dst_transform, dst_width, dst_height = calculate_default_transform(
                src_crs, LUNAR_CRS, src.width, src.height,
                *src.bounds,
                resolution=(resolution_m, resolution_m)
            )

    with rasterio.open(src_path) as src:
        src_crs = src.crs if src.crs else LUNAR_CRS
        meta = src.meta.copy()
        meta.update({
            "crs": dst_crs,
            "transform": dst_transform,
            "width": dst_width,
            "height": dst_height,
            "driver": "GTiff",
            "compress": "lzw",
        })

        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with rasterio.open(dst_path, "w", **meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src_crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=rs,
                )
        return {"transform": dst_transform, "crs": dst_crs,
                "shape": (dst_height, dst_width), "nodata": meta.get("nodata")}


def coregister_to_reference(src_path: str, ref_path: str,
                             dst_path: str, resampling: str = "bilinear") -> None:
    """
    Resample src raster to exactly match the grid (extent + resolution + CRS)
    of a reference raster. Essential for pixel-wise operations between DFSAR,
    OHRC, and LOLA DEM layers.
    """
    rs_map = {
        "bilinear": Resampling.bilinear,
        "nearest": Resampling.nearest,
        "cubic": Resampling.cubic,
    }
    rs = rs_map.get(resampling, Resampling.bilinear)

    with rasterio.open(ref_path) as ref:
        ref_transform = ref.transform
        ref_crs = ref.crs if ref.crs else LUNAR_CRS
        ref_width = ref.width
        ref_height = ref.height
        ref_meta = ref.meta.copy()

    with rasterio.open(src_path) as src:
        src_crs = src.crs if src.crs else LUNAR_CRS
        meta = src.meta.copy()
        meta.update({
            "crs": ref_crs,
            "transform": ref_transform,
            "width": ref_width,
            "height": ref_height,
            "driver": "GTiff",
            "compress": "lzw",
        })
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with rasterio.open(dst_path, "w", **meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src_crs,
                    dst_transform=ref_transform,
                    dst_crs=ref_crs,
                    resampling=rs,
                )


def read_band(path: str, band: int = 1) -> tuple:
    """
    Read a single band from a GeoTIFF/PDS4 file.

    Returns
    -------
    (data: np.ndarray, profile: dict)
    """
    with rasterio.open(path) as src:
        data = src.read(band).astype(np.float32)
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        return data, src.profile.copy()


def save_band(data: np.ndarray, profile: dict, path: str) -> None:
    """Save a 2D numpy array as a single-band GeoTIFF."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    p = profile.copy()
    p.update({"count": 1, "dtype": "float32",
               "driver": "GTiff", "compress": "lzw"})
    with rasterio.open(path, "w", **p) as dst:
        dst.write(data.astype(np.float32), 1)


def latlon_to_pixel(lat: float, lon: float, profile: dict) -> tuple:
    """Convert geographic lat/lon to pixel row/col (works for both Earth and lunar CRS)."""
    import os
    from pyproj import Transformer
    old_val = os.environ.get("PROJ_IGNORE_CELESTIAL_BODY")
    os.environ["PROJ_IGNORE_CELESTIAL_BODY"] = "YES"
    try:
        t = Transformer.from_crs("EPSG:4326", profile["crs"], always_xy=True)
        x, y = t.transform(lon, lat)
    finally:
        if old_val is None:
            os.environ.pop("PROJ_IGNORE_CELESTIAL_BODY", None)
        else:
            os.environ["PROJ_IGNORE_CELESTIAL_BODY"] = old_val
    transform = profile["transform"]
    col = int((x - transform.c) / transform.a)
    row = int((y - transform.f) / transform.e)
    return row, col


def pixel_to_latlon(row: int, col: int, profile: dict) -> tuple:
    """Convert pixel row/col to geographic lat/lon (works for both Earth and lunar CRS)."""
    import os
    from pyproj import Transformer
    transform = profile["transform"]
    x = transform.c + col * transform.a
    y = transform.f + row * transform.e

    # Lunar CRS uses Moon ellipsoid; pyproj blocks cross-body transforms by default.
    # Setting PROJ_IGNORE_CELESTIAL_BODY allows the projection inversion.
    old_val = os.environ.get("PROJ_IGNORE_CELESTIAL_BODY")
    os.environ["PROJ_IGNORE_CELESTIAL_BODY"] = "YES"
    try:
        t = Transformer.from_crs(profile["crs"], "EPSG:4326", always_xy=True)
        lon, lat = t.transform(x, y)
    finally:
        if old_val is None:
            os.environ.pop("PROJ_IGNORE_CELESTIAL_BODY", None)
        else:
            os.environ["PROJ_IGNORE_CELESTIAL_BODY"] = old_val

    return lat, lon
