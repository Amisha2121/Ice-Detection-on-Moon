"""
prepare_regional_dem.py

Clip LOLA global DEM to south pole region and prepare for pipeline.
"""

import os
import sys
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
import numpy as np
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOLA_GLOBAL = os.path.join(ROOT, "data", "raw", "lola", "lola_south_pole_118m.tif")
LOLA_REGIONAL = os.path.join(ROOT, "data", "raw", "lola", "lola_south_pole_regional.tif")


def clip_to_south_pole(input_path: str, output_path: str, lat_min: float = -90.0, lat_max: float = -80.0):
    """Clip global LOLA to south pole region."""
    print(f"\n[CLIP] Extracting south pole region ({lat_min}° to {lat_max}°S)...")
    
    with rasterio.open(input_path) as src:
        print(f"  Input CRS: {src.crs}")
        print(f"  Input bounds: {src.bounds}")
        print(f"  Input size: {src.width} x {src.height}")
        
        # Create bounding box in lat/lon
        # LOLA is in degrees, south pole is negative latitude
        bbox = box(-180, lat_min, 180, lat_max)
        
        # Mask the raster
        out_image, out_transform = mask(src, [bbox], crop=True, all_touched=True)
        out_meta = src.meta.copy()
        
        out_meta.update({
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        })
        
        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(out_image)
    
    print(f"  ✓ Clipped DEM saved: {output_path}")
    
    with rasterio.open(output_path) as src:
        print(f"  Output size: {src.width} x {src.height}")
        print(f"  Output bounds: {src.bounds}")
    
    return output_path


def main():
    print("\n" + "="*70)
    print("  Prepare Regional LOLA DEM for South Pole")
    print("="*70)
    
    if not os.path.exists(LOLA_GLOBAL):
        print(f"\n✗ LOLA global DEM not found: {LOLA_GLOBAL}")
        print("  Run: python scripts/download_lola_south_pole.py")
        return
    
    if os.path.exists(LOLA_REGIONAL):
        print(f"\n✓ Regional DEM already exists: {LOLA_REGIONAL}")
        print("  Skipping preparation.")
        return
    
    # Clip to south pole (-90° to -80°S covers all your DFSAR swaths)
    clip_to_south_pole(LOLA_GLOBAL, LOLA_REGIONAL, lat_min=-90.0, lat_max=-80.0)
    
    print("\n" + "="*70)
    print("  ✓ Regional DEM Ready")
    print("="*70)
    print(f"\n  Location: {LOLA_REGIONAL}")
    print("\n  Next: Run regional pipeline")
    print("  Command: python src\\run_pipeline.py --resolution 20 --psr_positions 36")
    print("\n")


if __name__ == "__main__":
    main()
