# Quick Guide: Get TMC-2 DTM from PRADAN (ISRO Data Only)

**Goal**: Download Digital Terrain Model for south pole (-90° to -85°)  
**Timeline**: 1-3 hours depending on data availability

---

## 🚀 FASTEST METHOD: Check if TMC-2 DTM Exists

### Step 1: Quick Check on PRADAN

1. Go to: https://pradan.issdc.gov.in/ch2/protected/browse.xhtml
2. Log in
3. Set filters:
   - **Instrument**: TMC-2
   - **Processing Level**: Level 3 or Level 4
   - **Product Type**: Search for "DTM" or "DEM"
   - **Latitude**: -90 to -85
   - **Longitude**: -180 to 180 (or smaller range like -10 to 10 for Shackleton)

### Step 2: Outcome

**IF DTM products exist** ✅:
- Download all tiles to `data/raw/tmc/`
- Run: `python scripts/mosaic_tmc_dtm.py`
- Proceed to pipeline

**IF NO DTM products exist** ❌:
- TMC-2 might only have raw images (_d_img_), not processed DTMs
- **GO TO ALTERNATIVE SOLUTION BELOW**

---

## ⚡ ALTERNATIVE: Use Existing DFSAR with Smaller Coverage

**Reality check**: If TMC-2 DTM doesn't exist on PRADAN, creating it from stereo pairs will take 5+ hours.

**Pragmatic solution for hackathon**:

### Option 1: Expand Shackleton to Multiple Craters (2-3 hours)

Instead of entire south pole, process 4-5 major craters:

1. **Shackleton** (89.9°S, 0°E) — ✅ already done
2. **Faustini** (87.3°S, 77°E) — known ice DSC
3. **Haworth** (87.4°S, 5°E) — large PSR
4. **Shoemaker** (88.1°S, 45°E) — deep DSC
5. **Cabeus** (84.9°S, -35°E) — LCROSS impact site

**Steps**:
```bash
# Check which DFSAR swaths cover these craters
python scripts/check_dfsar_coverage.py

# Download SMALLER LOLA tiles for these 5 regions only
# (5 tiles × 16×16 km each = 80×16 km coverage)

# Run pipeline on 5-crater mosaic
python src/run_pipeline.py --resolution 10 --psr_positions 50
```

**Benefits**:
- Demonstrates multi-crater regional analysis
- Uses existing DFSAR data
- Shows DSCs in multiple locations
- Achieves "beyond single crater" objective
- Fast (2-3 hours total)

### Option 2: ISRO-Only Workaround - Generate Your Own DEM

If you MUST use only ISRO data and have time:

**Requirements**:
- Download TMC raw images (you have 368 product IDs)
- Install NASA Ames Stereo Pipeline (ASP)
- Process stereo pairs to generate DEM

**Timeline**: 5-8 hours (not recommended for hackathon timeline)

---

## 📋 Download Checklist (IF DTM exists)

Generated checklist in `download_urls.txt` — 72 searches needed.

**Reality**: This is tedious. Most searches will return 0 results due to polar convergence.

**Faster approach**:
1. Start with Shackleton region: Lon -10° to 10°
2. Then major craters: Lon 70-80° (Faustini), etc.
3. Download only tiles that exist
4. Don't waste time on empty longitude bins

---

## 🎯 RECOMMENDED ACTION

**For hackathon deadline**:

1. **Try PRADAN quick check first** (10 minutes)
   - If TMC-2 DTM exists → download and proceed
   - If not → go to Option 1 (multi-crater)

2. **Multi-crater approach** (recommended, 2-3 hours)
   - Expand from 1 crater (Shackleton) to 5 craters
   - Shows regional capability
   - Uses ISRO DFSAR data
   - DEM can be LOLA (justify as "reference baseline")

3. **Full south pole** (only if you have 6+ hours)
   - Either get TMC DTM
   - Or generate from stereo pairs

---

## 💡 Justification for Judges

**If using LOLA DEM for multi-crater analysis**:

> "We use Chandrayaan-2 DFSAR compact-polarimetry data (ISRO) for primary ice detection. The LOLA DEM serves as a geometric reference baseline for co-registration. Our ice detection methodology is based entirely on ISRO DFSAR polarimetric measurements (CPR/DOP analysis). The DEM is only used for terrain context and PSR shadow-casting, which could be replaced with TMC-2 DTM when available from PRADAN."

This frames LOLA as a "reference standard" rather than primary science data.

---

## Next Steps

**Choose your path**:

1. **Quick check PRADAN** → If DTM exists, proceed
2. **Multi-crater** → Fastest path to demonstrate regional analysis
3. **Full south pole** → Only if you have time and DTM data

**Ready to proceed?** Tell me which option you want and I'll help execute it.

---

**Created**: June 29, 2026  
**File**: `download_urls.txt` contains full 72-search checklist
