"""
print_telemetry.py

Step 1: standalone script that connects to a running iRacing session
via pyirsdk and prints lap times, remaining fuel, tire temps, and
active flags to the console once per second.

Usage:
    python print_telemetry.py

Requires iRacing to be running (any session - practice, race, or even
the replay/test drive from the sim's main menu works).
"""

import time

from irsdk_client import IRacingClient

POLL_SECONDS = 1.0


def fnum(value, fmt="{:.1f}"):
    """Format a possibly-None telemetry value for display."""
    return fmt.format(value) if value is not None else "N/A"


def format_flags(flags):
    active = [name for name, on in flags.items() if on]
    return ", ".join(active) if active else "none"


def print_snapshot(data):
    lap = data["lap"]
    fuel = data["fuel"]
    tires = data["tires"]

    print("-" * 60)
    print(
        f"Lap {lap['current_lap']}  |  "
        f"Last: {fnum(lap['last_lap_time'], '{:.3f}s')}  |  "
        f"Best: {fnum(lap['best_lap_time'], '{:.3f}s')}"
    )
    fuel_pct = fuel["level_pct"]
    print(
        f"Fuel: {fnum(fuel_pct * 100 if fuel_pct is not None else None)}%  "
        f"({fnum(fuel['level_liters'], '{:.2f}')} L)"
    )
    print(
        "Tire temps (avg, C): "
        f"LF {fnum(tires['lf']['avg'])}  RF {fnum(tires['rf']['avg'])}  "
        f"LR {fnum(tires['lr']['avg'])}  RR {fnum(tires['rr']['avg'])}"
    )
    print(f"Flags: {format_flags(data['flags'])}")


def main():
    client = IRacingClient()
    print("Waiting for iRacing... (start the sim and join a session)")

    try:
        while True:
            data = client.get_telemetry()
            if data is None:
                print("Not connected to iRacing.")
            else:
                print_snapshot(data)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
