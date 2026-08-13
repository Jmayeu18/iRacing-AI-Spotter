"""
run_coaching_logger.py

Phase 1 of AI race coaching: standalone script that connects to
iRacing, auto-detects corners from your own driving, tracks your
fastest clean lap as a reference, and logs per-corner deltas (turn-in
point, braking point, minimum corner speed, throttle application
point) after every subsequent lap - to the console and to a log file -
so the detection/comparison logic can be checked for accuracy before
any voice output is layered on top.

This is a separate, standalone tool from server.py / print_telemetry.py
and does not touch the fuel/tire spotter code at all.

Usage:
    python run_coaching_logger.py
"""

import datetime
import time
from pathlib import Path

from lap_analyzer import LapAnalyzer
from telemetry_reader import CoachingTelemetryReader

POLL_HZ = 30
LOG_DIR = Path(__file__).parent / "logs"


def _open_log_file():
    LOG_DIR.mkdir(exist_ok=True)
    name = f"coaching_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
    return open(LOG_DIR / name, "w", encoding="utf-8")


def _log(log_file, message):
    print(message)
    log_file.write(message + "\n")
    log_file.flush()


def _format_delta(value, unit):
    if value is None:
        return "n/a"
    label = "later" if value > 0 else "earlier"
    if unit == "feet":
        return f"{abs(value):.1f} ft {label}"
    return f"{abs(value):.2f}% of lap {label}"


def _log_result(log_file, result):
    lap = result["lap"]
    status = result["status"]

    if status == "too_short":
        _log(log_file, f"Lap {lap}: too few samples, skipped.")

    elif status == "new_reference":
        corner_list = ", ".join(
            f"C{c['index']} (entry {c['entry_pct']:.3f} / apex {c['apex_pct']:.3f} / exit {c['exit_pct']:.3f})"
            for c in result["corners"]
        )
        _log(
            log_file,
            f"Lap {lap}: NEW REFERENCE LAP - {result['lap_time']:.3f}s, "
            f"{len(result['corners'])} corners detected: {corner_list}",
        )

    elif status == "no_reference_yet":
        note = " (off-track, won't be used as reference)" if result["off_track"] else ""
        _log(log_file, f"Lap {lap}: no reference yet{note}, waiting for a clean fast lap.")

    elif status == "skipped":
        reason_txt = {
            "stopped_on_track": "car stopped on track mid-lap (not pit road)",
            "pit_or_yellow": "pit road / yellow flag",
        }.get(result["reason"], result["reason"])
        _log(log_file, f"Lap {lap}: {result['lap_time']:.3f}s - excluded ({reason_txt}).")

    elif status == "compared":
        gap = result["lap_time"] - result["reference_lap_time"]
        flag = "  [OFF-TRACK - low confidence]" if result["off_track"] else ""
        _log(
            log_file,
            f"Lap {lap}: {result['lap_time']:.3f}s (ref {result['reference_lap_time']:.3f}s, {gap:+.3f}s){flag}",
        )
        for c in result["corners"]:
            if c["status"] != "ok":
                _log(log_file, f"  Corner {c['index']}: no data")
                continue
            unit = c["unit"]
            speed_txt = "n/a" if c["min_speed_delta_mph"] is None else f"{c['min_speed_delta_mph']:+.1f} mph"
            _log(
                log_file,
                f"  Corner {c['index']}: turn-in {_format_delta(c['turn_in_delta'], unit)}, "
                f"brake {_format_delta(c['brake_delta'], unit)}, "
                f"min speed {speed_txt}, "
                f"throttle {_format_delta(c['throttle_delta'], unit)}",
            )


def main():
    reader = CoachingTelemetryReader()
    log_file = _open_log_file()
    analyzer = None
    was_connected = False

    _log(log_file, "Waiting for iRacing...")
    try:
        while True:
            sample = reader.read()

            if sample is None:
                if was_connected:
                    _log(log_file, "Disconnected from iRacing.")
                was_connected = False
                time.sleep(1)
                continue

            if not was_connected:
                _log(log_file, "Connected. Building corner map from your driving...")
                analyzer = LapAnalyzer(track_length_feet=reader.track_length_feet())
                was_connected = True

            result = analyzer.add_sample(sample)
            if result is not None:
                _log_result(log_file, result)

            time.sleep(1.0 / POLL_HZ)
    except KeyboardInterrupt:
        _log(log_file, "Stopping.")
    finally:
        reader.close()
        log_file.close()


if __name__ == "__main__":
    main()
