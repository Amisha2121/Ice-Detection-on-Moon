/**
 * app_unified.js — Unified Lunar South Pole Ice Detection Dashboard
 * 
 * Single map showing all ice detection results from Chandrayaan-2 DFSAR
 * No phase separation - one unified view of southern pole ice
 */

'use strict';

const CFG = {
  dataDir: './data/',
  overlayDir: './data/overlays/',
};

const STATE = {
  map: null,
  layers: {},
  metadata: null,
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
  if (!el) return;
  el.textContent = msg;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), duration);
}

// ── Map Initialization ────────────────────────────────────────────────────────

async function initMap() {
  console.log('[Init] Loading ice detection metadata...');
  
  try {
    STATE.metadata = await fetchJSON('overlays/phase2_meta.json');
  } catch (e) {
    console.error('Failed to load metadata:', e);
    const banner = document.getElementById('error-banner');
    if (banner) {
      banner.textContent = '⚠ Ice detection data not found. Run: python scripts/generate_proper_south_pole_map.py';
      banner.classList.remove('hidden');
    }
    return null;
  }
  
  const bounds = STATE.metadata.ice_overlay.bounds;
  console.log('[Init] Coverage bounds (meters):', bounds);
  
  // Create map with Simple CRS
  STATE.map = L.map('map', {
    crs: L.CRS.Simple,
    minZoom: -3,
    maxZoom: 4,
    zoom: -2,
    center: [0, 0],
    zoomControl: true,
    attributionControl: false,
    preferCanvas: true,
  });
  
  // Leaflet bounds: [south, west] to [north, east]
  const leafletBounds = [
    [bounds.south, bounds.west],
    [bounds.north, bounds.east]
  ];
  
  console.log('[Init] Leaflet bounds:', leafletBounds);
  
  // Base terrain layer
  const basemap = L.imageOverlay(
    CFG.overlayDir + 'south_pole_basemap.png',
    leafletBounds,
    {
      opacity: 0.6,
      interactive: false,
      zIndex: 1,
      className: 'basemap-layer'
    }
  );
  basemap.addTo(STATE.map);
  STATE.layers.basemap = basemap;
  
  // Ice detection overlay
  const iceOverlay = L.imageOverlay(
    CFG.overlayDir + 'ice_detection_overlay.png',
    leafletBounds,
    {
      opacity: 0.90,
      interactive: false,
      zIndex: 10,
      className: 'ice-layer'
    }
  );
  
  STATE.layers.ice = iceOverlay;
  
  // Layer toggle
  const iceCheckbox = document.getElementById('layer-ice');
  if (iceCheckbox) {
    if (iceCheckbox.checked) iceOverlay.addTo(STATE.map);
    iceCheckbox.addEventListener('change', () => {
      if (iceCheckbox.checked) {
        iceOverlay.addTo(STATE.map);
        toast('Ice detection layer: ON', 1500);
      } else {
        STATE.map.removeLayer(iceOverlay);
        toast('Ice detection layer: OFF', 1500);
      }
    });
  }
  
  // Coverage context overlay (optional)
  const coverageCheckbox = document.getElementById('layer-coverage');
  if (coverageCheckbox) {
    const coverageOverlay = L.imageOverlay(
      CFG.overlayDir + 'regional_context.png',
      leafletBounds,
      {
        opacity: 0.4,
        interactive: false,
        zIndex: 5,
      }
    );
    STATE.layers.coverage = coverageOverlay;
    
    coverageCheckbox.addEventListener('change', () => {
      if (coverageCheckbox.checked) {
        coverageOverlay.addTo(STATE.map);
        toast('DFSAR coverage context: ON', 1500);
      } else {
        STATE.map.removeLayer(coverageOverlay);
        toast('DFSAR coverage context: OFF', 1500);
      }
    });
  }
  
  // Fit to data bounds
  STATE.map.fitBounds(leafletBounds);
  STATE.map.setMaxBounds(leafletBounds);
  STATE.map.options.maxBoundsViscosity = 1.0;
  
  // Coordinate display
  STATE.map.on('mousemove', e => {
    const x = e.latlng.lng;
    const y = e.latlng.lat;
    const coordDiv = document.getElementById('map-coords');
    if (coordDiv) {
      coordDiv.textContent = 
        `📍 ${(x / 1000).toFixed(1)} km E  ·  ${(y / 1000).toFixed(1)} km N  ·  South Pole Stereographic`;
    }
  });
  
  // Add visual elements
  addLegend();
  addScaleIndicator();
  
  console.log('[Init] Map initialized successfully');
  return STATE.map;
}

// ── Legend ─────────────────────────────────────────────────────────────────────

function addLegend() {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = () => {
    const div = L.DomUtil.create('div');
    div.style.cssText =
      'background:rgba(5,15,35,0.92);border:1px solid #1e3a5f;border-radius:8px;' +
      'padding:12px 16px;font-size:11px;color:#7eb8e8;line-height:1.8;backdrop-filter:blur(10px);' +
      'box-shadow:0 4px 20px rgba(0,0,0,0.6);';
    
    div.innerHTML = `
      <div style="font-size:13px;font-weight:600;color:#22d3ee;margin-bottom:8px;">
        Ice Detection Legend
      </div>
      <div style="display:flex;align-items:center;margin-bottom:6px;">
        <span style="display:inline-block;width:16px;height:16px;background:linear-gradient(90deg,#50D0E8,#C850D0);
                     border-radius:3px;margin-right:8px;"></span>
        <span>Ice candidates (CPR>1.0, DOP<0.13)</span>
      </div>
      <div style="margin-top:10px;padding-top:10px;border-top:1px solid #1e3a5f;">
        <div style="font-size:10px;color:#888;">
          <strong style="color:#22d3ee;">54,558 pixels</strong> · 
          <strong style="color:#22d3ee;">34.1 km²</strong> · 
          25m resolution
        </div>
        <div style="font-size:9px;color:#666;margin-top:4px;">
          Chandrayaan-2 DFSAR · South Pole (-90° to -84°S)
        </div>
      </div>`;
    return div;
  };
  legend.addTo(STATE.map);
}

function addScaleIndicator() {
  const scale = L.control({ position: 'bottomleft' });
  scale.onAdd = () => {
    const div = L.DomUtil.create('div');
    div.style.cssText =
      'background:rgba(5,15,35,0.92);border:1px solid #1e3a5f;border-radius:6px;' +
      'padding:8px 12px;font-size:11px;color:#22d3ee;font-weight:600;backdrop-filter:blur(10px);';
    div.innerHTML = `
      <div style="margin-bottom:4px;">Resolution: 25 m/pixel</div>
      <div style="font-size:9px;color:#7eb8e8;font-weight:normal;">Lunar South Pole Stereographic</div>`;
    return div;
  };
  scale.addTo(STATE.map);
}

// ── Statistics Display ─────────────────────────────────────────────────────────

function updateStatistics() {
  if (!STATE.metadata) return;
  
  const ice = STATE.metadata.ice_overlay;
  const pixels = ice.ice_pixels;
  const res = ice.resolution_m;
  
  // Calculate areas
  const ice_area_km2 = (pixels * res * res) / 1e6;
  const bounds_width = ice.bounds.east - ice.bounds.west;
  const bounds_height = ice.bounds.north - ice.bounds.south;
  const coverage_km2 = (bounds_width * bounds_height) / 1e6;
  const fraction = (ice_area_km2 / coverage_km2) * 100;
  
  // Update DOM
  const updates = {
    'stat-pixels': pixels.toLocaleString(),
    'stat-area': ice_area_km2.toFixed(1) + ' km²',
    'stat-coverage': coverage_km2.toFixed(0) + ' km²',
    'stat-resolution': res + 'm',
    'stat-fraction': fraction.toFixed(3) + '%',
  };
  
  Object.entries(updates).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  });
  
  console.log('[Stats] Ice pixels:', pixels, '| Area:', ice_area_km2.toFixed(1), 'km²');
}

// ── Map Controls ───────────────────────────────────────────────────────────────

function initControls() {
  // Zoom to full extent
  const btnFit = document.getElementById('btn-zoom-fit');
  if (btnFit && STATE.metadata) {
    btnFit.addEventListener('click', () => {
      const bounds = STATE.metadata.ice_overlay.bounds;
      const leafletBounds = [
        [bounds.south, bounds.west],
        [bounds.north, bounds.east]
      ];
      STATE.map.fitBounds(leafletBounds);
      toast('Zoomed to full coverage area', 1500);
    });
  }
  
  // Center on pole
  const btnPole = document.getElementById('btn-zoom-pole');
  if (btnPole) {
    btnPole.addEventListener('click', () => {
      STATE.map.setView([0, 0], 0);
      toast('Centered on South Pole (90°S)', 1500);
    });
  }
}

// ── Initialization ─────────────────────────────────────────────────────────────

async function init() {
  console.log('[App] Starting unified ice detection dashboard...');
  
  const map = await initMap();
  if (!map) {
    console.error('[App] Failed to initialize map');
    return;
  }
  
  updateStatistics();
  initControls();
  
  toast('✓ Lunar South Pole Ice Detection Loaded', 2500);
  console.log('[App] Dashboard ready');
}

window.addEventListener('DOMContentLoaded', init);
