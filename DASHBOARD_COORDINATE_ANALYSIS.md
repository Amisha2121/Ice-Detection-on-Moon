# Dashboard Coordinate System Analysis

## Summary: Coordinates Are Actually Correct ✓

After running diagnostics, the coordinate system is **working correctly**. All GeoJSON features project to the right locations within the AOI bounds.

## Diagnostic Results

### Landing Sites Projection (Python)
```
LS-1: lon=-141.44°, lat=-89.5294° -> mx=-8895m, my=-11160m  ✓ INSIDE AOI
LS-2: lon=-156.14°, lat=-89.7750° -> mx=-2760m, my=-6240m   ✓ INSIDE AOI
LS-3: lon=-144.63°, lat=-89.9596° -> mx=-710m, my=-1000m    ✓ INSIDE AOI
```

### AOI Bounds (from LOLA DEM and meta.json)
```
West  = -9000 m
South = -15000 m
East  =  7000 m
North =  1000 m
```

All landing sites fall correctly within these bounds.

### Coordinate System Verification
- ✓ LOLA DEM bounds match meta.json exactly
- ✓ JavaScript `lonLatToStereo()` matches Python projection
- ✓ GeoJSON coordinates project to correct stereographic meters
- ✓ L.CRS.Simple correctly interprets meters as pixel coordinates

## The Real Issue: Resolution Mismatch (Already Fixed)

The visual "mismatch" between zoomed-out and zoomed-in views is **NOT a coordinate bug** — it's a resolution gap:

- **AOI layers**: 15.6 m/pixel (sharp, detailed)
- **Global context**: 5,859 m/pixel (375× coarser)

When zoomed in, the global layer upsamples poorly → blurry/marble effect.

### Fix Already Implemented

The dashboard now includes zoom-aware layer opacity (commit 862e9dd):

```javascript
const GLOBAL_LAYER_MAX_ZOOM = -2;
STATE.map.on('zoomend', () => {
  const z = STATE.map.getZoom();
  if (z > GLOBAL_LAYER_MAX_ZOOM) {
    globalLayer.setOpacity(0);  // Hide blurry global layer when zoomed in
  } else {
    globalLayer.setOpacity(0.6); // Show context when zoomed out
  }
});
```

## What Users See Now

1. **Wide zoom (< -2)**: Global context visible, shows where AOI sits on the Moon
2. **Close zoom (> -2)**: Global layer fades out, only sharp AOI data visible
3. **No blurry artifacts**: Each layer only shows at appropriate resolutions

## Conclusion

No further coordinate fixes needed. The system is working as designed. The visual difference between zoom levels is now properly handled by resolution-appropriate layer visibility.

## Files Verified

- ✓ `data/processed/lola_dem_5m.tif` - correct bounds
- ✓ `dashboard/data/overlays/meta.json` - matches DEM bounds
- ✓ `dashboard/data/landing_sites.geojson` - correct coordinates
- ✓ `dashboard/app.js` - correct projection and zoom handling
