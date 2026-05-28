# Vienna U-Bahn Navigator — Development Plan

> A web-based pathfinding application that finds the fastest walk + U-Bahn route between any two points on the Vienna Subway network, built on the architecture of the Paris Metro Navigator project.

---

## 1. Project Overview

### Goal
A localhost-first web app where a user picks two points on an interactive Leaflet map (by clicking on the map **or** selecting from a station dropdown) and gets back:
- The **optimal time-based route** via A\* search
- A **polyline drawn on the map** for the route
- A **step-by-step itinerary** (walk → enter → ride → transfer → exit → walk)

### What we keep from Paris Metro Navigator
- A\* pathfinding engine (`pathfinding.py`) — copied almost verbatim
- Graph model: walk nodes, platforms, ride/transfer/entrance/walk edges
- All API endpoints: `GET /api/network`, `POST /api/path`, scenario CRUD
- Leaflet frontend with network overlay and route polyline

### What we remove
- ~~JWT authentication~~ — no login, no tokens, no bcrypt (`python-jose`, `passlib` dropped)
- ~~`AuthService`, `access_control.py`~~ — no `get_current_admin` dependency; admin endpoints are unprotected (localhost only)
- ~~`.env` secrets~~ — no JWT_SECRET, no ADMIN_USERNAME/PASSWORD
- ~~`init_db.py`~~ — no admin user seeding
- ~~Scenario DB persistence~~ — scenarios live in an in-memory dict that resets on server restart
- ~~SQLite entirely~~ — `database.py` and `config.py` deleted; graph data stored as JSON files read on startup

### What we keep (including admin)
- Admin scenario panel — close a station, a line, or a segment; routes reroute automatically
- `ScenarioService` — rewritten to use a plain in-memory `dict` instead of a `scenarios` DB table; `ClosureMask` compiled on every write
- `GET/POST/DELETE /api/scenarios` — same REST surface as Paris, just no auth guard and no DB

### Core differences from Paris Metro Navigator

| Aspect | Paris Metro Navigator | Vienna U-Bahn Navigator |
|---|---|---|
| City | Central Paris | Vienna |
| Data source | IDFM GTFS feed + OSM | Wiener Linien GTFS feed + OSM |
| Lines | 16 metro lines | 5 U-Bahn lines (U1–U6 excl. U5) |
| Graph storage | SQLite (`metro.db`) | **JSON files** (`backend/data/*.json`) |
| Auth | JWT login required for admin | **None** — admin open on localhost |
| Scenario storage | SQLite `scenarios` table | **In-memory dict** (resets on restart) |
| Station selector | Text search only | Click on map **or** dropdown |
| Route display | Magenta polyline | Per-line colored polyline |

---

## 2. Architecture

```
vienna-ubahn-navigator/
├── backend/
│   ├── __init__.py
│   ├── data/                        # written by build scripts, read on startup
│   │   ├── platforms.json
│   │   ├── walk_nodes.json
│   │   ├── ride_edges.json
│   │   ├── transfer_edges.json
│   │   ├── entrance_edges.json
│   │   └── walk_edges.json
│   └── app/
│       ├── __init__.py
│       ├── main.py              # FastAPI app, lifespan, CORS, static mount
│       ├── api/
│       │   ├── __init__.py
│       │   ├── network.py       # GET /api/network
│       │   ├── path.py          # POST /api/path
│       │   ├── scenarios.py     # GET/POST/DELETE /api/scenarios (no auth guard)
│       │   └── weather.py       # GET/PUT /api/weather (admin weather condition)
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── path.py          # PathRequest, PathResponse, PathStepOut
│       │   └── scenario.py      # ScenarioCreate, ScenarioResponse
│       ├── services/
│       │   ├── __init__.py
│       │   ├── pathfinding.py   # PathfindingService + A* — reads JSON on init
│       │   └── scenario.py      # ScenarioService — in-memory dict, no DB
│       └── dependencies/
│           ├── __init__.py
│           └── services.py      # get_pathfinder() + get_scenario_service() singletons
├── frontend/
│   ├── index.html               # User page
│   ├── admin.html               # Admin page (scenario management)
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── config.js            # LINE_COLORS, MAP_CENTER, API_BASE
│       ├── map.js               # Leaflet init, network overlay, click-to-pick
│       ├── ui.js                # Dropdown, form state, button wiring
│       ├── pathfinding.js       # POST /api/path, draw polyline, render steps
│       └── admin.js             # Scenario CRUD calls, disruption banner
├── scripts/
│   ├── download_gtfs.py         # Download Wiener Linien GTFS
│   ├── download_walk_osm.py     # Overpass walking graph for Vienna
│   └── build_graph.py           # GTFS + OSM → 6 JSON files in backend/data/
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   └── test_pathfinding.py
├── requirements.txt
└── README.md
```

**Removed vs Paris:** `database.py`, `config.py`, `api/auth.py`, `services/auth.py`, `schemas/auth.py`, `dependencies/access_control.py`, `scripts/init_db.py`, `.env`, `.env.example`.  
**Changed vs Paris:** `build_graph.py` — writes JSON instead of SQLite. `pathfinding.py` — reads JSON instead of DB. `api/network.py` — reads JSON instead of DB. `services/scenario.py` — in-memory dict, reads platforms JSON once for segment blocking. `api/scenarios.py` — auth guard removed.

---

## 3. Data Pipeline

### 3.1 GTFS Source

**Wiener Linien** publishes a freely available GTFS feed:
- URL: `https://www.wienerlinien.at/ogd_realtime/doku/ogd/gtfs/gtfs.zip`
- License: Creative Commons Attribution 4.0 (CC BY 4.0)
- Contains: U-Bahn, tram, bus — filter `route_type == "1"` for subway only
- Lines present: U1, U2, U3, U4, U6 (U5 is under construction and absent from the feed)

**`scripts/download_gtfs.py`:**
1. Download zip to `backend/data/raw/gtfs/`
2. Unzip `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`

### 3.2 Walking Graph (OSM via Overpass)

**`scripts/download_walk_osm.py`** — query Overpass for walkable ways inside Vienna's bounding box:
- Bounding box: `(48.10, 16.20, 48.32, 16.58)` — covers all of Vienna
- Query: `way[highway~"^(footway|path|pedestrian|residential|living_street|unclassified|tertiary|secondary|primary)$"]`
- Output: `backend/data/raw/walk.osm.json`

### 3.3 Graph Build

**`scripts/build_graph.py`** — ported from Paris with three changes: `BBOX` updated to Vienna values, `route_short_name` normalization removed (Wiener Linien already uses clean `U1`–`U6` names), and output changed from SQLite to **6 JSON files**.

Each file is a list of plain dicts with the same field names the SQL rows had, so downstream code stays nearly identical:

| File | Contents | Approx. rows (Vienna) |
|---|---|---|
| `platforms.json` | `{id, station_id, station_name, line_id, lat, lng}` | ~130 |
| `walk_nodes.json` | `{id, lat, lng}` | ~50k–150k |
| `ride_edges.json` | `{from_platform, to_platform, travel_time_s, line_id}` | ~200 |
| `transfer_edges.json` | `{from_platform, to_platform, transfer_time_s}` | ~20 |
| `entrance_edges.json` | `{platform_id, walk_node_id, travel_time_s}` | ~130 |
| `walk_edges.json` | `{from_node, to_node, travel_time_s}` | ~100k–300k |

**Build output** (instead of `metro.db`):
```python
import json
DATA_DIR = ROOT / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

json.dump(platforms,       open(DATA_DIR / "platforms.json",       "w"))
json.dump(walk_nodes,      open(DATA_DIR / "walk_nodes.json",      "w"))
json.dump(ride_edges,      open(DATA_DIR / "ride_edges.json",      "w"))
json.dump(transfer_edges,  open(DATA_DIR / "transfer_edges.json",  "w"))
json.dump(entrance_edges,  open(DATA_DIR / "entrance_edges.json",  "w"))
json.dump(walk_edges,      open(DATA_DIR / "walk_edges.json",      "w"))
```

Expected total size: 15–40 MB uncompressed. Startup load time: 2–5 seconds (one-time cost; graph lives in RAM after that).

---

## 4. Backend

### 4.1 No `config.py`, no `database.py`

Both files are deleted entirely. There is no DB connection to configure, no schema to initialise, no path settings to manage.

The only shared constant needed is `DATA_DIR`, defined inline at the top of any file that reads JSON:

```python
from pathlib import Path
DATA_DIR = Path(__file__).resolve().parents[3] / "backend" / "data"
```

`main.py` no longer calls `init_tables()` on startup — there is nothing to initialise.

### 4.2 `services/pathfinding.py` — reads JSON instead of DB

The `_load()` method replaces its six `conn.execute(...)` calls with six `json.load()` calls. Everything else — node/edge dataclasses, A\* algorithm, overlay logic — is unchanged:

```python
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "backend" / "data"

def _load(self) -> None:
    walk_rows     = json.load(open(DATA_DIR / "walk_nodes.json"))
    plat_rows     = json.load(open(DATA_DIR / "platforms.json"))
    ride_rows     = json.load(open(DATA_DIR / "ride_edges.json"))
    transfer_rows = json.load(open(DATA_DIR / "transfer_edges.json"))
    entrance_rows = json.load(open(DATA_DIR / "entrance_edges.json"))
    walk_edge_rows= json.load(open(DATA_DIR / "walk_edges.json"))
    # rest of _load() is identical — rows are dicts, r["lat"] still works
```

### 4.3 `services/pathfinding.py` — JSON load + weather-aware walk speed

```python
WALK_SPEED_MPS    = 1.4          # clear conditions baseline
WALK_SPEED_RAIN   = 1.1          # ~80% of normal (light rain, umbrella)
WALK_SPEED_SNOW   = 0.8          # ~57% of normal (snow/ice underfoot)
RIDE_TIME_FACTOR  = 0.75
V_MAX_MPS         = 15.0 / RIDE_TIME_FACTOR
EARTH_RADIUS_M    = 6_371_000
ENTRANCE_K        = 3
ENTRANCE_R_MAX_M  = 150.0
STATION_SNAP_R_M  = 100.0
```

**`ClosureMask`** gains one new field — `walk_speed_mps` — with a default of the normal baseline. Everything else in the dataclass is unchanged:

```python
@dataclass(frozen=True)
class ClosureMask:
    blocked_stations: frozenset[str] = frozenset()
    blocked_segments: frozenset[tuple[int, int]] = frozenset()
    blocked_lines: frozenset[str] = frozenset()
    walk_speed_mps: float = WALK_SPEED_MPS   # ← new field
```

**`find_path()`** passes `closures.walk_speed_mps` into `_build_overlay()` and the walk-edge weighting, replacing every hardcoded `WALK_SPEED_MPS` reference inside the per-query path with the value from the mask:

```python
def find_path(self, lat_start, lng_start, lat_end, lng_end,
              closures: ClosureMask | None = None) -> PathResult:
    closures = closures or ClosureMask.empty()
    ws = closures.walk_speed_mps          # ← use weather-adjusted speed

    overlay, start_idx, end_idx = self._build_overlay(
        lat_start, lng_start, lat_end, lng_end, walk_speed=ws
    )
    ...
```

Walk edges in the **base graph** are pre-computed at build time with fixed `travel_time_s` values, so they cannot be adjusted at query time. Instead, `_build_overlay()` scales the two virtual endpoint edges (start→nearest-walk-node and nearest-walk-node→end) using `walk_speed`, and a new `walk_speed` parameter is threaded into `_augment_entrances()` so the entrance edge weights in the overlay also reflect weather. The pre-built walk-edge weights in `walk_edges.json` are **not** changed — only the short first/last-mile segments that A\* uses to enter and exit the walk graph are weather-adjusted. This is a reasonable approximation: the bulk of any walk route goes through pre-built edges, so to apply weather uniformly those edges need reweighting too.

**Full approach for uniform weather effect:** rather than re-loading the graph on weather change, `_a_star()` accepts a `walk_speed` parameter and applies a correction factor inline when relaxing walk edges:

```python
correction = WALK_SPEED_MPS / walk_speed   # e.g. 1.4/0.8 = 1.75× for snow

for edge in self._neighbors(current, overlay):
    weight = edge.weight
    if edge.kind in ("walk", "entrance"):
        weight *= correction               # stretch walk time by weather factor
    tentative_g = g_score[current] + weight
    ...
```

This is clean, zero-copy, and requires no graph reload — the correction is applied on the fly during each search.

### 4.4 `services/scenario.py` — Rewritten: in-memory dict, no DB

`ClosureMask` and `_is_blocked()` stay as-is and are fully active for the admin panel.

### 4.4 `services/scenario.py` — in-memory dict + weather toggle

Weather is a separate piece of state from the scenario list — it has no ID, it's not a list item, it's just a single enum value that replaces `walk_speed_mps` in the compiled `ClosureMask`. It lives alongside `_store` in the service:

```python
import itertools, json
from pathlib import Path
from enum import Enum
from backend.app.services.pathfinding import (
    ClosureMask, WALK_SPEED_MPS, WALK_SPEED_RAIN, WALK_SPEED_SNOW
)

DATA_DIR = Path(__file__).resolve().parents[3] / "backend" / "data"
_counter = itertools.count(1)

class Weather(str, Enum):
    CLEAR = "clear"
    RAIN  = "rain"
    SNOW  = "snow"

WEATHER_SPEEDS = {
    Weather.CLEAR: WALK_SPEED_MPS,
    Weather.RAIN:  WALK_SPEED_RAIN,
    Weather.SNOW:  WALK_SPEED_SNOW,
}

@dataclass
class Scenario:
    id: int
    type: str       # "station" | "segment" | "line"
    payload: dict

class ScenarioService:
    def __init__(self):
        self._store: dict[int, Scenario] = {}
        self._weather: Weather = Weather.CLEAR
        self._mask: ClosureMask = ClosureMask.empty()
        self._platforms = json.load(open(DATA_DIR / "platforms.json"))

    # --- scenario CRUD (unchanged from before) ---
    def list_scenarios(self) -> list[Scenario]: ...
    def create_scenario(self, s_type, payload) -> Scenario: ...
    def delete_scenario(self, sid) -> bool: ...
    def clear_all(self) -> int: ...

    # --- weather ---
    def set_weather(self, w: Weather) -> None:
        self._weather = w
        self._recompile()

    def get_weather(self) -> Weather:
        return self._weather

    def get_mask(self) -> ClosureMask:
        return self._mask

    def _recompile(self) -> None:
        # Build blocked_stations / blocked_segments / blocked_lines
        # from self._store exactly as before, then add walk_speed_mps
        # from the current weather state.
        self._mask = ClosureMask(
            blocked_stations=...,
            blocked_segments=...,
            blocked_lines=...,
            walk_speed_mps=WEATHER_SPEEDS[self._weather],
        )
```

### 4.5 `dependencies/services.py` — Two singletons, same as Paris

```python
from functools import lru_cache
from backend.app.services.pathfinding import PathfindingService
from backend.app.services.scenario import ScenarioService

@lru_cache
def get_pathfinder() -> PathfindingService:
    return PathfindingService()

@lru_cache
def get_scenario_service() -> ScenarioService:
    return ScenarioService()
```

### 4.6 `api/path.py` — Scenario mask passed in, no auth

```python
@router.post("/path", response_model=PathResponse)
def find_path(
    req: PathRequest,
    pathfinder: PathfindingService = Depends(get_pathfinder),
    scenarios: ScenarioService = Depends(get_scenario_service),
):
    try:
        result = pathfinder.find_path(
            lat_start=req.lat_start, lng_start=req.lng_start,
            lat_end=req.lat_end,   lng_end=req.lng_end,
            closures=scenarios.get_mask(),
        )
    except PathNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PathResponse(...)
```

### 4.7 `api/scenarios.py` — No auth guard

The Paris version wrapped mutating endpoints with `_admin: str = Depends(get_current_admin)`. We simply remove that dependency — on localhost there's no need to protect these routes.

```python
@router.post("", status_code=201)
def create_scenario(body: ScenarioCreate, service = Depends(get_scenario_service)):
    return service.create_scenario(body.type, body.payload)

@router.delete("/{sid}", status_code=204)
def delete_scenario(sid: int, service = Depends(get_scenario_service)):
    if not service.delete_scenario(sid):
        raise HTTPException(404, "Not found")

@router.delete("", status_code=200)
def clear_scenarios(service = Depends(get_scenario_service)):
    return {"deleted": service.clear_all()}
```

### 4.8 `api/network.py` — reads JSON instead of DB

The two `conn.execute()` calls are replaced with `json.load()`. The response structure is identical:

```python
DATA_DIR = Path(__file__).resolve().parents[3] / "backend" / "data"

@router.get("/network", response_model=NetworkResponse)
def get_network():
    platforms = json.load(open(DATA_DIR / "platforms.json"))
    ride_edges = json.load(open(DATA_DIR / "ride_edges.json"))
    # build stations dict and segments list — same logic as Paris
    ...
```

### 4.9 `main.py` — no init_tables, otherwise same

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pathfinder()        # loads JSON graph into RAM on startup
    get_scenario_service()  # loads platforms.json for segment lookups
    yield

app = FastAPI(title="Vienna U-Bahn Navigator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(path.router)
app.include_router(network.router)
app.include_router(scenarios.router)
```

No `init_tables()`, no `database` import, no `config` import.

### 4.10 API Surface (final)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/network` | Stations + segments for map rendering |
| `POST` | `/api/path` | `{lat_start, lng_start, lat_end, lng_end}` → itinerary |
| `GET` | `/api/scenarios` | List active closures |
| `POST` | `/api/scenarios` | Create a closure (station / segment / line) |
| `DELETE` | `/api/scenarios/{id}` | Remove one closure |
| `DELETE` | `/api/scenarios` | Clear all closures |
| `GET` | `/api/weather` | Get current weather condition (`clear` / `rain` / `snow`) |
| `PUT` | `/api/weather` | Set weather condition — body: `{"condition": "rain"}` |

### 4.10a `api/weather.py` — Weather Condition Endpoint

A dedicated router keeps weather concerns out of `scenarios.py`. It exposes two endpoints — one to read the current condition and one to set it — both delegating to `ScenarioService`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.app.services.scenario import ScenarioService, Weather
from backend.app.dependencies.services import get_scenario_service

router = APIRouter(prefix="/api/weather", tags=["weather"])

class WeatherRequest(BaseModel):
    condition: str   # "clear" | "rain" | "snow"

@router.get("")
def get_weather(service: ScenarioService = Depends(get_scenario_service)):
    return {"condition": service.get_weather().value}

@router.put("")
def set_weather(body: WeatherRequest, service: ScenarioService = Depends(get_scenario_service)):
    try:
        w = Weather(body.condition)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown condition '{body.condition}'. Use: clear, rain, snow"
        )
    service.set_weather(w)
    return {"condition": w.value}
```

Register the new router in `main.py` alongside the others:

```python
from backend.app.api import weather as weather_router
app.include_router(weather_router.router)
```

### 4.11 `requirements.txt`

```
fastapi
uvicorn[standard]
pydantic>=2
scipy
pandas
requests
```

Removed vs Paris: `pydantic-settings`, `python-jose[cryptography]`, `passlib[bcrypt]`. No new dependencies added — `json` is stdlib.

---

## 5. Frontend

### 5.1 `js/config.js` — Constants

```javascript
const API_BASE = '';

const LINE_COLORS = {
  U1: '#e2001a',   // red
  U2: '#9b479f',   // purple
  U3: '#f07d00',   // orange
  U4: '#009a44',   // green
  U6: '#8b6f47',   // brown
};

const MAP_CENTER = [48.2082, 16.3738];  // Vienna
const MAP_ZOOM   = 13;
const WALK_COLOR = '#666666';
```

### 5.2 `js/map.js` — Leaflet Map

- Init map at Vienna center
- On load: `GET /api/network` → draw colored `L.polyline` per segment, `L.circleMarker` per station
- Two pick modes (`pickingStart` / `pickingEnd`): `map.on('click')` places a pin and updates state
- Clicking a station marker in pick mode snaps to that station's exact lat/lng
- After routing: draw route as `L.layerGroup` of colored polyline segments; `map.fitBounds()` to route

### 5.3 `js/ui.js` — Dual Input (Dropdown + Click)

- Two `<select>` elements populated from `/api/network` stations (sorted A–Z)
- `#btn-pick-start` / `#btn-pick-end` — toggle map click mode, change cursor to crosshair
- Selecting from dropdown updates the map pin; clicking the map updates the dropdown (nearest station name or raw coordinates)
- `#btn-find` — validates both points are set, calls `findRoute()`
- `#btn-reset` — clears all state, removes route layer, resets selects

### 5.4 `js/pathfinding.js` — Route Display

1. `POST /api/path` with `{lat_start, lng_start, lat_end, lng_end}`
2. Remove previous route layer group
3. Draw colored polyline segments (walk = dashed gray, ride = solid line in `LINE_COLORS[line_id]`)
4. Render `data.steps` as a numbered itinerary list in `#result-steps`
5. Show `data.total_time_s` formatted as "X min Y sec" in `#result-banner`

### 5.5 `index.html` — Layout

```
+------------------------------------------+
| Vienna U-Bahn Navigator           header  |
+------------+-----------------------------+
|  SIDEBAR   |                             |
|            |       LEAFLET MAP           |
| Plan Route |   (network overlay)         |
| [Start ▾] |                             |
| [Pick map] |   (route polyline)          |
|            |                             |
| [End ▾]   |                             |
| [Pick map] |                             |
|            |                             |
| [Find Route] [Reset]                     |
|------------|                             |
| Itinerary  |                             |
| Total: 8 min                             |
| 1. 🚶 Walk…|                             |
| 2. ⬇️ Enter U1                           |
| 3. 🚇 U1…  |                             |
+------------+-----------------------------+
```

### 5.6 `admin.html` — Admin Panel Layout

The admin page hosts two distinct control areas: **Disruptions** (station/line/segment closures, unchanged from Paris) and the new **Weather Condition** toggle. Both areas communicate with the backend independently.

```
+-----------------------------------------------+
| Vienna U-Bahn Navigator — Admin       header   |
+-----------------------------------------------+
|  ⚠️  DISRUPTIONS                               |
|  Type: [Station ▾]  Target: [Karlsplatz ▾]    |
|  [Add Closure]                                 |
|  Active closures:                              |
|  • Station: Karlsplatz  [✕]                   |
|  • Line: U3             [✕]                   |
|  [Clear All]                                   |
+-----------------------------------------------+
|  🌦️  WEATHER CONDITION                         |
|  Current conditions affect pedestrian speed.   |
|                                                |
|  [☀️ Clear]  [🌧️ Rain]  [❄️ Snow]              |
|                                                |
|  Walk speed: Clear=1.4 m/s · Rain=1.1 m/s     |
|              Snow=0.8 m/s                      |
+-----------------------------------------------+
```

The three weather buttons are a radio-style toggle group: selecting one immediately sends a `PUT /api/weather` request and highlights the active button. The current condition is fetched on page load via `GET /api/weather` and the matching button is pre-highlighted.

### 5.7 `js/admin.js` — Weather Toggle Logic

`admin.js` already handles scenario CRUD and the disruption banner. Weather is appended as a self-contained block at the bottom of the file:

```javascript
// ── Weather ──────────────────────────────────────────────────────────────

const WEATHER_LABELS = {
  clear: { emoji: '☀️', label: 'Clear', speed: '1.4 m/s' },
  rain:  { emoji: '🌧️', label: 'Rain',  speed: '1.1 m/s' },
  snow:  { emoji: '❄️', label: 'Snow',  speed: '0.8 m/s' },
};

// Fetch current condition from the server and highlight the right button.
async function loadWeather() {
  const res  = await fetch(`${API_BASE}/api/weather`);
  const data = await res.json();
  setWeatherUI(data.condition);
}

// Send the chosen condition to the server, then update the UI.
async function applyWeather(condition) {
  const res = await fetch(`${API_BASE}/api/weather`, {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ condition }),
  });
  if (!res.ok) {
    console.error('Weather update failed', await res.text());
    return;
  }
  const data = await res.json();
  setWeatherUI(data.condition);
}

// Reflect the active condition in the button group and speed label.
function setWeatherUI(condition) {
  document.querySelectorAll('.weather-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.condition === condition);
  });
  const info = WEATHER_LABELS[condition] ?? WEATHER_LABELS.clear;
  document.getElementById('weather-speed-label').textContent =
    `Walk speed: ${info.speed} — ${info.emoji} ${info.label}`;
}

// Wire up buttons once the DOM is ready.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.weather-btn').forEach(btn => {
    btn.addEventListener('click', () => applyWeather(btn.dataset.condition));
  });
  loadWeather();
});
```

The corresponding HTML snippet inside `admin.html`:

```html
<section id="weather-panel">
  <h2>🌦️ Weather Condition</h2>
  <p>Current conditions affect pedestrian walking speed across all routes.</p>
  <div class="weather-btn-group">
    <button class="weather-btn" data-condition="clear">☀️ Clear</button>
    <button class="weather-btn" data-condition="rain">🌧️ Rain</button>
    <button class="weather-btn" data-condition="snow">❄️ Snow</button>
  </div>
  <p id="weather-speed-label" class="weather-speed-info"></p>
</section>
```

CSS for the active-state highlight (add to `style.css`):

```css
.weather-btn-group {
  display: flex;
  gap: 0.5rem;
  margin: 0.75rem 0;
}

.weather-btn {
  flex: 1;
  padding: 0.5rem 1rem;
  border: 2px solid #ccc;
  border-radius: 6px;
  background: #f8f8f8;
  cursor: pointer;
  font-size: 1rem;
  transition: border-color 0.15s, background 0.15s;
}

.weather-btn.active {
  border-color: #0057a8;
  background: #ddeeff;
  font-weight: bold;
}

.weather-speed-info {
  font-size: 0.85rem;
  color: #555;
}
```

---

## 6. Vienna U-Bahn Line Reference

| Line | Color | Key interchanges |
|------|-------|-----------------|
| U1 | Red `#e2001a` | Karlsplatz, Stephansplatz, Schwedenplatz |
| U2 | Purple `#9b479f` | Karlsplatz, Schottentor |
| U3 | Orange `#f07d00` | Stephansplatz, Westbahnhof |
| U4 | Green `#009a44` | Schwedenplatz, Karlsplatz, Längenfeldgasse, Spittelau |
| U6 | Brown `#8b6f47` | Längenfeldgasse, Westbahnhof, Spittelau |

---

## 7. Step-by-Step Development Order

### Phase 0 — Setup (15 min)
1. Create `vienna-ubahn-navigator/` folder structure (see Section 2)
2. Write `requirements.txt` (6 packages — see Section 4.11)
3. Create empty `backend/data/` directory (gitignored; populated by build scripts)

### Phase 1 — Data Pipeline (1–2 hrs)
1. Write `scripts/download_gtfs.py` — Wiener Linien GTFS zip → `backend/data/raw/gtfs/`
2. Write `scripts/download_walk_osm.py` — Overpass query, Vienna bbox `(48.10, 16.20, 48.32, 16.58)`
3. Write `scripts/build_graph.py` — port from Paris; change `BBOX`, remove route name normalization, replace SQLite writes with `json.dump()` to 6 files in `backend/data/`
4. Run all three scripts, verify 6 JSON files appear in `backend/data/`

### Phase 2 — Backend (45 min)
1. Write `services/pathfinding.py` — port from Paris, replace `get_db_connection()` calls with `json.load()` (see Section 4.2); ensure `WALK_SPEED_RAIN` and `WALK_SPEED_SNOW` constants are defined and `ClosureMask` includes `walk_speed_mps` (see Section 4.3)
2. Copy `schemas/path.py` and `schemas/scenario.py` verbatim
3. Write `api/network.py` — replace DB queries with `json.load()` (see Section 4.8)
4. Write `services/scenario.py` — in-memory dict, reads `platforms.json` once, includes `Weather` enum and `set_weather()` / `get_weather()` (see Section 4.4)
5. Write `api/path.py` — keep `ScenarioService` dependency, remove auth (see Section 4.6)
6. Write `api/scenarios.py` — remove `_admin = Depends(get_current_admin)` from mutating endpoints (see Section 4.7)
7. Write `api/weather.py` — `GET` and `PUT /api/weather` endpoints (see Section 4.10a)
8. Write `dependencies/services.py` — two singletons (see Section 4.5)
9. Write `main.py` — no `init_tables()`, register four routers (path, network, scenarios, weather) (see Section 4.9)
10. `uvicorn backend.app.main:app --reload` → test all endpoints with curl or `/docs`; verify `PUT /api/weather {"condition":"snow"}` changes the mask and a subsequent `POST /api/path` returns a longer walk time

### Phase 3 — Frontend: Network Map (45 min)
1. Write `index.html` with sidebar + map layout
2. Write `js/config.js` with Vienna constants and U-Bahn colors
3. Write `js/map.js` — init Leaflet, fetch `/api/network`, draw network overlay
4. Verify all 5 lines render with correct colors

### Phase 4 — Frontend: Input (45 min)
1. Write `js/ui.js` — dropdown population, pick-mode buttons, state management
2. Wire dropdown ↔ map pin sync
3. Test clicking on map vs selecting from dropdown

### Phase 5 — Frontend: Routing (45 min)
1. Write `js/pathfinding.js` — POST request, colored polyline drawing, itinerary rendering
2. Test end-to-end: pick two points → Find Route → polyline appears + steps listed
3. Test reset button clears everything

### Phase 5.5 — Admin Panel: Weather Toggle (20 min)
1. Write `admin.html` — two sections: Disruptions (existing) + Weather Condition (new); add the three-button toggle group and `#weather-speed-label` paragraph (see Section 5.6)
2. Append weather block to `admin.js` — `loadWeather()`, `applyWeather()`, `setWeatherUI()`, DOMContentLoaded wiring (see Section 5.7)
3. Add `.weather-btn`, `.weather-btn.active`, `.weather-speed-info` to `style.css` (see Section 5.7)
4. Manual test: open admin page → click Rain → open user page → find a route → confirm itinerary walk time is ~27% longer than Clear; click Snow → confirm ~75% longer than Clear

### Phase 6 — Polish (30 min)
1. Write `frontend/css/style.css` — clean transit-app styling
2. Write `tests/test_api.py` and `tests/test_pathfinding.py` with 3–5 known routes; add one test for weather: set snow via `PUT /api/weather`, run the same path, assert `total_time_s` is greater than the clear-weather result
3. Write `README.md`

---

## 8. Key Technical Decisions

### A\* with time as objective
- Time is the only meaningful metric for transit routing
- `h(n) = haversine(n, goal) / V_MAX` is admissible — never overestimates — so A\* finds the optimal path
- All edge weights (walk, ride, transfer) are in seconds, giving a homogeneous cost function

### Virtual endpoint overlay
- The base graph is loaded once into RAM on startup
- Each query creates 2 temporary nodes (start/end) with edges to nearby walk nodes/platforms
- The overlay is garbage-collected after each A\* run — base graph is never mutated, safe for concurrent requests

### Per-platform nodes
- Each line at a station gets its own platform node (e.g. Karlsplatz has 3: U1, U2, U4)
- Transfer edges (180 s flat) connect platforms at the same station
- A\* naturally decides whether a transfer is worth the cost

---

## 9. Testing Scenarios

| Route | Expected behavior |
|-------|-------------------|
| Stephansplatz → Karlsplatz | Direct U1 (3 stops) |
| Westbahnhof → Schwedenplatz | U3 → transfer at Stephansplatz → U1 |
| Floridsdorf → Hütteldorf | U6 south → transfer at Spittelau or Längenfeldgasse → U4 |
| Click near Prater → Stephansplatz | Walk + U1 or U2 (tests entrance snapping) |
| Two points 150 m apart, no station nearby | Walk only (tests pure walk path) |

---

## 10. Run Instructions

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Build data (one-time, ~2 min, downloads ~30 MB, writes ~15–40 MB of JSON)
python scripts/download_gtfs.py
python scripts/download_walk_osm.py
python scripts/build_graph.py

# Run (graph loads into RAM on first startup, takes 2–5 s)
uvicorn backend.app.main:app --reload --port 8000
# Open http://localhost:8000
```

---

## 11. Future Extensions

- Switch JSON files to MessagePack or pickle for faster startup (JSON parse of 40 MB takes ~3–5 s; msgpack cuts that to under 1 s)
- Persist scenarios to a JSON file so they survive server restarts
- Real-time departures via Wiener Linien Realtime API
- Tram and bus integration (`route_type` 0 and 3 from GTFS)
- Address geocoding (type an address instead of clicking)
- Mobile-responsive layout
