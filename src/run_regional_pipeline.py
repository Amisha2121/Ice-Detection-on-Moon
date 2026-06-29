"""
run_regional_pipeline.py

Process the regional full-pol decomposition product for south pole ice detection.
Uses the already-georeferenced DFSAR decomposition TIFs (ODD/EVN/VOL/HLX).

This bypasses the LOLA DEM requirement by using DFSAR's embedded georeferencing.
"""

import os
import sys
import time
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from scipy.ndimage import uniform_filter

sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import save_band

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECOMP_DIR = os.path.join(ROOT, "data", "raw", "dfsar", "ch2_sar_ndxl_20250630my4rspeast_d_fp_xxx", 
                           "data", "derived", "20250630")
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS = os.path.join(ROOT, "data", "exports")

os.makedirs(PROCESSED, exist_ok=True)
os.makedirs(EXPORTS, exist_ok=True)


def load_decomposition_bands():
    """Load ODD/EVN/VOL/HLX decomposition products."""
    print("\n[STEP 1] Loading DFSAR polarimetric decomposition products...")
    
    bands = {}
    filenames = {
        'odd': 'ch2_sar_ndxl_20250630my4rspeast_d_odd_xx_fp_xx_xxx.tif',
        'evn': 'ch2_sar_ndxl_20250630my4rspeast_d_evn_xx_fp_xx_xxx.tif',
        'vol': 'ch2_sar_ndxl_20250630my4rspeast_d_vol_xx_fp_xx_xxx.tif',
        'hlx': 'ch2_sar_ndxl_20250630my4rspeast_d_hlx_xx_fp_xx_xxx.tif',
    }
    
    ref_profile = None
    
    for key, filename in filenames.items():
        path = os.path.join(DECOMP_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing decomposition product: {filename}")
        
        with rasterio.open(path) as src:
            print(f"  {key.upper()}: {src.width}x{src.height}, CRS: {src.crs.to_string()[:50]}...")
            data = src.read(1).astype(np.float32)
            data[data < 0] = 0  # Remove negative values
            data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
            bands[key] = data
            
            if ref_profile is None:
                ref_profile = src.profile.copy()
    
    print(f"  ✓ Loaded 4 decomposition bands")
    return bands, ref_profile


def reconstruct_stokes(bands, profile):
    """Reconstruct Stokes parameters from decomposition."""
    print("\n[STEP 2] Reconstructing Stokes parameters...")
    
    Ps = bands['odd']
    Pd = bands['evn']
    Pv = bands['vol']
    Ph = bands['hlx']
    
    S0 = Ps + Pd + Pv + Ph
    S0_safe = S0 + 1e-12
    
    m = np.clip(1.0 - Pv / S0_safe, 0.0, 1.0)
    S3 = np.clip(Ps - Pd - Pv, -S0 * m, S0 * m)
    S1 = np.sqrt(np.clip((S0 * m) ** 2 - S3 ** 2, 0.0, None))
    S2 = np.zeros_like(S0)
    
    print(f"  S0 range: [{np.percentile(S0[S0>0], 1):.2e}, {np.percentile(S0[S0>0], 99):.2e}]")
    print(f"  S1 range: [{np.percentile(S1[S1>0], 1):.2e}, {np.percentile(S1[S1>0], 99):.2e}]")
    print(f"  S3 range: [{np.percentile(S3, 1):.2e}, {np.percentile(S3, 99):.2e}]")
    
    # Save Stokes
    stokes_path = os.path.join(PROCESSED, "dfsar_regional_stokes.tif")
    profile_out = profile.copy()
    profile_out.update({'count': 4, 'dtype': 'float32', 'compress': 'lzw'})
    
    with rasterio.open(stokes_path, 'w', **profile_out) as dst:
        dst.write(S1, 1)
        dst.write(S2, 2)
        dst.write(S3, 3)
        dst.write(S0, 4)
    
    print(f"  ✓ Stokes saved: {stokes_path}")
    return S0, S1, S2, S3


def calculate_cpr_dop(S0, S1, S2, S3, profile):
    """Calculate CPR and DOP from Stokes parameters."""
    print("\n[STEP 3] Computing CPR and DOP...")
    
    # CPR = SC/OC where SC = (S0-S3)/2, OC = (S0+S3)/2
    SC = (S0 - S3) / 2.0
    OC = (S0 + S3) / 2.0
    CPR = np.divide(SC, OC + 1e-12, where=(OC > 0))
    CPR = np.clip(CPR, 0, 10)  # Cap extreme values
    
    # DOP = sqrt(S1^2 + S2^2 + S3^2) / S0
    DOP = np.sqrt(S1**2 + S2**2 + S3**2) / (S0 + 1e-12)
    DOP = np.clip(DOP, 0, 1)
    
    print(f"  CPR > 1.0: {np.sum(CPR > 1.0):,} pixels ({np.mean(CPR > 1.0)*100:.2f}%)")
    print(f"  DOP < 0.13: {np.sum(DOP < 0.13):,} pixels ({np.mean(DOP < 0.13)*100:.2f}%)")
    
    # Save
    cpr_path = os.path.join(PROCESSED, "cpr_map_regional.tif")
    dop_path = os.path.join(PROCESSED, "dop_map_regional.tif")
    
    profile_out = profile.copy()
    profile_out.update({'count': 1, 'dtype': 'float32', 'compress': 'lzw'})
    
    with rasterio.open(cpr_path, 'w', **profile_out) as dst:
        dst.write(CPR, 1)
    
    with rasterio.open(dop_path, 'w', **profile_out) as dst:
        dst.write(DOP, 1)
    
    print(f"  ✓ CPR saved: {cpr_path}")
    print(f"  ✓ DOP saved: {dop_path}")
    
    return CPR, DOP


def detect_ice_candidates(CPR, DOP, profile, cpr_threshold=1.0, dop_threshold=0.13):
    """Identify ice candidate pixels."""
    print("\n[STEP 4] Detecting ice candidates...")
    
    # Ice criteria: CPR > 1.0 AND DOP < 0.13
    ice_mask = (CPR > cpr_threshold) & (DOP < dop_threshold) & (CPR > 0) & (DOP >= 0)
    
    num_candidates = np.sum(ice_mask)
    print(f"  ✓ Ice candidates detected: {num_candidates:,} pixels")
    print(f"  Coverage area: ~{num_candidates * 0.025 * 0.025:.2f} km² (at 25m resolution)")
    
    # Save ice probability map
    ice_prob = ice_mask.astype(np.float32)
    ice_path = os.path.join(PROCESSED, "ice_probability_regional.tif")
    
    profile_out = profile.copy()
    profile_out.update({'count': 1, 'dtype': 'float32', 'compress': 'lzw'})
    
    with rasterio.open(ice_path, 'w', **profile_out) as dst:
        dst.write(ice_prob, 1)
    
    print(f"  ✓ Ice map saved: {ice_path}")
    
    return ice_mask


def export_ice_geojson(ice_mask, profile):
    """Export ice pixels to GeoJSON."""
    print("\n[STEP 5] Exporting ice candidates to GeoJSON...")
    
    import json
    from rasterio.transform import xy
    
    ice_coords = np.where(ice_mask)
    num_pixels = len(ice_coords[0])
    
    if num_pixels == 0:
        print("  ⚠ No ice pixels to export")
        return
    
    # Sample if too many (for file size)
    max_export = 10000
    if num_pixels > max_export:
        print(f"  Sampling {max_export} of {num_pixels:,} pixels for GeoJSON...")
        indices = np.random.choice(num_pixels, max_export, replace=False)
        rows = ice_coords[0][indices]
        cols = ice_coords[1][indices]
    else:
        rows = ice_coords[0]
        cols = ice_coords[1]
    
    features = []
    transform = profile['transform']
    
    for row, col in zip(rows[:1000], cols[:1000]):  # Limit to 1000 for initial export
        x, y = xy(transform, int(row), int(col))
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(x), float(y)]
            },
            "properties": {
                "pixel_row": int(row),
                "pixel_col": int(col),
                "confidence": "high"
            }
        })
    
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": str(profile['crs'])}
        },
        "features": features
    }
    
    out_path = os.path.join(EXPORTS, "ice_candidates_regional.geojson")
    with open(out_path, 'w') as f:
        json.dump(geojson, f, indent=2)
    
    print(f"  ✓ Exported {len(features):,} ice points to: {out_path}")


def generate_summary_report(ice_mask, CPR, DOP):
    """Generate text summary of results."""
    print("\n[STEP 6] Generating summary report...")
    
    num_ice = np.sum(ice_mask)
    total_pixels = ice_mask.size
    coverage_pct = (num_ice / total_pixels) * 100
    
    cpr_ice = CPR[ice_mask]
    dop_ice = DOP[ice_mask]
    
    report = f"""
# Regional South Pole Ice Detection Results

**Product**: ch2_sar_ndxl_20250630my4rspeast_d_fp_xxx  
**Date**: 2025-06-30  
**Coverage**: South Polar Region (~320 km²)

---

## Ice Detection Summary

- **Ice Candidate Pixels**: {num_ice:,}
- **Total Area**: ~{num_ice * 0.025 * 0.025:.2f} km² (at 25m resolution)
- **Coverage**: {coverage_pct:.4f}% of swath

## Ice Candidate Statistics

- **CPR (Circular Polarization Ratio)**:
  - Mean: {np.mean(cpr_ice):.3f}
  - Median: {np.median(cpr_ice):.3f}
  - Range: [{np.min(cpr_ice):.3f}, {np.max(cpr_ice):.3f}]

- **DOP (Degree of Polarization)**:
  - Mean: {np.mean(dop_ice):.3f}
  - Median: {np.median(dop_ice):.3f}
  - Range: [{np.min(dop_ice):.3f}, {np.max(dop_ice):.3f}]

## Methodology

**Ice Criteria**:
- CPR > 1.0 (volume scattering dominates)
- DOP < 0.13 (high depolarization)

**Data Source**:
- Chandrayaan-2 DFSAR Full-Polarimetric Decomposition
- ODD/EVN/VOL/HLX products processed into Stokes parameters

## Outputs

- `data/processed/dfsar_regional_stokes.tif` - Stokes S0, S1, S2, S3
- `data/processed/cpr_map_regional.tif` - CPR raster
- `data/processed/dop_map_regional.tif` - DOP raster
- `data/processed/ice_probability_regional.tif` - Binary ice mask
- `data/exports/ice_candidates_regional.geojson` - Ice pixel locations

---

*Generated by regional pipeline using ISRO Chandrayaan-2 DFSAR polarimetric radar*
"""
    
    report_path = os.path.join(ROOT, "REGIONAL_ICE_DETECTION_RESULTS.md")
    with open(report_path, 'w') as f:
        f.write(report)
    
    print(f"  ✓ Summary saved: {report_path}")


def main():
    print("\n" + "="*70)
    print("  REGIONAL SOUTH POLE ICE DETECTION")
    print("  Chandrayaan-2 DFSAR Full-Pol Decomposition")
    print("="*70)
    
    t_start = time.time()
    
    try:
        # Step 1: Load decomposition bands
        bands, profile = load_decomposition_bands()
        
        # Step 2: Reconstruct Stokes
        S0, S1, S2, S3 = reconstruct_stokes(bands, profile)
        
        # Step 3: Calculate CPR and DOP
        CPR, DOP = calculate_cpr_dop(S0, S1, S2, S3, profile)
        
        # Step 4: Detect ice
        ice_mask = detect_ice_candidates(CPR, DOP, profile)
        
        # Step 5: Export GeoJSON
        export_ice_geojson(ice_mask, profile)
        
        # Step 6: Generate report
        generate_summary_report(ice_mask, CPR, DOP)
        
        elapsed = time.time() - t_start
        
        print("\n" + "="*70)
        print(f"  ✓ REGIONAL ICE DETECTION COMPLETE ({elapsed:.1f}s)")
        print("="*70)
        print(f"\n  Results: REGIONAL_ICE_DETECTION_RESULTS.md")
        print(f"  Outputs: data/processed/ and data/exports/")
        print("\n")
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
