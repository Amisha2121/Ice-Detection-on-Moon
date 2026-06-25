# Lunar South Pole Ice Detection Pipeline
## Bharatiya Antariksh Hackathon 2026 — Challenge #8

> **Target**: Shackleton Crater (89.9°S) · **Data**: Chandrayaan-2 DFSAR + OHRC + LOLA DEM

---

## Quick Start

### 1. Download Real Data
| Data | Portal | Save to |
|---|---|---|
| DFSAR SRI (CP mode) | [pradan.issdc.gov.in/ch2](https://pradan.issdc.gov.in/ch2/) → SAR | `data/raw/dfsar/` |
| OHRC Calibrated | [pradan.issdc.gov.in/ch2](https://pradan.issdc.gov.in/ch2/) → OHRC | `data/raw/ohrc/` |
| LOLA 5m South Pole DEM | [pgda.gsfc.nasa.gov/products/78](https://pgda.gsfc.nasa.gov/products/78) | `data/raw/lola/` |

### 2. Set Up Environment
```bash
# Activate the pre-created conda environment
conda activate lunar_ice

# Install remaining packages
pip install opencv-python scikit-image plotly folium networkx tqdm
```

### 3. Run the Pipeline
```bash
# Full pipeline (Steps 1–7)
python src/run_pipeline.py

# Fast preview (20 solar positions for PSR — much quicker)
python src/run_pipeline.py --psr_positions 20

# Individual steps
python src/01_data_ingestion.py
python src/02_psr_mapping.py --n_positions 100
python src/03_radar_ice_detection.py
python src/04_terrain_analysis.py
python src/05_landing_site_selection.py
python src/06_rover_traverse.py
python src/07_ice_volume_estimation.py
```

### 4. Launch Dashboard
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
