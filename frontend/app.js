const apiUrl = 'http://127.0.0.1:8000/api/path';

let stations = [];
const stationMap = new Map();

async function loadStations() {
  try {
    const res = await fetch('data/stations.json');
    if (!res.ok) throw new Error(`Failed to load stations.json: ${res.status}`);
    stations = await res.json();
    stationMap.clear();
    stations.forEach(s => stationMap.set(s.name.trim(), s.coords));
  } catch (err) {
    console.error(err);
    updateStatus('Failed to load station data.', true);
  }
}

const map = L.map('map').setView([48.2082, 16.3738], 14);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const stationLayer = L.layerGroup().addTo(map);
let routeLayer;
let stationMarkers = [];
let selectionMode = null;
let clickMarker = null;
let startPin = null;
let endPin = null;
const MAP_PICK_THRESHOLD = 250;

function haversineMeters(a, b) {
  const [lat1, lon1] = a;
  const [lat2, lon2] = b;
  const toRad = deg => deg * Math.PI / 180;
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);
  const x = Math.sin(dLat/2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLon/2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

function setSelectionMode(mode) {
  selectionMode = selectionMode === mode ? null : mode;
  document.getElementById('pickStartBtn').classList.toggle('active', selectionMode === 'start');
  document.getElementById('pickEndBtn').classList.toggle('active', selectionMode === 'end');
  if (selectionMode) {
    updateStatus(`Click on a station on the map to set ${selectionMode}.`);
  } else {
    updateStatus('Selection canceled.');
    if (clickMarker) {
      map.removeLayer(clickMarker);
      clickMarker = null;
    }
  }
}

function findNearestStation(latlng) {
  let nearest = null;
  let minDist = Infinity;
  stations.forEach(station => {
    const dist = haversineMeters(latlng, station.coords);
    if (dist < minDist) {
      minDist = dist;
      nearest = station;
    }
  });
  return minDist <= MAP_PICK_THRESHOLD ? nearest : null;
}

function updateSelection(stationName) {
  if (!selectionMode) return;
  const selectId = selectionMode === 'start' ? 'startStation' : 'endStation';
  const select = document.getElementById(selectId);
  select.value = stationName.trim();
  updateStatus(`${selectionMode.charAt(0).toUpperCase() + selectionMode.slice(1)} station set to ${stationName}.`);

  const markerCoords = stationMap.get(stationName.trim());
  if (selectionMode === 'start') {
    if (startPin) map.removeLayer(startPin);
    console.log('Setting START to', stationName.trim(), markerCoords);
    startPin = L.circleMarker(markerCoords, { radius: 8, color: '#2e86de', fillColor: '#2e86de', fillOpacity: 0.8 }).addTo(map);
    startPin.bindTooltip(`Start: ${stationName}`, { permanent: true, direction: 'right' });
    startPin.bringToFront();
  } else {
    if (endPin) map.removeLayer(endPin);
    console.log('Setting END to', stationName.trim(), markerCoords);
    endPin = L.circleMarker(markerCoords, { radius: 8, color: '#e74c3c', fillColor: '#e74c3c', fillOpacity: 0.8 }).addTo(map);
    endPin.bindTooltip(`End: ${stationName}`, { permanent: true, direction: 'right' });
    endPin.bringToFront();
  }

  if (clickMarker) {
    map.removeLayer(clickMarker);
    clickMarker = null;
  }

  selectionMode = null;
  document.getElementById('pickStartBtn').classList.remove('active');
  document.getElementById('pickEndBtn').classList.remove('active');
}

function populateStationSelectors() {
  const startSelect = document.getElementById('startStation');
  const endSelect = document.getElementById('endStation');

  const placeholderOption = document.createElement('option');
  placeholderOption.value = '';
  placeholderOption.textContent = '-- Select station --';
  placeholderOption.disabled = true;
  placeholderOption.selected = true;
  startSelect.appendChild(placeholderOption);

  const placeholderOption2 = placeholderOption.cloneNode(true);
  endSelect.appendChild(placeholderOption2);

  stations.forEach(station => {
    const startOption = document.createElement('option');
    startOption.value = station.name.trim();
    startOption.textContent = station.name;
    startSelect.appendChild(startOption);

    const endOption = document.createElement('option');
    endOption.value = station.name.trim();
    endOption.textContent = station.name;
    endSelect.appendChild(endOption);
  });
}

function drawStations() {
  stationLayer.clearLayers();
  stationMarkers = [];
  stations.forEach(station => {
    const marker = L.marker(station.coords)
      .bindPopup(station.name)
      .on('click', () => updateSelection(station.name))
      .addTo(stationLayer);
    stationMarkers.push(marker);
  });
}

function updateStatus(message, isError = false) {
  const status = document.getElementById('statusMessage');
  status.textContent = message;
  status.style.color = isError ? '#c0392b' : '#444';
}

async function requestRoute() {
  const startStation = document.getElementById('startStation').value;
  const endStation = document.getElementById('endStation').value;

  if (!startStation || !endStation) {
    updateStatus('Please select both start and end stations.', true);
    return;
  }

  if (startStation === endStation) {
    updateStatus('Start and end stations are the same. Showing station on the map.');
    renderRoute([startStation]);
    return;
  }

  updateStatus('Requesting route from the mock API...');

  try {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_station: startStation, end_station: endStation })
    });

    if (!response.ok) {
      throw new Error(`API returned status ${response.status}`);
    }

    const data = await response.json();
    if (data.status !== 'success' || !Array.isArray(data.route)) {
      throw new Error('Invalid API response format');
    }

    renderRoute(data.route);
    displayRouteDetails(data.route, data.segments, data.total_stops, data.estimated_time_seconds);
    updateStatus(`Route found: ${data.route.join(' → ')} (${data.total_stops} stops, ${data.estimated_time_seconds} sec)`);
  } catch (error) {
    updateStatus(`Request failed: ${error.message}`, true);
  }
}

function renderRoute(routeNames) {
  if (routeLayer) {
    map.removeLayer(routeLayer);
  }

  const unknownStations = [];
  const routeCoords = routeNames.map(name => {
    const coords = stationMap.get(name.trim());
    if (!coords) {
      unknownStations.push(name);
    }
    return coords ?? null;
  }).filter(Boolean);

  if (unknownStations.length > 0) {
    updateStatus(`Route includes unknown stations: ${unknownStations.join(', ')}`, true);
    return;
  }

  if (routeCoords.length === 0) {
    updateStatus('No matching route coordinates found.', true);
    return;
  }

  routeLayer = L.polyline(routeCoords, { color: '#d35400', weight: 6 }).addTo(map);

  if (routeCoords.length === 1) {
    map.setView(routeCoords[0], 16);
  } else {
    map.fitBounds(routeLayer.getBounds().pad(0.3));
  }
}

function displayRouteDetails(routeNames, segments = [], totalStops = 0, totalTime = 0) {
  const details = document.getElementById('routeDetails');
  if (!segments || segments.length === 0) {
    details.innerHTML = `<p><strong>Route:</strong> ${routeNames.join(' → ')}</p>`;
    return;
  }

  const segmentItems = segments.map(seg => `
    <li><strong>${seg.mode.toUpperCase()}</strong>: ${seg.from} → ${seg.to} (${seg.duration_seconds} sec)</li>
  `).join('');

  details.innerHTML = `
    <p><strong>Route:</strong> ${routeNames.join(' → ')}</p>
    <p><strong>Total stops:</strong> ${totalStops}, <strong>Total time:</strong> ${totalTime} sec</p>
    <ul>${segmentItems}</ul>
  `;
}

document.getElementById('findRouteBtn').addEventListener('click', requestRoute);
document.getElementById('pickStartBtn').addEventListener('click', () => setSelectionMode('start'));
document.getElementById('pickEndBtn').addEventListener('click', () => setSelectionMode('end'));

map.on('click', event => {
  if (!selectionMode) return;
  if (clickMarker) {
    map.removeLayer(clickMarker);
  }
  clickMarker = L.circleMarker([event.latlng.lat, event.latlng.lng], {
    radius: 6,
    color: '#2c3e50',
    fillColor: '#ecf0f1',
    fillOpacity: 0.9,
    weight: 2
  }).addTo(map);
  const nearest = findNearestStation([event.latlng.lat, event.latlng.lng]);
  if (nearest) {
    updateSelection(nearest.name);
  } else {
    updateStatus('No station near that click. Try closer to a marker.', true);
  }
});

// Initialize after loading station data
async function init() {
  await loadStations();
  populateStationSelectors();
  drawStations();
}

init();
