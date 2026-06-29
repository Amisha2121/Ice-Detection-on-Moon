# South Pole Expansion - Implementation Plan

## OBJECTIVE: Expand from Shackleton (16×16 km) to Entire South Pole

### Current Status (June 29, 2026)
- ✅ Shackleton crater dashboard working at 100% (37 ice pixels, 3 landing sites, 27.2 km traverse)
- ✅ Successfully pushed to GitHub
- ✅ Downloaded **11 DFSAR compact-pol products** (_d_cp_n18) covering south pole regions
- ✅ Downloaded **2 full-pol products** (_d_fp_xxx) near south pole
- ⚠️ **Need: South pole DEM from TMC-2 or OHRC stereo** (current LOLA DEM only covers Shackleton 16×16 km)
- ⚠️ **Must use ONLY ISRO data** (Chandrayaan-2) per hackathon rules

### Problem Statement Requirements (from hackathon):
1. ✅ **Detect subsurface ice** using DFSAR + OHRC data (framework complete)
2. ✅ **Select landing sites** near scientifically relevant targets (working)
3. ⚠️ **Cover entire southern pole** - NOT just Shackleton (needs expansion)
4. ❌ **Regional-scale DEM** - current LOLA DEM too small (need TMC-2 DTM or OHRC-derived DEM)

## Available Data Inventory

### ✅ DFSAR Products (13 total)
Located in `data/raw/dfsar/`:

**Compact-Polarimetry (CP) — 11 products:**
- `ch2_sar_ncxl_20250917t163359347_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20250917t163359347_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20250918t160856477_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20251006t052537568_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20251006t151527671_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20251006t171326188_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20251006t191123640_d_cp_n18` (extracted)
- `ch2_sar_nrxl_20251006t210921252_d_cp_n18` (extracted)
- Plus 3 more zip files to extract

**Full-Polarimetry (FP) — 2 products:**
- `ch2_sar_ndxl_20250630my4rnpwest_d_fp_xxx` (extracted)
- `ch2_sar_ndxl_20250630my4rspeast_d_fp_xxx` (extracted)

**Status**: ✅ **These products support proper CPR/DOP ice detection!**
- Compact-pol provides LH+LV channels → can derive Stokes parameters
- Full-pol provides complete polarimetric information
- Current pipeline already has code to handle these (see `_ingest_compact_pol_products()`)

### ❌ DEM Coverage Issue

**Current DEM**: `data/raw/lola/Site04_final_adj_5mpp_surf.tif`
- **Coverage**: Only 16×16 km around Shackleton crater (89.9°S)
- **Source**: NASA LOLA (not ISRO — may violate hackathon rules!)
- **Problem**: DFSAR swaths cover entire south pole, but DEM doesn't → pipeline rejects products as "no overlap"

**Required DEM**: Entire south pole coverage from **ISRO Chandrayaan-2 only**
- **Option 1**: Download TMC-2 DTM (Digital Terrain Model) from PRADAN covering -90° to -85° latitude
- **Option 2**: Generate DEM from OHRC stereo pairs (368 TMC products listed in `TMC368_Product_IDs.txt`)

## Implementation Plan: South Pole Expansion

### PHASE 1: Get South Pole DEM (CRITICAL — BLOCKS EVERYTHING)

#### Option A: Download TMC-2 DTM from PRADAN (RECOMMENDED — fastest)
**Steps:**
1. Go to https://pradan.issdc.gov.in/ch2/protected/browse.xhtml
2. Select "TMC-2" instrument
3. Filter by **Processing Level** = "DTM" or "DEM" (Level 3/4 products)
4. **Spatial filter**: Latitude -90 to -85, Longitude -180 to 180
   - Note: PRADAN limits search to 5° × 5° at a time
   - Must make multiple queries: (-90,-85) × (-180,-175), (-90,-85) × (-175,-170), etc.
5. Download all south pole DTM tiles to `data/raw/tmc/`
6. Mosaic tiles into single GeoTIFF covering -90° to -85° latitude

**Expected products:**
- Multiple tiles like `ch2_tmc2_YYYYMMDD_dtm_*.tif`
- Each tile covers 5° × 5° region
- Need ~36 tiles to cover entire south pole (360° longitude / 5° = 72, but polar convergence reduces this)

#### Option B: Generate DEM from OHRC Stereo (BACKUP — slower, more complex)
**Requirements:**
- 368 TMC product IDs already identified in `TMC368_Product_IDs.txt`
- Need stereo processing pipeline (ASP or custom photogrammetry)
- Time-intensive: 3-5 hours for stereo matching + mosaicking

**Why Option A is better:**
- TMC-2 DTM is official ISRO product (already processed)
- Faster: download + mosaic vs. stereo processing
- Official DTM has better accuracy (ground-controlled)

### PHASE 2: Modify Pipeline for Regional Processing

Once south pole DEM is ready, update pipeline scripts:

#### 2A: Update `src/01_data_ingestion.py` — Multi-Swath Mosaic
**Current behavior:**
- Loads single LOLA DEM (16×16 km)
- Checks each DFSAR swath for overlap
- Rejects swaths outside DEM bounds → only 1-2 swaths used

**Required changes:**
```python
# Around line 50, remove hard-coded target_bounds
# Let the DEM define the AOI automatically:

def ingest_lola_dem(lola_path: str, out_path: str) -> str:
    """Reproject LOLA DEM (or TMC DTM) to lunar polar CRS."""
    print(f"\n[DEM] Reprojecting: {os.path.basename(lola_path)}")
    reproject_to_lunar_polar(lola_path, out_path, resolution_m=20.0)  # ← Change to 20m for performance
    print(f"  Saved: {out_path}")
    return out_path
```

**Enable multi-swath mosaicking:**
- Current code already has `mosaic_dfsar_products()` at line ~200
- Enable it to mosaic all overlapping CP products:
  ```python
  overlapping = [p for p in products if _check_dfsar_overlap(p, ref_path)]
  if len(overlapping) > 1:
      # Mosaic all CP products covering south pole
      result = _ingest_compact_pol_products_multi(overlapping, ref_path, ref_profile)
  ```

#### 2B: Adjust Resolution for Performance
**Problem**: 5m resolution × entire south pole = huge arrays (100GB+ memory)

**Solution**: Use 20m or 50m resolution for regional processing
```python
# src/run_pipeline.py — add resolution argument
parser.add_argument("--resolution", type=int, default=20,
                    help="DEM resolution in meters (5 for local, 20 for regional)")

# Pass to ingestion:
extra = {"resolution_m": args.resolution}
```

**Memory estimate:**
- 5m resolution, 500 km × 500 km → 100 million pixels → 400 MB per band × 4 bands = 1.6 GB
- 20m resolution, 500 km × 500 km → 6.25 million pixels → 25 MB per band × 4 bands = 100 MB ✅

#### 2C: PSR Mapping — Reduce Sun Positions for Speed
**Current**: 100 solar positions (accurate but slow for large areas)

**For regional processing**:
```bash
python src/run_pipeline.py --resolution 20 --psr_positions 36
```
- 36 positions = 10° increments around sun's polar orbit
- Fast enough for 500+ km² areas
- Still captures PSR regions accurately

#### 2D: Update Dashboard Map Bounds
**Current**: `dashboard/app.js` hard-coded to Shackleton bounds

**Update `src/generate_map_overlays.py`:**
```python
# Around line 400, make bounds dynamic:
with rasterio.open(dem_path) as src:
    bounds = src.bounds
    # Write to dashboard/data/overlays/meta.json
    meta = {
        "bounds": [[bounds.bottom, bounds.left], [bounds.top, bounds.right]],
        "center": [(bounds.bottom + bounds.top)/2, (bounds.left + bounds.right)/2],
        "zoom": 8  # Adjust for regional scale
    }
```

Then update `dashboard/app.js` to read bounds from meta.json instead of hard-coding.

### PHASE 3: Execute Regional Pipeline

Once DEM and code updates are complete:

```bash
# Step 1: Extract remaining DFSAR zip files (if any)
python -c "import zipfile, glob; [zipfile.ZipFile(z).extractall('data/raw/dfsar/') for z in glob.glob('data/raw/dfsar/*.zip')]"

# Step 2: Run full regional pipeline at 20m resolution
python src/run_pipeline.py --resolution 20 --psr_positions 36

# Step 3: Generate dashboard overlays
python src/generate_map_overlays.py

# Step 4: Export data to dashboard
python src/export_for_dashboard.py

# Step 5: View results
python -m http.server 8080 --directory dashboard
# Open http://localhost:8080
```

**Expected outcomes:**
- ✅ Ice detection across entire south pole (not just Shackleton)
- ✅ Multiple DSCs identified in various craters (Shackleton, Faustini, Haworth, etc.)
- ✅ Regional-scale landing site ranking
- ✅ Traverse paths connecting multiple DSCs
- ✅ Meaningful ice volume estimates from DSC regions

---

## Timeline Estimate

| Phase | Task | Time | Priority |
|-------|------|------|----------|
| 1 | Download TMC-2 DTM tiles from PRADAN | 1-2 hours | 🔴 CRITICAL |
| 1 | Mosaic DTM tiles into south pole DEM | 30 min | 🔴 CRITICAL |
| 2A | Modify `01_data_ingestion.py` for multi-swath | 30 min | 🟡 HIGH |
| 2B | Add resolution parameter to pipeline | 15 min | 🟡 HIGH |
| 2C | Test with 20m resolution | 30 min | 🟡 HIGH |
| 2D | Update dashboard bounds to be dynamic | 20 min | 🟢 MEDIUM |
| 3 | Run full regional pipeline | 1-2 hours | 🟡 HIGH |
| 3 | Verify results & regenerate dashboard | 30 min | 🟡 HIGH |
| | **TOTAL** | **4-6 hours** | |

---

## Next Steps (Immediate Actions)

1. **Download TMC-2 DTM from PRADAN** — this is the blocker for everything else
   - Use filter: Instrument=TMC-2, Level=DTM/DEM, Lat=-90 to -85
   - Multiple 5°×5° tile queries needed (PRADAN search limit)
   - Save to `data/raw/tmc/`

2. **Mosaic DTM tiles** — create single `south_pole_dem_20m.tif`
   - Use `rasterio.merge` or GDAL `gdal_merge.py`
   - Target: 20m resolution for performance

3. **Modify pipeline scripts** — enable multi-swath processing
   - Update `src/01_data_ingestion.py`
   - Add `--resolution` parameter to `src/run_pipeline.py`

4. **Run regional pipeline** — process entire south pole
   - `python src/run_pipeline.py --resolution 20 --psr_positions 36`

5. **Update dashboard** — regenerate overlays and GeoJSON files
   - `python src/generate_map_overlays.py`
   - `python src/export_for_dashboard.py`

6. **Push to GitHub** — commit regional expansion
   - Remove old Shackleton-only limitation notes
   - Update README.md with south pole coverage

---

## Questions for User

1. **DEM Source**: Do you want to download TMC-2 DTM (recommended, faster) or generate DEM from OHRC stereo (slower, more work)?

2. **Resolution**: For entire south pole, 20m resolution is reasonable. Do you need higher (5m = slower) or lower (50m = faster)?

3. **Timeline**: Do you have 4-6 hours for this expansion, or do you need a faster "proof of concept" with just a few swaths?

---

## Fallback: Partial Expansion (If Time-Limited)

If downloading/processing full south pole takes too long:

**Quick win**: Process just **3-4 DFSAR swaths** covering known DSCs
- Faustini crater (87.3°S, 77°E)
- Haworth crater (87.4°S, 5°E)  
- Shoemaker crater (88.1°S, 45°E)
- Shackleton (89.9°S, 0°E) — already done

**Steps:**
1. Find which CP products cover these 4 craters (check XML lat/lon corners)
2. Download only those 4 regions' TMC DTM tiles (~8 tiles)
3. Run pipeline on 4-crater mosaic instead of full pole
4. Still demonstrates regional capability without full pole processing

**Benefit**: Proves multi-swath mosaicking works, shows DSCs in multiple locations, much faster than full pole.

---

## References

- **PRADAN Data Portal**: https://pradan.issdc.gov.in/ch2/
- **TMC-2 DTM Products**: Select "TMC" or "TMC-2" instrument, filter by "DTM" or "DEM" processing level
- **DFSAR Compact-Pol**: Already downloaded (11 products in `data/raw/dfsar/`)
- **Pipeline Code**: All mosaic logic already exists in `src/01_data_ingestion.py` (lines 200-250)
