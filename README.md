# Lunar South Pole Ice Detection Pipeline

**Bharatiya Antariksh Hackathon 2026 — Challenge #8**

> Detect and characterize subsurface ice in lunar south polar regions using Chandrayaan-2 DFSAR radar, OHRC optical imagery, and TMC-2 digital terrain models.

[![Status](https://img.shields.io/badge/Phase%201-Complete-success)](PROJECT_STATUS.md)
[![Status](https://img.shields.io/badge/Phase%202-In%20Progress-yellow)](PROJECT_STATUS.md)

**Current Coverage**: Shackleton Crater (16×16 km) ✅  
**Target Coverage**: Entire South Pole (85-90°S) ⏳  
**Data Source**: ISRO Chandrayaan-2 only

📊 [View Project Status](PROJECT_STATUS.md) | 📖 [Documentation](docs/) | 🚀 [Quick Start](#quick-start)

---

## Features

- 🛰️ **DFSAR Ice Detection**: CPR/DOP analysis from compact-polarimetry radar
- 🌑 **PSR Mapping**: Permanently shadowed regions via shadow-casting simulation
- 🎯 **Landing Site Selection**: Multi-criteria scoring for mission planning
- 🤖 **Rover Traverse Planning**: A* pathfinding with terrain hazard avoidance
- 📊 **Ice Volume Estimation**: Fresnel inversion + Maxwell-Garnett mixing models
- 🗺️ **Interactive Dashboard**: Leaflet + Plotly web visualization

---

## Current Results (Shackleton Crater)

- **37 ice pixels** detected in permanently shadowed regions
- **10 doubly-shadowed craters** (DSCs) identified
- **3 landing sites** ranked by science value and safety
- **27.2 km rover traverse** optimized for ice sampling
- **Ice volume**: 2.31×10⁻⁷ km³ (90% confidence interval)

🎥 [View Dashboard](http://localhost:8080) (requires local server)

---

## Quick Start

## Quick Start

### Prerequisites
```bash
# Python 3.9+ with conda
conda activate lunar_ice
pip install -r requirements.txt
```

### Option 1: View Existing Dashboard (Shackleton)
```bash
# Start local server
python -m http.server 8080 --directory dashboard

# Open browser: http://localhost:8080
```

### Option 2: Run Full Pipeline (Requires Data)

**Step 1**: Download data from PRADAN
- TMC-2 DTM (elevation) → `data/raw/tmc/` 
- DFSAR CP (radar) → `data/raw/dfsar/` ✅ Already downloaded (13 products)
- OHRC CAL (optical) → `data/raw/ohrc/` (optional)

See [Download Guide](docs/guides/HOW_TO_DOWNLOAD_TMC_DTM.md) for detailed instructions.

**Step 2**: Mosaic TMC tiles (if using regional data)
```bash
python scripts/mosaic_tmc_dtm.py
```

**Step 3**: Run pipeline
```bash
# Regional south pole (20m resolution, fast)
python src/run_pipeline.py --resolution 20 --psr_positions 36

# High-resolution local (5m resolution, slow)
python src/run_pipeline.py --resolution 5 --psr_positions 100
```

**Step 4**: Generate dashboard
```bash
python src/generate_map_overlays.py
python src/export_for_dashboard.py
```

**Step 5**: Launch dashboard
```bash
python -m http.server 8080 --directory dashboard
```

---

## Project Status

**Phase 1: Shackleton Crater** ✅ COMPLETE
- 16×16 km coverage
- Dashboard working
- All outputs validated

**Phase 2: South Pole Regional** ⏳ IN PROGRESS
- Need: TMC-2 DTM covering -90° to -85° latitude
- Have: 13 DFSAR products ready
- Timeline: 3-5 hours after TMC DTM download

📄 [Detailed Status Report](PROJECT_STATUS.md)

---

## Documentation

| Document | Description |
|----------|-------------|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | Current status, data inventory, to-do list |
| [docs/SOUTH_POLE_EXPANSION_STATUS.md](docs/SOUTH_POLE_EXPANSION_STATUS.md) | Regional expansion technical guide |
| [docs/guides/HOW_TO_DOWNLOAD_TMC_DTM.md](docs/guides/HOW_TO_DOWNLOAD_TMC_DTM.md) | Step-by-step PRADAN download |
| [docs/DASHBOARD_INSTRUCTIONS.md](docs/DASHBOARD_INSTRUCTIONS.md) | Dashboard usage guide |
| [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md) | Implementation roadmap |

---

## Pipeline Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ DFSAR Radar │  │  TMC-2 DTM  │  │ OHRC Optical│
│  (13 swaths)│  │ (south pole)│  │  (optional) │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                 │
       └────────────────┼─────────────────┘
                        ▼
            ┌───────────────────────┐
            │  01: Data Ingestion   │  Reproject + co-register
            │  • Mosaic DFSAR swaths│
            │  • Align to DEM grid  │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  02: PSR Mapping      │  Shadow-casting simulation
            │  • 36-100 sun angles  │
            │  • DSC identification │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  03: Ice Detection    │  Radar polarimetry analysis
            │  • CPR from CP data   │
            │  • DOP computation    │
            │  • Ice probability    │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  04: Terrain Analysis │  Hazard mapping
            │  • Slope, roughness   │
            │  • Boulder density    │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  05: Landing Sites    │  Multi-criteria scoring
            │  • Science value      │
            │  • Safety assessment  │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  06: Rover Traverse   │  A* pathfinding
            │  • Energy-aware cost  │
            │  • DSC targeting      │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  07: Volume Estimate  │  Monte Carlo uncertainty
            │  • Fresnel inversion  │
            │  • 90% confidence     │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  Dashboard Export     │  Interactive visualization
            │  • GeoJSON + JSON     │
            │  • Map overlays       │
            └───────────────────────┘
```

---

## Ice Detection Method

**CPR (Circular Polarization Ratio)**:  
`CPR = SC / OC` where SC = same-sense, OC = opposite-sense  
Ice threshold: **CPR > 1.0** (volume scattering dominates)

**DOP (Degree of Polarization)**:  
`DOP = sqrt(S1² + S2² + S3²) / S0`  
Ice threshold: **DOP < 0.13** (high depolarization)

**Location**: Must be in **PSR** (permanently shadowed region)

Combined ice probability:  
`P(ice) = 1` if `CPR > 1.0 AND DOP < 0.13 AND in_PSR`  
`P(ice) = 0` otherwise

---

## Output Files

| File | Description |
|------|-------------|
| `data/processed/psr_mask.tif` | Permanently shadowed regions binary mask |
| `data/processed/cpr_map.tif` | Circular polarization ratio per pixel |
| `data/processed/dop_map.tif` | Degree of polarization per pixel |
| `data/processed/ice_probability.tif` | Combined ice score [0-1] |
| `data/processed/hazard_score.tif` | Landing/traverse hazard composite |
| `data/exports/ice_candidates.geojson` | Ice pixel locations (GeoJSON) |
| `data/exports/dsc_locations.geojson` | Doubly-shadowed craters |
| `data/exports/landing_sites.geojson` | Ranked landing candidates |
| `data/exports/traverse_path.geojson` | Optimal rover traverse |
| `data/exports/ice_volume_report.json` | Volume + uncertainty estimate |

---

## Technology Stack

**Languages**: Python 3.9+, JavaScript (ES6)  
**Geospatial**: rasterio, pyproj, GDAL  
**Science**: numpy, scipy, scikit-image  
**Visualization**: Leaflet.js, Plotly.js, Folium  
**Web**: HTML5, CSS3, HTTP server

---

## Project Structure

```
Ice_on_moon/
├── README.md                    ← You are here
├── PROJECT_STATUS.md            ← Current status & to-do
├── requirements.txt
│
├── docs/                        ← All documentation
├── scripts/                     ← Utility scripts
├── src/                         ← Pipeline source code
├── dashboard/                   ← Web interface
├── data/                        ← Input & output data
├── reference_data/              ← Product ID lists
└── assets/                      ← Images & figures
```

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for detailed folder structure.

---

## Contributing

This is a hackathon project — contributions welcome for:
- Additional ice detection algorithms (bistatic radar, m-chi decomposition)
- OHRC stereo DEM generation
- Enhanced traverse planning (energy models, comm windows)
- Machine learning ice classification

---

## References

- Spudis et al. (2013) — Mini-RF CPR anomalous craters
- Li et al. (2018) — M³/LOLA/LAMP ice-bearing PSRs
- Kumar et al. (2021) — Chandrayaan-2 DFSAR instrument
- Raney (2007) — m-chi decomposition for hybrid polarimetry
- Hayne et al. (2015) — Lunar PSR thermal modeling
- Nozette et al. (1996) — Bistatic radar ice detection

---

## License

MIT License — see LICENSE file

---

## Acknowledgments

- **ISRO** for Chandrayaan-2 data via PRADAN portal
- **Bharatiya Antariksh Hackathon 2026** organizers
- Lunar science community for detection algorithms

---

**Questions?** Check [PROJECT_STATUS.md](PROJECT_STATUS.md) or documentation in `docs/`

**Dashboard**: http://localhost:8080 (start server first)  
**GitHub**: https://github.com/Amisha2121/Ice-Detection-on-Moon.git
