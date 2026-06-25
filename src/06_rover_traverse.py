"""
06_rover_traverse.py

Step 6: Rover Traverse Path Planning
  - Build terrain cost graph from LOLA DEM + hazard map
  - A* pathfinding from landing site to ice-bearing DSC targets
  - Multi-waypoint optimization
  - Export traverse path as GeoJSON + summary table

Usage:
  python src/06_rover_traverse.py

Inputs:
  data/processed/lola_dem_5m.tif
  data/processed/hazard_score.tif
  data/processed/psr_mask.tif
  data/processed/ice_probability.tif
  data/exports/landing_sites.geojson
  data/exports/dsc_locations.geojson

Outputs:
  data/processed/cost_map.tif
  data/exports/traverse_path.geojson
  data/exports/traverse_waypoints.json
"""

import os
import sys
import json
import heapq
import numpy as np
import rasterio

sys.path.insert(0, os.path.dirname(__file__))
from utils.geo_utils import read_band, save_band, pixel_to_latlon, latlon_to_pixel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
EXPORTS   = os.path.join(ROOT, "data", "exports")


# ── Cost Function ─────────────────────────────────────────────────────────────

def build_cost_map(slope: np.ndarray,
                    hazard: np.ndarray,
                    psr_mask: np.ndarray,
                    pixel_size_m: float = 5.0) -> np.ndarray:
    """
    Per-pixel traversal cost map for the rover.

    Cost components:
      - Slope penalty:   prevents driving on steep terrain (>20° = very high)
      - Hazard penalty:  boulders/roughness slow the rover
      - Shadow penalty:  PSR pixels require extra power (rover battery drain)

    Returns
    -------
    cost_map : 2D float32 array (cost per pixel step)
    """
    # Slope cost: exponential penalty
    slope_cost = np.where(slope < 20.0,
                           1.0 + 4.0 * (slope / 20.0) ** 2,
                           1e6)  # impassable above 20°

    # Hazard cost: linear
    hazard_cost = 1.0 + 2.0 * np.clip(hazard, 0, 1)

    # Shadow/PSR cost: 2x energy needed in PSR
    shadow_cost = np.where(psr_mask == 1, 2.0, 1.0)

    cost = slope_cost * hazard_cost * shadow_cost
    cost[~np.isfinite(cost)] = 1e7

    return cost.astype(np.float32)


# ── A* Pathfinding ────────────────────────────────────────────────────────────

def astar(cost_map: np.ndarray,
           start: tuple, goal: tuple) -> list | None:
    """
    A* pathfinding on a 2D cost grid with 8-connectivity.
    Optimized for large grids by downsampling by a factor of 8.
    """
    ds_factor = 8
    
    # Downsample cost map by simple slicing
    cost_small = cost_map[::ds_factor, ::ds_factor]
    
    # Map start/goal to small grid
    sr = int(start[0] // ds_factor)
    sc = int(start[1] // ds_factor)
    gr = int(goal[0] // ds_factor)
    gc = int(goal[1] // ds_factor)
    
    # Ensure start/goal are within bounds of small grid
    H_small, W_small = cost_small.shape
    sr = np.clip(sr, 0, H_small - 1)
    sc = np.clip(sc, 0, W_small - 1)
    gr = np.clip(gr, 0, H_small - 1)
    gc = np.clip(gc, 0, W_small - 1)
    
    def heuristic(r, c):
        # Octile distance heuristic
        dr, dc = abs(r - gr), abs(c - gc)
        return max(dr, dc) + (np.sqrt(2) - 1) * min(dr, dc)
    
    # Priority queue: (f_score, g_score, row, col)
    open_set = []
    heapq.heappush(open_set, (heuristic(sr, sc), 0.0, sr, sc))
    
    g_score = np.full((H_small, W_small), np.inf)
    g_score[sr, sc] = 0.0
    came_from = {}
    
    # 8-directional moves
    MOVES = [(-1, -1), (-1, 0), (-1, 1),
             ( 0, -1),           ( 0, 1),
             ( 1, -1), ( 1, 0), ( 1, 1)]
    DIAG = {(-1, -1), (-1, 1), (1, -1), (1, 1)}
    
    while open_set:
        _, g, r, c = heapq.heappop(open_set)
        
        if r == gr and c == gc:
            # Reconstruct path and map back to full resolution
            path = []
            node = (r, c)
            while node in came_from:
                path.append((node[0] * ds_factor, node[1] * ds_factor))
                node = came_from[node]
            path.append((sr * ds_factor, sc * ds_factor))
            path.reverse()
            return path
            
        if g > g_score[r, c]:
            continue
            
        for dr, dc in MOVES:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < H_small and 0 <= nc < W_small):
                continue
                
            step = cost_small[nr, nc]
            if (dr, dc) in DIAG:
                step *= np.sqrt(2)
                
            new_g = g + step
            if new_g < g_score[nr, nc]:
                g_score[nr, nc] = new_g
                came_from[(nr, nc)] = (r, c)
                f = new_g + heuristic(nr, nc)
                heapq.heappush(open_set, (f, new_g, nr, nc))
                
    return None  # No path found


def simplify_path(path: list, n_waypoints: int = 20) -> list:
    """Downsample path to approximately n_waypoints evenly spaced waypoints."""
    if len(path) <= n_waypoints:
        return path
    indices = np.linspace(0, len(path) - 1, n_waypoints, dtype=int)
    return [path[i] for i in indices]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_rover_traverse() -> dict:
    print("=" * 60)
    print(" LUNAR ICE PIPELINE — Step 6: Rover Traverse Planning")
    print("=" * 60)

    # ── Load data ─────────────────────────────────────────────────────────────
    lola_path   = os.path.join(PROCESSED, "lola_dem_5m.tif")
    hazard_path = os.path.join(PROCESSED, "hazard_score.tif")
    psr_path    = os.path.join(PROCESSED, "psr_mask.tif")
    ls_path     = os.path.join(EXPORTS,   "landing_sites.geojson")
    dsc_path    = os.path.join(EXPORTS,   "dsc_locations.geojson")

    for p in [lola_path, hazard_path]:
        if not os.path.exists(p):
            print(f"[ERROR] Missing: {p}. Run previous steps first.")
            return {}

    print("\n[1/4] Loading terrain data...")
    dem,    profile = read_band(lola_path)
    hazard, _       = read_band(hazard_path)
    pixel_size_m    = abs(profile["transform"].a)

    slope_path = os.path.join(PROCESSED, "slope_map.tif")
    slope = read_band(slope_path)[0] if os.path.exists(slope_path) else np.zeros_like(dem)

    psr_mask = read_band(psr_path)[0].astype(np.uint8) if os.path.exists(psr_path) else np.zeros_like(dem, dtype=np.uint8)

    # ── Build cost map ────────────────────────────────────────────────────────
    print("\n[2/4] Building traversal cost map...")
    cost_map = build_cost_map(slope, hazard, psr_mask, pixel_size_m)
    cost_path = os.path.join(PROCESSED, "cost_map.tif")
    save_band(cost_map, profile, cost_path)
    print(f"  Saved cost map: {cost_path}")

    # ── Define start (landing site) ───────────────────────────────────────────
    if os.path.exists(ls_path):
        with open(ls_path) as f:
            ls_data = json.load(f)
        best_ls = ls_data["features"][0]["properties"]
        start_lat = best_ls["lat"]
        start_lon = best_ls["lon"]
        start_pixel = latlon_to_pixel(start_lat, start_lon, profile)
        print(f"\n  Start: Landing Site LS-1 ({start_lat:.4f}°, {start_lon:.4f}°)")
    else:
        # Default: center of scene
        start_pixel = (dem.shape[0] // 2, dem.shape[1] // 2)
        start_lat, start_lon = pixel_to_latlon(*start_pixel, profile)
        print(f"\n  [WARNING] No landing site found. Using scene center.")

    # ── Define goals (DSC targets) ────────────────────────────────────────────
    goals = []
    if os.path.exists(dsc_path):
        with open(dsc_path) as f:
            dsc_data = json.load(f)
        for feat in dsc_data["features"][:5]:   # top 5 DSCs
            lat = feat["properties"]["lat"]
            lon = feat["properties"]["lon"]
            pix = latlon_to_pixel(lat, lon, profile)
            goals.append({"pixel": pix, "lat": lat, "lon": lon,
                           "area_km2": feat["properties"].get("area_km2", 0)})
        print(f"  Goals: {len(goals)} DSC target(s)")
    else:
        # Use highest ice probability pixel as goal
        ice_prob_path = os.path.join(PROCESSED, "ice_probability.tif")
        if os.path.exists(ice_prob_path):
            ice_prob, _ = read_band(ice_prob_path)
            idx = np.unravel_index(np.nanargmax(ice_prob), ice_prob.shape)
            lat, lon = pixel_to_latlon(idx[0], idx[1], profile)
            goals.append({"pixel": idx, "lat": lat, "lon": lon, "area_km2": 0})
            print(f"  Goal: highest ice probability at ({lat:.4f}°, {lon:.4f}°)")

    # ── A* pathfinding ────────────────────────────────────────────────────────
    print("\n[3/4] Running A* pathfinding...")
    all_paths = []
    all_features = []
    total_distance = 0.0

    current_start = start_pixel
    for i, goal_info in enumerate(goals):
        goal_pixel = goal_info["pixel"]
        print(f"  Segment {i+1}: {current_start} → {goal_pixel}")
        path = astar(cost_map, current_start, goal_pixel)

        if path is None:
            print(f"  [WARNING] No path found to goal {i+1}. Skipping.")
            continue

        # Compute exact path distance in meters
        dist_m = 0.0
        for idx in range(len(path) - 1):
            r1, c1 = path[idx]
            r2, c2 = path[idx+1]
            dist_m += np.sqrt((r1 - r2)**2 + (c1 - c2)**2) * pixel_size_m
        total_distance += dist_m
        print(f"    Path found: {len(path)} pixels, ~{dist_m/1000:.2f} km")

        # Simplify for GeoJSON (20 waypoints per segment)
        waypoints = simplify_path(path, n_waypoints=20)
        all_paths.extend(waypoints)

        # Create LineString coordinates
        coords = []
        for r, c in waypoints:
            lat, lon = pixel_to_latlon(r, c, profile)
            elev = float(dem[r, c]) if np.isfinite(dem[r, c]) else 0.0
            coords.append([lon, lat, elev])

        all_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "segment": i + 1,
                "goal_lat": goal_info["lat"],
                "goal_lon": goal_info["lon"],
                "length_m": round(dist_m, 0),
                "n_waypoints": len(waypoints),
            }
        })

        # Next start = this goal
        current_start = goal_pixel

    # ── Build waypoint table ──────────────────────────────────────────────────
    waypoint_table = []
    cumulative_dist = 0.0
    for j, (r, c) in enumerate(all_paths[::max(1, len(all_paths)//50)]):
        lat, lon = pixel_to_latlon(r, c, profile)
        elev = float(dem[r, c]) if np.isfinite(dem[r, c]) else 0.0
        hz = float(hazard[r, c]) if np.isfinite(hazard[r, c]) else 0.0
        sl = float(slope[r, c]) if np.isfinite(slope[r, c]) else 0.0
        cumulative_dist += pixel_size_m
        waypoint_table.append({
            "waypoint_id": j + 1,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "elevation_m": round(elev, 1),
            "slope_deg": round(sl, 2),
            "hazard_score": round(hz, 4),
            "cumulative_dist_km": round(cumulative_dist / 1000, 3),
        })

    # ── Export ────────────────────────────────────────────────────────────────
    print("\n[4/4] Exporting traverse path...")

    traverse_path = os.path.join(EXPORTS, "traverse_path.geojson")
    with open(traverse_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f, indent=2)

    waypoints_path = os.path.join(EXPORTS, "traverse_waypoints.json")
    with open(waypoints_path, "w") as f:
        json.dump({
            "total_distance_km": round(total_distance / 1000, 2),
            "n_segments": len(all_features),
            "waypoints": waypoint_table
        }, f, indent=2)

    print(f"  Saved traverse path:      {traverse_path}")
    print(f"  Saved waypoint table:     {waypoints_path}")

    print("\n" + "=" * 60)
    print(" Rover Traverse Planning complete.")
    print(f"  Total traverse distance: {total_distance/1000:.2f} km")
    print(f"  Segments: {len(all_features)}, Waypoints: {len(waypoint_table)}")
    print("=" * 60)
    print(" Next: run  python src/07_ice_volume_estimation.py")

    return {
        "cost_map": cost_path,
        "traverse_path_geojson": traverse_path,
        "waypoints_json": waypoints_path,
        "total_distance_km": total_distance / 1000,
    }


if __name__ == "__main__":
    run_rover_traverse()
