import os
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
import cv2

ROOT = r"c:\Users\AMISHA\Desktop\Codes\Ice_on_moon"
INPUT_IMG = os.path.join(ROOT, "moon_global.png")
OUT_IMG = os.path.join(ROOT, "dashboard", "data", "overlays", "global_basemap.png")

# Lunar South Pole Stereographic
DST_CRS = "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=1737400 +b=1737400 +units=m +no_defs"

# Context map bounds (3000 km radius from the south pole)
radius = 3000000.0
dst_bounds = (-radius, -radius, radius, radius)
dst_shape = (1024, 1024)
dst_transform = from_bounds(*dst_bounds, dst_shape[1], dst_shape[0])

def main():
    print("Reading global moon map...")
    # Read the PNG using cv2 to handle typical RGB loading
    img = cv2.imread(INPUT_IMG, cv2.IMREAD_COLOR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Clementine map is global equirectangular:
    # Left: -180, Right: 180, Top: 90, Bottom: -90
    h, w, c = img.shape
    src_transform = from_bounds(-180, -90, 180, 90, w, h)
    src_crs = "+proj=longlat +a=1737400 +b=1737400 +no_defs"
    
    # Create empty destination array
    dst_data = np.zeros((c, dst_shape[0], dst_shape[1]), dtype=np.uint8)
    
    # Reproject each band
    print("Reprojecting to South Pole Stereographic...")
    for band in range(c):
        reproject(
            source=img[:, :, band],
            destination=dst_data[band],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=DST_CRS,
            resampling=Resampling.bilinear
        )
    
    # Save as PNG
    print("Saving basemap overlay...")
    out_img = np.dstack([dst_data[0], dst_data[1], dst_data[2]])
    out_img = cv2.cvtColor(out_img, cv2.COLOR_RGB2BGR)
    
    # Add alpha channel (make black background transparent)
    # The area outside the moon globe will project as 0 (black). 
    # Let's make pure black transparent, or just leave it since the user wants a full map.
    # Actually, a black background for space is fine. Let's make it a nice dark space color.
    out_img[np.all(out_img == [0,0,0], axis=-1)] = [11, 12, 16] # match CSS #0b0c10
    
    cv2.imwrite(OUT_IMG, out_img)
    print("Done. Saved to", OUT_IMG)

if __name__ == "__main__":
    main()
