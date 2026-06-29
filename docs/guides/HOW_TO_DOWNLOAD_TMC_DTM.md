# Step-by-Step: Download TMC-2 DTM from PRADAN

**Goal**: Get Digital Terrain Model (DTM) tiles covering entire south pole (-90° to -85° latitude)

**Portal**: https://pradan.issdc.gov.in/ch2/protected/browse.xhtml

**Time**: 1-2 hours (depends on number of tiles and download speed)

---

## Step 1: Log in to PRADAN

1. Go to: https://pradan.issdc.gov.in/ch2/protected/browse.xhtml
2. If not already logged in, use your PRADAN credentials
3. You should see the "Chandrayaan-2 Data Archive Browse" interface

---

## Step 2: Set Basic Filters

In the left sidebar under "Browse Filters":

### **Instrument**
- ☑ Check **TMC** (Terrain Mapping Camera)
  - Or if you see **TMC-2** separately, check that

### **Processing Level**
- Look for dropdown or checkboxes for:
  - ☑ **Level 3** (processed products)
  - ☑ **Level 4** (higher-level products)
- Or search for keywords:
  - ☑ **DTM** (Digital Terrain Model)
  - ☑ **DEM** (Digital Elevation Model)

### **Product Type** (if available)
- Look for:
  - "Terrain Model"
  - "DTM"
  - "DEM"
  - "Elevation"
- Uncheck raw imagery (_d_img_) — you want processed elevation, not images

---

## Step 3: Set Spatial Filters

### **Latitude Range**
```
Min: -90
Max: -85
```
(This covers the south polar region)

### **Longitude Range**
⚠️ **IMPORTANT**: PRADAN limits search to 5° × 5° areas at a time!

You'll need to make **MULTIPLE SEARCHES** with different longitude bins:

#### Search 1:
```
Min Longitude: -180
Max Longitude: -175
```

#### Search 2:
```
Min Longitude: -175
Max Longitude: -170
```

#### Search 3:
```
Min Longitude: -170
Max Longitude: -165
```

... and so on ...

#### Search 72:
```
Min Longitude: 175
Max Longitude: 180
```

**Tip**: You might not need all 72 searches — polar convergence means tiles near the pole cover wider longitude ranges. Start with -180 to -175 and see how many results you get.

---

## Step 4: Execute Search

1. Click **"Search"** or **"Apply Filters"** button
2. Wait for results to load (may take 10-30 seconds)
3. You should see a list of TMC DTM products

### Expected Results:
- Product names like: `ch2_tmc_*_dtm_*.tif` or `ch2_tmc2_*_dem_*.tif`
- Multiple tiles per longitude bin (different orbit passes, dates)
- Each tile ~50-200 MB

### If You Get "No Records Found":
Try adjusting filters:
- Change "TMC" → "TMC-2" (or vice versa)
- Look for "Elevation" or "Topography" instead of "DTM"
- Expand processing level: include Level 2 if Level 3/4 return nothing
- Check "Advanced Filters" for terrain products

---

## Step 5: Download Tiles

### For Each Search Result:
1. Select tiles (use checkboxes or "Select All")
2. Click **"Add to Cart"** or **"Download"** button
3. Choose download location: `C:\Users\AMISHA\Desktop\Codes\Ice_on_moon\data\raw\tmc\`
4. Wait for download to complete

### Tips:
- **Create folder first**: `mkdir data\raw\tmc` if it doesn't exist
- **Download all tiles**: Even if multiple tiles cover same area (pipeline will mosaic/merge them)
- **Check file sizes**: TMC DTM tiles are typically 50-200 MB each
- **Organize by date**: Optional — you can put tiles in subdirectories like `tmc/2021/`, `tmc/2022/`

---

## Step 6: Repeat for All Longitude Bins

After completing Search 1 (-180 to -175), increment longitude:

```
Search 2:  -175 to -170
Search 3:  -170 to -165
Search 4:  -165 to -160
...
Search 72: 175 to 180
```

### How Many Tiles to Expect?
- **Minimum**: 36 tiles (one per 10° longitude bin, accounting for multiple orbits)
- **Typical**: 72-144 tiles (multiple passes per region)
- **Maximum**: Could be 200+ if many overlapping orbits

**Don't worry about duplicates** — the mosaic script will merge them automatically.

---

## Step 7: Verify Downloads

Check that tiles are GeoTIFFs:

```powershell
cd data\raw\tmc
dir *.tif
```

Expected output:
```
ch2_tmc_*_dtm_*.tif  (many files)
```

---

## Step 8: Mosaic the Tiles

Once all tiles are downloaded:

```bash
python mosaic_tmc_dtm.py
```

This will:
1. Find all `.tif` files in `data/raw/tmc/`
2. Reproject each to lunar polar stereographic
3. Mosaic into single `south_pole_dem_20m.tif`
4. Save to `data/raw/tmc/south_pole_dem_20m.tif`

**Expected runtime**: 30 min to 1 hour (depends on number of tiles)

---

## Troubleshooting

### "No TMC DTM products found"

**Possible reasons**:
1. **TMC-2 DTM not yet publicly released** on PRADAN
   - Check instrument list: might only have TMC raw images (_d_img_)
   - If so, you'll need to generate DEM from stereo pairs (more complex)

2. **Wrong processing level**
   - Try expanding to Level 2, Level 3, Level 4
   - Or remove level filter entirely

3. **Product type filter too strict**
   - Remove "DTM" keyword filter
   - Browse all TMC products and look manually

### Alternative: Generate DEM from Stereo

If TMC DTM truly doesn't exist on PRADAN, you'll need to:

1. Download stereo image pairs from TMC (you have 368 product IDs in `TMC368_Product_IDs.txt`)
2. Use NASA Ames Stereo Pipeline (ASP) to process:
   ```bash
   stereo left.tif right.tif stereo_result/ --stereo-algorithm asp_bm
   point2dem stereo_result/pc.tif -o dem_output.tif
   ```
3. This is **much more complex** and time-consuming (3-5 hours)

**Recommendation**: Try very hard to find TMC DTM on PRADAN first!

---

## Alternative Data Source: LOLA South Pole Mosaic

If TMC DTM is unavailable and stereo is too complex:

**NASA LOLA South Pole DTM**:
- URL: https://pgda.gsfc.nasa.gov/products/78
- File: `LOLA_POLAR_DTM.tif` or similar
- Coverage: Entire south pole at 5-10m resolution
- **Issue**: NASA data, not ISRO (might violate hackathon rules)

**Use only if**:
1. TMC DTM doesn't exist on PRADAN
2. You don't have time for stereo processing
3. You confirm with hackathon organizers that NASA data is acceptable

---

## Summary Checklist

- [ ] Log in to PRADAN
- [ ] Set filters: TMC, Level 3/4, DTM/DEM
- [ ] Set spatial: Lat -90 to -85
- [ ] Search longitude bins: -180 to 180 in 5° increments (make 72 searches)
- [ ] Download all tiles to `data/raw/tmc/`
- [ ] Verify `.tif` files exist
- [ ] Run `python mosaic_tmc_dtm.py`
- [ ] Confirm `south_pole_dem_20m.tif` created
- [ ] Proceed to run pipeline: `python src/run_pipeline.py --resolution 20 --psr_positions 36`

---

## Need Help?

Check these files:
- **SUMMARY_FOR_USER.md** — Quick overview
- **SOUTH_POLE_EXPANSION_STATUS.md** — Technical details
- **CURRENT_STATUS_VISUAL.txt** — Visual summary

Good luck! 🚀
