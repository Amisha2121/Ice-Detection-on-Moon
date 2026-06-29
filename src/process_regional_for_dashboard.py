"""
process_regional_for_dashboard.py

Process regional ice detection data to create overlays that work with
the existing Shackleton-centered dashboard coordinate system.

Approach:
1. Use LOLA 118m global DEM as reference
2. Clip to south pole region that includes both Shackleton + regional data
3. Create ice overlay at same resolution/projection as Phase 1 dashboard
4. Export as PNG overlay compatible with existing Leaflet setup
"""

import os
import sys
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.transform import from_bounds
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
RAW_LOLA = os.path.join(ROOT, "data", "raw", "lola")
DASHBOARD_OVERLAYS = os.path.join(ROOT, "dashboard", "data", "overlays")

def process_regional_ice_for_dashboard():
    """
    Create dashboard-compatible ice overlay from regional detection.
    This expands the existing Shackleton view to show regional ice.
    """
    
    print("\n" + "="*70)
    print("  PROCESS REGIONAL ICE FOR DASHBOARD")
    print("="*70 + "\n")
    
    # Load Phase 2 regional ice
    ice_regional_path = os.path.join(PROCESSED, "ice_probability_regional.tif")
    if not os.path.exists(ice_regional_path):
        print(f"ERROR: Regional ice data not found: {ice_regional_path}")
        print("  Run: python src/run_regional_pipeline.py")
        return 1
    
    print("[1/3] Loading regional ice detection data...")
    with rasterio.open(ice_regional_path) as src:
        ice_data = src.read(1)
        ice_transform = src.transform
        ice_crs = src.crs
        ice_bounds = src.bounds
        
        print(f"  Ice data shape: {ice_data.shape}")
        print(f"  Ice pixels: {np.sum(ice_data > 0):,}")
        print(f"  Bounds: [{ice_bounds.left:.0f}, {ice_bounds.right:.0f}] x "
              f"[{ice_bounds.bottom:.0f}, {ice_bounds.top:.0f}] m")
        print(f"  CRS: {ice_crs}")
    
    # Create visualization
    print("\n[2/3] Creating ice overlay visualization...")
    
    # Create RGBA image where ice pixels are colored
    height, width = ice_data.shape
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    
    ice_mask = ice_data > 0
    
    if np.sum(ice_mask) > 0:
        # Color ice pixels (cyan/blue for ice)
        overlay[ice_mask, 0] = 100   # R
        overlay[ice_mask, 1] = 200   # G  
        overlay[ice_mask, 2] = 255   # B
        overlay[ice_mask, 3] = 200   # Alpha (semi-transparent)
        
        print(f"  Created overlay with {np.sum(ice_mask):,} ice pixels")
    
    # Save overlay as PNG
    overlay_path = os.path.join(DASHBOARD_OVERLAYS, "ice_regional_overlay.png")
    plt.imsave(overlay_path, overlay)
    print(f"  ✓ Saved: {overlay_path}")
    
    # Save metadata for dashboard
    print("\n[3/3] Saving metadata...")
    import json
    
    meta = {
        'bounds_m': {
            'west': float(ice_bounds.left),
            'east': float(ice_bounds.right),
            'south': float(ice_bounds.bottom),
            'north': float(ice_bounds.top),
        },
        'shape': [height, width],
        'crs': str(ice_crs),
        'ice_pixels': int(np.sum(ice_mask)),
        'resolution_m': 25,
    }
    
    meta_path = os.path.join(DASHBOARD_OVERLAYS, "regional_ice_meta.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"  ✓ Metadata saved: {meta_path}")
    
    print("\n" + "="*70)
    print("  ✓ REGIONAL ICE OVERLAY COMPLETE")
    print("="*70)
    print(f"\n  Ice pixels: {np.sum(ice_mask):,}")
    print(f"  Overlay: {overlay_path}")
    print(f"  Metadata: {meta_path}")
    print("\n  This creates a simple overlay. The dashboard shows Shackleton")
    print("  in detail. Regional expansion requires proper DEM co-registration.\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(process_regional_ice_for_dashboard())
