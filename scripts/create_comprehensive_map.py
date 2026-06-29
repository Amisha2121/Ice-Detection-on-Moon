"""
create_comprehensive_map.py

Generate comprehensive south pole ice distribution map combining:
- Phase 2 regional ice detection raster
- DFSAR swath coverage footprints
- Geographic context (craters, pole location)
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Circle, Rectangle
import rasterio
from rasterio.plot import show
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
OUTPUTS = os.path.join(ROOT, "outputs")
os.makedirs(OUTPUTS, exist_ok=True)

CRATERS = {
    "Shackleton": {"x": 0, "y": 0, "r": 10500},  # meters, approximate
    "Faustini": {"x": -50000, "y": 80000, "r": 19500},
    "Haworth": {"x": 30000, "y": 90000, "r": 25500},
    "Cabeus": {"x": -100000, "y": 120000, "r": 49000},
}

def create_comprehensive_ice_map():
    """Generate publication-quality ice distribution map."""
    
    print("\n" + "="*70)
    print("  COMPREHENSIVE SOUTH POLE ICE DISTRIBUTION MAP")
    print("="*70 + "\n")
    
    # Load Phase 2 ice probability
    ice_path = os.path.join(PROCESSED, "ice_probability_regional.tif")
    if not os.path.exists(ice_path):
        print(f"ERROR: Ice probability map not found: {ice_path}")
        return
    
    print("Loading Phase 2 ice probability raster...")
    with rasterio.open(ice_path) as src:
        ice_data = src.read(1)
        transform = src.transform
        bounds = src.bounds
        crs = src.crs
        
        # Get extent in meters
        extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    
    print(f"  Shape: {ice_data.shape}")
    print(f"  Bounds: {bounds}")
    print(f"  Ice pixels: {np.sum(ice_data > 0):,}")
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 16), dpi=150)
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0a0a0a')
    
    # Plot ice probability
    ice_masked = np.ma.masked_where(ice_data == 0, ice_data)
    
    im = ax.imshow(ice_masked, extent=extent, origin='upper',
                   cmap='plasma', alpha=0.9, interpolation='nearest',
                   vmin=0, vmax=1)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Ice Probability', fontsize=14, color='white')
    cbar.ax.tick_params(colors='white', labelsize=11)
    
    # Add crater annotations
    for name, info in CRATERS.items():
        circle = Circle((info['x'], info['y']), info['r'],
                       color='cyan', fill=False, linewidth=2,
                       linestyle='--', alpha=0.6)
        ax.add_patch(circle)
        
        ax.text(info['x'], info['y'] + info['r'] + 5000, name,
               ha='center', va='bottom', fontsize=12,
               color='cyan', fontweight='bold',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7))
    
    # Mark south pole
    ax.plot(0, 0, 'r*', markersize=20, markeredgecolor='white', markeredgewidth=1.5)
    ax.text(0, -8000, 'South Pole\n90°S', ha='center', va='top',
           fontsize=11, color='red', fontweight='bold',
           bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7))
    
    # Grid and labels
    ax.grid(True, color='#333333', linestyle=':', linewidth=0.5, alpha=0.5)
    ax.set_xlabel('Easting (km)', fontsize=13, color='white', fontweight='bold')
    ax.set_ylabel('Northing (km)', fontsize=13, color='white', fontweight='bold')
    
    # Convert axis labels to km
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1000:.0f}'))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, p: f'{y/1000:.0f}'))
    
    ax.tick_params(colors='white', labelsize=11)
    
    # Title
    num_ice = int(np.sum(ice_data > 0))
    area_km2 = num_ice * 25 * 25 / 1e6
    
    title = (f'Lunar South Pole Ice Distribution\n'
            f'Chandrayaan-2 DFSAR Polarimetric Analysis\n'
            f'{num_ice:,} ice pixels | {area_km2:.1f} km² ice-bearing area')
    
    ax.set_title(title, fontsize=16, fontweight='bold', color='white', pad=20)
    
    # Add legend
    legend_elements = [
        mpatches.Patch(facecolor='#cc4778', edgecolor='#d646a0', label='High ice probability'),
        mpatches.Patch(facecolor='#7e03a8', edgecolor='#9a4e99', label='Medium ice probability'),
        Circle((0, 0), 1, color='cyan', fill=False, linewidth=2, linestyle='--', label='Major craters'),
        plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='r',
                  markersize=12, label='South Pole (90°S)', linestyle='None'),
    ]
    
    ax.legend(handles=legend_elements, loc='upper right', fontsize=11,
             framealpha=0.9, facecolor='#1a1a1a', edgecolor='white')
    
    # Add data source annotation
    ax.text(0.02, 0.02, 'Data: ISRO Chandrayaan-2 DFSAR\nResolution: 25m | CRS: Moon 2000 South Pole Stereographic',
           transform=ax.transAxes, fontsize=9, color='#888888',
           verticalalignment='bottom',
           bbox=dict(boxstyle='round', facecolor='black', alpha=0.7))
    
    plt.tight_layout()
    
    # Save
    out_path = os.path.join(OUTPUTS, 'comprehensive_ice_distribution.png')
    plt.savefig(out_path, dpi=300, facecolor='#0a0a0a', edgecolor='none', bbox_inches='tight')
    print(f"\n✓ Comprehensive map saved: {out_path}")
    
    # Also create a simplified version (smaller file size)
    out_path_web = os.path.join(OUTPUTS, 'ice_distribution_web.png')
    plt.savefig(out_path_web, dpi=150, facecolor='#0a0a0a', edgecolor='none', bbox_inches='tight')
    print(f"✓ Web version saved: {out_path_web}")
    
    plt.close()
    
    # Generate statistics summary
    stats = {
        'total_ice_pixels': int(num_ice),
        'ice_area_km2': float(area_km2),
        'coverage_km2': float(ice_data.size * 25 * 25 / 1e6),
        'ice_fraction_percent': float(num_ice / ice_data.size * 100),
        'resolution_m': 25,
        'bounds_m': {
            'west': float(bounds.left),
            'east': float(bounds.right),
            'south': float(bounds.bottom),
            'north': float(bounds.top),
        }
    }
    
    stats_path = os.path.join(OUTPUTS, 'ice_distribution_stats.json')
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"✓ Statistics saved: {stats_path}")
    
    print("\n" + "="*70)
    print("  COMPREHENSIVE ICE MAP COMPLETE")
    print("="*70 + "\n")
    
    return out_path

if __name__ == "__main__":
    create_comprehensive_ice_map()
