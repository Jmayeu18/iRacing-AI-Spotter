"""
telemetry_reader.py

Standalone, read-only connection to iRacing's SDK for the AI coaching
module. Deliberately separate from irsdk_client.py (used by the
fuel/tire spotter) so this feature can be built and iterated on
without touching that code at all - it opens its own shared-memory
handle via pyirsdk, same as any other reader.

Security note: read-only, same as irsdk_client.py - never calls any
input/command/broadcast methods.
"""

import irsdk

# SessionFlags bits that mean "not a clean lap" for reference/comparison
# purposes: red, yellow, yellow_waving, caution, caution_waving.
_YELLOW_BITS = 0x00000010 | 0x00000008 | 0x00000100 | 0x00004000 | 0x00008000


class CoachingTelemetryReader:
    """Thin, read-only wrapper around irsdk.IRSDK() for the coaching module."""

    def __init__(self):
        self._ir = irsdk.IRSDK()
        self._connected = False

    def ensure_connected(self):
        if not self._connected:
            if self._ir.startup():
                self._connected = True
        elif not self._ir.is_initialized or not self._ir.is_connected:
            self._connected = False
            self._ir.shutdown()
        return self._connected

    def read(self):
        """Return one telemetry sample dict, or None if not connected."""
        if not self.ensure_connected():
            return None

        ir = self._ir
        flags = ir["SessionFlags"] or 0

        return {
            "lap": ir["Lap"],
            "lap_dist_pct": ir["LapDistPct"],
            "last_lap_time": ir["LapLastLapTime"],
            "speed": ir["Speed"],
            "brake": ir["Brake"],
            "throttle": ir["Throttle"],
            "steering": ir["SteeringWheelAngle"],
            "on_pit_road": bool(ir["OnPitRoad"]),
            "under_yellow": bool(flags & _YELLOW_BITS),
            # irsdk_TrkLoc enum: -1 NotInWorld, 0 OffTrack, 1 InPitStall,
            # 2 ApproachingPits, 3 OnTrack.
            "track_surface": ir["PlayerTrackSurface"],
        }

    def track_length_feet(self):
        """Best-effort track length in feet, from session info. None if unavailable."""
        try:
            weekend = self._ir["WeekendInfo"]
            return _parse_track_length(weekend.get("TrackLength")) if weekend else None
        except Exception:
            return None

    def close(self):
        if self._connected:
            self._ir.shutdown()
            self._connected = False


def _parse_track_length(text):
    """Parse strings like '2.4600 km' or '1.366 mi' into feet."""
    if not text:
        return None
    try:
        value_str, unit = text.strip().split()
        value = float(value_str)
    except (ValueError, AttributeError):
        return None
    unit = unit.lower()
    if unit.startswith("km"):
        return value * 3280.84
    if unit.startswith("mi"):
        return value * 5280.0
    return None
