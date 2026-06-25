import rasterio
import geopandas
import numpy
import scipy
import cv2
import skimage
import pyproj
from rasterio.warp import reproject

print("=" * 40)
print("ALL IMPORTS OK")
print("=" * 40)
print(f"rasterio : {rasterio.__version__}")
print(f"numpy    : {numpy.__version__}")
print(f"cv2      : {cv2.__version__}")
print(f"scipy    : {scipy.__version__}")
print(f"skimage  : {skimage.__version__}")
print(f"pyproj   : {pyproj.__version__}")
print(f"geopandas: {geopandas.__version__}")
print(f"GDAL     : {rasterio.gdal_version()}")
print("=" * 40)
print("Environment is READY for pipeline!")
