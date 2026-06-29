# Dashboard Setup Instructions

## The Problem You Were Experiencing

1. **File protocol issue**: Opening `dashboard/index.html` directly (double-clicking) loads it as `file:///` which blocks browser `fetch()` calls for security reasons
2. **Result**: The dashboard appeared black/broken because no data could load

## The Solution: Use a Local HTTP Server

### Start the Server

From the project root directory:

```bash
python -m http.server 8080 --directory dashboard
```

Leave this terminal window open while using the dashboard.

### Access the Dashboard

Open your browser and go to:

```
http://localhost:8080
```

**NOT** `file:///C:/Users/AMISHA/Desktop/Codes/Ice_on_moon/dashboard/index.html`

### What You Should See

- Map with lunar surface terrain (DEM hillshade)
- Landing site markers (green circles with LS-1, LS-2, LS-3)
- Rover traverse path (colored corridors)
- All data panels populated on the right side
- Console logs showing successful data loading

### Verify It's Working

Open DevTools (F12) → Console tab:

✅ **Good**: You should see:
```
[Init] Loading meta.json...
[Init] Meta loaded: Object
[Init] Leaflet map created
[Init] AOI bounds: Array(2)
[Map Zoom] Current zoom: -9.00, Threshold: -2
```

❌ **Bad**: If you see:
```
Failed to fetch
CORS policy error
```
→ You're still using `file://` protocol. Use `http://localhost:8080` instead.

### Stop the Server

When done, press `Ctrl+C` in the terminal where the server is running.

## About the Overlay PNGs

The following files exist in `dashboard/data/overlays/` but are **gitignored** (not tracked by git):

- `dem_hillshade.png` - High-res lunar terrain basemap (THE MAP ITSELF)
- `global_basemap.png` - Wide-area south pole context
- `psr_overlay.png` - Permanently Shadowed Regions
- `cpr_overlay.png` - Circular Polarization Ratio (radar ice signal)
- `ice_prob_overlay.png` - Ice probability layer
- `hazard_overlay.png` - Landing hazard layer

These are multi-MB files regenerated from pipeline data, so they're excluded from git to keep the repo small.

**If you're sharing this project**: Send these 6 PNG files separately, or have recipients regenerate them by running:

```bash
python src/generate_map_overlays.py
```

(Requires completed pipeline run with data in `data/processed/`)

## Quick Check Commands

### Check if all required PNGs exist:
```bash
ls dashboard/data/overlays/*.png
```

Should show 6+ PNG files.

### Test if server is responding:
```bash
curl -I http://localhost:8080/data/overlays/dem_hillshade.png
```

Should return `HTTP/1.0 200 OK`

## Troubleshooting

### "Port 8080 is already in use"

Use a different port:
```bash
python -m http.server 8081 --directory dashboard
```

Then access at `http://localhost:8081`

### PNGs are missing (404 errors)

Regenerate them:
```bash
python src/generate_map_overlays.py
```

### Data files are missing

Re-export from pipeline:
```bash
python src/export_for_dashboard.py
```

## For Deployment

For a permanent web deployment (not just local testing):

1. Copy the entire `dashboard/` folder to your web server
2. Ensure all PNG files are included (they're gitignored, so copy manually)
3. No special server configuration needed - static files only
4. Can use GitHub Pages, Netlify, Vercel, or any static hosting

Note: You'll need to manually add the PNGs to deployment since they're gitignored.
