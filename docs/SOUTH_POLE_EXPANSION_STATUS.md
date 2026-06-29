# South Pole Expansion — Current Status & Next Steps

**Date**: June 29, 2026  
**Objective**: Expand from Shackleton (16×16 km) to entire south pole coverage

---

## ✅ GOOD NEWS: You Have the Right DFSAR Data!

### Discovered Data Assets
Located in `data/raw/dfsar/`:

- **11 Compact-Polarimetry products** (_d_cp_n18) ✅
- **2 Full-Polarimetry products** (_d_fp_xxx) ✅

**These support proper ice detection!** Your pipeline already has code to handle compact-pol (LH+LV channels) → can derive CPR/DOP correctly.

### DFSAR Product List (already extracted):
```
ch2_sar_ncxl_20250917t163359347_d_cp_n18/
ch2_sar_nrxl_20250917t163359347_d_cp_n18/
ch2_sar_nrxl_20250918t160856477_d_cp_n18/
ch2_sar_nrxl_20251006t052537568_d_cp_n18/
ch2_sar_nrxl_20251006t151527671_d_cp_n18/
ch2_sar_nrxl_20251006t171326188_d_cp_n18/
ch2_sar_nrxl_20251006t191123640_d_cp_n18/
ch2_sar_nrxl_20251006t210921252_d_cp_n18/
ch2_sar_ndxl_20250630my4rnpwest_d_fp_xxx/
ch2_sar_ndxl_20250630my4rspeast_d_fp_xxx/
+ 3 more zip files to extract
```

These swaths cover multiple passes over the south pole — perfect for regional mosaicking!

---

## ❌ BLOCKER: Need South Pole DEM

### Current Situation
**Current DEM**: `data/raw/lola/Site04_final_adj_5mpp_surf.tif`
- Only covers 16×16 km around Shackleton
- Source: NASA LOLA (may violate "ISRO only" hackathon rule)
- **Problem**: DFSAR swaths overlap check fails → pipeline rejects 10+ products as "no overlap"

### What You Need
**South Pole DEM from ISRO Chandrayaan-2**
- Coverage: -90° to -85° latitude (entire south pole)
- Resolution: 20m is sufficient for regional scale (5m would be 100GB+ memory)
- Source: TMC-2 DTM products from PRADAN

---

## 🎯 IMMEDIATE ACTION REQUIRED

### Step 1: Download TMC-2 DTM from PRADAN

**Portal**: https://pradan.issdc.gov.in/ch2/protected/browse.xhtml

**Filters to apply**:
1. **Instrument**: TMC or TMC-2
2. **Processing Level**: Level 3 or Level 4 (DTM/DEM products)
3. **Data Type**: Search for "DTM" or "DEM" in product type
4. **Spatial Coverage**:
   - Latitude: -90 to -85 (south pole)
   - Longitude: -180 to 180 (full circumference)
   
**Important**: PRADAN limits searches to 5° × 5° areas. You'll need to make **multiple queries**:
- Search 1: Lat -90 to -85, Lon -180 to -175
- Search 2: Lat -90 to -85, Lon -175 to -170
- ... continue for all longitude bins ...
- Search 72: Lat -90 to -85, Lon 175 to 180

**Estimate**: ~36-72 DTM tiles covering south pole (polar convergence reduces number needed)

**Save to**: `data/raw/tmc/` (create this folder if it doesn't exist)

---

### Step 2: Mosaic DTM Tiles

Once downloaded, combine tiles into single south pole DEM:

```python
# Create mosaic script: mosaic_tmc_dtm.py
import glob
import rasterio
from rasterio.merge import merge

# Find all TMC DTM tiles
tiles = glob.glob("data/raw/tmc/**/*.tif", recursive=True)
print(f"Found {len(tiles)} TMC DTM tiles")

# Open all tiles
datasets = [rasterio.open(t) for t in tiles]

# Mosaic with average blending in overlap regions
mosaic, transform = merge(datasets, method="first", res=(20, 20))

# Save merged DEM
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
    "blockysize": 256
})

with rasterio.open("data/raw/tmc/south_pole_dem_20m.tif", "w", **profile) as dst:
    dst.write(mosaic[0], 1)

print("✓ Saved: data/raw/tmc/south_pole_dem_20m.tif")

# Close all datasets
for ds in datasets:
    ds.close()
```

**Run**:
```bash
python mosaic_tmc_dtm.py
```

---

### Step 3: Update Pipeline Configuration

Modify `src/01_data_ingestion.py` to use TMC DEM instead of LOLA:

**Find** (around line 380):
```python
lola_path = find_lola_dem(RAW_LOLA)
```

**Replace with**:
```python
# Try TMC DEM first (ISRO data), fall back to LOLA
RAW_TMC = os.path.join(ROOT, "data", "raw", "tmc")
tmc_dem = os.path.join(RAW_TMC, "south_pole_dem_20m.tif")
if os.path.exists(tmc_dem):
    lola_path = tmc_dem
    print(f"[DEM] Using TMC south pole DEM: {tmc_dem}")
else:
    lola_path = find_lola_dem(RAW_LOLA)
    print(f"[DEM] Fallback to LOLA DEM: {lola_path}")
```

---

### Step 4: Run Regional Pipeline

```bash
# Process entire south pole at 20m resolution
python src/run_pipeline.py --resolution 20 --psr_positions 36

# Generate dashboard overlays
python src/generate_map_overlays.py

# Export to dashboard
python src/export_for_dashboard.py

# View results
python -m http.server 8080 --directory dashboard
# Open http://localhost:8080
```

**Expected runtime**: 1-2 hours (depends on number of DFSAR swaths processed)

---

## Expected Results After Expansion

✅ **Ice detection across entire south pole** (not just Shackleton)  
✅ **Multiple DSCs identified** in various craters  
✅ **Regional-scale landing sites** ranked by science value  
✅ **Long-range rover traverses** connecting multiple DSCs  
✅ **Meaningful ice volume estimates** from PSR regions  
✅ **Satisfies hackathon "whole southern pole" requirement**

---

## Alternative: Quick Partial Expansion (if time is limited)

If downloading/processing full south pole takes too long, you can do a **4-crater demonstration**:

### Target Craters
1. **Shackleton** (89.9°S, 0°E) — already done
2. **Faustini** (87.3°S, 77°E) — known ice-bearing DSC
3. **Haworth** (87.4°S, 5°E) — large PSR crater
4. **Shoemaker** (88.1°S, 45°E) — deep DSC

### Quick Process
1. Find which 3-4 DFSAR swaths cover these craters (check XML corner coords)
2. Download only 8-12 TMC DTM tiles covering these regions
3. Mosaic into 4-crater DEM
4. Run pipeline on 4-crater AOI

**Timeline**: 2-3 hours instead of 4-6 hours  
**Benefit**: Still demonstrates regional capability, shows ice in multiple DSCs

---

## Questions?

**Q: Which TMC product types should I download?**  
A: Look for "DTM" (Digital Terrain Model) or "DEM" products. These are Level 3/4 processed elevation models. Avoid raw images (_d_img_) — those need stereo processing.

**Q: How do I know which TMC tiles cover the south pole?**  
A: Use PRADAN's spatial filter: Latitude -90 to -85. Any tiles returned by this query cover the pole.

**Q: Can I use LOLA DEM for a larger area?**  
A: LOLA has south pole coverage, but it's NASA data. Hackathon says "ISRO only", so TMC-2 is safer. If judges allow NASA data, you can download LOLA's south pole mosaic (LOLA_POLAR_DTM) instead.

**Q: What if TMC DTM doesn't exist?**  
A: Worst case, you'll need to generate DEM from OHRC stereo pairs (you have 368 TMC image IDs listed). This requires ASP (Ames Stereo Pipeline) or custom photogrammetry — much more complex.

---

## Timeline Estimate

| Task | Time |
|------|------|
| Download TMC DTM tiles | 1-2 hours |
| Mosaic tiles into south pole DEM | 30 min |
| Modify pipeline scripts | 30 min |
| Run regional pipeline | 1-2 hours |
| Regenerate dashboard | 30 min |
| **TOTAL** | **4-6 hours** |

---

## Ready to Start?

**Next command**: Go to PRADAN and start downloading TMC-2 DTM tiles!

Once you have the tiles, run:
```bash
mkdir data\raw\tmc
# (extract TMC tiles here)
python mosaic_tmc_dtm.py
python src/run_pipeline.py --resolution 20 --psr_positions 36
```

---

**Updated**: June 29, 2026  
**Contact**: Kiro AI Assistant
