"""
corner_detector.py

Auto-detects corner entry/apex/exit zones on the current track purely
from a lap's own telemetry trace - no per-track configuration needed.

A "corner" is a contiguous stretch of the lap where the (smoothed)
steering wheel angle is turned past STEER_ENTER; the apex is the
slowest point in that stretch. Two refinements keep this stable
lap-to-lap, which raw single-sample thresholding was not:

  - The steering signal is smoothed (rolling average) before
    thresholding, so a brief wheel correction on the straights can't
    flicker a zone open.
  - Hysteresis: a zone starts once steering exceeds STEER_ENTER but
    only ends once it drops below the lower STEER_EXIT, and zones
    separated by a gap shorter than MIN_GAP_PCT get bridged into one -
    both needed because long, continuous oval sweepers (e.g. a
    quad-oval's turn 1-2 complex) can dip briefly near zero mid-corner
    without the driver actually straightening out.

This finds however many zones the track actually has (typically 2 or
4 on an oval) rather than assuming a fixed corner count.
"""

import statistics

STEER_ENTER = 0.08  # radians (~4.6 degrees) - zone starts once past this
STEER_EXIT = 0.03  # radians (~1.7 degrees) - zone only ends once back under this
SMOOTH_WINDOW = 9  # samples (~0.3s at 30Hz) - centered moving average on steering
MIN_GAP_PCT = 0.015  # bridge zones separated by less than this (noise, not a real straight)
MIN_ZONE_PCT = 0.02  # discard zones shorter than this after merging


def detect_corners(trace):
    """trace: list of samples (dicts with lap_dist_pct/steering/speed),
    sorted by lap_dist_pct ascending, covering one full lap.

    Returns a list of {index, entry_pct, apex_pct, exit_pct} dicts in
    lap order (index starting at 1)."""
    if len(trace) < SMOOTH_WINDOW * 2:
        return []

    trace = _rotate_to_straight(trace)
    smoothed = _smooth_steering(trace, SMOOTH_WINDOW)

    zones = _hysteresis_zones(trace, smoothed)
    zones = _merge_close_zones(zones, MIN_GAP_PCT)
    zones = [z for z in zones if _zone_span(z) >= MIN_ZONE_PCT]

    corners = []
    for zone in zones:
        apex = min(zone, key=lambda s: s["speed"] if s["speed"] is not None else float("inf"))
        corners.append(
            {
                "index": len(corners) + 1,
                "entry_pct": zone[0]["lap_dist_pct"],
                "apex_pct": apex["lap_dist_pct"],
                "exit_pct": zone[-1]["lap_dist_pct"],
            }
        )
    return corners


def _rotate_to_straight(trace):
    """Rotate the trace to start at a point where the car is going
    straight, so corner zones never wrap across the lap_dist_pct 0/1
    seam and a simple linear scan works."""
    straight_idx = next(
        (i for i, s in enumerate(trace) if abs(s["steering"] or 0.0) <= STEER_EXIT),
        None,
    )
    if straight_idx is None:
        return trace
    return trace[straight_idx:] + trace[:straight_idx]


def _smooth_steering(trace, window):
    """Centered moving average of signed steering angle (averaged signed,
    then thresholds take abs() - so genuine oscillation actually cancels
    out, unlike averaging the absolute value would)."""
    values = [s["steering"] or 0.0 for s in trace]
    half = window // 2
    n = len(values)
    return [statistics.fmean(values[max(0, i - half) : min(n, i + half + 1)]) for i in range(n)]


def _hysteresis_zones(trace, smoothed):
    zones = []
    current = None
    for sample, steer in zip(trace, smoothed):
        magnitude = abs(steer)
        if current is None:
            if magnitude > STEER_ENTER:
                current = [sample]
        elif magnitude < STEER_EXIT:
            zones.append(current)
            current = None
        else:
            current.append(sample)
    if current:
        zones.append(current)
    return zones


def _merge_close_zones(zones, min_gap_pct):
    if not zones:
        return zones
    merged = [zones[0]]
    for zone in zones[1:]:
        gap = zone[0]["lap_dist_pct"] - merged[-1][-1]["lap_dist_pct"]
        if gap < min_gap_pct:
            merged[-1].extend(zone)
        else:
            merged.append(zone)
    return merged


def _zone_span(zone):
    return zone[-1]["lap_dist_pct"] - zone[0]["lap_dist_pct"]
