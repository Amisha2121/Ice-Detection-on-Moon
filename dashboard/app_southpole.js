/**
 * app_southpole.js — South Pole Ice Detection Dashboard
 * 
 * Proper implementation using Leaflet with custom CRS for lunar coordinates
 */

'use strict';

// ── Configuration ─────────────────────────────────────────────────────────────

const CFG = {
  overlayDir: './data/overlays/',
};

const STATE = {
  map: null,
  layers: {},
};

// ── Custom CRS for South Pole Stereographic ──────────────────────────────────

// Use kilometers instead of meters for better Leaflet handling
const LunarSouthPoleCRS = L.extend({}, L.CRS.Simple, {
  transformation: new L.Transformation(1, 0, -1, 0)
});

// ── Map Initialization ────────────────────────────────────────────────────────

function initMap() {
  console.log('[Init] Creating south pole map...');
  
  // Create map with custom CRS
  STATE.map = L.map('map', {
    crs: LunarSouthPoleCRS,
    center: [0, 0],  // Center of south pole region
    zoom: 1,
    minZoom: 0,
    maxZoom: 4,
    zoomControl: true,
    attributionControl: false,
  });
  
  console.log('[Init] ✓ Map created');
  
  // Define bounds in KILOMETERS (converted from meters for better display)
  // Basemap covers ±200km
  const basemapBounds = [[-200, -200], [200, 200]];
  
  // Ice detection covers smaller region (in km)
  const iceBounds = [[-156.815, -159.351], [149.110, 160.499]];
  
  console.log('[Init] Basemap bounds:', basemapBounds);
  console.log('[Init] Ice bounds:', iceBounds);
  
  // Add LOLA hillshade basemap
  const basemap = L.imageOverlay(
    CFG.overlayDir + 'south_pole_basemap_proper.png',
    basemapBounds,
    {
      opacity: 1.0,
      interactive: false,
      zIndex: 1,
    }
  ).addTo(STATE.map);
  
  basemap.on('load', () => {
    console.log('[Init] ✓ Basemap loaded');
  });
  
  basemap.on('error', () => {
    console.error('[Init] ✗ Basemap failed to load');
  });
  
  // Add ice detection overlay
  const iceOverlay = L.imageOverlay(
    CFG.overlayDir + 'ice_detection_south_pole.png',
    iceBounds,
    {
      opacity: 0.85,
      interactive: false,
      zIndex: 2,
    }
  ).addTo(STATE.map);
  
  iceOverlay.on('load', () => {
    console.log('[Init] ✓ Ice overlay loaded (54,558 pixels)');
  });
  
  iceOverlay.on('error', () => {
    console.error('[Init] ✗ Ice overlay failed to load');
  });
  
  STATE.layers.basemap = basemap;
  STATE.layers.ice = iceOverlay;
  
  // Set view to show entire region
  STATE.map.fitBounds(basemapBounds);
  STATE.map.setMaxBounds([[-250, -250], [250, 250]]);
  
  // Add coordinate display
  STATE.map.on('mousemove', e => {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    document.getElementById('map-coords').textContent = 
      `📍 E: ${lng.toFixed(1)} km, N: ${lat.toFixed(1)} km`;
  });
  
  // Add scale indicator
  addScaleBar();
  
  console.log('[Init] ✓ Map initialization complete');
}

// ── Scale Bar ─────────────────────────────────────────────────────────────────

function addScaleBar() {
  const control = L.control({position: 'bottomleft'});
  
  control.onAdd = function(map) {
    const div = L.DomUtil.create('div', 'scale-indicator');
    div.style.cssText = `
      background: rgba(5,15,35,0.9);
      border: 1px solid #1e3a5f;
      border-radius: 4px;
      padding: 4px 8px;
      font-size: 11px;
      color: #7eb8e8;
    `;
    
    function update() {
      const zoom = map.getZoom();
      const bounds = map.getBounds();
      const widthKm = bounds.getEast() - bounds.getWest();
      div.textContent = `View width: ${widthKm.toFixed(0)} km | Zoom: ${zoom}`;
    }
    
    map.on('zoomend moveend', update);
    update();
    
    return div;
  };
  
  control.addTo(STATE.map);
}

// ── Layer Controls ────────────────────────────────────────────────────────────

function initLayerControls() {
  // Ice layer toggle
  const iceCheckbox = document.getElementById('layer-ice');
  if (iceCheckbox && STATE.layers.ice) {
    iceCheckbox.checked = true;
    iceCheckbox.addEventListener('change', () => {
      if (iceCheckbox.checked) {
        STATE.layers.ice.addTo(STATE.map);
        console.log('[Toggle] Ice layer ON');
      } else {
        STATE.map.removeLayer(STATE.layers.ice);
        console.log('[Toggle] Ice layer OFF');
      }
    });
  }
}

// ── Info Panel ────────────────────────────────────────────────────────────────

function updateInfoPanel() {
  document.getElementById('ice-count').textContent = '54,558';
  document.getElementById('ice-area').textContent = '34.1 km²';
  document.getElementById('coverage').textContent = '±200 km from pole';
  document.getElementById('resolution-basemap').textContent = '~98 m/px';
  document.getElementById('resolution-ice').textContent = '25 m/px';
}

// ── Zoom Controls ─────────────────────────────────────────────────────────────

function initZoomControls() {
  // Zoom to full extent
  document.getElementById('btn-zoom-full').addEventListener('click', () => {
    const bounds = [[-200, -200], [200, 200]];
    STATE.map.fitBounds(bounds);
    console.log('[Zoom] Reset to full extent');
  });
  
  // Zoom to ice region
  document.getElementById('btn-zoom-ice').addEventListener('click', () => {
    const bounds = [[-156.815, -159.351], [149.110, 160.499]];
    STATE.map.fitBounds(bounds);
    console.log('[Zoom] Zoomed to ice detection region');
  });
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function init() {
  console.log('[Init] Starting dashboard...');
  
  try {
    initMap();
    initLayerControls();
    initZoomControls();
    updateInfoPanel();
    
    console.log('[Init] ✓ Dashboard ready');
    document.getElementById('status').textContent = 'Ready';
    document.getElementById('status').style.color = '#4ade80';
  } catch (e) {
    console.error('[Init] ✗ Failed to initialize:', e);
    document.getElementById('status').textContent = 'Error: ' + e.message;
    document.getElementById('status').style.color = '#ef4444';
  }
}

window.addEventListener('DOMContentLoaded', init);
