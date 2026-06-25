/**
 * app.js — LunarIce Dashboard
 *
 * Coordinate system: L.CRS.Simple with pixel space.
 * The DEM hillshade (2048×2048 px) covers the LOLA 5m tile:
 *   W=-9000m  S=-15000m  E=7000m  N=1000m  (South Pole Stereographic)
 *
 * GeoJSON points (lon/lat) → projected to SP-stereo (mx, my) → pixel [row, col].
 */

'use strict';

// ── Configuration ─────────────────────────────────────────────────────────────

const CFG = {
  dataDir:    './data/',
  overlayDir: './data/overlays/',
  regionPx:   2048,
  regionBounds: { west: -150000, east: 150000, south: -150000, north: 150000 },
  traverseSpeedMs: 80,
};

const FILES = {
  overlayMeta:   'overlays/meta.json',
  landingSites:  'landing_sites.geojson',
  dscLocations:  'dsc_locations.geojson',
  iceCandidates: 'ice_candidates.geojson',
  traversePath:  'traverse_path.geojson',
  traverseWpts:  'traverse_waypoints.json',
  volumeReport:  'ice_volume_report.json',
  terrainStats:  'terrain_stats.json',
  cprHistogram:  'cpr_histogram.json',
};

// ── State ─────────────────────────────────────────────────────────────────────

const STATE = {
  map:    null,
  meta:   null,
  layers: {},
  traverseWaypoints: [],
  traverseIndex: 0,
  traverseTimer: null,
  roverMarker:   null,
  volumeData:    null,
  cprData:       null,
  elevData:      null,
};

// ── Coordinate conversion ─────────────────────────────────────────────────────

/**
 * Lunar South Pole Stereographic projection (spherical Moon).
 * Returns [mx, my] in metres.
 */
function lonLatToStereo(lon, lat) {
  const R   = 1737400;
  const phi = lat * Math.PI / 180;
  const lam = lon * Math.PI / 180;
  // Use 1 - Math.sin(phi) for South Pole Stereographic projection
  const t   = Math.cos(phi) / (1 - Math.sin(phi));
  const rho = 2 * R * t;
  return [rho * Math.sin(lam), rho * Math.cos(lam)];
}

/**
 * Projected metres → Leaflet pixel [row, col].
 * In L.CRS.Simple, we can directly map [y, x] to [lat, lng].
 */
function mToPixel(mx, my) {
  return [my, mx];
}

/**
 * GeoJSON [lon, lat] → Leaflet pixel [row, col].
 */
function geomToPixel(coords) {
  const [mx, my] = lonLatToStereo(coords[0], coords[1]);
  return mToPixel(mx, my);
}

// ── Utilities ─────────────────────────────────────────────────────────────────

async function fetchJSON(filename) {
  // Add a cache-buster query param so the browser always fetches the latest JSON
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

function setStatus(state) {
  const dot = document.getElementById('status-indicator');
  dot.className = `status-dot ${state}`;
  dot.title = state === 'ready' ? 'Data loaded'
            : state === 'error' ? 'Error loading data' : 'Loading…';
}

function formatNum(n, digits = 4) {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toFixed(digits);
}

// ── Map Initialisation ────────────────────────────────────────────────────────

async function initMap() {
  STATE.meta = await fetchJSON(FILES.overlayMeta);
  const sz = CFG.regionPx;

  STATE.map = L.map('map', {
    crs:              L.CRS.Simple,
    minZoom:          -10,
    maxZoom:          5,
    zoomControl:      true,
    attributionControl: false,
  });

  // Define actual geographic/projected bounds for the Shackleton tile
  const m = STATE.meta.bounds;
  // Leaflet expects [lat, lng] which maps to [y, x] in L.CRS.Simple
  const shkImgBounds = [[m.south, m.west], [m.north, m.east]];

  // ── Basemap: High-res LOLA DEM hillshade for Shackleton ─────────────────
  L.imageOverlay(CFG.overlayDir + 'dem_hillshade.png', shkImgBounds, {
    opacity: 1.0, interactive: false, zIndex: 1,
  }).addTo(STATE.map);

  // ── Named toggleable overlays ────────────────────────────────────────────
  const overlayDefs = [
    { id: 'psr',    file: 'psr_overlay.png',      opacity: 0.45, zIndex: 10 },
    { id: 'cpr',    file: 'cpr_overlay.png',      opacity: 0.55, zIndex: 11 },
    { id: 'ice',    file: 'ice_prob_overlay.png', opacity: 0.60, zIndex: 12 },
    { id: 'hazard', file: 'hazard_overlay.png',   opacity: 0.40, zIndex: 13 },
  ];

  overlayDefs.forEach(def => {
    // Test if the overlay PNG actually exists before adding (avoids silent blank layers)
    const imgUrl = CFG.overlayDir + def.file;
    const testImg = new Image();
    testImg.onerror = () => {
      const cb = document.getElementById(`layer-${def.id}`);
      if (cb) {
        cb.disabled = true;
        cb.title = 'Overlay PNG not found — run generate_map_overlays.py';
        const label = cb.parentElement;
        if (label) label.style.opacity = '0.45';
      }
      console.info(`Overlay missing (expected for repo clone): ${def.file}`);
    };
    testImg.src = imgUrl;

    const layer = L.imageOverlay(imgUrl, shkImgBounds, {
      opacity:     def.opacity,
      interactive: false,
      zIndex:      def.zIndex,
    });
    STATE.layers[def.id] = layer;

    const cb = document.getElementById(`layer-${def.id}`);
    if (cb) {
      if (cb.checked) layer.addTo(STATE.map);
      cb.addEventListener('change', () =>
        cb.checked ? layer.addTo(STATE.map) : STATE.map.removeLayer(layer));
    }
  });

  STATE.map.fitBounds(shkImgBounds);
  STATE.map.setMaxBounds(shkImgBounds);
  STATE.map.options.maxBoundsViscosity = 1.0;

  // Coordinate readout (pixel → approx metres)
  STATE.map.on('mousemove', e => {
    const mx = e.latlng.lng;
    const my = e.latlng.lat;
    document.getElementById('map-coords').textContent =
      `📍 ${(mx / 1000).toFixed(2)} km E,  ${(my / 1000).toFixed(2)} km N  (SP-stereo)`;
  });
}

// ── Layer helpers ─────────────────────────────────────────────────────────────

function makeCircleMarker(latlng, color, radius, tooltip) {
  return L.circleMarker(latlng, {
    radius,
    fillColor:   color,
    fillOpacity: 0.85,
    color:       '#ffffff',
    weight:      1.5,
  }).bindTooltip(tooltip, { sticky: true, className: 'dark-tooltip' });
}

// ── Ice Candidates ────────────────────────────────────────────────────────────

async function loadIceCandidates() {
  try {
    const gj = await fetchJSON(FILES.iceCandidates);
    const markers = [];
    STATE.cprData = [];

    gj.features.forEach(feat => {
      if (!feat.geometry) return;
      const p      = feat.properties;
      const latlng = geomToPixel(feat.geometry.coordinates);
      const r      = 4 + p.ice_probability * 8;
      const hue    = Math.round((1 - p.ice_probability) * 120);

      const mk = makeCircleMarker(latlng, `hsl(${hue},90%,55%)`, r,
        `🧊 Ice Prob: ${(p.ice_probability * 100).toFixed(1)}%<br>` +
        `CPR: ${p.cpr.toFixed(3)}  DOP: ${p.dop.toFixed(3)}`);
      mk.on('click', () => showPopup('Ice Candidate', p));
      markers.push(mk);
      STATE.cprData.push(p.cpr);
    });

    const layer = L.layerGroup(markers);
    STATE.layers.icePoints = layer;
    const cb = document.getElementById('layer-ice');
    if (cb) {
      if (cb.checked) layer.addTo(STATE.map);
      cb.addEventListener('change', () =>
        cb.checked ? layer.addTo(STATE.map) : STATE.map.removeLayer(layer));
    }
    renderCPRChart();
    if (markers.length)
      toast(`Loaded ${markers.length} ice candidates`, 2500);
    else
      toast('No ice candidates (DFSAR swath has no overlap with Shackleton tile)', 4000);
  } catch (e) {
    console.warn('Ice candidates:', e.message);
  }
}

// ── DSC Locations ─────────────────────────────────────────────────────────────

async function loadDSCLocations() {
  try {
    const gj = await fetchJSON(FILES.dscLocations);
    const icons = [];

    gj.features.forEach((feat, i) => {
      if (!feat.geometry) return;
      const p      = feat.properties;
      const latlng = geomToPixel(feat.geometry.coordinates);

      const divIcon = L.divIcon({
        className: '',
        html: `<div class="dsc-marker-icon" title="DSC ${i + 1}">D</div>`,
        iconSize: [24, 24], iconAnchor: [12, 12],
      });
      icons.push(
        L.marker(latlng, { icon: divIcon })
          .bindTooltip(
            `🌑 DSC ${i + 1}<br>Area: ${p.area_km2} km²<br>Min elev: ${p.min_elevation_m} m`,
            { sticky: true })
          .on('click', () => showPopup('Doubly Shadowed Crater', p))
      );
    });

    const layer = L.layerGroup(icons);
    STATE.layers.dsc = layer;
    const cb = document.getElementById('layer-dsc');
    if (cb) {
      if (cb.checked) layer.addTo(STATE.map);
      cb.addEventListener('change', () =>
        cb.checked ? layer.addTo(STATE.map) : STATE.map.removeLayer(layer));
    }
  } catch (e) {
    console.warn('DSC locations:', e.message);
  }
}

// ── Landing Sites ─────────────────────────────────────────────────────────────

async function loadLandingSites() {
  try {
    const gj = await fetchJSON(FILES.landingSites);
    const markers = [], cards = [];

    gj.features.forEach(feat => {
      const p      = feat.properties;
      const latlng = geomToPixel(feat.geometry.coordinates);

      const divIcon = L.divIcon({
        className: '',
        html: `<div class="landing-marker-icon">LS${p.rank}</div>`,
        iconSize: [34, 34], iconAnchor: [17, 17],
      });
      markers.push(
        L.marker(latlng, { icon: divIcon })
          .bindPopup(buildLandingPopup(p))
          .on('click', () => STATE.map.setView(latlng, 1))
      );

      const pct = (p.suitability_score * 100).toFixed(1);
      cards.push(`
        <div class="ls-card" onclick="flyToSite(${latlng[0]},${latlng[1]})">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="ls-rank rank-${p.rank}">★ Rank ${p.rank}</span>
            <span class="ls-score">${pct}%</span>
          </div>
          <div class="ls-details">
            ${p.lat.toFixed(4)}°, ${p.lon.toFixed(4)}°<br>
            Slope: ${p.slope_deg}° · Hazard: ${(p.hazard_score * 100).toFixed(0)}%<br>
            Ice dist: ${(p.distance_to_ice_m / 1000).toFixed(2)} km
          </div>
          <div class="ls-bar"><div class="ls-bar-fill" style="width:${pct}%"></div></div>
        </div>`);
    });

    const layer = L.layerGroup(markers);
    STATE.layers.landing = layer;
    const cb = document.getElementById('layer-landing');
    if (cb) {
      if (cb.checked) layer.addTo(STATE.map);
      cb.addEventListener('change', () =>
        cb.checked ? layer.addTo(STATE.map) : STATE.map.removeLayer(layer));
    }
    document.getElementById('landing-table').innerHTML = cards.join('') ||
      '<div style="font-size:0.72rem;color:var(--text-muted);padding:8px">No landing sites yet.</div>';
  } catch (e) {
    const isNetwork = e.message && (e.message.includes('404') || e.message.includes('fetch') || e.message.includes('JSON'));
    const msg = isNetwork
      ? 'Data not found — run <code>python src/run_pipeline.py</code> then <code>python src/export_for_dashboard.py</code>'
      : 'Run pipeline step 5.';
    console.warn('Landing sites fetch error:', e.message);
    document.getElementById('landing-table').innerHTML =
      `<div style="font-size:0.72rem;color:var(--text-muted);padding:8px">${msg}</div>`;
  }
}

window.flyToSite = (row, col) => STATE.map.setView([row, col], 1);

function buildLandingPopup(p) {
  return `
    <div style="min-width:180px">
      <b style="color:#4ade80">Landing Site LS-${p.rank}</b><br>
      <hr style="border-color:#1e3a5f;margin:5px 0">
      Score: <b>${(p.suitability_score * 100).toFixed(1)}%</b><br>
      Lat/Lon: ${p.lat.toFixed(4)}°, ${p.lon.toFixed(4)}°<br>
      Slope: ${p.slope_deg}°<br>
      Solar: ${(p.solar_fraction * 100).toFixed(0)}%<br>
      Ice dist: ${(p.distance_to_ice_m / 1000).toFixed(2)} km
    </div>`;
}

// ── Traverse Path ─────────────────────────────────────────────────────────────

async function loadTraversePath() {
  try {
    const gj   = await fetchJSON(FILES.traversePath);
    const wpts = await fetchJSON(FILES.traverseWpts);
    const lines = [], labels = [], elevData = { x: [], y: [], text: [] };

    // Corridor colour palette
    const SEG_COLORS = ['#f59e0b','#22d3ee','#a78bfa','#4ade80','#fb923c'];

    gj.features.forEach((feat, si) => {
      if (feat.geometry.type !== 'LineString') return;
      const coords  = feat.geometry.coordinates;
      const latlngs = coords.map(c => geomToPixel([c[0], c[1]]));
      const lenKm   = (feat.properties.length_m / 1000).toFixed(2);
      const color   = SEG_COLORS[si % SEG_COLORS.length];

      lines.push(L.polyline(latlngs, {
        color, weight: 3, opacity: 0.92, dashArray: '8 5',
      }).bindTooltip(`Corridor ${String.fromCharCode(65 + si)}: ${lenKm} km`,
                    { sticky: true, className: 'dark-tooltip' }));

      // Distance label at midpoint of each segment
      if (latlngs.length > 1) {
        const mid = latlngs[Math.floor(latlngs.length / 2)];
        labels.push(
          L.marker(mid, {
            icon: L.divIcon({
              className: '',
              html: `<div class="corridor-label" style="border-color:${color}">` +
                    `<span style="color:${color}">Corridor ${String.fromCharCode(65 + si)}</span>` +
                    `<br><span class="corridor-dist">${lenKm} km</span></div>`,
              iconSize:   [90, 36],
              iconAnchor: [45, 18],
            }),
            interactive: false,
          })
        );
      }

      coords.forEach((c, i) => {
        elevData.x.push(si + i / coords.length);
        elevData.y.push(c[2] || 0);
        elevData.text.push(`Seg ${si + 1}, pt ${i}`);
      });
    });

    const layer = L.layerGroup([...lines, ...labels]);
    STATE.layers.traverse = layer;
    const cb = document.getElementById('layer-traverse');
    if (cb) {
      if (cb.checked) layer.addTo(STATE.map);
      cb.addEventListener('change', () =>
        cb.checked ? layer.addTo(STATE.map) : STATE.map.removeLayer(layer));
    }

    STATE.traverseWaypoints = (wpts.waypoints || []).map(wp => ({
      ...wp, _latlng: geomToPixel([wp.lon, wp.lat]),
    }));
    STATE.elevData = elevData;
    renderElevChart();

    if (STATE.traverseWaypoints.length > 0) {
      const first = STATE.traverseWaypoints[0];
      STATE.roverMarker = L.marker(first._latlng, {
        icon: L.divIcon({
          className: '',
          html: '<div class="rover-icon">🛸</div>',
          iconSize: [28, 28], iconAnchor: [14, 14],
        }),
        zIndexOffset: 1000,
      });
    }

    if (wpts.total_distance_km)
      toast(`Traverse: ${wpts.total_distance_km} km, ${wpts.waypoints.length} waypoints`);
  } catch (e) {
    console.warn('Traverse path:', e.message);
  }
}

// ── Traverse Animation ─────────────────────────────────────────────────────────

function startTraverse() {
  if (!STATE.traverseWaypoints.length) { toast('No traverse waypoints loaded.'); return; }
  if (STATE.traverseTimer) return;
  if (STATE.roverMarker) STATE.map.addLayer(STATE.roverMarker);

  const delay = Math.round(CFG.traverseSpeedMs *
    (11 - parseInt(document.getElementById('speed-slider').value)));

  function step() {
    const wpts = STATE.traverseWaypoints;
    if (STATE.traverseIndex >= wpts.length) { stopTraverse(); toast('Traverse complete!'); return; }
    const wp = wpts[STATE.traverseIndex];
    STATE.roverMarker.setLatLng(wp._latlng);
    const pct = Math.round(STATE.traverseIndex / wpts.length * 100);
    document.getElementById('prog-pct').textContent    = `${pct}%`;
    document.getElementById('prog-bar').style.width    = `${pct}%`;
    document.getElementById('rover-stats').textContent =
      `WP ${STATE.traverseIndex + 1}/${wpts.length} · ${wp.cumulative_dist_km} km · ${wp.elevation_m} m`;
    STATE.traverseIndex++;
    STATE.traverseTimer = setTimeout(step, delay);
  }
  step();
  document.getElementById('btn-play').textContent = '⏸ Pause';
}

function stopTraverse() {
  clearTimeout(STATE.traverseTimer);
  STATE.traverseTimer = null;
  document.getElementById('btn-play').textContent = '▶ Play';
}

function resetTraverse() {
  stopTraverse();
  STATE.traverseIndex = 0;
  document.getElementById('prog-pct').textContent = '0%';
  document.getElementById('prog-bar').style.width = '0%';
  document.getElementById('rover-stats').textContent = '';
  if (STATE.roverMarker) STATE.map.removeLayer(STATE.roverMarker);
}

document.getElementById('btn-play').addEventListener('click', () =>
  STATE.traverseTimer ? stopTraverse() : startTraverse());
document.getElementById('btn-reset').addEventListener('click', resetTraverse);

// ── Ice Volume Report ──────────────────────────────────────────────────────────

async function loadVolumeReport() {
  try {
    const report = await fetchJSON(FILES.volumeReport);
    STATE.volumeData = report;
    const ve = report.volume_estimate, mc = ve.monte_carlo;
    const ic = report.ice_detection,  co = report.concentration;
    document.getElementById('vol-point').textContent =
      `${ve.point_estimate_km3.toExponential(3)} km³`;
    document.getElementById('vol-ci').textContent =
      `[${mc.p5_km3.toExponential(2)}, ${mc.p95_km3.toExponential(2)}]`;
    document.getElementById('vol-area').textContent  = `${ic.ice_area_km2.toFixed(4)} km²`;
    document.getElementById('vol-conc').textContent  = `${co.mean_ice_fraction_pct.toFixed(1)}%`;
    document.getElementById('vol-mass').textContent  = `${ve.mass_Gt.toExponential(3)} Gt`;
    renderVolumeGauge(mc);
  } catch (e) {
    console.warn('Volume report:', e.message);
  }
}

// ── Plotly Charts ─────────────────────────────────────────────────────────────

const PLOT_LAYOUT = {
  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
  font: { family: 'Inter', color: '#7eb8e8', size: 9 },
  margin: { l: 35, r: 8, t: 6, b: 28 },
  xaxis: { gridcolor: '#1e3a5f', linecolor: '#1e3a5f' },
  yaxis: { gridcolor: '#1e3a5f', linecolor: '#1e3a5f' },
};
const PLOT_CFG = { displayModeBar: false, responsive: true };

function renderVolumeGauge(mc) {
  if (!mc) return;
  Plotly.newPlot('volume-gauge', [{
    type: 'indicator', mode: 'gauge+number',
    value: mc.mean_km3 * 1e6,
    number: { suffix: ' ×10⁻⁶ km³', font: { size: 11, color: '#22d3ee' } },
    gauge: {
      axis: { range: [0, mc.p95_km3 * 1.5 * 1e6], tickfont: { size: 7, color: '#4a7aa8' } },
      bar: { color: '#22d3ee' }, bgcolor: '#0d1a2e', bordercolor: '#1e3a5f',
      steps: [
        { range: [0, mc.p5_km3  * 1e6], color: '#1e3a5f' },
        { range: [mc.p5_km3 * 1e6, mc.p95_km3 * 1e6], color: '#1e4d7a' },
      ],
    },
  }], { ...PLOT_LAYOUT, margin: { l: 10, r: 10, t: 10, b: 10 } }, PLOT_CFG);
}

async function renderCPRChart() {
  try {
    const hist = await fetchJSON(FILES.cprHistogram);
    if (!hist || !hist.x || !hist.y) return;
    
    Plotly.newPlot('cpr-chart', [
      {
        type: 'bar',
        x: hist.x,
        y: hist.y,
        marker: { color: '#378ADD' },
        name: 'CPR values'
      },
      {
        type: 'line',
        x: [1.0, 1.0],
        y: [0, Math.max(...hist.y)],
        mode: 'lines',
        line: { color: '#E24B4A', dash: 'dash' },
        name: 'CPR=1.0 threshold'
      }
    ], {
      ...PLOT_LAYOUT,
      title: 'CPR distribution within PSR',
      xaxis: { ...PLOT_LAYOUT.xaxis, title: { text: 'Circular Polarisation Ratio', font: { size: 10 } } },
      yaxis: { ...PLOT_LAYOUT.yaxis, title: { text: 'Pixel count', font: { size: 10 } } },
      showlegend: false,
      margin: { t: 30, b: 30, l: 40, r: 10 },
      annotations: [{
        x: 1.0,
        y: Math.max(...hist.y),
        text: 'CPR=1.0 threshold',
        showarrow: false,
        xanchor: 'left',
        yanchor: 'bottom',
        font: { color: '#E24B4A', size: 10 }
      }]
    }, PLOT_CFG);
  } catch(e) {
    console.error('Failed to render CPR chart:', e);
  }
}

function renderElevChart() {
  if (!STATE.elevData?.y.length) return;
  Plotly.newPlot('elev-chart', [{
    type: 'scatter', x: STATE.elevData.x, y: STATE.elevData.y,
    mode: 'lines', fill: 'tozeroy',
    line: { color: '#f59e0b', width: 1.5 },
    fillcolor: 'rgba(245,158,11,0.12)',
  }], {
    ...PLOT_LAYOUT,
    xaxis: { ...PLOT_LAYOUT.xaxis, title: { text: 'Traverse progress', font: { size: 9 } } },
    yaxis: { ...PLOT_LAYOUT.yaxis, title: { text: 'Elev (m)', font: { size: 9 } } },
    showlegend: false,
  }, PLOT_CFG);
}

// ── Info Popup ─────────────────────────────────────────────────────────────────

function showPopup(title, props) {
  document.getElementById('popup-title').textContent = title;
  const body = document.getElementById('popup-body');
  
  if (title === 'Doubly Shadowed Crater') {
    body.innerHTML = `
      <b>Doubly Shadowed Crater #${Math.round(props.region_id)}</b><br>
      Area: ${props.area_km2.toFixed(3)} km²<br>
      Depth: ${Math.round(props.mean_elevation_m - props.min_elevation_m)} m<br>
      Mean elevation: ${Math.round(props.mean_elevation_m)} m<br>
      Location: ${props.lat.toFixed(4)}°S, ${props.lon.toFixed(4)}°E
    `;
  } else {
    body.innerHTML = Object.entries(props)
      .filter(([k]) => !['type', 'rationale'].includes(k))
      .map(([k, v]) => `<b>${k}:</b> ${typeof v === 'number' ? formatNum(v, 4) : v}`)
      .join('<br>');
  }
  document.getElementById('info-popup').classList.remove('hidden');
}

// ── Threshold Controls ─────────────────────────────────────────────────────────

function initThresholdControls() {
  ['cpr', 'dop', 'prob'].forEach(id => {
    const slider = document.getElementById(`thresh-${id}`);
    const label  = document.getElementById(`${id}-val`);
    if (slider && label) slider.addEventListener('input', () =>
      label.textContent = parseFloat(slider.value).toFixed(2));
  });
  document.getElementById('btn-apply-thresh').addEventListener('click', () => {
    const cpr  = parseFloat(document.getElementById('thresh-cpr').value);
    const dop  = parseFloat(document.getElementById('thresh-dop').value);
    const prob = parseFloat(document.getElementById('thresh-prob').value);
    toast(`Thresholds: CPR>${cpr}, DOP<${dop}, prob>${prob}`);
  });
}

// ── Legend ─────────────────────────────────────────────────────────────────────

function addLegend() {
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = () => {
    const div = L.DomUtil.create('div');
    div.style.cssText =
      'background:rgba(5,15,35,0.88);border:1px solid #1e3a5f;border-radius:8px;' +
      'padding:8px 12px;font-size:11px;color:#7eb8e8;line-height:1.6;backdrop-filter:blur(6px);';
    div.innerHTML = `
      <b style="color:#22d3ee">Map Layers</b><br>
      <span style="display:inline-block;width:12px;height:12px;background:rgba(0,0,180,0.6);border-radius:2px;vertical-align:middle"></span> PSR (shadow)<br>
      <span style="display:inline-block;width:12px;height:12px;background:linear-gradient(90deg,#0f0,#f00);border-radius:2px;vertical-align:middle"></span> Ice Prob.<br>
      <span style="display:inline-block;width:12px;height:12px;background:#f59e0b;border-radius:2px;vertical-align:middle"></span> Traverse<br>
      <span style="display:inline-block;width:12px;height:12px;background:#4ade80;border-radius:2px;vertical-align:middle"></span> Landing Site<br>
      <span style="display:inline-block;width:12px;height:12px;background:#7e22ce;border-radius:2px;vertical-align:middle"></span> DSC crater`;
    return div;
  };
  legend.addTo(STATE.map);
}

// ── Main ───────────────────────────────────────────────────────────────────────

async function init() {
  try {
    await initMap();
  } catch (e) {
    setStatus('error');
    toast('⚠ Failed to load map: ' + e.message, 6000);
    return;
  }

  initThresholdControls();
  addLegend();

  const results = await Promise.allSettled([
    loadIceCandidates(),
    loadDSCLocations(),
    loadLandingSites(),
    loadTraversePath(),
    loadVolumeReport(),
  ]);

  const errors = results.filter(r => r.status === 'rejected');
  if (errors.length === 0) {
    setStatus('ready');
    toast('All data loaded! 🌙', 2500);
  } else if (errors.length === results.length) {
    setStatus('error');
    toast('⚠ No pipeline data found. Run python src/run_pipeline.py first.', 6000);
  } else {
    setStatus('ready');
    toast(`Loaded with ${errors.length} missing layer(s).`, 4000);
  }
}

window.addEventListener('DOMContentLoaded', init);
