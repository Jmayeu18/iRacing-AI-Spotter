"""
reference_lap.py

Holds the fastest *clean* lap recorded this session as the reference
"ghost" every other lap gets compared against. A lap only becomes (or
replaces) the reference if it was faster than the current one and had
no pit-road time and no yellow/caution flag active at any point during
the lap - matching the same "clean lap" spirit used elsewhere in this
project (see fuel_strategy.py's pit-road exclusion), independently
implemented here since this module doesn't import from that code.
"""

from corner_detector import detect_corners


class ReferenceLap:
    def __init__(self):
        self.lap_time = None
        self.trace = None
        self.corners = None

    def has_reference(self):
        return self.trace is not None

    def consider(self, lap_time, trace):
        """Replace the reference if this lap qualifies (caller has already
        verified the lap was clean: no pit road, no yellow, no off-track,
        no stop). Returns True if it did."""
        if lap_time is None or lap_time <= 0:
            return False
        if self.lap_time is not None and lap_time >= self.lap_time:
            return False

        self.lap_time = lap_time
        self.trace = trace
        self.corners = detect_corners(trace)
        return True

    def reset(self):
        self.lap_time = None
        self.trace = None
        self.corners = None
