# Project Status: Lunar South Pole Ice Detection

**Date**: June 29, 2026  
**Hackathon**: Bharatiya Antariksh Hackathon 2026 — Challenge #8  
**GitHub**: https://github.com/Amisha2121/Ice-Detection-on-Moon.git

---

## 🎯 Current Status

### ✅ Phase 1: Shackleton Crater Dashboard — **COMPLETE**

**Coverage**: 16×16 km around Shackleton crater (89.9°S, 0°E)

**Achievements**:
- 37 ice pixels detected (CPR>1 AND DOP<0.13 in PSR regions)
- Ice volume: 2.31×10⁻⁷ km³ with 90% confidence interval
- 10 doubly-shadowed craters (DSCs) identified
- 3 ranked landing sites (LS-1, LS-2, LS-3)
- 27.2 km optimized rover traverse with A* pathfinding
- Interactive dashboard at http://localhost:8080

**Data Used**:
- DFSAR: Single compact-pol product
- DEM: LOLA 5m (NASA — 16×16 km coverage)
- Resolution: 5m
- PSR positions: 100 solar positions

**Status**: Dashboard working perfectly, pushed to GitHub ✅

---

### ⏳ Phase 2: South Pole Regional Expansion — **IN PROGRESS**

**Goal**: Expand coverage from 16×16 km to entire south pole (85-90°S, ~500 km diameter)

**Current Blockers**:
1. ❌ **Need TMC-2 DTM** covering -90° to -85° latitude (ISRO Chandrayaan-2 data)
   - Current LOLA DEM too small → DFSAR swaths rejected as "no overlap"
   - Must use ISRO data only per hackathon requirements

**Available Resources**:
- ✅ **13 DFSAR products** with proper polarimetry:
  - 11 compact-pol (_d_cp_n18)
  - 2 full-pol (_d_fp_xxx)
  - All extracted and ready in `data/raw/dfsar/`
  
- ✅ **Pipeline code ready**:
  - Multi-swath mosaicking implemented
  - Compact-pol → Stokes conversion working
  - Regional processing mode available

**Next Steps**:
1. Download TMC-2 DTM tiles from PRADAN (see `docs/guides/HOW_TO_DOWNLOAD_TMC_DTM.md`)
2. Mosaic tiles: `python scripts/mosaic_tmc_dtm.py`
3. Run regional pipeline: `python src/run_pipeline.py --resolution 20 --psr_positions 36`
4. Regenerate dashboard with regional data

**Expected Timeline**: 3-5 hours after TMC DTM download

---

## 📊 Data Inventory

### DFSAR (Radar) — ✅ Complete
```
data/raw/dfsar/
├── ch2_sar_ncxl_20250917t163359347_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20250917t163359347_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20250918t160856477_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20251006t052537568_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20251006t151527671_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20251006t171326188_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20251006t191123640_d_cp_n18/  (extracted)
├── ch2_sar_nrxl_20251006t210921252_d_cp_n18/  (extracted)
├── ch2_sar_ndxl_20250630my4rnpwest_d_fp_xxx/  (extracted)
└── ch2_sar_ndxl_20250630my4rspeast_d_fp_xxx/  (extracted)
```
**Status**: 13 products covering south pole, ready for processing

### DEM (Elevation) — ⚠️ Needs Expansion
```
data/raw/lola/
└── Site04_final_adj_5mpp_surf.tif  (16×16 km Shackleton only)

data/raw/tmc/  (empty — needs TMC-2 DTM tiles)
```
**Status**: Need to download TMC-2 DTM covering -90° to -85° latitude

### TMC/OHRC (Optical) — 📋 Reference Only
```
reference_data/
├── TMC368_Product_IDs.txt          (368 product IDs)
├── TMC368_Product_IDs.xlsx
├── OHRC_102_PRODUCT_IDS.txt        (102 product IDs)
└── OHRC_102_PRODUCT_IDS.csv
```
**Status**: Product IDs listed, not yet downloaded (optional for optical context)

---

## 🗂️ Project Organization

```
Ice_on_moon/
├── README.md                    # Main documentation
├── PROJECT_STATUS.md            # This file — current status
├── requirements.txt             # Python dependencies
│
├── docs/                        # Documentation
│   ├── SOUTH_POLE_EXPANSION_STATUS.md
│   ├── IMPROVEMENT_PLAN.md
│   ├── DASHBOARD_INSTRUCTIONS.md
│   └── guides/
│       └── HOW_TO_DOWNLOAD_TMC_DTM.md
│
├── src/                         # Pipeline source code
│   ├── 01_data_ingestion.py
│   ├── 02_psr_mapping.py
│   ├── 03_radar_ice_detection.py
│   ├── 04_terrain_analysis.py
│   ├── 05_landing_site_selection.py
│   ├── 06_rover_traverse.py
│   ├── 07_ice_volume_estimation.py
│   ├── generate_map_overlays.py
│   ├── export_for_dashboard.py
│   ├── run_pipeline.py
│   └── utils/
│
├── scripts/                     # Utility scripts
│   ├── mosaic_tmc_dtm.py       # Mosaic TMC DTM tiles
│   ├── apply_appjs_fixes.py
│   ├── apply_fixes.py
│   ├── check_env.py
│   ├── generate_traverse_demo.py
│   └── scratch_test_gcp.py
│
├── dashboard/                   # Interactive web dashboard
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── data/                   # GeoJSON + JSON data
│   └── static/                 # Base map images
│
├── data/
│   ├── raw/                    # Downloaded raw data
│   │   ├── dfsar/             # ✅ 13 products ready
│   │   ├── lola/              # ⚠️ Shackleton only
│   │   ├── tmc/               # ❌ Empty (needs TMC-2 DTM)
│   │   └── ohrc/              # Optional
│   ├── processed/             # Pipeline intermediate outputs
│   └── exports/               # Final outputs (GeoJSON, JSON)
│
├── reference_data/             # Product ID lists
│   ├── TMC368_Product_IDs.txt
│   ├── OHRC_102_PRODUCT_IDS.txt
│   ├── Book1 (2).xlsx
│   └── Book1 (3).xlsx
│
├── assets/                     # Images and visualizations
│   ├── moon_global.png
│   ├── regional_test.png
│   └── test_usgs.jpg
│
├── notebooks/                  # Jupyter analysis notebooks
├── tests/                      # Unit tests
└── scratch/                    # Temporary/experimental files
```

---

## 🚀 Quick Start

### Current Shackleton Dashboard (Working)
```bash
# Dashboard server should already be running on terminal ID: 2
# If not, start it:
python -m http.server 8080 --directory dashboard

# Open: http://localhost:8080
```

### South Pole Expansion (Next Steps)
```bash
# 1. Download TMC-2 DTM (see docs/guides/HOW_TO_DOWNLOAD_TMC_DTM.md)
#    Save tiles to: data/raw/tmc/

# 2. Mosaic TMC tiles
python scripts/mosaic_tmc_dtm.py

# 3. Run regional pipeline
python src/run_pipeline.py --resolution 20 --psr_positions 36

# 4. Generate dashboard
python src/generate_map_overlays.py
python src/export_for_dashboard.py

# 5. View results
python -m http.server 8080 --directory dashboard
# Open: http://localhost:8080
```

---

## 📈 Performance Expectations

### Shackleton (Current — 16×16 km)
- Resolution: 5m
- Processing time: ~30 min
- Memory: ~2 GB
- Ice pixels: 37
- DSCs: 10
- Landing sites: 3

### South Pole Regional (Target — 500 km diameter)
- Resolution: 20m (for performance)
- Processing time: ~2 hours
- Memory: ~8-16 GB
- Ice pixels: 500-2000 (estimate)
- DSCs: 50-100 (estimate)
- Landing sites: 10-20 (estimate)

---

## 🔗 Important Links

- **PRADAN Data Portal**: https://pradan.issdc.gov.in/ch2/protected/browse.xhtml
- **GitHub Repository**: https://github.com/Amisha2121/Ice-Detection-on-Moon.git
- **Dashboard**: http://localhost:8080 (when server running)

---

## 📋 To-Do List

- [ ] Download TMC-2 DTM tiles from PRADAN
- [ ] Mosaic DTM tiles into south_pole_dem_20m.tif
- [ ] Run regional pipeline
- [ ] Regenerate dashboard with regional coverage
- [ ] Update README with final results
- [ ] Prepare presentation materials
- [ ] Test dashboard on different browsers
- [ ] Document ice volume estimates
- [ ] Create visualization of DSC locations
- [ ] Write final report

---

## 🤝 Contact & Support

**Documentation**:
- Main guide: `README.md`
- TMC download: `docs/guides/HOW_TO_DOWNLOAD_TMC_DTM.md`
- Technical details: `docs/SOUTH_POLE_EXPANSION_STATUS.md`
- Dashboard help: `docs/DASHBOARD_INSTRUCTIONS.md`

**Questions?** Check the docs folder for detailed guides.

---

**Last Updated**: June 29, 2026  
**Status**: Phase 1 complete ✅ | Phase 2 ready to execute ⏳
