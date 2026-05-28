# Minimum Viable Product (MVP): Vienna U-Bahn Navigator

## 1. Project Overview
A web-based pathfinding application that calculates the optimal route between two stations on the Vienna U-Bahn network. This MVP utilizes a **Frontend-First** development approach, allowing the user interface to be built and tested via a mock API while the backend team develops the core Artificial Intelligence search algorithms (like A* for the IT3160 project).

## 2. Core MVP Features
For the initial MVP, we will restrict the scope to ensure a rapid, functional prototype.

* **Simplified Map:** A smaller graph utilizing 5-10 central Vienna stations (e.g., Stephansplatz, Karlsplatz, Schwedenplatz) instead of the entire network.
* **Interactive Frontend:** An interactive Leaflet.js map where users can visualize the stations.
* **Mock API Integration:** A FastAPI backend that returns a hardcoded, predefined JSON route to immediately unblock frontend development.
* **Basic Routing UI:** Two dropdown menus for selecting the "Start" and "End" stations, and a "Find Route" button that draws a polyline on the map.

## 3. Tech Stack (MVP Phase)
* **Frontend:** Vanilla JavaScript, HTML5, CSS3.
* **Map Library:** Leaflet.js (loaded via CDN) using OpenStreetMap tiles.
* **Backend / API:** Python 3.11+, FastAPI, Uvicorn (initially running mock endpoints).
* **AI Algorithm (Pending Backend Team):** A* Search with a great-circle distance heuristic (haversine formula).

## 4. The API Contract (Crucial for MVP)
To ensure the frontend and backend connect seamlessly once both are finished, both teams agree to the following JSON structure for the `/api/path` endpoint.

**Request (Frontend -> Backend):**
` ` `json
{
  "start_station": "Schwedenplatz",
  "end_station": "Museumsquartier"
}
` ` `

**Response (Backend -> Frontend):**
` ` `json
{
  "status": "success",
  "route": ["Schwedenplatz", "Stephansplatz", "Karlsplatz", "Museumsquartier"],
  "total_stops": 3,
  "estimated_time_seconds": 360
}
` ` `

## 5. MVP Development Milestones

### Milestone 1: The "Dummy" API (Backend Mock)
- [ ] Setup a basic FastAPI application (`api.py`).
- [ ] Implement CORS middleware to allow localhost frontend requests.
- [ ] Create the `/api/path` endpoint to return the hardcoded JSON contract above.
- [ ] Run the server locally using Uvicorn.

### Milestone 2: Frontend Skeleton & Map
- [ ] Create `index.html` with the basic UI layout (Start dropdown, End dropdown, Submit button).
- [ ] Import Leaflet.js and render a map centered on Vienna coordinates (`[48.2082, 16.3738]`).
- [ ] Hardcode the coordinates of the 5 MVP stations and plot them as markers on the Leaflet map.

### Milestone 3: Connecting the Pieces
- [ ] Write an asynchronous JavaScript `fetch()` function triggered by the "Find Route" button.
- [ ] Send the selected stations to the FastAPI mock endpoint.
- [ ] Parse the returned JSON response.
- [ ] Use Leaflet's `L.polyline` to draw a line connecting the stations returned in the `route` array.

## 6. Implementation Plan
This plan covers the first development cycle for the MVP:
1. Build the frontend UI with two dropdowns for the start and end stations, a Find Route button, and a Leaflet map centered on Vienna.
2. Hardcode the coordinates for the 5 MVP stations and place markers for each on the Leaflet map.
3. Create a mock FastAPI backend with `/api/path` that returns the agreed JSON route format.
4. Connect the frontend to the backend using a POST request and render the returned route as a polyline.
5. Verify the MVP by running the backend locally and serving `index.html` from a local static server, then confirm the route renders correctly on the map.

### Run commands
- Install dependencies: `.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Start backend: `.venv\Scripts\python.exe -m uvicorn api:app --reload --host 127.0.0.1 --port 8000`
- Start frontend server: `.venv\Scripts\python.exe -m http.server 5500`
- Open in browser: `http://127.0.0.1:5500/index.html`

## 7. Post-MVP (Handoff)
Once the MVP is functional:
1. The backend team replaces the "dummy" data in FastAPI with the actual Python A* algorithm.
2. Expand the station dataset from the 5 MVP stations to the full Vienna U-Bahn GTFS/OSM dataset.
3. Introduce edge weights (transfer penalties, walking times) as defined in the original IT3160 requirements.