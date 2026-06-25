"""
radar_utils.py
SAR radar processing utilities:
  - Refined Lee speckle filter
  - Stokes parameter extraction from DFSAR bands
  - CPR (Circular Polarization Ratio) computation
  - DOP (Degree of Polarization) computation
  - m-chi decomposition for volume/surface/dihedral classification
"""

import numpy as np
from scipy.ndimage import uniform_filter, generic_filter


# ── Speckle Filtering ─────────────────────────────────────────────────────────

def lee_filter(band: np.ndarray, window: int = 5) -> np.ndarray:
    """
    Refined Lee speckle filter for SAR intensity images.

    Parameters
    ----------
    band   : 2D float32 array of SAR intensity
    window : filter window size (odd integer, default 5)

    Returns
    -------
    Filtered 2D array of same shape
    """
    band = band.astype(np.float64)
    img_mean = uniform_filter(band, size=window)
    img_sq_mean = uniform_filter(band ** 2, size=window)
    img_var = img_sq_mean - img_mean ** 2

    # Equivalent number of looks (ENL) estimate
    overall_var = np.nanvar(band)
    if overall_var == 0:
        return band.astype(np.float32)

    weight = img_var / (img_var + overall_var + 1e-10)
    filtered = img_mean + weight * (band - img_mean)
    return filtered.astype(np.float32)


def boxcar_filter(band: np.ndarray, window: int = 5) -> np.ndarray:
    """Simple boxcar (mean) filter — fallback for very noisy data."""
    filtered = uniform_filter(band.astype(np.float64), size=window)
    return filtered.astype(np.float32)


# ── Stokes Parameter Extraction ───────────────────────────────────────────────

def extract_stokes(dfsar_path: str) -> dict:
    """
    Read a DFSAR SRI GeoTIFF and extract Stokes parameters.

    DFSAR hybrid-polarimetric SRI products contain 4 bands:
      Band 1 → S1  (linear H-V component)
      Band 2 → S2  (linear 45° component)
      Band 3 → S3  (circular component)
      Band 4 → S0  (total power)

    Returns
    -------
    dict with keys 'S0', 'S1', 'S2', 'S3' as float32 np.ndarrays,
    plus 'profile' (rasterio metadata dict)
    """
    import rasterio
    with rasterio.open(dfsar_path) as src:
        profile = src.profile.copy()
        bands = src.read().astype(np.float32)   # shape: (4, H, W)

    if bands.shape[0] < 4:
        raise ValueError(
            f"Expected 4 Stokes bands in DFSAR SRI, found {bands.shape[0]}. "
            "Check that you loaded an SRI hybrid-polarimetric product."
        )

    S1 = bands[0]
    S2 = bands[1]
    S3 = bands[2]
    S0 = bands[3]

    # Replace nodata / negative total power with NaN
    S0[S0 <= 0] = np.nan
    S1[np.isnan(S0)] = np.nan
    S2[np.isnan(S0)] = np.nan
    S3[np.isnan(S0)] = np.nan

    return {"S0": S0, "S1": S1, "S2": S2, "S3": S3, "profile": profile}


# ── CPR Computation ───────────────────────────────────────────────────────────

def compute_cpr(S0: np.ndarray, S3: np.ndarray,
                filter_window: int = 5) -> np.ndarray:
    """
    Compute Circular Polarization Ratio (CPR).

    CPR = (S0 - S3) / (S0 + S3)
      where S0 = total power, S3 = circular Stokes component.

    CPR > 1  →  same-sense return dominant  →  ice / volume scatterer candidate
    CPR < 1  →  Bragg / surface scattering  →  rough bare surface

    Parameters
    ----------
    S0, S3     : Stokes band arrays (float32)
    filter_window : Lee filter window applied before ratio (0 = skip)

    Returns
    -------
    CPR array (float32); NaN where invalid
    """
    if filter_window > 0:
        S0 = lee_filter(S0, filter_window)
        S3 = lee_filter(S3, filter_window)

    denom = S0 + S3
    denom[np.abs(denom) < 1e-12] = np.nan
    cpr = (S0 - S3) / denom
    cpr[cpr < 0] = np.nan     # physically impossible
    return cpr.astype(np.float32)


# ── DOP Computation ───────────────────────────────────────────────────────────

def compute_dop(S0: np.ndarray, S1: np.ndarray,
                S2: np.ndarray, S3: np.ndarray) -> np.ndarray:
    """
    Compute Degree of Polarization (DOP).

    DOP = sqrt(S1^2 + S2^2 + S3^2) / S0

    DOP range: [0, 1]
    DOP < 0.13  →  depolarization consistent with volume scattering (ice)
    DOP → 1     →  fully polarized (smooth surface return)

    Returns
    -------
    DOP array (float32)
    """
    S0_safe = S0.copy()
    S0_safe[S0_safe < 1e-12] = np.nan

    pol_mag = np.sqrt(S1 ** 2 + S2 ** 2 + S3 ** 2)
    dop = pol_mag / S0_safe
    dop = np.clip(dop, 0, 1)
    return dop.astype(np.float32)


# ── m-chi Decomposition ───────────────────────────────────────────────────────

def mchi_decomposition(S0: np.ndarray, S1: np.ndarray,
                        S2: np.ndarray, S3: np.ndarray) -> dict:
    """
    Raney (2007) m-chi decomposition for compact polarimetry.

    Decomposes backscatter into three physical mechanisms:
      - Ps (surface/odd bounce)   → blue in RGB
      - Pd (double bounce)        → red in RGB
      - Pv (volume scattering)    → green in RGB   ← ice indicator

    Parameters
    ----------
    S0, S1, S2, S3 : Stokes bands

    Returns
    -------
    dict with keys: 'Ps', 'Pd', 'Pv', 'm', 'chi', 'rgb'
      'rgb' is shape (H, W, 3) uint8 false-colour image
    """
    S0_safe = np.where(S0 > 1e-12, S0, np.nan)

    # Degree of polarization m
    m = np.sqrt(S1 ** 2 + S2 ** 2 + S3 ** 2) / S0_safe

    # Ellipticity angle chi  (−45° to +45°)
    chi = 0.5 * np.arctan2(S3, np.sqrt(S1 ** 2 + S2 ** 2))   # radians

    # Power components
    Ps = 0.5 * S0 * (1 - m * np.sin(2 * chi))   # surface
    Pd = 0.5 * S0 * (1 - m * np.cos(2 * chi))   # double bounce — NOTE: corrected sign
    Pv = S0 * (1 - m)                             # volume (unpolarized)

    # Clamp negatives
    Ps = np.clip(Ps, 0, None)
    Pd = np.clip(Pd, 0, None)
    Pv = np.clip(Pv, 0, None)

    # False-colour RGB: R=Pd, G=Pv, B=Ps
    def _normalize(arr):
        vmin, vmax = np.nanpercentile(arr, 2), np.nanpercentile(arr, 98)
        return np.clip((arr - vmin) / (vmax - vmin + 1e-10), 0, 1)

    rgb = np.stack([
        (_normalize(Pd) * 255).astype(np.uint8),
        (_normalize(Pv) * 255).astype(np.uint8),
        (_normalize(Ps) * 255).astype(np.uint8),
    ], axis=-1)

    return {"Ps": Ps.astype(np.float32),
            "Pd": Pd.astype(np.float32),
            "Pv": Pv.astype(np.float32),
            "m": m.astype(np.float32),
            "chi": chi.astype(np.float32),
            "rgb": rgb}


# ── Ice Probability Map ───────────────────────────────────────────────────────

def compute_ice_probability(cpr: np.ndarray, dop: np.ndarray,
                             psr_mask: np.ndarray) -> np.ndarray:
    """
    Generate a continuous ice probability map [0, 1] by combining:
      - CPR score (higher CPR = more probable ice)
      - DOP score (lower DOP = more probable ice)
      - PSR mask (must be inside permanently shadowed region)

    Parameters
    ----------
    cpr      : CPR array (float32)
    dop      : DOP array (float32)
    psr_mask : binary mask (1 = PSR, 0 = illuminated)

    Returns
    -------
    ice_prob : float32 array in [0, 1]
    """
    # CPR score: sigmoid centred on threshold 1.0
    cpr_score = 1.0 / (1.0 + np.exp(-3.0 * (cpr - 1.0)))

    # DOP score: inverted sigmoid centred on threshold 0.13
    dop_score = 1.0 / (1.0 + np.exp(30.0 * (dop - 0.13)))

    # Combined score
    prob = 0.6 * cpr_score + 0.4 * dop_score

    # Zero outside PSR
    prob = np.where(psr_mask == 1, prob, 0.0)

    return np.clip(prob, 0, 1).astype(np.float32)


# ── Radiometric Calibration ───────────────────────────────────────────────────

def apply_radiometric_calibration(raw_dn: np.ndarray,
                                   cal_factor: float = 1.0) -> np.ndarray:
    """
    Convert raw DN values to sigma-naught backscatter coefficient.
    The calibration factor is instrument-specific and found in the
    DFSAR XML label file under <calibration_factor>.

    sigma0 (dB) = 10 * log10(DN^2 * cal_factor)
    """
    sigma0_linear = (raw_dn.astype(np.float64) ** 2) * cal_factor
    sigma0_linear[sigma0_linear <= 0] = np.nan
    sigma0_db = 10.0 * np.log10(sigma0_linear)
    return sigma0_db.astype(np.float32)
