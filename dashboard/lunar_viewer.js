/**
 * Lunar Ice Viewer - Custom WebGL-based map viewer
 * Designed for ISRO Chandrayaan-2 DFSAR ice detection data
 * South Pole Stereographic projection
 */

'use strict';

class LunarViewer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    
    // View state
    this.centerX = 0;  // km
    this.centerY = 0;  // km
    this.scale = 1.0;  // pixels per km
    this.minScale = 0.5;
    this.maxScale = 50;
    
    // Layers
    this.layers = {
      basemap: null,
      ice: null
    };
    
    // Images
    this.images = {};
    this.imagesLoaded = 0;
    this.totalImages = 0;
    
    // Mouse interaction
    this.isDragging = false;
    this.lastMouseX = 0;
    this.lastMouseY = 0;
    
    this.setupCanvas();
    this.setupEvents();
  }
  
  setupCanvas() {
    // Make canvas fill container
    const resize = () => {
      const rect = this.canvas.parentElement.getBoundingClientRect();
      this.canvas.width = rect.width;
      this.canvas.height = rect.height;
      this.render();
    };
    
    window.addEventListener('resize', resize);
    resize();
  }
  
  setupEvents() {
    // Mouse wheel zoom
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      
      const rect = this.canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      
      // Get world coordinates before zoom
      const worldX = this.screenToWorldX(mouseX);
      const worldY = this.screenToWorldY(mouseY);
      
      // Zoom
      const zoomFactor = e.deltaY < 0 ? 1.2 : 0.8;
      this.scale *= zoomFactor;
      this.scale = Math.max(this.minScale, Math.min(this.maxScale, this.scale));
      
      // Adjust center to keep mouse position fixed
      const newWorldX = this.screenToWorldX(mouseX);
      const newWorldY = this.screenToWorldY(mouseY);
      this.centerX += (worldX - newWorldX);
      this.centerY += (worldY - newWorldY);
      
      this.render();
      this.updateInfo();
    });
    
    // Mouse drag pan
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
      this.canvas.style.cursor = 'grabbing';
    });
    
    this.canvas.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        const dx = e.clientX - this.lastMouseX;
        const dy = e.clientY - this.lastMouseY;
        
        this.centerX -= dx / this.scale;
        this.centerY -= dy / this.scale;
        
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
        
        this.render();
      }
      
      // Update coordinates
      const rect = this.canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const worldX = this.screenToWorldX(mouseX);
      const worldY = this.screenToWorldY(mouseY);
      
      document.getElementById('map-coords').textContent = 
        `📍 E: ${worldX.toFixed(1)} km, N: ${worldY.toFixed(1)} km`;
    });
    
    this.canvas.addEventListener('mouseup', () => {
      this.isDragging = false;
      this.canvas.style.cursor = 'grab';
    });
    
    this.canvas.addEventListener('mouseleave', () => {
      this.isDragging = false;
      this.canvas.style.cursor = 'grab';
    });
    
    this.canvas.style.cursor = 'grab';
  }
  
  screenToWorldX(screenX) {
    return this.centerX + (screenX - this.canvas.width / 2) / this.scale;
  }
  
  screenToWorldY(screenY) {
    return this.centerY + (screenY - this.canvas.height / 2) / this.scale;
  }
  
  worldToScreenX(worldX) {
    return (worldX - this.centerX) * this.scale + this.canvas.width / 2;
  }
  
  worldToScreenY(worldY) {
    return (worldY - this.centerY) * this.scale + this.canvas.height / 2;
  }
  
  loadLayer(name, imagePath, bounds) {
    console.log(`[Viewer] Loading ${name}...`);
    
    this.totalImages++;
    
    const img = new Image();
    img.onload = () => {
      console.log(`[Viewer] ✓ ${name} loaded`);
      this.images[name] = img;
      this.layers[name] = bounds;
      this.imagesLoaded++;
      
      if (this.imagesLoaded === this.totalImages) {
        console.log('[Viewer] All images loaded');
        this.render();
      }
    };
    
    img.onerror = () => {
      console.error(`[Viewer] ✗ Failed to load ${name}`);
    };
    
    img.src = imagePath;
  }
  
  render() {
    // Clear canvas
    this.ctx.fillStyle = '#000';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    
    // Draw basemap
    if (this.images.basemap && this.layers.basemap) {
      this.drawLayer('basemap', 1.0);
    }
    
    // Draw ice overlay
    if (this.images.ice && this.layers.ice) {
      this.drawLayer('ice', 1.0);
    }
    
    // Draw scale bar
    this.drawScaleBar();
  }
  
  drawLayer(name, opacity) {
    const img = this.images[name];
    const bounds = this.layers[name];
    
    if (!img || !bounds) return;
    
    // bounds: [south, west, north, east] in km
    const [south, west, north, east] = bounds;
    
    // Convert world bounds to screen coordinates
    const screenLeft = this.worldToScreenX(west);
    const screenTop = this.worldToScreenY(north);
    const screenRight = this.worldToScreenX(east);
    const screenBottom = this.worldToScreenY(south);
    
    const screenWidth = screenRight - screenLeft;
    const screenHeight = screenBottom - screenTop;
    
    // Only draw if visible
    if (screenRight < 0 || screenLeft > this.canvas.width ||
        screenBottom < 0 || screenTop > this.canvas.height) {
      return;
    }
    
    this.ctx.save();
    this.ctx.globalAlpha = opacity;
    this.ctx.imageSmoothingEnabled = true;
    this.ctx.imageSmoothingQuality = 'high';
    
    this.ctx.drawImage(img, screenLeft, screenTop, screenWidth, screenHeight);
    
    this.ctx.restore();
  }
  
  drawScaleBar() {
    const barWidth = 100; // pixels
    const barKm = barWidth / this.scale;
    
    // Round to nice number
    let displayKm = barKm;
    let unit = 'km';
    
    if (barKm < 1) {
      displayKm = barKm * 1000;
      unit = 'm';
    }
    
    // Round to 1 significant figure
    const magnitude = Math.pow(10, Math.floor(Math.log10(displayKm)));
    displayKm = Math.round(displayKm / magnitude) * magnitude;
    
    const actualBarWidth = (unit === 'km' ? displayKm : displayKm / 1000) * this.scale;
    
    this.ctx.save();
    this.ctx.strokeStyle = '#fff';
    this.ctx.fillStyle = '#fff';
    this.ctx.lineWidth = 2;
    this.ctx.font = '12px monospace';
    
    const x = 20;
    const y = this.canvas.height - 40;
    
    // Draw bar
    this.ctx.beginPath();
    this.ctx.moveTo(x, y);
    this.ctx.lineTo(x + actualBarWidth, y);
    this.ctx.moveTo(x, y - 5);
    this.ctx.lineTo(x, y + 5);
    this.ctx.moveTo(x + actualBarWidth, y - 5);
    this.ctx.lineTo(x + actualBarWidth, y + 5);
    this.ctx.stroke();
    
    // Draw label
    this.ctx.fillText(`${displayKm} ${unit}`, x + actualBarWidth / 2 - 20, y - 10);
    
    this.ctx.restore();
  }
  
  zoomTo(minLat, minLon, maxLat, maxLon) {
    // Calculate center
    this.centerX = (minLon + maxLon) / 2;
    this.centerY = (minLat + maxLat) / 2;
    
    // Calculate scale to fit bounds
    const width = maxLon - minLon;
    const height = maxLat - minLat;
    
    const scaleX = this.canvas.width / width * 0.9;
    const scaleY = this.canvas.height / height * 0.9;
    
    this.scale = Math.min(scaleX, scaleY);
    this.scale = Math.max(this.minScale, Math.min(this.maxScale, this.scale));
    
    this.render();
    this.updateInfo();
  }
  
  updateInfo() {
    const zoomLevel = Math.log2(this.scale / this.minScale).toFixed(1);
    const viewWidth = this.canvas.width / this.scale;
    
    const infoEl = document.getElementById('view-info');
    if (infoEl) {
      infoEl.textContent = `View: ${viewWidth.toFixed(0)} km | Zoom: ${zoomLevel}`;
    }
  }
}

// Global viewer instance
let viewer = null;

function initViewer() {
  console.log('[Init] Creating lunar viewer...');
  
  viewer = new LunarViewer('lunar-canvas');
  
  // Load basemap (±200km region)
  viewer.loadLayer('basemap', './data/overlays/south_pole_basemap_proper.png', 
    [-200, -200, 200, 200]);  // [south, west, north, east] in km
  
  // Load ice detection overlay
  viewer.loadLayer('ice', './data/overlays/ice_detection_south_pole_bright.png',
    [-156.815, -159.351, 149.110, 160.499]);  // [south, west, north, east] in km
  
  // Set initial view to full region
  viewer.zoomTo(-200, -200, 200, 200);
  
  console.log('[Init] ✓ Viewer initialized');
  
  return viewer;
}

// Export for use in dashboard
window.LunarViewer = LunarViewer;
window.initViewer = initViewer;
