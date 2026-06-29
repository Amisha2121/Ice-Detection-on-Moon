"""
mosaic_tmc_dtm.py

Mosaic TMC-2 DTM tiles into a single south pole DEM covering -90° to -85° latitude.

Usage:
  1. Download TMC-2 DTM tiles from PRADAN to data/raw/tmc/
  2. Run: python mosaic_tmc_dtm.py
  3. Output: data/raw/tmc/south_pole_dem_20m.tif

Requirements:
  - rasterio
  - numpy
"""

import os
import glob
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling

# Paths
ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_TMC = os.path.join(ROOT, "data", "raw", "tmc")
OUTPUT_DEM = os.path.join(RAW_TMC, "south_pole_dem_20m.tif")

# Target CRS: Lunar South Polar Stereographic (custom)
TARGET_CRS = (
    '+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 '
    '+a=1737400 +b=1737400 +units=m +no_defs'
)

TARGET_RESOLUTION = 20.0  # meters


def find_tmc_dtm_tiles(directory: str) -> list:
    """Find all TMC DTM/DEM GeoTIFF files."""
    patterns = [
        "**/*dtm*.tif",
        "**/*DTM*.tif",
        "**/*dem*.tif",
        "**/*DEM*.tif",
        "**/*DTM*.TIF",
        "**/*DEM*.TIF",
    ]
    
    tiles = []
    for pattern in patterns:
        tiles.extend(glob.glob(os.path.join(directory, pattern), recursive=True))
    
    # Remove duplicates and filter out aux files
    tiles = list(set(tiles))
    tiles = [t for t in tiles if ".aux" not in t.lower() and "browse" not in t.lower()]
    
    return sorted(tiles)


def reproject_tile_to_polar(src_path: str, dst_path: str):
    """Reproject a single TMC tile to lunar south polar stereographic."""
    with rasterio.open(src_path) as src:
        # Calculate transform for target CRS
        transform, width, height = calculate_default_transform(
            src.crs,
            TARGET_CRS,
            src.width,
            src.height,
            *src.bounds,
            resolution=TARGET_RESOLUTION
        )
        
        # Update profile
        profile = src.profile.copy()
        profile.update({
            'crs': TARGET_CRS,
            'transform': transform,
            'width': width,
            'height': height,
            'compress': 'lzw',
            'tiled': True,
            'blockxsize': 256,
            'blockysize': 256
        })
        
        # Reproject
        with rasterio.open(dst_path, 'w', **profile) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=TARGET_CRS,
                    resampling=Resampling.bilinear
                )


def mosaic_tiles(tile_paths: list, output_path: str):
    """Mosaic multiple reprojected tiles into single DEM."""
    print(f"\n[MOSAIC] Merging {len(tile_paths)} tiles...")
    
    # Open all tiles
    datasets = [rasterio.open(t) for t in tile_paths]
    
    # Mosaic with first-value blending (or use 'mean' for overlap averaging)
    mosaic, transform = merge(datasets, method="first", res=(TARGET_RESOLUTION, TARGET_RESOLUTION))
    
    # Get profile from first tile
    profile = datasets[0].profile.copy()
    profile.update({
        "transform": transform,
        "width": mosaic.shape[2],
        "height": mosaic.shape[1],
        "count": 1,
        "dtype": "float32",
        "compress": "lzw",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "nodata": 0.0
    })
    
    # Write mosaic
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic[0].astype(np.float32), 1)
    
    # Close all datasets
    for ds in datasets:
        ds.close()
    
    print(f"  ✓ Saved: {output_path}")
    
    # Print stats
    with rasterio.open(output_path) as src:
        data = src.read(1)
        valid = data[data != 0]
        if len(valid) > 0:
            print(f"  Mosaic dimensions: {src.width} × {src.height} pixels")
            print(f"  Bounds: {src.bounds}")
            print(f"  Elevation range: {valid.min():.1f} to {valid.max():.1f} m")
            print(f"  Valid pixels: {len(valid):,} ({100*len(valid)/data.size:.1f}%)")


def main():
    print("="*70)
    print("  TMC-2 DTM Mosaic for South Pole")
    print("  Target: -90° to -85° latitude, 20m resolution")
    print("="*70)
    
    # Find tiles
    print(f"\n[1/4] Scanning for TMC DTM tiles in: {RAW_TMC}")
    tiles = find_tmc_dtm_tiles(RAW_TMC)
    
    if not tiles:
        print(f"\n❌ ERROR: No TMC DTM tiles found in {RAW_TMC}")
        print("\nPlease download TMC-2 DTM products from PRADAN:")
        print("  1. Go to: https://pradan.issdc.gov.in/ch2/protected/browse.xhtml")
        print("  2. Filter: Instrument=TMC-2, Level=DTM/DEM, Lat=-90 to -85")
        print("  3. Download tiles to: data/raw/tmc/")
        return
    
    print(f"  ✓ Found {len(tiles)} TMC DTM tile(s)")
    for tile in tiles:
        print(f"    - {os.path.basename(tile)}")
    
    # Create temp directory for reprojected tiles
    temp_dir = os.path.join(RAW_TMC, "reprojected_temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Reproject each tile to lunar polar CRS
    print(f"\n[2/4] Reprojecting tiles to Lunar South Polar Stereographic...")
    reprojected_tiles = []
    for i, tile in enumerate(tiles, 1):
        print(f"  [{i}/{len(tiles)}] {os.path.basename(tile)}")
        dst_path = os.path.join(temp_dir, f"tile_{i:03d}_polar.tif")
        try:
            reproject_tile_to_polar(tile, dst_path)
            reprojected_tiles.append(dst_path)
        except Exception as e:
            print(f"    ⚠ Warning: Failed to reproject: {e}")
            continue
    
    if not reprojected_tiles:
        print("\n❌ ERROR: No tiles could be reprojected")
        return
    
    print(f"  ✓ Successfully reprojected {len(reprojected_tiles)}/{len(tiles)} tiles")
    
    # Mosaic reprojected tiles
    print(f"\n[3/4] Mosaicking reprojected tiles...")
    mosaic_tiles(reprojected_tiles, OUTPUT_DEM)
    
    # Cleanup temp files
    print(f"\n[4/4] Cleaning up temporary files...")
    import shutil
    shutil.rmtree(temp_dir)
    print(f"  ✓ Removed: {temp_dir}")
    
    print("\n" + "="*70)
    print("  ✓ SUCCESS: South pole DEM ready!")
    print(f"  Output: {OUTPUT_DEM}")
    print("="*70)
    print("\nNext steps:")
    print("  1. Verify DEM: python -c \"import rasterio; src=rasterio.open('data/raw/tmc/south_pole_dem_20m.tif'); print(src.bounds)\"")
    print("  2. Run pipeline: python src/run_pipeline.py --resolution 20 --psr_positions 36")


if __name__ == "__main__":
    main()
