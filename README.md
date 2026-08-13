# iRacing AI Spotter

A lightweight, local telemetry overlay for iRacing streams. Reads live
data from iRacing's shared-memory SDK, serves it as a small JSON API,
and renders it in a transparent HTML overlay suitable for an OBS
browser source on oval races.

```
iRacing-AI-Spotter/
├── backend/
│   ├── irsdk_client.py     # Read-only wrapper around pyirsdk
│   ├── print_telemetry.py  # Step 1: console printout of live telemetry
│   └── server.py           # Step 2: Flask JSON API on http://127.0.0.1:5000
├── frontend/
│   ├── index.html          # Step 3: overlay markup
│   ├── style.css           # Transparent, glanceable panel styling
│   └── app.js              # Polls the API every 100ms and updates the DOM
├── requirements.txt
└── README.md
```

## Requirements

- Windows with iRacing installed (pyirsdk only works on Windows, since
  it reads iRacing's Windows shared-memory interface)
- Python 3.9+
- iRacing running and in a session (practice, race, or even the
  replay/test drive from the main menu) to have live data to read

## Setup

```powershell
cd "iRacing-AI-Spotter"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running it

**1. Console printout (Step 1 only, no server/UI)**

Prints lap times, fuel, tire temps, and flags to the terminal once per
second - useful for confirming pyirsdk can see the sim before wiring
up anything else.

```powershell
cd backend
python print_telemetry.py
```

**2. JSON API**

Starts the Flask server, which polls the sim in a background thread
and serves the latest snapshot at `http://127.0.0.1:5000/telemetry`.
It binds to localhost only, so it's not reachable from your network.

```powershell
cd backend
python server.py
```

Visit `http://127.0.0.1:5000/telemetry` in a browser to see the raw
JSON while iRacing is running.

**3. Overlay**

With `server.py` running, open `frontend/index.html` directly in a
browser, or add it to OBS as a **Browser Source** pointing at the
file's path (or serve the `frontend/` folder with any static file
server and point OBS at that URL). The page polls the API every
100ms and is transparent everywhere except its panels, so it composites
cleanly over race footage.

Typical OBS Browser Source settings:
- Local file: point at `frontend/index.html`
- Width/Height: match your canvas (e.g. 1920x1080)
- Check "Shutdown source when not visible" off, so it keeps polling

## Data exposed

The `/telemetry` JSON payload includes:

- `lap`: current lap number, last lap time, best lap time, current lap time
- `fuel`: fuel level as a percentage and in liters
- `tires`: per-corner (LF/RF/LR/RR) left/middle/right tread temps and their average
- `flags`: booleans for green, yellow, caution, red, white, checkered, etc.
- `speed_mph`, `rpm`, `gear` as extra context

When iRacing isn't running or you're not in a session, the API returns
`{"connected": false}` and the overlay dims itself rather than showing
stale numbers.

**Tire temps only refresh on pit stops / exiting the car.** This is a
deliberate iRacing SDK limitation, not a bug here - iRacing only pushes
fresh `LFtempCL/CM/CR`-style carcass temps at those moments (mirroring
real-world tire checks happening back in the pits, and limiting the
telemetry surface available to cheat tools). They will not visibly
change lap-to-lap while you're out on track. Other sims (ACC, AMS2)
expose live tire temps; iRacing does not.

## Notes on security

`irsdk_client.py` only ever *reads* from the SDK - it never calls any
of pyirsdk's input, camera, or broadcast/command methods, so this tool
has no ability to control the sim, only observe it. The Flask server
binds to `127.0.0.1` so the API is local-only by default.
