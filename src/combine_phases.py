"""
combine_phases.py

Combine Phase 1 (Shackleton) and Phase 2 (Regional) ice detection results
into a unified south pole ice inventory.
"""

import os
import json
import numpy as np
import rasterio
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
EXPORTS = ROOT / "data" / "exports"
OUTPUTS = ROOT / "outputs"

def load_phase1_stats():
    """Load Phase 1 (Shackleton) ice statistics."""
    ice_candidates = EXPORTS / "ice_candidates.geojson"
    
    if not ice_candidates.exists():
        return None
    
    with open(ice_candidates) as f:
        gj = json.load(f)
    
    num_pixels = len(gj['features'])
    
    # Calculate area (assuming 5m resolution for Phase 1)
    area_km2 = num_pixels * (5 * 5) / 1e6
    
    cprs = [f['properties']['cpr'] for f in gj['features'] if 'cpr' in f['properties']]
    dops = [f['properties']['dop'] for f in gj['features'] if 'dop' in f['properties']]
    
    return {
        'name': 'Phase 1: Shackleton Crater',
        'ice_pixels': num_pixels,
        'area_km2': area_km2,
        'resolution_m': 5,
        'coverage_km2': 256,  # 16×16 km
        'cpr_mean': np.mean(cprs) if cprs else None,
        'cpr_median': np.median(cprs) if cprs else None,
        'dop_mean': np.mean(dops) if dops else None,
        'dop_median': np.median(dops) if dops else None,
    }

def load_phase2_stats():
    """Load Phase 2 (Regional) ice statistics."""
    ice_prob = PROCESSED / "ice_probability_regional.tif"
    cpr_map = PROCESSED / "cpr_map_regional.tif"
    dop_map = PROCESSED / "dop_map_regional.tif"
    
    if not ice_prob.exists():
        return None
    
    with rasterio.open(ice_prob) as src:
        ice_mask = src.read(1).astype(bool)
        num_pixels = np.sum(ice_mask)
        
        # Resolution from transform
        transform = src.transform
        res = abs(transform.a)  # pixel size in meters
        
        area_km2 = num_pixels * (res * res) / 1e6
        
        # Total coverage area
        total_pixels = ice_mask.size
        coverage_km2 = total_pixels * (res * res) / 1e6
    
    # Load CPR/DOP for ice pixels
    with rasterio.open(cpr_map) as src:
        cpr = src.read(1)
        cpr_ice = cpr[ice_mask]
    
    with rasterio.open(dop_map) as src:
        dop = src.read(1)
        dop_ice = dop[ice_mask]
    
    return {
        'name': 'Phase 2: Regional South Pole',
        'ice_pixels': int(num_pixels),
        'area_km2': float(area_km2),
        'resolution_m': float(res),
        'coverage_km2': float(coverage_km2),
        'cpr_mean': float(np.mean(cpr_ice)),
        'cpr_median': float(np.median(cpr_ice)),
        'cpr_min': float(np.min(cpr_ice)),
        'cpr_max': float(np.max(cpr_ice)),
        'dop_mean': float(np.mean(dop_ice)),
        'dop_median': float(np.median(dop_ice)),
        'dop_min': float(np.min(dop_ice)),
        'dop_max': float(np.max(dop_ice)),
    }

def generate_combined_report():
    """Generate comprehensive combined report."""
    print("\n" + "="*70)
    print("  COMBINED PHASE 1 + PHASE 2 ICE INVENTORY")
    print("="*70 + "\n")
    
    p1 = load_phase1_stats()
    p2 = load_phase2_stats()
    
    if not p1 or not p2:
        print("ERROR: Missing phase data")
        return
    
    print(f"Phase 1: {p1['name']}")
    print(f"  Ice pixels: {p1['ice_pixels']:,}")
    print(f"  Ice area: {p1['area_km2']:.4f} km²")
    print(f"  Coverage: {p1['coverage_km2']:.0f} km²")
    print(f"  Resolution: {p1['resolution_m']}m")
    if p1['cpr_mean']:
        print(f"  CPR: {p1['cpr_mean']:.3f} (mean), {p1['cpr_median']:.3f} (median)")
        print(f"  DOP: {p1['dop_mean']:.3f} (mean), {p1['dop_median']:.3f} (median)")
    
    print(f"\nPhase 2: {p2['name']}")
    print(f"  Ice pixels: {p2['ice_pixels']:,}")
    print(f"  Ice area: {p2['area_km2']:.2f} km²")
    print(f"  Coverage: {p2['coverage_km2']:.0f} km²")
    print(f"  Resolution: {p2['resolution_m']:.0f}m")
    print(f"  CPR: {p2['cpr_mean']:.3f} (mean), range [{p2['cpr_min']:.3f}, {p2['cpr_max']:.3f}]")
    print(f"  DOP: {p2['dop_mean']:.3f} (mean), range [{p2['dop_min']:.3f}, {p2['dop_max']:.3f}]")
    
    # Combined totals
    total_pixels = p1['ice_pixels'] + p2['ice_pixels']
    total_area = p1['area_km2'] + p2['area_km2']
    total_coverage = p1['coverage_km2'] + p2['coverage_km2']
    
    print(f"\n{'='*70}")
    print("COMBINED TOTALS:")
    print(f"  Total ice pixels: {total_pixels:,}")
    print(f"  Total ice area: {total_area:.2f} km²")
    print(f"  Total coverage: {total_coverage:.0f} km²")
    print(f"  Ice fraction: {(total_area/total_coverage)*100:.4f}%")
    
    scaling_factor = total_pixels / p1['ice_pixels'] if p1['ice_pixels'] > 0 else total_pixels / 37
    print(f"\nSCALING:")
    if p1['ice_pixels'] > 0:
        print(f"  Phase 2 detected {scaling_factor:.1f}x more ice than Phase 1")
    else:
        print(f"  Phase 1 data not available (using reference: 37 pixels)")
        print(f"  Phase 2 detected {scaling_factor:.1f}x more ice than Phase 1 reference")
    
    # Save JSON report
    combined = {
        'phase1': p1,
        'phase2': p2,
        'combined': {
            'total_ice_pixels': total_pixels,
            'total_ice_area_km2': total_area,
            'total_coverage_km2': total_coverage,
            'ice_fraction_percent': (total_area/total_coverage)*100,
            'scaling_factor': scaling_factor,
        },
        'comparison': {
            'resolution': f"Phase 1: {p1['resolution_m']}m, Phase 2: {p2['resolution_m']:.0f}m",
            'coverage': f"Phase 1: {p1['coverage_km2']:.0f} km², Phase 2: {p2['coverage_km2']:.0f} km²",
            'ice_detection_increase': f"{scaling_factor:.1f}x",
        }
    }
    
    out_path = OUTPUTS / "combined_ice_inventory.json"
    with open(out_path, 'w') as f:
        json.dump(combined, f, indent=2)
    
    print(f"\n✓ Combined inventory saved: {out_path}")
    print("="*70 + "\n")
    
    return combined

if __name__ == "__main__":
    generate_combined_report()
