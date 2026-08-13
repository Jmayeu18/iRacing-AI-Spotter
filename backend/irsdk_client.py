"""
irsdk_client.py

Read-only wrapper around pyirsdk for pulling live telemetry out of
iRacing's shared-memory interface (the same interface the in-sim HUD
and official broadcast tools use).

Security note: this module only ever *reads* from the SDK. It never
touches irsdk's camera/chat/pit-command/broadcast methods, so it has
no ability to control the sim, only observe it. Keep it that way -
don't add write/command calls here.
"""

import irsdk


# Bit flags from iRacing's irsdk_Flags enum (see pyirsdk's irsdk/__init__.py
# for the authoritative list). Only the subset relevant to an oval-race
# overlay is decoded here.
FLAG_BITS = {
    "checkered": 0x00000001,
    "white": 0x00000002,
    "green": 0x00000004,
    "yellow": 0x00000008,
    "red": 0x00000010,
    "blue": 0x00000020,
    "debris": 0x00000040,
    "crossed": 0x00000080,
    "yellow_waving": 0x00000100,
    "one_lap_to_green": 0x00000200,
    "green_held": 0x00000400,
    "ten_to_go": 0x00000800,
    "five_to_go": 0x00001000,
    "random_waving": 0x00002000,
    "caution": 0x00004000,
    "caution_waving": 0x00008000,
}

# Tire temp channels pyirsdk exposes per corner: cold/left, middle, hot/right
# across the tread. Averaging the three gives one glanceable number per corner.
#
# NOTE: iRacing only refreshes these values when you pit or exit the car -
# not continuously while on track. This is a deliberate restriction on
# iRacing's end (mirrors real-world tire checks happening back in the pits,
# and limits telemetry data available for cheating tools), not a bug in
# this client. Sims like ACC/AMS2 expose live tire temps; iRacing does not.
TIRE_CORNERS = {
    "lf": ("LFtempCL", "LFtempCM", "LFtempCR"),
    "rf": ("RFtempCL", "RFtempCM", "RFtempCR"),
    "lr": ("LRtempCL", "LRtempCM", "LRtempCR"),
    "rr": ("RRtempCL", "RRtempCM", "RRtempCR"),
}


def decode_flags(bits):
    """Turn the SessionFlags bitmask into a dict of {flag_name: bool}."""
    if bits is None:
        return {name: False for name in FLAG_BITS}
    return {name: bool(bits & mask) for name, mask in FLAG_BITS.items()}


class IRacingClient:
    """Thin, read-only wrapper around irsdk.IRSDK().

    Handles connect/reconnect (iRacing may not be running yet, or may
    be closed and reopened between laps of a stream) and exposes a
    single get_telemetry() call that returns a plain, JSON-serializable
    dict so callers never touch the irsdk module directly.
    """

    def __init__(self):
        self._ir = irsdk.IRSDK()
        self._connected = False

    def ensure_connected(self):
        """(Re)connect to the sim's shared memory if needed. Cheap to call every tick."""
        if not self._connected:
            if self._ir.startup():
                self._connected = True
        elif not self._ir.is_initialized or not self._ir.is_connected:
            # iRacing was closed or we lost the shared-memory mapping.
            self._connected = False
            self._ir.shutdown()
        return self._connected

    def get_telemetry(self):
        """Return a JSON-serializable snapshot of current telemetry, or None if not connected."""
        if not self.ensure_connected():
            return None

        ir = self._ir
        lap_last = ir["LapLastLapTime"]
        lap_best = ir["LapBestLapTime"]
        lap_curr = ir["LapCurrentLapTime"]
        fuel_pct = ir["FuelLevelPct"]

        return {
            "connected": True,
            "lap": {
                "current_lap": ir["Lap"],
                "last_lap_time": lap_last,
                "best_lap_time": lap_best,
                "current_lap_time": lap_curr,
            },
            "fuel": {
                "level_pct": fuel_pct if fuel_pct is not None else None,
                "level_liters": ir["FuelLevel"],
            },
            "tires": self._tire_temps(ir),
            "flags": decode_flags(ir["SessionFlags"]),
            "speed_mph": _mps_to_mph(ir["Speed"]),
            "rpm": ir["RPM"],
            "gear": ir["Gear"],
            "on_pit_road": bool(ir["OnPitRoad"]),
            "session": {
                # Laps remaining in the *current* session - for a multi-stage
                # oval race each stage is its own session, so this tracks
                # remaining laps to the end of the stage; in the final stage
                # that's the same as remaining laps to the checkered flag.
                "laps_remain": _clean_laps_remain(ir["SessionLapsRemainEx"] or ir["SessionLapsRemain"]),
            },
        }

    def _tire_temps(self, ir):
        result = {}
        for corner, (left_key, mid_key, right_key) in TIRE_CORNERS.items():
            left, mid, right = ir[left_key], ir[mid_key], ir[right_key]
            result[corner] = {
                "left": left,
                "middle": mid,
                "right": right,
                "avg": _avg(left, mid, right),
            }
        return result

    def close(self):
        if self._connected:
            self._ir.shutdown()
            self._connected = False


def _avg(*vals):
    present = [v for v in vals if v is not None]
    return sum(present) / len(present) if present else None


def _mps_to_mph(speed_mps):
    return speed_mps * 2.23694 if speed_mps is not None else None


# iRacing reports an unlimited/timed session (no fixed lap count) as a huge
# sentinel value rather than None - treat anything absurd as "unknown".
_UNLIMITED_LAPS_SENTINEL = 30000


def _clean_laps_remain(laps_remain):
    if laps_remain is None or laps_remain < 0 or laps_remain >= _UNLIMITED_LAPS_SENTINEL:
        return None
    return laps_remain
