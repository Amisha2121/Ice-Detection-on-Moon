"""
Generate a demo traverse path connecting landing sites
This creates a realistic traverse for dashboard visualization
"""
import json
import os
import math

ROOT = os.path.dirname(os.path.abspath(__file__))
EXPORTS = os.path.join(ROOT, "data", "exports")
DASH_DATA = os.path.join(ROOT, "dashboard", "data")

# Load landing sites
with open(os.path.join(EXPORTS, "landing_sites.geojson"), encoding='utf-8') as f:
    landing_sites = json.load(f)

sites = landing_sites['features']
print(f"Loaded {len(sites)} landing sites")

# Create traverse segments connecting the sites
segments = []

for i in range(len(sites) - 1):
    site1 = sites[i]
    site2 = sites[i + 1]
    
    lon1, lat1 = site1['geometry']['coordinates']
    lon2, lat2 = site2['geometry']['coordinates']
    
    # Create a path with intermediate waypoints (10 points)
    coords = []
    for t in range(11):
        frac = t / 10.0
        lon_interp = lon1 + (lon2 - lon1) * frac
        lat_interp = lat1 + (lat2 - lat1) * frac
        
        # Add elevation (approximate)
        elev = -4200 + (frac * 100)  # Simple elevation variation
        coords.append([lon_interp, lat_interp, elev])
    
    # Calculate segment length
    R = 1737400  # Moon radius in meters
    def haversine_distance(lat1, lon1, lat2, lon2):
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)
        dlat = lat2_rad - lat1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c
    
    length_m = haversine_distance(lat1, lon1, lat2, lon2)
    
    segment = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        },
        "properties": {
            "segment_id": i,
            "from_site": site1['properties']['label'],
            "to_site": site2['properties']['label'],
            "length_m": length_m,
            "corridor_name": chr(65 + i)  # A, B, C...
        }
    }
    segments.append(segment)
    print(f"  Segment {chr(65 + i)}: {site1['properties']['label']} → {site2['properties']['label']} ({length_m/1000:.2f} km)")

# Create traverse GeoJSON
traverse_geojson = {
    "type": "FeatureCollection",
    "features": segments
}

# Save to exports
traverse_path = os.path.join(EXPORTS, "traverse_path.geojson")
with open(traverse_path, "w", encoding='utf-8') as f:
    json.dump(traverse_geojson, f, indent=2)
print(f"\n✓ Saved: {traverse_path}")

# Create waypoints
total_distance = sum(seg['properties']['length_m'] for seg in segments)
waypoints = []
cumulative_dist = 0

for seg in segments:
    coords = seg['geometry']['coordinates']
    seg_length = seg['properties']['length_m']
    
    for i, coord in enumerate(coords):
        waypoint = {
            "segment": seg['properties']['corridor_name'],
            "lon": coord[0],
            "lat": coord[1],
            "elevation_m": round(coord[2], 1),
            "cumulative_dist_km": round(cumulative_dist / 1000, 2)
        }
        waypoints.append(waypoint)
        cumulative_dist += seg_length / (len(coords) - 1) if len(coords) > 1 else 0

waypoints_data = {
    "total_distance_km": round(total_distance / 1000, 2),
    "n_segments": len(segments),
    "waypoints": waypoints
}

waypoints_path = os.path.join(EXPORTS, "traverse_waypoints.json")
with open(waypoints_path, "w", encoding='utf-8') as f:
    json.dump(waypoints_data, f, indent=2)
print(f"✓ Saved: {waypoints_path}")

print(f"\n{'='*60}")
print(f"Traverse generation complete!")
print(f"Total distance: {total_distance/1000:.2f} km")
print(f"Segments: {len(segments)}")
print(f"Waypoints: {len(waypoints)}")
print(f"{'='*60}")
print("\nNow run: python src/export_for_dashboard.py")
