# Vienna U-Bahn Navigator — Development Plan

> A web-based pathfinding application that finds the fastest walk + metro route between any two points on the Vienna Subway (U-Bahn) network, built on the architecture of the Paris Metro Navigator project.

---

## 1. Project Overview

### Goal
A localhost-first web app where a user picks two points on an interactive Leaflet map (by clicking on the map **or** selecting from a station dropdown) and gets back:
- The **optimal time-based route** via A\* search
- A **polyline drawn on the map** for the route
- A **step-by-step itinerary** (walk → enter → ride → transfer → exit → walk)

### Core differences from Paris Metro Navigator

| Aspect | Paris Metro Navigator | Vienna U-Bahn Navigator |
|---|---|---|
| City | Central Paris | Vienna |
| Data source | IDFM GTFS feed + OSM | Wiener Linien GTFS feed + OSM |
| Lines | 16 metro lines (M1–M14, 3b, 7b) | 5 U-Bahn lines (U1–U6 excl. U5) |
| Admin panel | Yes (scenario closures) | Optional (keep for future) |
| Station selector | Text search only | Click on map **or** dropdown list |
| Route display | Magenta polyline | Per-line colored polyline |

---

## 2. Architecture

The project is a **monorepo** with a Python/FastAPI backend and a vanilla JS + Leaflet frontend. No build step required.

```
vienna-ubahn-navigator/
├── backend/
│   ├── __init__.py
│   └── app/
│       ├── __init__.py
│       ├── main.py              # FastAPI app, lifespan, CORS, static mount
│       ├── config.py            # Pydantic settings, project root resolution
│       ├── database.py          # SQLite helper (get_db_connection, init_tables)
│       ├── api/
│       │   ├── __init__.py
│       │   ├── network.py       # GET /api/network  (stations + segments)
│       │   └── path.py          # POST /api/path    (A* route)
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── path.py          # Pydantic request/response models
│       ├── services/
│       │   ├── __init__.py
│       │   └── pathfinding.py   # PathfindingService with A* (ported + adapted)
│       └── dependencies/
│           ├── __init__.py
│           └── services.py      # Singleton injection helpers
├── frontend/
│   ├── index.html               # Main user page
│   ├── css/
│   │   └── style.css            # UI styling
│   └── js/
│       ├── config.js            # API_BASE, LINE_COLORS, constants
│       ├── map.js               # Leaflet init, network overlay, click-to-pick
│       ├── ui.js                # Dropdown logic, station search, form state
│       └── pathfinding.js       # POST /api/path, draw polyline, render steps
├── scripts/
│   ├── download_gtfs.py         # Download Wiener Linien GTFS → data/raw/
│   ├── download_walk_osm.py     # Overpass walking graph for Vienna → data/raw/
│   ├── build_graph.py           # GTFS + OSM → SQLite graph
│   └── init_db.py               # (optional) admin table seeding
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   └── test_pathfinding.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## 3. Data Pipeline

### 3.1 GTFS Source

**Wiener Linien** publishes a freely available GTFS feed:
- URL: `https://www.wienerlinien.at/ogd_realtime/doku/ogd/gtfs/gtfs.zip`
- License: Creative Commons Attribution 4.0 (CC BY 4.0)
- Contains: U-Bahn, tram, bus — we filter `route_type == "1"` for subway only
- Lines present: U1, U2, U3, U4, U6 (U5 is under construction and absent)

**`scripts/download_gtfs.py`** — same pattern as Paris version:
1. Download zip to `backend/data/raw/gtfs/`
2. Unzip `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`

### 3.2 Walking Graph (OSM via Overpass)

**`scripts/download_walk_osm.py`** — query Overpass for walkable ways inside Vienna's bounding box:
- Bounding box: `(48.10, 16.20, 48.32, 16.58)` — covers entire Vienna
- Query: `way[highway~"^(footway|path|pedestrian|residential|living_street|unclassified|tertiary|secondary|primary)$"][!access]`
- Output: `backend/data/raw/walk.osm.json`

### 3.3 Graph Build

**`scripts/build_graph.py`** — almost identical to Paris version, adapted for Vienna's GTFS:

**Tables created in `metro.db`:**

| Table | Columns |
|---|---|
| `platforms` | id, station_id, station_name, line_id, lat, lng |
| `walk_nodes` | id, lat, lng |
| `ride_edges` | from_platform, to_platform, travel_time_s, line_id |
| `transfer_edges` | from_platform, to_platform, transfer_time_s |
| `entrance_edges` | platform_id, walk_node_id, travel_time_s |
| `walk_edges` | from_node, to_node, travel_time_s |

**Key difference from Paris:** Vienna has ~109 stations on 5 lines; the build is significantly faster (seconds vs minutes).

**Build steps:**
1. Parse GTFS → filter metro routes → resolve station IDs → compute median ride times
2. Parse OSM JSON → extract walkable nodes and edges in bounding box
3. For each platform, find the nearest walk node (entrance edge, bidirectional)
4. For platforms sharing the same station_id (interchange stations), add transfer edges (180 s flat)
5. Write all to SQLite

---

## 4. Backend

### 4.1 Database (`backend/app/database.py`)

Identical to Paris version. `get_db_connection()` returns a context-manager-wrapped `sqlite3.Connection`. `init_tables()` creates all tables with `CREATE TABLE IF NOT EXISTS`.

### 4.2 Pathfinding Service (`backend/app/services/pathfinding.py`)

**Ported directly** from Paris version with these constants updated for Vienna:

```python
WALK_SPEED_MPS    = 1.4          # average pedestrian speed
RIDE_TIME_FACTOR  = 0.75         # compresses ride times slightly for admissibility
V_MAX_MPS         = 15.0 / RIDE_TIME_FACTOR
EARTH_RADIUS_M    = 6_371_000
ENTRANCE_K        = 3            # extra walk entrances per platform
ENTRANCE_R_MAX_M  = 150.0        # max radius for extra entrances
STATION_SNAP_R_M  = 100.0        # snap endpoint to platform if within this radius
```

**A\* algorithm** (time-optimal):
- `g(n)` = accumulated travel time in seconds
- `h(n)` = haversine distance to goal ÷ V\_MAX\_MPS (admissible — never overestimates)
- `f(n)` = g(n) + h(n)
- Uses `heapq` min-heap; tie-broken by insertion counter
- Walk, ride, transfer, and entrance edges all have second-based weights
- Virtual start/end nodes attached per query (overlay pattern — base graph never mutated)

**Result format:**
```python
@dataclass
class PathResult:
    total_time_s: float
    steps: list[PathStep]        # human-readable itinerary steps
    coords: list[tuple[float, float]]  # lat/lng polyline points
```

### 4.3 API Endpoints (`backend/app/api/`)

**`GET /api/network`** — returns all stations and ride segments for map rendering:
```json
{
  "stations": [
    {"id": "...", "name": "Stephansplatz", "lat": 48.208, "lng": 16.373, "lines": ["U1", "U3"]}
  ],
  "segments": [
    {"line_id": "U1", "from_station_id": "...", "to_station_id": "...",
     "from_lat": ..., "from_lng": ..., "to_lat": ..., "to_lng": ...}
  ]
}
```

**`POST /api/path`** — accepts start/end coordinates, returns route:
```json
// Request
{"lat_start": 48.200, "lng_start": 16.370, "lat_end": 48.220, "lng_end": 16.400}

// Response
{
  "total_time_s": 720,
  "steps": [
    {"kind": "walk",     "description": "Walk",                        "duration_s": 120, "distance_m": 168},
    {"kind": "enter",    "description": "Enter U-Bahn at Karlsplatz (U1)", "duration_s": 30,  "line_id": "U1"},
    {"kind": "ride",     "description": "Take U1 from Karlsplatz to Stephansplatz", "duration_s": 120, "line_id": "U1"},
    {"kind": "exit",     "description": "Exit U-Bahn at Stephansplatz", "duration_s": 30},
    {"kind": "walk",     "description": "Walk",                        "duration_s": 90,  "distance_m": 126}
  ],
  "coords": [[48.200, 16.370], ..., [48.220, 16.400]]
}
```

### 4.4 Main App (`backend/app/main.py`)

- FastAPI app with `lifespan` context: `init_tables()` + warm-up `get_pathfinder()`
- CORS: `allow_origins=["*"]` (localhost dev)
- Mounts `/frontend` as static files at `/`

---

## 5. Frontend

### 5.1 `js/config.js` — Constants

```javascript
const API_BASE = '';   // same-origin

// Vienna U-Bahn official line colors
const LINE_COLORS = {
  U1: '#e2001a',   // red
  U2: '#9b479f',   // purple
  U3: '#f07d00',   // orange
  U4: '#009a44',   // green
  U6: '#8b6f47',   // brown
};

const LINE_WEIGHTS = { default: 4, highlight: 7 };
const MAP_CENTER   = [48.2082, 16.3738];  // Vienna city center
const MAP_ZOOM     = 13;
const WALK_COLOR   = '#555555';
const ROUTE_COLOR  = '#e63946';  // magenta-red for mixed/walk-only route
```

### 5.2 `js/map.js` — Leaflet Map

**Initialization:**
```javascript
const map = L.map('map').setView(MAP_CENTER, MAP_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { ... }).addTo(map);
```

**Network overlay (on page load):**
- `GET /api/network`
- Draw each `segment` as a colored `L.polyline` using `LINE_COLORS[line_id]`
- Draw each `station` as a small `L.circleMarker`; on click → populate the dropdown/coord display
- Station markers store their `{name, lat, lng}` in `marker.options.stationData`

**Click-to-pick interaction:**
- Two modes: `pickingStart` and `pickingEnd` (toggled by UI buttons)
- `map.on('click', handler)` — when active, read `e.latlng`, update `state.start` or `state.end`, place a colored pin, switch cursor back to default
- Clicking a station marker in pick mode snaps the coordinate to the station's exact lat/lng and fills the dropdown label

**Route polyline:**
- After a successful `/api/path` call, the result `coords` are drawn as a `L.polyline`
- Segments are colored by `line_id` (walk segments in `WALK_COLOR`)
- Previous route polyline is removed before drawing a new one
- Map pans/zooms to fit the route bounds: `map.fitBounds(polyline.getBounds(), {padding: [40,40]})`

### 5.3 `js/ui.js` — Dropdown & Station Selector

**Dropdown list:**
- Populated from `/api/network` stations, sorted alphabetically
- Two `<select>` elements: `#select-start` and `#select-end`
- On change → update `state.start` or `state.end` and place map pin

**Dual input mode (click on map OR use dropdown):**
- Both inputs are always visible side-by-side
- Selecting from dropdown updates and centers the map pin
- Clicking map updates the dropdown to the nearest station name (or shows raw coords if off-network)
- A small coord label below each selector shows the active lat/lng

**Buttons:**
- `#btn-pick-start` — enters "pick start" mode, changes cursor to crosshair
- `#btn-pick-end` — enters "pick end" mode
- `#btn-find` — validates both points are set, calls pathfinding
- `#btn-reset` — clears all state, removes route, resets dropdowns

### 5.4 `js/pathfinding.js` — Route Display

```javascript
async function findRoute() {
  const { start, end } = state;
  if (!start || !end) return showError('Please select start and end points.');

  showLoading();
  const res = await fetch(`${API_BASE}/api/path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat_start: start.lat, lng_start: start.lng,
                           lat_end: end.lat, lng_end: end.lng })
  });
  if (!res.ok) return showError('No route found.');

  const data = await res.json();
  renderRoute(data);
}
```

**`renderRoute(data)`:**
1. Remove previous route layer group
2. Split `data.coords` by step type and draw colored polyline segments:
   - Walk segments → gray dashed line
   - Ride segments → solid line with `LINE_COLORS[step.line_id]`
3. Add animated start/end markers (pulsing CSS circle)
4. Render `data.steps` as a numbered list in `#result-steps`:
   - Walk step: 🚶 "Walk 350 m (4 min)"
   - Enter step: ⬇️ "Enter at Stephansplatz (U1)"
   - Ride step: 🚇 "U1 · Karlsplatz → Stephansplatz (2 min)"
   - Transfer step: 🔄 "Transfer to U3 (3 min)"
   - Exit step: ⬆️ "Exit at Westbahnhof"
5. Show total time prominently in `#result-banner`

### 5.5 `index.html` — Layout

```
+-------------------------------------------+
| [Vienna U-Bahn Navigator]          header  |
+-------------+-----------------------------+
|  SIDEBAR    |                             |
|             |        LEAFLET MAP          |
| Plan Route  |                             |
| [Start ▾]  |    (U-Bahn network drawn)   |
| [Pick on map]|                            |
| [End ▾]    |    (route polyline)         |
| [Pick on map]|                            |
| [Find Route]|                             |
| [Reset]     |                             |
|-------------|                             |
| Itinerary   |                             |
| 1. Walk…    |                             |
| 2. Enter U1 |                             |
| 3. Ride U1… |                             |
+-------------+-----------------------------+
```

---

## 6. Vienna U-Bahn Line Data Reference

| Line | Color | Stations | Key interchanges |
|------|-------|----------|-----------------|
| U1   | Red `#e2001a` | 24 | Karlsplatz, Stephansplatz, Schwedenplatz |
| U2   | Purple `#9b479f` | 20 | Karlsplatz, Schottentor, Stadion |
| U3   | Orange `#f07d00` | 21 | Stephansplatz, Westbahnhof, Erdberg |
| U4   | Green `#009a44` | 20 | Schwedenplatz, Karlsplatz, Hütteldorf |
| U6   | Brown `#8b6f47` | 24 | Längenfeldgasse, Westbahnhof, Floridsdorf |

**Key interchange stations (multiple lines):**

| Station | Lines |
|---------|-------|
| Karlsplatz | U1, U2, U4 |
| Stephansplatz | U1, U3 |
| Schwedenplatz | U1, U4 |
| Westbahnhof | U3, U6 |
| Längenfeldgasse | U4, U6 |
| Spittelau | U4, U6 |
| Floridsdorf | U6 terminus |

---

## 7. Step-by-Step Development Order

### Phase 0 — Repository Setup (30 min)
1. Create project folder `vienna-ubahn-navigator/`
2. Copy and adapt `requirements.txt` from Paris project (same deps: fastapi, uvicorn, pydantic, scipy, pandas, requests, python-jose, passlib)
3. Create `.env.example` (only `DATABASE_URL` needed; auth is optional)
4. Initialize `backend/app/config.py` with `PROJECT_ROOT` and `DATABASE_URL` pointing to `backend/data/metro.db`
5. Copy `backend/app/database.py` verbatim from Paris project

### Phase 1 — Data Pipeline (1–2 hours)
1. **`scripts/download_gtfs.py`** — download Wiener Linien GTFS zip, extract to `backend/data/raw/gtfs/`
2. **`scripts/download_walk_osm.py`** — Overpass query for Vienna walkable ways, save `walk.osm.json`; adjust bounding box to `(48.10, 16.20, 48.32, 16.58)`
3. **`scripts/build_graph.py`** — port from Paris; change:
   - `BBOX` constant to Vienna values
   - Filter `route_type == "1"` (same for metro)
   - Remove Paris-specific `route_short_name` normalization (Wiener Linien uses `U1`–`U6` directly)
   - Keep all edge-building logic identical
4. Run `python scripts/download_gtfs.py && python scripts/download_walk_osm.py && python scripts/build_graph.py` — verify DB created

### Phase 2 — Backend (1 hour)
1. **`backend/app/services/pathfinding.py`** — copy from Paris; update city-specific constants if needed (mostly identical)
2. **`backend/app/schemas/path.py`** — copy verbatim
3. **`backend/app/api/network.py`** — copy verbatim
4. **`backend/app/api/path.py`** — copy verbatim (no scenario dependency needed unless keeping admin)
5. **`backend/app/dependencies/services.py`** — simplify to just `get_pathfinder()` singleton
6. **`backend/app/main.py`** — copy and simplify (remove auth/scenario routers if not needed)
7. Test: `uvicorn backend.app.main:app --reload` → hit `GET /api/network` and `POST /api/path`

### Phase 3 — Frontend: Map & Network (1 hour)
1. **`frontend/index.html`** — design sidebar + map layout (see Section 5.5)
2. **`frontend/js/config.js`** — set Vienna map center, line colors, API_BASE
3. **`frontend/js/map.js`** — init Leaflet, fetch `/api/network`, draw polylines + station circles
4. Verify Vienna U-Bahn network renders correctly on the map

### Phase 4 — Frontend: Station Selector (1 hour)
1. **`frontend/js/ui.js`** — build dual-mode selector (dropdown + click-on-map)
2. Populate `<select>` dropdowns from `/api/network` stations sorted alphabetically
3. Wire `#btn-pick-start` / `#btn-pick-end` to set map click mode
4. Sync map clicks ↔ dropdown selection (snap to nearest station or use raw coords)

### Phase 5 — Frontend: Pathfinding & Route Display (1 hour)
1. **`frontend/js/pathfinding.js`** — `POST /api/path` on button click
2. Draw per-segment colored polyline on map
3. Render step-by-step itinerary list in sidebar
4. Show total time in header banner
5. `#btn-reset` — clear all state

### Phase 6 — Polish & Testing (1 hour)
1. **`frontend/css/style.css`** — Vienna-themed styling (red accent for U1, clean transit UI)
2. Test all interchange routes: Karlsplatz (U1/U2/U4), Stephansplatz (U1/U3), etc.
3. Test edge cases: same station start/end, click far from network, endpoint snapping
4. Write `tests/test_pathfinding.py` with 3–5 known routes and expected line usage
5. Write `tests/test_api.py` for `/api/network` and `/api/path` happy paths

---

## 8. Key Technical Decisions

### Why A\* with time as objective?
- Time is the most meaningful metric for transit (not distance)
- Admissible heuristic: `haversine / V_MAX` never overestimates travel time → optimal paths guaranteed
- Ride time (from GTFS median) + walk time + transfer time all measured in seconds → homogeneous cost function

### Why virtual endpoint overlay?
- The base graph (100k+ nodes) is loaded once at startup into RAM
- Each query adds 2 temporary nodes (start + end) with edges to nearest walk nodes / platforms
- After A\* finishes, the overlay is garbage-collected — no mutation of shared state
- This makes concurrent requests safe without locking

### Why per-platform nodes instead of per-station?
- A single station can serve multiple lines (e.g. Karlsplatz: U1, U2, U4)
- Each line gets its own platform node, connected by transfer edges
- A\* can decide whether a transfer is worth the 180 s cost vs. continuing on the current line
- This naturally models real-world behavior

### Polyline coloring strategy
- After A\*, the `coords` list is a flat sequence of lat/lng points
- The `steps` list tells us the `line_id` and `duration_s` for each segment
- We map `coords` windows to steps by counting nodes per step
- Walk segments use dashed gray; ride segments use solid line with official U-Bahn color

---

## 9. Data Quality Notes

- **Wiener Linien GTFS** is well-maintained and updated frequently
- `route_type = "1"` in GTFS = heavy rail/metro — correctly selects all U-Bahn lines
- U5 is under construction and **absent** from the feed — no special handling needed
- Some platforms may have slightly incorrect coordinates in GTFS — visual inspection recommended after build
- Transfer time of 180 s (3 min) is a reasonable flat estimate for Vienna's underground stations; can be tuned per-station if real data is available

---

## 10. Testing Scenarios

| Route | Expected lines used | Notes |
|-------|-------------------|-------|
| Stephansplatz → Karlsplatz | U1 or U3+transfer | Should prefer direct U1 |
| Westbahnhof → Schwedenplatz | U3 → transfer at Stephansplatz → U1 | Tests transfer |
| Floridsdorf → Hütteldorf | U6 (partial) + U4 | Long cross-city route |
| Point near Prater → Stephansplatz | Walk + U1 or U2 | Tests entrance snapping |
| Walk-only (200 m apart, no metro needed) | Walk only | Tests pure walk path |

---

## 11. Run Instructions (for README)

```bash
# 1. Clone & install
git clone <repo-url>
cd vienna-ubahn-navigator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Build data (one-time, ~2 min, downloads ~30 MB)
python scripts/download_gtfs.py
python scripts/download_walk_osm.py
python scripts/build_graph.py

# 3. Run
uvicorn backend.app.main:app --reload --port 8000
# Open http://localhost:8000
```

---

## 12. Future Extensions (Out of Scope for V1)

- Real-time departure data via Wiener Linien's Realtime API
- Schedule-aware routing (time-of-day departure boards)
- Tram and bus integration (GTFS `route_type` 0 and 3)
- Accessibility routing (elevator-only paths)
- Address geocoding (type an address, not just click)
- Multiple route alternatives
- Docker / deployment configuration
- Mobile-responsive layout
