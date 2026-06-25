import os, sys
import numpy as np
import rasterio
from scipy.ndimage import uniform_filter, label

ROOT = r"c:\Users\AMISHA\Desktop\Codes\Ice_on_moon"
PROC = os.path.join(ROOT, "data", "processed")

dem_path = os.path.join(PROC, "lola_dem_5m.tif")
psr_path = os.path.join(PROC, "psr_mask.tif")

if not os.path.exists(dem_path) or not os.path.exists(psr_path):
    print("Missing files. Run pipeline step 1 and 2 first.")
    sys.exit(1)

with rasterio.open(dem_path) as src:
    dem = src.read(1).astype(np.float32)
with rasterio.open(psr_path) as src:
    psr = src.read(1).astype(np.uint8)

print(f"DEM shape: {dem.shape}, PSR pixels: {np.sum(psr == 1)}")

# Try different window sizes and thresholds
for window in [50, 100, 150, 200]:
    for threshold in [10.0, 25.0, 50.0]:
        dem_mean = uniform_filter(dem, size=window)
        depression = (dem_mean - dem) > threshold
        dsc = (psr == 1) & depression
        labeled, n_regions = label(dsc)
        
        # count regions with area >= 50
        large_regions = 0
        total_area = 0
        for r in range(1, n_regions + 1):
            area = np.sum(labeled == r)
            if area >= 50:
                large_regions += 1
                total_area += area
        print(f"Window={window:3d}, Thresh={threshold:4.1f}m -> DSC regions (area>=50): {large_regions}, total pixels: {total_area}")
