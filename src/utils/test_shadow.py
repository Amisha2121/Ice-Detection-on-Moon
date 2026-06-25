import numpy as np
import time
from scipy.ndimage import generic_filter, uniform_filter

def compute_roughness_original(slope: np.ndarray, window: int = 10) -> np.ndarray:
    def _local_std(values):
        return np.std(values)
    return generic_filter(slope.astype(np.float64), _local_std, size=window).astype(np.float32)

def compute_roughness_vectorized(slope: np.ndarray, window: int = 10) -> np.ndarray:
    slope_sq = slope ** 2
    mean_slope = uniform_filter(slope, size=window)
    mean_slope_sq = uniform_filter(slope_sq, size=window)
    var = mean_slope_sq - (mean_slope ** 2)
    var = np.clip(var, 0, None)
    return np.sqrt(var).astype(np.float32)

# Test on 200x200 array
slope = np.random.uniform(0, 45, (200, 200)).astype(np.float32)

print("Running original roughness...")
t0 = time.time()
r1 = compute_roughness_original(slope, window=10)
t1 = time.time()
print(f"Original took {t1-t0:.4f}s")

print("Running vectorized roughness...")
t2 = time.time()
r2 = compute_roughness_vectorized(slope, window=10)
t3 = time.time()
print(f"Vectorized took {t3-t2:.4f}s")

# Check similarity
diff = np.abs(r1 - r2)
max_diff = np.max(diff)
print(f"Max difference: {max_diff:.6f}")
