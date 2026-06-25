import os
import numpy as np
import rasterio

PROCESSED = 'data/processed'

cpr_path = os.path.join(PROCESSED, 'cpr_map.tif')
dop_path = os.path.join(PROCESSED, 'dop_map.tif')
psr_path = os.path.join(PROCESSED, 'psr_mask.tif')

with rasterio.open(cpr_path) as src:
    cpr_data = src.read(1)
with rasterio.open(dop_path) as src:
    dop_data = src.read(1)
with rasterio.open(psr_path) as src:
    psr_mask = src.read(1)

print("CPR shape:", cpr_data.shape)
print("DOP shape:", dop_data.shape)
print("PSR shape:", psr_mask.shape)

print("PSR pixels non-zero:", np.sum(psr_mask > 0))
print("CPR > 1.0 pixels:", np.sum(cpr_data > 1.0))
print("DOP < 0.13 pixels:", np.sum(dop_data < 0.13))
print("DOP < 0.30 pixels:", np.sum(dop_data < 0.30))

print("Intersection (DOP < 0.13):", np.sum((psr_mask > 0) & (cpr_data > 1.0) & (dop_data < 0.13)))
print("Intersection (DOP < 0.30):", np.sum((psr_mask > 0) & (cpr_data > 1.0) & (dop_data < 0.30)))
