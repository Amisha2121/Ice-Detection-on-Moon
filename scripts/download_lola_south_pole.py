"""
download_lola_south_pole.py

Download LOLA Polar DTM (118m resolution) for lunar south pole region.
This provides geometric reference for co-registering DFSAR swaths.

Source: PDS Geosciences Node
Product: LOLA Polar DTM (118 m/px)
Coverage: South pole, -90° to -60°S
"""

import os
import sys
import requests
from tqdm import tqdm

# LOLA Polar DTM URL (PDS Geosciences Node)
LOLA_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-4-gdr-v1/lrolol_2xxx/data/lola_gdr/polar/jp2/south_polar/ldem_80s_118m.tif"

# Alternative: LOLA Global LDEM (lower resolution but faster)
LOLA_GLOBAL_URL = "https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "raw", "lola")
os.makedirs(OUT_DIR, exist_ok=True)

OUT_PATH = os.path.join(OUT_DIR, "lola_south_pole_118m.tif")


def download_file(url: str, output_path: str) -> bool:
    """Download file with progress bar."""
    try:
        print(f"\nDownloading from: {url}")
        print(f"Saving to: {output_path}\n")
        
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        
        print(f"\n✓ Download complete: {output_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n✗ Download failed: {e}")
        return False


def main():
    print("\n" + "="*70)
    print("  LOLA South Pole DEM Download")
    print("  118m resolution | PDS Geosciences Node")
    print("="*70)
    
    if os.path.exists(OUT_PATH):
        print(f"\n✓ File already exists: {OUT_PATH}")
        print("  Skipping download. Delete file to re-download.")
        return
    
    # Try primary URL first
    print("\nAttempting primary source (PDS South Polar DTM)...")
    success = download_file(LOLA_URL, OUT_PATH)
    
    # If primary fails, try global mosaic
    if not success:
        print("\nPrimary source failed. Trying alternative (USGS Global LDEM)...")
        success = download_file(LOLA_GLOBAL_URL, OUT_PATH)
    
    if success:
        file_size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
        print(f"\n✓ LOLA DEM ready: {file_size_mb:.1f} MB")
        print(f"  Location: {OUT_PATH}")
        print("\n  Next step: Run pipeline with regional DEM")
        print("  Command: python src\\run_pipeline.py --resolution 20")
    else:
        print("\n✗ Download failed from all sources.")
        print("\nManual download instructions:")
        print("1. Visit: https://ode.rsl.wustl.edu/moon/")
        print("2. Search for: LOLA Polar DTM")
        print("3. Download: ldem_80s_118m.tif")
        print(f"4. Place in: {OUT_DIR}")


if __name__ == "__main__":
    main()
