from fastapi import FastAPI, Response, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from math import radians, sin, cos, sqrt, atan2
try:
    from scipy.spatial import cKDTree
except Exception:
    cKDTree = None
import json
from pathlib import Path
import heapq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).parent / 'data'

with open(DATA_DIR / 'stations.json', 'r', encoding='utf-8') as f:
    STATIONS = json.load(f)

with open(DATA_DIR / 'lines.json', 'r', encoding='utf-8') as f:
    LINES = json.load(f)

# Parameters
WALK_SPEED = 1.25  # m/s (~4.5 km/h) for realistic walking
SUBWAY_SPEED = 14.0  # m/s (~50 km/h) average subway travel speed
STOP_PENALTY = 25  # seconds dwell/boarding penalty per subway segment
TRANSFER_PENALTY = 60  # seconds penalty for changing between walk and subway
WALK_THRESHOLD = 700  # meters: maximum reasonable station walking distance
WALK_GRID_SPACING = 200  # meters between synthetic walk graph nodes
WALK_GRID_MARGIN = 1200  # meters of padding around station bounding box

def haversine_meters(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371000
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    x = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return 2 * R * atan2(sqrt(x), sqrt(1 - x))

def _meters_to_lat_deg(meters: float) -> float:
    return meters / 110540.0


def _meters_to_lng_deg(meters: float, lat: float) -> float:
    return meters / (111320.0 * cos(radians(lat)))


def build_walk_grid(stations_by_name: dict[str, tuple[float, float]]) -> tuple[dict[str, list[tuple[str, float, str]]], dict[str, tuple[float, float]]]:
    lats = [coords[0] for coords in stations_by_name.values()]
    lngs = [coords[1] for coords in stations_by_name.values()]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    center_lat = (min_lat + max_lat) / 2

    lat_margin = _meters_to_lat_deg(WALK_GRID_MARGIN)
    lng_margin = _meters_to_lng_deg(WALK_GRID_MARGIN, center_lat)
    lat_step = _meters_to_lat_deg(WALK_GRID_SPACING)
    lng_step = _meters_to_lng_deg(WALK_GRID_SPACING, center_lat)

    lat0 = min_lat - lat_margin
    lng0 = min_lng - lng_margin
    rows = int((max_lat - min_lat + 2 * lat_margin) / lat_step) + 1
    cols = int((max_lng - min_lng + 2 * lng_margin) / lng_step) + 1

    grid_graph: dict[str, list[tuple[str, float, str]]] = {}
    grid_coords: dict[str, tuple[float, float]] = {}

    for r in range(rows):
        for c in range(cols):
            node_id = f"GRID_{r}_{c}"
            lat = lat0 + r * lat_step
            lng = lng0 + c * lng_step
            grid_coords[node_id] = (lat, lng)
            grid_graph[node_id] = []

    def add_grid_edge(a: str, b: str) -> None:
        a_coords = grid_coords[a]
        b_coords = grid_coords[b]
        dist = haversine_meters(a_coords, b_coords)
        t = dist / WALK_SPEED
        grid_graph[a].append((b, t, 'walk'))

    for r in range(rows):
        for c in range(cols):
            node_id = f"GRID_{r}_{c}"
            neighbors = []
            if r + 1 < rows:
                neighbors.append(f"GRID_{r+1}_{c}")
            if c + 1 < cols:
                neighbors.append(f"GRID_{r}_{c+1}")
            if r + 1 < rows and c + 1 < cols:
                neighbors.append(f"GRID_{r+1}_{c+1}")
            if r + 1 < rows and c - 1 >= 0:
                neighbors.append(f"GRID_{r+1}_{c-1}")
            for neighbor in neighbors:
                add_grid_edge(node_id, neighbor)
                add_grid_edge(neighbor, node_id)

    # connect stations to nearby grid nodes
    for station, coords in stations_by_name.items():
        nearest: list[tuple[str, float]] = []
        for node_id, node_coords in grid_coords.items():
            dist = haversine_meters(coords, node_coords)
            nearest.append((node_id, dist))
        nearest.sort(key=lambda item: item[1])
        for node_id, dist in nearest[:2]:
            t = dist / WALK_SPEED
            grid_graph.setdefault(station, []).append((node_id, t, 'walk'))
            grid_graph.setdefault(node_id, []).append((station, t, 'walk'))

    return grid_graph, grid_coords


def build_graph():
    stations_by_name = {s['name'].strip(): tuple(s['coords']) for s in STATIONS}
    graph = {name: [] for name in stations_by_name}

    # Subway edges from lines
    for line, seq in LINES.items():
        for i in range(len(seq)-1):
            a = seq[i]
            b = seq[i+1]
            if a not in stations_by_name or b not in stations_by_name:
                continue
            dist = haversine_meters(stations_by_name[a], stations_by_name[b])
            t = dist / SUBWAY_SPEED + STOP_PENALTY
            graph[a].append((b, t, 'subway'))
            graph[b].append((a, t, 'subway'))

    # Walking grid sample mesh around the station area
    grid_graph, grid_coords = build_walk_grid(stations_by_name)
    for node_id, neighbors in grid_graph.items():
        graph[node_id] = list(neighbors)

    coords_map = {**stations_by_name, **grid_coords}
    return graph, coords_map, stations_by_name

graph, NODE_COORDS, STATION_COORDS = build_graph()

# prepare node KD-tree (optional)
NODE_NAMES = list(NODE_COORDS.keys())
NODE_COORD_LIST = [tuple(NODE_COORDS[name]) for name in NODE_NAMES]
if cKDTree is not None and NODE_COORD_LIST:
    try:
        NODE_TREE = cKDTree(NODE_COORD_LIST)
    except Exception:
        NODE_TREE = None
else:
    NODE_TREE = None

class PathRequest(BaseModel):
    start_station: str | None = None
    end_station: str | None = None
    lat_start: float | None = None
    lng_start: float | None = None
    lat_end: float | None = None
    lng_end: float | None = None


def a_star_graph(graph_local, coords_map, start, goal):
    if start not in graph_local or goal not in graph_local:
        return None, None

    # admissible heuristic: great-circle / fastest possible speed
    V_MAX = max(SUBWAY_SPEED, WALK_SPEED)

    def heuristic(a, b):
        return haversine_meters(coords_map[a], coords_map[b]) / V_MAX

    open_set = [(heuristic(start, goal), 0, start, None, None)]  # (f, g, node, parent_state, current_mode)
    came_from = {}
    g_score = {(start, None): 0}

    while open_set:
        f, g, current, parent_state, current_mode = heapq.heappop(open_set)
        state = (current, current_mode)
        if state in came_from:
            continue
        came_from[state] = parent_state

        if current == goal:
            path_states = []
            node_state = state
            while node_state is not None:
                path_states.append(node_state)
                node_state = came_from[node_state]
            path_states.reverse()
            return path_states, g

        for neighbor, cost, mode in graph_local.get(current, []):
            transfer_cost = 0
            if current_mode is not None and mode != current_mode:
                transfer_cost = TRANSFER_PENALTY
            tentative_g = g + cost + transfer_cost
            neighbor_state = (neighbor, mode)
            if neighbor_state in g_score and tentative_g >= g_score[neighbor_state]:
                continue
            g_score[neighbor_state] = tentative_g
            heapq.heappush(open_set, (tentative_g + heuristic(neighbor, goal), tentative_g, neighbor, state, mode))

    return None, None


def build_itinerary_from_path(path_states, coords_map):
    """Return route (names), segments (per-edge), steps (coalesced), total_time_s, total_stops."""
    if not path_states:
        return [], [], [], 0, 0

    # raw edges
    raw = []
    total_time = 0.0
    total_stops = 0
    for i in range(1, len(path_states)):
        frm = path_states[i - 1][0]
        to = path_states[i][0]
        mode = path_states[i][1]
        a = coords_map.get(frm)
        b = coords_map.get(to)
        dist = haversine_meters(a, b) if a and b else 0
        if mode == 'walk':
            dur = dist / WALK_SPEED
        else:
            dur = dist / SUBWAY_SPEED + STOP_PENALTY
            if mode == 'subway':
                total_stops += 1
        raw.append({'from': frm, 'to': to, 'mode': mode or 'walk', 'duration': dur, 'distance': dist})
        total_time += dur

        # if next edge changes mode, insert transfer penalty as its own raw item
        if i + 1 < len(path_states):
            next_mode = path_states[i + 1][1]
            if next_mode is not None and next_mode != mode:
                raw.append({'from': to, 'to': to, 'mode': 'transfer', 'duration': TRANSFER_PENALTY, 'distance': 0})
                total_time += TRANSFER_PENALTY

    # coalesce raw into steps
    steps = []
    segs = []
    i = 0
    while i < len(raw):
        r = raw[i]
        segs.append({'from': r['from'], 'to': r['to'], 'mode': r['mode'], 'duration_seconds': int(round(r['duration']))})
        if r['mode'] == 'walk':
            # accumulate consecutive walk
            dur = r['duration']
            dist = r['distance']
            j = i + 1
            while j < len(raw) and raw[j]['mode'] == 'walk':
                dur += raw[j]['duration']
                dist += raw[j]['distance']
                segs.append({'from': raw[j]['from'], 'to': raw[j]['to'], 'mode': 'walk', 'duration_seconds': int(round(raw[j]['duration']))})
                j += 1
            steps.append({'kind': 'walk', 'description': 'Walk', 'duration_s': int(round(dur)), 'distance_m': int(round(dist)), 'line_id': None})
            i = j
            continue

        if r['mode'] == 'subway' or r['mode'] == 'ride':
            # accumulate consecutive subway rides
            dur = r['duration']
            dist = r['distance']
            j = i + 1
            while j < len(raw) and raw[j]['mode'] == 'subway':
                dur += raw[j]['duration']
                dist += raw[j]['distance']
                segs.append({'from': raw[j]['from'], 'to': raw[j]['to'], 'mode': 'subway', 'duration_seconds': int(round(raw[j]['duration']))})
                j += 1
            steps.append({'kind': 'ride', 'description': 'Take subway', 'duration_s': int(round(dur)), 'distance_m': int(round(dist)), 'line_id': None})
            i = j
            continue

        if r['mode'] == 'transfer':
            steps.append({'kind': 'transfer', 'description': 'Transfer', 'duration_s': int(round(r['duration'])), 'distance_m': 0, 'line_id': None})
            i += 1
            continue

        # fallback: single-edge step
        steps.append({'kind': r['mode'], 'description': r['mode'].capitalize(), 'duration_s': int(round(r['duration'])), 'distance_m': int(round(r['distance'])), 'line_id': None})
        i += 1

    def is_station_node(node: str) -> bool:
        return node not in ('__start', '__end') and not node.startswith('GRID_')

    route = [node for node, _ in path_states if is_station_node(node)]
    return route, segs, steps, int(round(total_time)), total_stops


@app.post("/api/path")
def get_path(request: PathRequest = Body(...)):
    # Support two shapes: {start_station, end_station} or {lat_start,lng_start,lat_end,lng_end}
    if request.start_station and request.end_station:
        start = request.start_station
        end = request.end_station
        if start == end:
            return {"status": "success", "route": [start], "segments": [], "total_stops": 0, "estimated_time_seconds": 0}

        path_states, total_time = a_star_graph(graph, NODE_COORDS, start, end)
        if path_states is None:
            return {"status": "error", "message": "No route found"}

        route, segments, steps, total_time_s, subway_stops = build_itinerary_from_path(path_states, STATION_COORDS)
        return {
            "status": "success",
            "route": route,
            "segments": segments,
            "steps": steps,
            "total_stops": subway_stops,
            "estimated_time_seconds": total_time_s,
        }

    # coordinate-based request: build a temporary overlay with virtual endpoints
    if (
        request.lat_start is not None
        and request.lng_start is not None
        and request.lat_end is not None
        and request.lng_end is not None
    ):
        lat_s = request.lat_start
        lng_s = request.lng_start
        lat_e = request.lat_end
        lng_e = request.lng_end

        # local copy of graph and coords
        local_graph = {k: list(v) for k, v in graph.items()}
        coords_map = dict(NODE_COORDS)

        # add virtual nodes
        START_KEY = "__start"
        END_KEY = "__end"
        coords_map[START_KEY] = (lat_s, lng_s)
        coords_map[END_KEY] = (lat_e, lng_e)
        local_graph[START_KEY] = []
        local_graph[END_KEY] = []

        # helper: find up to K nearest graph nodes within R meters
        def nearest_nodes(lat, lng, k=3, r=150):
            results = []
            if NODE_TREE is not None:
                try:
                    dists, idxs = NODE_TREE.query((lat, lng), k=min(k, len(NODE_COORD_LIST)))
                    if isinstance(idxs, int):
                        idxs = [idxs]
                        dists = [dists]
                    for d, ix in zip(dists, idxs):
                        name = NODE_NAMES[int(ix)]
                        dist_m = haversine_meters((lat, lng), NODE_COORD_LIST[int(ix)])
                        if dist_m <= r:
                            results.append((name, dist_m))
                except Exception:
                    pass
            # fallback linear scan
            if not results:
                for name, coords in NODE_COORDS.items():
                    dist_m = haversine_meters((lat, lng), coords)
                    if dist_m <= r:
                        results.append((name, dist_m))
                results.sort(key=lambda x: x[1])
                results = results[:k]
            return results

        s_nearest = nearest_nodes(lat_s, lng_s)
        e_nearest = nearest_nodes(lat_e, lng_e)

        # if no station within radius, still attach to the absolute nearest (no radius)
        if not s_nearest:
            # find absolute nearest
            best = None
            best_d = float('inf')
            for name, coords in STATION_COORDS.items():
                d = haversine_meters((lat_s, lng_s), coords)
                if d < best_d:
                    best_d = d
                    best = name
            s_nearest = [(best, best_d)] if best else []
        if not e_nearest:
            best = None
            best_d = float('inf')
            for name, coords in STATION_COORDS.items():
                d = haversine_meters((lat_e, lng_e), coords)
                if d < best_d:
                    best_d = d
                    best = name
            e_nearest = [(best, best_d)] if best else []

        # connect virtual start to its nearest stations (directed)
        for name, d_m in s_nearest:
            t = d_m / WALK_SPEED
            local_graph[START_KEY].append((name, t, 'walk'))

        # connect nearest stations to virtual end (directed)
        for name, d_m in e_nearest:
            t = d_m / WALK_SPEED
            local_graph.setdefault(name, []).append((END_KEY, t, 'walk'))

        # run A* on local graph
        path_states, total_time = a_star_graph(local_graph, coords_map, START_KEY, END_KEY)
        if path_states is None:
            return {"status": "error", "message": "No route found"}

        route, segments, steps, total_time_s, subway_stops = build_itinerary_from_path(path_states, coords_map)
        return {
            "status": "success",
            "route": route,
            "segments": segments,
            "steps": steps,
            "total_stops": subway_stops,
            "estimated_time_seconds": total_time_s,
        }

    return {"status": "error", "message": "Invalid request payload"}


@app.get("/api/path")
def get_path_info():
    return {
        "status": "info",
        "message": "POST JSON to /api/path with start_station and end_station. Example: {\"start_station\": \"Schwedenplatz\", \"end_station\": \"Museumsquartier\"}",
    }


@app.get("/")
def root():
    return {
        "status": "ready",
        "message": "FastAPI mock backend is running. Open the frontend and POST /api/path.",
    }


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
