"""
server.py

Step 2: exposes live iRacing telemetry as a local JSON API using Flask.

A background thread continuously polls the sim through IRacingClient
and caches the latest snapshot in memory, so HTTP requests are served
instantly from the cache instead of blocking on a shared-memory read.

Security notes:
  - Binds to 127.0.0.1 only, never 0.0.0.0 - the API is not reachable
    from the network, only from this machine (e.g. the overlay page
    running in a local browser or OBS browser source).
  - Read-only: this process never sends inputs/commands to iRacing,
    it only relays what IRacingClient reads.

Usage:
    python server.py
"""

import threading
import time

from flask import Flask, jsonify
from flask_cors import CORS

from fuel_strategy import FuelStrategy
from irsdk_client import IRacingClient

HOST = "127.0.0.1"
PORT = 5000
POLL_HZ = 30  # sim read rate; independent of how often the overlay fetches

app = Flask(__name__)
CORS(app)  # lets the overlay page (opened as a file:// or different port) fetch this API

_client = IRacingClient()
_fuel_strategy = FuelStrategy()
_latest = {"connected": False}
_lock = threading.Lock()


def _poll_loop():
    """Continuously refresh the cached telemetry snapshot in the background."""
    period = 1.0 / POLL_HZ
    global _latest
    was_connected = False
    while True:
        data = _client.get_telemetry()

        if data is None:
            was_connected = False
            _fuel_strategy.reset()
            with _lock:
                _latest = {"connected": False}
        else:
            if not was_connected:
                # Sim just (re)connected - old fuel-per-lap history is from a
                # different session/car, so drop it and start fresh.
                _fuel_strategy.reset()
            was_connected = True

            flags = data["flags"]
            is_caution = flags["caution"] or flags["caution_waving"] or flags["yellow"] or flags["yellow_waving"]
            fuel_liters = data["fuel"]["level_liters"]

            _fuel_strategy.update(
                data["lap"]["current_lap"], fuel_liters, is_caution, data["on_pit_road"]
            )
            data["fuel_strategy"] = _fuel_strategy.estimate(
                fuel_liters, data["session"]["laps_remain"], is_caution
            )

            with _lock:
                _latest = data

        time.sleep(period)


@app.route("/telemetry")
def telemetry():
    """Return the most recently polled telemetry snapshot as JSON."""
    with _lock:
        return jsonify(_latest)


@app.route("/")
def index():
    return jsonify({"status": "ok", "endpoint": "/telemetry"})


def main():
    poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    poll_thread.start()
    print(f"Serving telemetry at http://{HOST}:{PORT}/telemetry")
    app.run(host=HOST, port=PORT)


if __name__ == "__main__":
    main()
