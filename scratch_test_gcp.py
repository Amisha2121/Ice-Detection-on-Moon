import os
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.control import GroundControlPoint
import pandas as pd
import numpy as np
from pyproj import Transformer

os.environ['PROJ_IGNORE_CELESTIAL_BODY'] = 'YES'

ref_path = 'data/processed/lola_dem_5m.tif'
xml_path = 'data/raw/ohrc/ch2_ohr_ncp_20260103T1005176450_d_img_d18/data/calibrated/20260103/ch2_ohr_ncp_20260103T1005176450_d_img_d18.xml'
csv_path = 'data/raw/ohrc/ch2_ohr_ncp_20260103T1005176450_d_img_d18/geometry/calibrated/20260103/ch2_ohr_ncp_20260103T1005176450_g_grd_d18.csv'
dst_path = 'data/processed/ohrc_radiance_test.tif'

# Open ref
with rasterio.open(ref_path) as ref:
    ref_crs = ref.crs
    ref_transform = ref.transform
    ref_width = ref.width
    ref_height = ref.height
    ref_bounds = ref.bounds
    ref_profile = ref.profile.copy()

print("LOLA DEM shape:", (ref_height, ref_width))
print("LOLA DEM bounds:", ref_bounds)

# Read GCPs
df = pd.read_csv(csv_path)
df_sub = df.iloc[::100]  # every 100th point

# Set up transformer
transformer = Transformer.from_crs("EPSG:4326", ref_crs, always_xy=True)

gcps = []
for _, r in df_sub.iterrows():
    # Convert lat/lon to target CRS (lunar stereographic)
    x, y = transformer.transform(r['Longitude'], r['Latitude'])
    # In rasterio GCP: col is Pixel (x in image space), row is Scan (y in image space)
    gcp = GroundControlPoint(
        row=float(r['Scan']),
        col=float(r['Pixel']),
        x=x,
        y=y
    )
    gcps.append(gcp)

print(f"Created {len(gcps)} GCPs.")

# Set up output profile
out_profile = ref_profile.copy()
out_profile.update({
    "count": 1,
    "dtype": "uint8",
    "compress": "lzw",
    "nodata": 0
})

print("Running warp...")
try:
    with rasterio.open(xml_path) as src:
        with rasterio.open(dst_path, "w", **out_profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                gcps=gcps,
                src_crs=ref_crs,
                dst_crs=ref_crs,
                dst_transform=ref_transform,
                resampling=Resampling.bilinear
            )
    print("Warp completed successfully!")
    with rasterio.open(dst_path) as test:
        data = test.read(1)
        print("Warped data min/max/mean:", data.min(), data.max(), data.mean())
        print("Warped data non-zero count:", np.sum(data > 0))
except Exception as e:
    print("Warp failed:", e)
