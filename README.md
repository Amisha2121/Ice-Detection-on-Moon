# Lunar South Pole Ice Detection Pipeline
## Bharatiya Antariksh Hackathon 2026 — Challenge #8

> **Target**: Entire South Pole (85-90°S) · **Data**: Chandrayaan-2 DFSAR + OHRC + TMC-2 DTM  
> **Status**: Expanding from Shackleton (16×16 km) to regional coverage (500+ km diameter)

---

## Quick Start

### 1. Download Real Data
| Data | Portal | Save to | Notes |
|---|---|---|---|
| **TMC-2 DTM** (south pole DEM) | [pradan.issdc.gov.in/ch2](https://pradan.issdc.gov.in/ch2/) → TMC | `data/raw/tmc/` | **REQUIRED** for regional processing |
| DFSAR SRI (CP mode) | [pradan.issdc.gov.in/ch2](https://pradan.issdc.gov.in/ch2/) → SAR | `data/raw/dfsar/` | ✅ 13 products already downloaded |
| OHRC Calibrated | [pradan.issdc.gov.in/ch2](https://pradan.issdc.gov.in/ch2/) → OHRC | `data/raw/ohrc/` | Optional (for optical context) |

**Important**: Download TMC-2 DTM tiles covering -90° to -85° latitude (entire south pole). PRADAN limits searches to 5°×5° at a time, so you'll need multiple queries.

### 2. Set Up Environment
```bash
# Activate the pre-created conda environment
conda activate lunar_ice

# Install remaining packages
pip install opencv-python scikit-image plotly folium networkx tqdm
```

### 3. Prepare South Pole DEM
```bash
# Mosaic TMC-2 DTM tiles into single south pole DEM
python mosaic_tmc_dtm.py
# Output: data/raw/tmc/south_pole_dem_20m.tif
```

### 4. Run the Pipeline
```bash
# Full regional pipeline (500+ km coverage, 20m resolution)
python src/run_pipeline.py --resolution 20 --psr_positions 36

# Fast preview (Shackleton area only, 5m resolution)
python src/run_pipeline.py --resolution 5 --psr_positions 20

# Individual steps
python src/01_data_ingestion.py
python src/02_psr_mapping.py --n_positions 100
python src/03_radar_ice_detection.py
python src/04_terrain_analysis.py
python src/05_landing_site_selection.py
python src/06_rover_traverse.py
python src/07_ice_volume_estimation.py
```

### 5. Launch Dashboard
```bash
# Copy outputs to dashboard/data/
python src/export_for_dashboard.py

# Open in browser (serve locally to avoid CORS)
python -m http.server 8080 --directory dashboard
# Then open: http://localhost:8080
```

---

## Pipeline Overview

```
DFSAR SRI GeoTIFF  +  OHRC CAL.img  +  LOLA 5m DEM
        │                   │                │
        ▼                   ▼                ▼
01 Data Ingestion   → Reproject + co-register to lunar polar CRS
02 PSR Mapping      → Shadow-cast illumination, PSR mask, DSC detection
03 Ice Detection    → CPR/DOP from Stokes bands, m-chi, ice probability
04 Terrain Analysis → Slope, roughness, boulder density, hazard score
05 Landing Sites    → Multi-criteria scoring, top-3 candidates
06 Rover Traverse   → A* pathfinding, energy-aware traverse
07 Ice Volume       → Fresnel inversion, Maxwell-Garnett, Monte Carlo
   Dashboard        → Leaflet + Plotly interactive explorer
```

## Ice Detection Thresholds
| Parameter | Ice Threshold | Physical Meaning |
|---|---|---|
| CPR (Circular Polarisation Ratio) | **> 1.0** | Same-sense return dominant → volume scattering |
| DOP (Degree of Polarisation) | **< 0.13** | High depolarisation → sub-surface scatter |
| Location | In PSR | Thermally stable, ice can persist |

## Output Files
| File | Location | Description |
|---|---|---|
| `psr_mask.tif` | `data/processed/` | Permanently shadowed regions |
| `cpr_map.tif` | `data/processed/` | CPR per pixel |
| `ice_probability.tif` | `data/processed/` | Combined ice score [0-1] |
| `hazard_score.tif` | `data/processed/` | Landing/traverse hazard |
| `cost_map.tif` | `data/processed/` | A* traversal cost |
| `landing_sites.geojson` | `data/exports/` | Top-3 landing candidates |
| `traverse_path.geojson` | `data/exports/` | Optimal rover traverse |
| `ice_volume_report.json` | `data/exports/` | Volume + uncertainty |

## References
- Spudis et al. (2013) — Mini-RF CPR anomalous craters
- Li et al. (2018) — M³/LOLA/LAMP ice-bearing pixels
- Kumar et al. (2021) — Chandrayaan-2 DFSAR instrument
- Raney (2007) — m-chi decomposition for hybrid polarimetry
- Hayne et al. (2015) — PSR thermal model
- Nozette et al. (1996) — Bistatic radar ice detection
