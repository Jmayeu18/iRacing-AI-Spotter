"""
lap_analyzer.py

Buffers telemetry samples for the lap currently in progress. When the
lap counter increments, the finished lap either:
  - becomes the new reference lap (if it was clean and faster than the
    current reference), or
  - gets compared against the existing reference, corner by corner:
    turn-in point, braking point, minimum corner speed, and throttle
    application point, each reported as a delta.

This module only produces structured result dicts - it doesn't format
anything for a human. run_coaching_logger.py turns those into
console/file output; a future voice layer would consume the same
structure for callouts.
"""

from corner_detector import STEER_ENTER
from reference_lap import ReferenceLap

BRAKE_THRESHOLD = 0.05
LIFT_THRESHOLD = 0.95  # throttle below this counts as "lifting" when no brake is used
THROTTLE_THRESHOLD = 0.80
SEARCH_MARGIN_PCT = 0.04  # how far around the reference corner boundaries we search
MPS_TO_MPH = 2.23694

# Below this, the car isn't cornering slowly - it's stopped/parked on
# track (e.g. exiting the session). ~10 mph, safely under any real
# racing speed even in a slow corner, so it won't false-positive.
STOPPED_SPEED_MPS = 4.47

OFF_TRACK_SURFACE = 0  # irsdk_TrkLoc.OffTrack


class LapAnalyzer:
    def __init__(self, track_length_feet=None):
        self.reference = ReferenceLap()
        self.track_length_feet = track_length_feet
        self._current_lap = None
        self._buffer = []
        self._saw_pit_or_yellow = False
        self._saw_stop = False
        self._saw_off_track = False

    def reset(self):
        """Call when a new session/car is detected - old data doesn't apply."""
        self.reference.reset()
        self._current_lap = None
        self._buffer = []
        self._saw_pit_or_yellow = False
        self._saw_stop = False
        self._saw_off_track = False

    def add_sample(self, sample):
        """Feed one telemetry tick in. Returns a result dict when a lap
        just completed, else None."""
        lap = sample["lap"]
        if lap is None or sample["lap_dist_pct"] is None:
            return None

        if self._current_lap is None:
            self._current_lap = lap
            self._buffer = [sample]
            self._reset_lap_flags(sample)
            return None

        if lap != self._current_lap:
            result = self._finish_lap(self._current_lap, self._buffer, sample["last_lap_time"])
            self._current_lap = lap
            self._buffer = [sample]
            self._reset_lap_flags(sample)
            return result

        self._update_lap_flags(sample)
        self._buffer.append(sample)
        return None

    def _reset_lap_flags(self, sample):
        self._saw_pit_or_yellow = False
        self._saw_stop = False
        self._saw_off_track = False
        self._update_lap_flags(sample)

    def _update_lap_flags(self, sample):
        if sample["on_pit_road"] or sample["under_yellow"]:
            self._saw_pit_or_yellow = True
        # Pit road naturally involves near-zero speed at the pit stall -
        # only count a "stop" as suspicious when it happens out on track.
        if not sample["on_pit_road"] and sample["speed"] is not None and sample["speed"] < STOPPED_SPEED_MPS:
            self._saw_stop = True
        if not sample["on_pit_road"] and sample["track_surface"] == OFF_TRACK_SURFACE:
            self._saw_off_track = True

    def _finish_lap(self, lap_number, trace, lap_time):
        if len(trace) < 10:
            return {"lap": lap_number, "status": "too_short"}

        if self._saw_pit_or_yellow or self._saw_stop:
            reason = "stopped_on_track" if self._saw_stop else "pit_or_yellow"
            return {"lap": lap_number, "status": "skipped", "reason": reason, "lap_time": lap_time}

        # Off-track excursions are excluded from *becoming* the reference
        # (it has to be a clean line to be worth chasing) but still get
        # compared and logged - flagged as low-confidence rather than
        # silently dropped, since a messy-but-legal lap is still useful
        # to see, just not to trust as precisely as a clean one.
        if not self._saw_off_track and self.reference.consider(lap_time, trace):
            return {
                "lap": lap_number,
                "status": "new_reference",
                "lap_time": lap_time,
                "corners": self.reference.corners,
            }

        if not self.reference.has_reference():
            return {"lap": lap_number, "status": "no_reference_yet", "off_track": self._saw_off_track}

        return {
            "lap": lap_number,
            "status": "compared",
            "off_track": self._saw_off_track,
            "lap_time": lap_time,
            "reference_lap_time": self.reference.lap_time,
            "corners": self._compare_to_reference(trace),
        }

    def _compare_to_reference(self, trace):
        results = []
        for corner in self.reference.corners:
            current = _measure_corner(trace, corner, SEARCH_MARGIN_PCT)
            reference = _measure_corner(self.reference.trace, corner, SEARCH_MARGIN_PCT)
            results.append(_diff_corner(corner["index"], current, reference, self.track_length_feet))
        return results


def _measure_corner(trace, corner, margin):
    lo = max(0.0, corner["entry_pct"] - margin)
    hi = min(1.0, corner["exit_pct"] + margin)
    window = [s for s in trace if lo <= s["lap_dist_pct"] <= hi]
    if not window:
        return None

    # Brake/throttle points are split on the *reference* corner's apex
    # position - fixed for both laps being compared - rather than each
    # lap's own re-detected minimum-speed point. On ovals, drivers often
    # carry partial throttle through a long sweeper instead of fully
    # lifting, so a per-lap apex can land too early and starve the
    # "before apex" half of any samples, making brake always look
    # missing and throttle always look artificially early.
    split_pct = corner["apex_pct"]

    turn_in = next((s for s in window if abs(s["steering"] or 0.0) > STEER_ENTER), window[0])
    speeds = [s["speed"] for s in window if s["speed"] is not None]
    min_speed = min(speeds) if speeds else None

    brake_point = next(
        (s for s in window if s["lap_dist_pct"] <= split_pct and (s["brake"] or 0) > BRAKE_THRESHOLD),
        None,
    )
    if brake_point is None:
        brake_point = next(
            (s for s in window if s["lap_dist_pct"] <= split_pct and (s["throttle"] or 0) < LIFT_THRESHOLD),
            None,
        )

    throttle_point = next(
        (s for s in window if s["lap_dist_pct"] >= split_pct and (s["throttle"] or 0) > THROTTLE_THRESHOLD),
        None,
    )

    return {
        "turn_in_pct": turn_in["lap_dist_pct"],
        "brake_pct": brake_point["lap_dist_pct"] if brake_point else None,
        "min_speed": min_speed,
        "throttle_pct": throttle_point["lap_dist_pct"] if throttle_point else None,
    }


def _diff_corner(index, current, reference, track_length_feet):
    if current is None or reference is None:
        return {"index": index, "status": "no_data"}

    def pct_delta(cur_pct, ref_pct):
        if cur_pct is None or ref_pct is None:
            return None
        delta_pct = cur_pct - ref_pct
        return delta_pct * track_length_feet if track_length_feet else delta_pct * 100

    speed_delta_mph = None
    if current["min_speed"] is not None and reference["min_speed"] is not None:
        speed_delta_mph = (current["min_speed"] - reference["min_speed"]) * MPS_TO_MPH

    return {
        "index": index,
        "status": "ok",
        "unit": "feet" if track_length_feet else "pct_lap",
        "turn_in_delta": pct_delta(current["turn_in_pct"], reference["turn_in_pct"]),
        "brake_delta": pct_delta(current["brake_pct"], reference["brake_pct"]),
        "min_speed_delta_mph": speed_delta_mph,
        "throttle_delta": pct_delta(current["throttle_pct"], reference["throttle_pct"]),
    }
