/**
 * app_phase2.js — Phase 2 Regional South Pole Ice Detection Dashboard
 * 
 * Displays DFSAR regional ice detection on lunar south pole stereographic projection
 * Shows 54,558 ice pixels detected across ~320 km² coverage area
 */

'use strict';

// ── Configuration ─────────────────────────────────────────────────────────────

const CFG = {
  dataDir: './data/',
  overlayDir: './data/overlays/',
};

// ── State ─────────────────────────────────────────────────────────────────────

const STATE = {
  map: null,
  meta: null,
  layers: {},
  phase2Meta: null,
};

// ── Utilities ─────────────────────────────────────────────────────────────────

async function fetchJSON(filename) {
  const url = CFG.dataDir + filename + '?t=' + Date.now();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.json();
}

function toast(msg, duration = 3000) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), duration);
}

// ── Map Initialization ────────────────────────────────────────────────────────

async function initMap() {
  console.log('[Init] Loading Phase 2 metadata...');
  
  try {
    STATE.phase2Meta = await fetchJSON('overlays/phase2_meta.json');
  } catch (e) {
    console.error('Failed to load Phase 2 metadata:', e);
    toast('⚠ Phase 2 data not found. Run generate_proper_south_pole_map.py', 6000);
    return null;
  }
  
  const bounds = STATE.phase2Meta.ice_overlay.bounds;
  console.log('[Init] Ice overlay bounds:', bounds);
  
  // Create Leaflet map with Simple CRS (direct coordinate mapping)
  STATE.map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -3,
    maxZoom: 4,
    zoom: -2,
    center: [0, 0],
    zoomControl: true,
    attributionControl: false,
  });
  
  console.log('[Init] Map created');
  
  // Calculate Leaflet bounds from meters
  // In L.CRS.Simple, [lat, lng] maps directly to [y, x]
  const leafletBounds = [
    [bounds.south, bounds.west],
    [bounds.north, bounds.east]
  ];
  
  console.log('[Init] Leaflet bounds:', leafletBounds);
  
  // Add basemap (placeholder terrain)
  const basemap = L.imageOverlay(
    CFG.overlayDir + 'south_pole_basemap.png',
    leafletBounds,
    {
      opacity: 0.5,
      interactive: false,
      zIndex: 1,
    }
  );
  basemap.addTo(STATE.map);
  STATE.layers.basemap = basemap;
  
  // Add ice detection overlay
  const iceOverlay = L.imageOverlay(
    CFG.overlayDir + 'ice_detection_overlay.png',
    leafletBounds,
    {
      opacity: 0.85,
      interactive: false,
      zIndex: 10,
    }
  );
  
  STATE.layers.iceOverlay = iceOverlay;
  
  // Toggle control
  const cb = document.getElementById('layer-ice');
  if (cb) {
    if (cb.checked) iceOverlay.addTo(STATE.map);
    cb.addEventListener('change', () => {
      if (cb.checked) {
        iceOverlay.addTo(STATE.map);
        toast('Ice detection overlay: ON', 1500);
      } else {
        STATE.map.removeLayer(iceOverlay);
        toast('Ice detection overlay: OFF', 1500);
      }
    });
  }
  
  // Fit to bounds
  STATE.map.fitBounds(leafletBounds);
  STATE.map.setMaxBounds(leafletBounds);
  STATE.map.options.maxBoundsViscosity = 1.0;
  
  // Coordinate display
  STATE.map.on('mousemove', e => {
    const x = e.latlng.lng;
    const y = e.latlng.lat;
    document.getElementById('map-coords').textContent =
      `📍 ${(x / 1000).toFixed(1)} km E,  ${(y / 1000).toFixed(1)} km N  (South Pole Stereo)`;
  });
  
  // Add scale indicator
  addScaleBar();
  
  // Add legend
  addLegend();
  
  return STATE.map;
}

// ── Legend ─────────────────────────────────────────────────────────────────────

function addLegend() {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = () => {
    const div = L.DomUtil.create('div');
    div.style.cssText =
      'background:rgba(5,15,35,0.9);border:1px solid #1e3a5f;border-radius:8px;' +
      'padding:10px 14px;font-size:11px;color:#7eb8e8;line-height:1.8;backdrop-filter:blur(8px);';
    div.innerHTML = `
      <b style="color:#22d3ee;font-size:12px">Ice Detection</b><br>
      <span style="display:inline-block;width:14px;height:14px;background:linear-gradient(90deg,#50D0E8,#C850D0);border-radius:3px;vertical-align:middle;margin-right:6px"></span> Ice pixels (CPR>1.0, DOP<0.13)<br>
      <span style="color:#888;font-size:10px">54,558 pixels | 34.1 km² | 25m resolution</span><br>
      <br>
      <b style="color:#22d3ee;font-size:12px">Coverage</b><br>
      <span style="color:#888;font-size:10px">Chandrayaan-2 DFSAR Regional<br>South Pole: -90° to -84°S</span>`;
    return div;
  };
  legend.addTo(STATE.map);
}

function addScaleBar() {
  const scale = L.control({ position: 'bottomleft' });
  scale.onAdd = () => {
    const div = L.DomUtil.create('div');
    div.style.cssText =
      'background:rgba(5,15,35,0.9);border:1px solid #1e3a5f;border-radius:6px;' +
      'padding:6px 10px;font-size:10px;color:#7eb8e8;font-weight:600;';
    div.innerHTML = `Scale: 25m/pixel`;
    return div;
  };
  scale.addTo(STATE.map);
}

// ── Statistics Display ─────────────────────────────────────────────────────────

function updateStatistics() {
  if (!STATE.phase2Meta) return;
  
  const ice = STATE.phase2Meta.ice_overlay;
  const area_km2 = (ice.ice_pixels * ice.resolution_m * ice.resolution_m) / 1e6;
  
  // Update statistics panel
  document.getElementById('stat-pixels').textContent = ice.ice_pixels.toLocaleString();
  document.getElementById('stat-area').textContent = area_km2.toFixed(1) + ' km²';
  document.getElementById('stat-resolution').textContent = ice.resolution_m + 'm';
  
  const coverage_km2 = (ice.bounds.east - ice.bounds.west) * 
                       (ice.bounds.north - ice.bounds.south) / 1e6;
  document.getElementById('stat-coverage').textContent = coverage_km2.toFixed(0) + ' km²';
  
  const fraction = (area_km2 / coverage_km2) * 100;
  document.getElementById('stat-fraction').textContent = fraction.toFixed(3) + '%';
}

// ── Zoom Controls ──────────────────────────────────────────────────────────────

function initZoomControls() {
  document.getElementById('btn-zoom-fit').addEventListener('click', () => {
    if (!STATE.phase2Meta) return;
    const bounds = STATE.phase2Meta.ice_overlay.bounds;
    const leafletBounds = [
      [bounds.south, bounds.west],
      [bounds.north, bounds.east]
    ];
    STATE.map.fitBounds(leafletBounds);
    toast('Zoomed to full extent', 1500);
  });
  
  document.getElementById('btn-zoom-pole').addEventListener('click', () => {
    STATE.map.setView([0, 0], 0);
    toast('Centered on South Pole (90°S)', 1500);
  });
}

// ── Main ───────────────────────────────────────────────────────────────────────

async function init() {
  console.log('[App] Initializing Phase 2 dashboard...');
  
  const map = await initMap();
  if (!map) {
    document.getElementById('error-banner').classList.remove('hidden');
    document.getElementById('error-banner').textContent =
      '⚠ Phase 2 data not loaded. Run: python scripts/generate_proper_south_pole_map.py';
    return;
  }
  
  updateStatistics();
  initZoomControls();
  
  toast('✓ Phase 2 Regional Ice Detection Loaded: 54,558 pixels', 3000);
  console.log('[App] Dashboard ready');
}

window.addEventListener('DOMContentLoaded', init);
