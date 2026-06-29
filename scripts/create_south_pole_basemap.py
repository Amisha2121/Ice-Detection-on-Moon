"""
create_south_pole_basemap.py

Create proper south pole basemap from LOLA 118m DEM for dashboard.
This generates a hillshade/elevation visualization covering the full
south polar region where we have ice detection data.
"""

import os
import sys
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.enums import Resampling as ResamplingEnum
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from scipy.ndimage import gaussian_filter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LOLA = os.path.join(ROOT, "data", "raw", "lola")
PROCESSED = os.path.join(ROOT, "data", "processed")
DASHBOARD_OVERLAYS = os.path.join(ROOT, "dashboard", "data", "overlays")
os.makedirs(DASHBOARD_OVERLAYS, exist_ok=True)

# Target output size for dashboard
OUTPUT_SIZE = 4096  # Higher resolution to preserve ice detail

def clip_lola_to_south_pole():
    """Clip LOLA global DEM to south pole region."""
    print("\n[1/5] Clipping LOLA DEM to south pole region...")
    
    lola_path = os.path.join(RAW_LOLA, "lola_south_pole_118m.tif")
    if not os.path.exists(lola_path):
        print(f"  ERROR: LOLA DEM not found: {lola_path}")
        print("  Expected LOLA 118m global DEM")
        return None
    
    print(f"  Loading LOLA DEM: {os.path.basename(lola_path)}")
    
    with rasterio.open(lola_path) as src:
        print(f"  Full DEM shape: {src.shape}")
        print(f"  Full DEM bounds: {src.bounds}")
        print(f"  CRS: {src.crs}")
        
        # The global LOLA is in simple cylindrical (equirectangular)
        # We need to reproject to lunar south pole stereographic
        
        # Target: Moon 2000 South Pole Stereographic (ESRI:103878)
        # This matches our DFSAR ice detection data
        target_crs = 'PROJCS["Moon_2000_South_Pole_Stereographic",GEOGCS["GCS_Moon_2000",DATUM["D_Moon_2000",SPHEROID["Moon_2000_IAU_IAG",1737400,0]],PRIMEM["Reference_Meridian",0],UNIT["Degree",0.0174532925199433]],PROJECTION["Polar_Stereographic"],PARAMETER["latitude_of_origin",-90],PARAMETER["central_meridian",0],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",NORTH],AXIS["Northing",NORTH],AUTHORITY["ESRI","103878"]]'
        
        # Define target bounds in meters (south pole stereographic)
        # Cover region from -90° to roughly -80°S (about 400 km radius from pole)
        target_bounds = (-200000, -200000, 200000, 200000)  # 400x400 km centered on pole
        
        # Calculate transform for target
        target_transform = rasterio.transform.from_bounds(
            *target_bounds, OUTPUT_SIZE, OUTPUT_SIZE
        )
        
        # Create output array
        target_data = np.zeros((OUTPUT_SIZE, OUTPUT_SIZE), dtype=np.float32)
        
        print(f"  Reprojecting to South Pole Stereographic...")
        print(f"  Target bounds: {target_bounds} meters")
        print(f"  Target size: {OUTPUT_SIZE}x{OUTPUT_SIZE}")
        
        # Reproject
        reproject(
            source=rasterio.band(src, 1),
            destination=target_data,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            resampling=Resampling.bilinear
        )
        
        # Save reprojected DEM
        out_path = os.path.join(PROCESSED, "lola_south_pole_stereo.tif")
        
        profile = src.profile.copy()
        profile.update({
            'driver': 'GTiff',
            'height': OUTPUT_SIZE,
            'width': OUTPUT_SIZE,
            'transform': target_transform,
            'crs': target_crs,
            'dtype': 'float32',
            'count': 1,
            'compress': 'lzw'
        })
        
        with rasterio.open(out_path, 'w', **profile) as dst:
            dst.write(target_data, 1)
        
        print(f"  ✓ Reprojected DEM saved: {out_path}")
        print(f"  Elevation range: [{np.nanmin(target_data):.0f}, {np.nanmax(target_data):.0f}] m")
        
        return out_path, target_data, target_bounds, target_transform

def create_hillshade(dem_data):
    """Create hillshade from DEM for visualization."""
    print("\n[2/5] Creating hillshade...")
    
    # Replace NaN with mean
    valid_mask = ~np.isnan(dem_data)
    if np.sum(valid_mask) == 0:
        print("  WARNING: No valid elevation data!")
        return np.ones_like(dem_data) * 0.5
    
    mean_elev = np.nanmean(dem_data)
    dem_clean = dem_data.copy()
    dem_clean[~valid_mask] = mean_elev
    
    # Smooth slightly to reduce noise
    dem_smooth = gaussian_filter(dem_clean, sigma=1.0)
    
    # Create hillshade using light source
    ls = LightSource(azdeg=315, altdeg=45)
    hillshade = ls.hillshade(dem_smooth, vert_exag=2.0, dx=100, dy=100)
    
    print(f"  ✓ Hillshade created")
    return hillshade

def create_basemap_png(hillshade, dem_data, output_path):
    """Save hillshade as PNG for dashboard."""
    print("\n[3/5] Creating basemap PNG...")
    
    # Normalize hillshade to 0-1
    hillshade_norm = (hillshade - hillshade.min()) / (hillshade.max() - hillshade.min())
    
    # Apply slight contrast enhancement
    hillshade_enhanced = np.clip(hillshade_norm * 1.2, 0, 1)
    
    # Save as grayscale PNG
    plt.imsave(output_path, hillshade_enhanced, cmap='gray', vmin=0, vmax=1)
    
    print(f"  ✓ Basemap saved: {output_path}")
    return output_path

def create_ice_overlay(dem_bounds, dem_transform):
    """Create ice detection overlay at native resolution, then save metadata for proper alignment."""
    print("\n[4/5] Creating ice overlay...")
    
    ice_path = os.path.join(PROCESSED, "ice_probability_regional.tif")
    if not os.path.exists(ice_path):
        print(f"  WARNING: Ice data not found: {ice_path}")
        return None
    
    with rasterio.open(ice_path) as src:
        ice_data = src.read(1)
        ice_transform = src.transform
        ice_crs = src.crs
        ice_bounds = src.bounds
        
        print(f"  Ice data: {ice_data.shape}, {np.sum(ice_data > 0):,} pixels")
        print(f"  Ice native resolution: {ice_transform[0]:.1f}m")
        print(f"  Ice bounds: [{ice_bounds.left:.0f}, {ice_bounds.bottom:.0f}, {ice_bounds.right:.0f}, {ice_bounds.top:.0f}]")
        
        # Keep ice at native resolution (25m) - don't downsample
        # This preserves all 54,558 ice pixels
        ice_height, ice_width = ice_data.shape
        
        # Create RGBA overlay at native resolution
        overlay = np.zeros((ice_height, ice_width, 4), dtype=np.uint8)
        ice_mask = ice_data > 0
        
        if np.sum(ice_mask) > 0:
            # Cyan color for ice
            overlay[ice_mask, 0] = 80    # R
            overlay[ice_mask, 1] = 220   # G
            overlay[ice_mask, 2] = 255   # B
            overlay[ice_mask, 3] = 220   # Alpha
        
        # Save overlay at native resolution
        overlay_path = os.path.join(DASHBOARD_OVERLAYS, 'ice_detection_south_pole.png')
        plt.imsave(overlay_path, overlay)
        
        print(f"  ✓ Ice overlay saved: {overlay_path}")
        print(f"  ✓ Overlay size: {ice_width}x{ice_height} pixels (native 25m resolution)")
        print(f"  ✓ All {np.sum(ice_mask):,} ice pixels preserved")
        
        # Save ice-specific metadata for dashboard alignment
        ice_metadata = {
            'bounds_m': {
                'west': float(ice_bounds.left),
                'south': float(ice_bounds.bottom),
                'east': float(ice_bounds.right),
                'north': float(ice_bounds.top),
            },
            'size': [ice_width, ice_height],
            'resolution_m': abs(ice_transform[0]),
            'ice_pixels': int(np.sum(ice_mask)),
        }
        
        ice_meta_path = os.path.join(DASHBOARD_OVERLAYS, 'south_pole_ice_meta.json')
        import json
        with open(ice_meta_path, 'w') as f:
            json.dump(ice_metadata, f, indent=2)
        print(f"  ✓ Ice metadata saved: {ice_meta_path}")
        
        return overlay_path

def save_metadata(bounds, transform):
    """Save metadata for dashboard."""
    print("\n[5/5] Saving metadata...")
    
    import json
    
    metadata = {
        'bounds_m': {
            'west': float(bounds[0]),
            'south': float(bounds[1]),
            'east': float(bounds[2]),
            'north': float(bounds[3]),
        },
        'size': OUTPUT_SIZE,
        'resolution_m': (bounds[2] - bounds[0]) / OUTPUT_SIZE,
        'crs': 'ESRI:103878',
        'crs_name': 'Moon_2000_South_Pole_Stereographic',
    }
    
    meta_path = os.path.join(DASHBOARD_OVERLAYS, 'south_pole_meta.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"  ✓ Metadata saved: {meta_path}")
    return metadata

def main():
    print("\n" + "="*70)
    print("  CREATE SOUTH POLE BASEMAP FOR DASHBOARD")
    print("  Generating proper geographic basemap + ice overlay")
    print("="*70)
    
    # Step 1: Clip and reproject LOLA DEM
    result = clip_lola_to_south_pole()
    if result is None:
        return 1
    
    dem_path, dem_data, dem_bounds, dem_transform = result
    
    # Step 2: Create hillshade
    hillshade = create_hillshade(dem_data)
    
    # Step 3: Save basemap PNG
    basemap_path = os.path.join(DASHBOARD_OVERLAYS, 'south_pole_basemap_proper.png')
    create_basemap_png(hillshade, dem_data, basemap_path)
    
    # Step 4: Create ice overlay
    ice_overlay_path = create_ice_overlay(dem_bounds, dem_transform)
    
    # Step 5: Save metadata
    metadata = save_metadata(dem_bounds, dem_transform)
    
    print("\n" + "="*70)
    print("  ✓ SOUTH POLE BASEMAP COMPLETE")
    print("="*70)
    print(f"\n  Basemap: {basemap_path}")
    print(f"  Ice overlay: {ice_overlay_path}")
    print(f"  Coverage: {metadata['bounds_m']}")
    print(f"  Size: {OUTPUT_SIZE}x{OUTPUT_SIZE} pixels")
    print(f"  Resolution: ~{metadata['resolution_m']:.0f} m/pixel")
    print("\n  Next: Update dashboard to use new basemap\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
