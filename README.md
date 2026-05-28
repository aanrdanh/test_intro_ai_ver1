# Vienna U-Bahn Navigator MVP

This repository contains a frontend-first MVP for a Vienna U-Bahn route finder.

## Project files
- `frontend/` — frontend package containing `index.html`, `styles.css`, and `app.js`
- `backend/` — backend package containing `api.py` and helper scripts
- `requirements.txt` — Python dependencies
- `.venv/` — local virtual environment

## Setup
1. Activate the virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

## Run the MVP
1. Start the backend (from the repository root):
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
   ```
2. Serve the frontend (serve the `frontend` directory):
   ```powershell
   cd frontend
   ..\ .venv\Scripts\python.exe -m http.server 5500
   ```
3. Open the frontend in the browser:
   ```text
   http://127.0.0.1:5500/index.html
   ```

> Do not open `index.html` directly from the filesystem. The page must be served over HTTP so Leaflet assets load correctly.

### Selecting stations on the map
- Use the **Pick start on map** and **Pick end on map** buttons to select stations by clicking their markers.
- After selecting a station, the dropdown will update automatically.

## Verify the API
Test the backend route manually:
```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/path -Method POST -ContentType "application/json" -Body '{"start_station":"Schwedenplatz","end_station":"Museumsquartier"}'
```

Or run the helper script while the backend is running:
```powershell
.\.venv\Scripts\python.exe backend\check_api.py
```

## Notes
- The mock backend returns a hardcoded route for frontend testing.
- The actual pathfinding algorithm will be added after the MVP is confirmed.
# test_intro_ai_ver1
