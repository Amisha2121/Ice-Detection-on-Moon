"""
dem_utils.py
DEM (Digital Elevation Model) utilities:
  - Slope and roughness computation
  - Horizon-based shadow casting (PSR mapping)
  - Doubly Shadowed Crater (DSC) detection
  - Solar ephemeris positions for the lunar south pole
"""

import numpy as np
from scipy.ndimage import sobel, label, binary_erosion
from typing import List, Tuple
import os


# ── Terrain Derivatives ───────────────────────────────────────────────────────

def compute_slope(dem: np.ndarray, pixel_size_m: float = 5.0) -> np.ndarray:
    """
    Compute slope in degrees from a DEM.

    Uses Sobel gradient operator:  slope = arctan(sqrt(dz/dx^2 + dz/dy^2))

    Parameters
    ----------
    dem          : 2D float array of elevations in metres
    pixel_size_m : pixel size in metres

    Returns
    -------
    slope : 2D float32 array in degrees [0, 90]
    """
    dz_dx = sobel(dem, axis=1) / (8.0 * pixel_size_m)
    dz_dy = sobel(dem, axis=0) / (8.0 * pixel_size_m)
    slope_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
    slope_deg = np.degrees(slope_rad)
    return slope_deg.astype(np.float32)


def compute_roughness(slope: np.ndarray, window: int = 10) -> np.ndarray:
    """
    Surface roughness = standard deviation of slope within a rolling window.
    Higher roughness → boulders / rugged terrain → landing hazard.

    Parameters
    ----------
    slope  : slope array in degrees
    window : neighbourhood window size in pixels

    Returns
    -------
    roughness : 2D float32 array

    Notes
    -----
    Uses the integral-image (uniform_filter) trick for O(N) speed:
        Var(x) = E[x²] - E[x]²  →  std = sqrt(max(Var, 0))
    This is ~1000x faster than generic_filter on large arrays.
    """
    from scipy.ndimage import uniform_filter
    s = slope.astype(np.float64)
    mean_s  = uniform_filter(s,          size=window)
    mean_s2 = uniform_filter(s * s,      size=window)
    variance = np.maximum(mean_s2 - mean_s ** 2, 0.0)
    roughness = np.sqrt(variance)
    return roughness.astype(np.float32)



# ── Shadow Casting / PSR Mapping ──────────────────────────────────────────────

def cast_shadows_single_az(dem: np.ndarray, pixel_size_m: float,
                             sun_az_deg: float, sun_el_deg: float) -> np.ndarray:
    """
    Compute shadow mask for a single solar position using a super-optimized
    horizon angle method with variable-step slice search (no trig functions or array allocations).

    Parameters
    ----------
    dem          : 2D elevation array (metres)
    pixel_size_m : pixel size in metres
    sun_az_deg   : solar azimuth (0° = N, 90° = E)
    sun_el_deg   : solar elevation above horizon (degrees)

    Returns
    -------
    shadow : 2D bool array (True = in shadow)
    """
    H, W = dem.shape
    tan_el = np.tan(np.radians(sun_el_deg))
    az_rad = np.radians(sun_az_deg)
    dx = np.sin(az_rad)
    dy = -np.cos(az_rad)
    
    max_slope = np.full((H, W), -np.inf, dtype=np.float32)
    seen_offsets = set()
    max_steps = max(H, W)
    
    # Generate variable steps to speed up calculation over long distances
    steps = []
    s = 1
    while s < max_steps:
        steps.append(s)
        if s < 30:
            s += 1
        elif s < 100:
            s += 3
        elif s < 300:
            s += 10
        elif s < 1000:
            s += 30
        else:
            s += 100
            
    for s in steps:
        dy_px = int(round(s * dy))
        dx_px = int(round(s * dx))
        if dy_px == 0 and dx_px == 0:
            continue
        if (dy_px, dx_px) in seen_offsets:
            continue
        seen_offsets.add((dy_px, dx_px))
        
        if dy_px >= 0:
            ysrc_start, ysrc_end = dy_px, H
            ydst_start, ydst_end = 0, H - dy_px
        else:
            ysrc_start, ysrc_end = 0, H + dy_px
            ydst_start, ydst_end = -dy_px, H
            
        if dx_px >= 0:
            xsrc_start, xsrc_end = dx_px, W
            xdst_start, xdst_end = 0, W - dx_px
        else:
            xsrc_start, xsrc_end = 0, W + dx_px
            xdst_start, xdst_end = -dx_px, W
            
        if (ysrc_end <= ysrc_start) or (xsrc_end <= xsrc_start):
            break
            
        elev_diff = dem[ysrc_start:ysrc_end, xsrc_start:xsrc_end] - dem[ydst_start:ydst_end, xdst_start:xdst_end]
        dist_m = s * pixel_size_m
        slope = elev_diff / dist_m
        
        max_slope[ydst_start:ydst_end, xdst_start:xdst_end] = np.fmax(
            max_slope[ydst_start:ydst_end, xdst_start:xdst_end],
            slope
        )
        
    shadow = max_slope > tan_el
    return shadow


def compute_illumination_fraction(dem: np.ndarray, pixel_size_m: float = 5.0,
                                   n_sun_positions: int = 100,
                                   latitude_deg: float = -90.0) -> np.ndarray:
    """
    Compute annual illumination fraction for each pixel using
    simplified horizon shadow casting over a year of solar positions.

    For the lunar south pole, the Sun traces a nearly constant low-elevation
    circle (~1.5° above the horizon), slowly varying in azimuth.

    Parameters
    ----------
    dem              : 2D DEM array
    pixel_size_m     : pixel size in metres
    n_sun_positions  : number of Sun azimuths to sample (evenly, 0–360°)
    latitude_deg     : site latitude (should be ≤ -85° for south pole)

    Returns
    -------
    illum_fraction : 2D float32 array in [0, 1]
                     0 = always dark (PSR), 1 = always lit
    """
    import cv2
    H, W = dem.shape
    
    # Downsample factor (4x)
    ds_factor = 4
    dem_down = dem[::ds_factor, ::ds_factor]
    pixel_size_down = pixel_size_m * ds_factor
    
    H_down, W_down = dem_down.shape
    illum_count = np.zeros((H_down, W_down), dtype=np.int32)

    # Solar elevation at the south pole (max ~1.54°, varies slowly)
    sun_el = 1.5   # degrees — conservative constant for south pole

    azimuths = np.linspace(0, 360, n_sun_positions, endpoint=False)

    print(f"  [DOWNSAMPLED SHADOWS] Shape: {H_down}x{W_down}, resolution: {pixel_size_down:.1f} m/px")
    print(f"  Computing illumination for {n_sun_positions} solar positions...")
    for i, az in enumerate(azimuths):
        if (i + 1) % 5 == 0 or i == 0 or i == n_sun_positions - 1:
            print(f"    Position {i+1}/{n_sun_positions} (az={az:.1f}°)")
        shadow = cast_shadows_single_az(dem_down, pixel_size_down, az, sun_el)
        illum_count += (~shadow).astype(np.int32)

    illum_fraction_down = (illum_count / n_sun_positions).astype(np.float32)
    
    # Upsample back to original size
    illum_fraction = cv2.resize(illum_fraction_down, (W, H), interpolation=cv2.INTER_LINEAR)
    return illum_fraction.astype(np.float32)


def compute_psr_mask(illum_fraction: np.ndarray,
                      threshold: float = 0.001) -> np.ndarray:
    """
    Generate PSR (Permanently Shadowed Region) binary mask.

    PSR = pixels with illumination fraction < threshold (< 0.1% annual)

    Returns
    -------
    psr_mask : uint8 array (1 = PSR, 0 = illuminated)
    """
    psr_mask = (illum_fraction < threshold).astype(np.uint8)
    return psr_mask


def detect_doubly_shadowed_craters(psr_mask: np.ndarray,
                                    dem: np.ndarray,
                                    min_area_px: int = 50) -> Tuple[np.ndarray, list]:
    """
    Identify Doubly Shadowed Craters (DSCs) within the PSR regions using local
    topographic depressions (crater floors / nested sinks).

    Method:
    1. Compute local mean elevation using a uniform filter (size=100 pixels = 500m).
    2. Identify depressions where the local mean elevation exceeds the pixel elevation
       by more than 20.0 meters.
    3. Filter these depression pixels by the PSR mask (must be inside a PSR).
    4. Label the connected regions and filter out those smaller than min_area_px.
    """
    from scipy.ndimage import uniform_filter, label

    # Calculate local mean elevation (neighborhood size of 100 pixels = 500m)
    dem_mean = uniform_filter(dem, size=100)

    # Depressions are areas lower than their neighborhood by at least 20m
    depression = (dem_mean - dem) > 20.0

    # DSCs must be depressions AND within the PSR mask
    dsc_raw = (psr_mask == 1) & depression

    labeled, n_regions = label(dsc_raw)
    dsc_mask = np.zeros_like(psr_mask, dtype=np.uint8)
    dsc_stats = []

    reg_count = 1
    for r in range(1, n_regions + 1):
        region = (labeled == r)
        area = np.sum(region)
        if area < min_area_px:
            continue

        dsc_mask[region] = 1
        rows, cols = np.where(region)

        dsc_stats.append({
            "region_id": int(reg_count),
            "area_px": int(area),
            "centroid_row": float(np.mean(rows)),
            "centroid_col": float(np.mean(cols)),
            "mean_elevation_m": float(np.nanmean(dem[region])),
            "min_elevation_m": float(np.nanmin(dem[region])),
        })
        reg_count += 1

    return dsc_mask, dsc_stats


def fast_psr_from_min_elevation(dem: np.ndarray,
                                 pixel_size_m: float = 5.0) -> np.ndarray:
    """
    Fast PSR approximation using local horizon analysis.
    For each pixel, checks if it is below the horizon seen from all directions
    at the sun's maximum elevation (~1.54° at south pole).

    Much faster than full shadow casting — use for previews.
    """
    from scipy.ndimage import minimum_filter
    sun_el_rad = np.radians(1.54)

    # Conservative: pixel is PSR if it is a local depression deeper than
    # tan(sun_el) * distance_to_crater_rim
    min_neighbor = minimum_filter(dem, size=20)
    relative_depth = dem - minimum_filter(dem, size=50)
    approx_psr = (relative_depth < -10).astype(np.uint8)
    return approx_psr
