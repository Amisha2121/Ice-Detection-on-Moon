"""
download_tmc_dtm_helper.py

Helper script to generate PRADAN search URLs for TMC-2 DTM download.
Since PRADAN limits searches to 5°×5°, this generates all required queries.

Usage:
  python scripts/download_tmc_dtm_helper.py

Output:
  - Prints all PRADAN search URLs to copy-paste into browser
  - Creates download_urls.txt with all URLs
"""

import os

# PRADAN base URL for Chandrayaan-2 data
PRADAN_BASE = "https://pradan.issdc.gov.in/ch2/protected/browse.xhtml"

# South pole coverage
LAT_MIN = -90
LAT_MAX = -85
LON_MIN = -180
LON_MAX = 180
STEP = 5  # PRADAN's 5° limit

def generate_search_urls():
    """Generate all PRADAN search URLs for south pole TMC-2 DTM."""
    
    urls = []
    search_num = 1
    
    print("="*80)
    print("  TMC-2 DTM DOWNLOAD HELPER")
    print("  Generating PRADAN search URLs for South Pole (-90° to -85°)")
    print("="*80)
    print()
    
    # Iterate through longitude bins
    for lon_start in range(LON_MIN, LON_MAX, STEP):
        lon_end = lon_start + STEP
        
        # Create search description
        search_desc = f"Search {search_num:3d}: Lat {LAT_MIN:4d}° to {LAT_MAX:3d}°, Lon {lon_start:4d}° to {lon_end:4d}°"
        
        # PRADAN search parameters (you'll need to manually apply these filters)
        search_params = {
            "instrument": "TMC or TMC-2",
            "level": "Level 3 or Level 4 (DTM/DEM)",
            "lat_min": LAT_MIN,
            "lat_max": LAT_MAX,
            "lon_min": lon_start,
            "lon_max": lon_end
        }
        
        urls.append({
            "num": search_num,
            "desc": search_desc,
            "params": search_params
        })
        
        search_num += 1
    
    return urls


def print_instructions(urls):
    """Print download instructions."""
    
    print(f"\n📋 TOTAL SEARCHES NEEDED: {len(urls)}")
    print()
    print("="*80)
    print("  INSTRUCTIONS")
    print("="*80)
    print()
    print("1. Open PRADAN in your browser:")
    print(f"   {PRADAN_BASE}")
    print()
    print("2. Log in with your PRADAN credentials")
    print()
    print("3. Set these FIXED filters (apply to ALL searches):")
    print("   ✓ Instrument: TMC or TMC-2")
    print("   ✓ Processing Level: Level 3 or Level 4")
    print("   ✓ Product Type: DTM or DEM (Digital Terrain Model)")
    print("   ✓ Latitude: -90 to -85  ← FIXED for all searches")
    print()
    print("4. For EACH search below, change ONLY the Longitude range:")
    print()
    
    # Print first 10 as examples
    print("="*80)
    print("  SEARCH QUERIES (Longitude bins)")
    print("="*80)
    print()
    
    for i, url in enumerate(urls[:10], 1):
        print(f"{url['desc']}")
        print(f"   → Set Longitude: {url['params']['lon_min']}° to {url['params']['lon_max']}°")
        print(f"   → Click 'Search'")
        print(f"   → Download all tiles found")
        print()
    
    if len(urls) > 10:
        print(f"... ({len(urls)-10} more searches)")
        print()
        print("TIP: Due to polar convergence, you might not need all 72 searches.")
        print("     If a longitude bin returns 0 results, skip nearby bins.")
    
    print()
    print("="*80)
    print("  SAVING TO FILE")
    print("="*80)
    print()
    
    # Save to file
    output_file = "download_urls.txt"
    with open(output_file, "w") as f:
        f.write("TMC-2 DTM DOWNLOAD CHECKLIST\n")
        f.write("="*80 + "\n\n")
        f.write(f"PRADAN URL: {PRADAN_BASE}\n\n")
        f.write("FIXED FILTERS FOR ALL SEARCHES:\n")
        f.write("  - Instrument: TMC or TMC-2\n")
        f.write("  - Level: Level 3 or Level 4\n")
        f.write("  - Product Type: DTM/DEM\n")
        f.write("  - Latitude: -90 to -85\n\n")
        f.write("LONGITUDE RANGES (change for each search):\n")
        f.write("="*80 + "\n\n")
        
        for url in urls:
            f.write(f"[ ] {url['desc']}\n")
            f.write(f"    Longitude: {url['params']['lon_min']}° to {url['params']['lon_max']}°\n")
            f.write(f"    Download to: data/raw/tmc/\n\n")
    
    print(f"✓ Search checklist saved to: {output_file}")
    print(f"  Use this file to track your progress (check off [ ] as you download)")
    print()
    print("="*80)
    print("  AFTER DOWNLOADING")
    print("="*80)
    print()
    print("Once you have downloaded TMC DTM tiles to data/raw/tmc/:")
    print()
    print("  1. Verify tiles: dir data\\raw\\tmc\\*.tif")
    print("  2. Mosaic tiles: python scripts/mosaic_tmc_dtm.py")
    print("  3. Run pipeline: python src/run_pipeline.py --resolution 20 --psr_positions 36")
    print()


def main():
    urls = generate_search_urls()
    print_instructions(urls)
    
    print("="*80)
    print("  QUICK START (if TMC DTM doesn't exist on PRADAN)")
    print("="*80)
    print()
    print("If TMC-2 DTM products don't exist on PRADAN, you have 2 options:")
    print()
    print("Option A: Use LOLA south pole mosaic (NASA data)")
    print("  - Faster, but not ISRO data")
    print("  - Check with hackathon organizers if NASA data is allowed")
    print()
    print("Option B: Generate DEM from OHRC stereo pairs")
    print("  - 100% ISRO data")
    print("  - Requires ASP (Ames Stereo Pipeline)")
    print("  - 3-5 hours processing time")
    print("  - You have 368 TMC product IDs in reference_data/")
    print()
    print("Contact me if TMC DTM is not available on PRADAN.")
    print()


if __name__ == "__main__":
    main()
