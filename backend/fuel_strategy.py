"""
fuel_strategy.py

Tracks fuel burned per completed lap, kept as two separate rolling
averages - one for laps run under green, one for laps run under
caution/yellow, since caution-pace laps burn dramatically less fuel.
Combined with the sim's remaining-laps-in-session count (which tracks
the current stage in a multi-stage race, or the whole race otherwise),
this estimates whether the fuel on board will stretch to the end and
tells the overlay when it's time to start saving.
"""

from collections import deque

HISTORY_LAPS = 5  # rolling window per flag state; recent laps predict best
MAX_PLAUSIBLE_USE_LITERS = 20  # guards against pit-stop refuels/resets


class FuelStrategy:
    def __init__(self, history_laps=HISTORY_LAPS):
        self._green_usage = deque(maxlen=history_laps)
        self._caution_usage = deque(maxlen=history_laps)
        self._last_lap = None
        self._last_fuel_liters = None
        self._pit_seen_this_lap = False

    def reset(self):
        """Clear tracked history - call when a new session/car is detected."""
        self._green_usage.clear()
        self._caution_usage.clear()
        self._last_lap = None
        self._last_fuel_liters = None
        self._pit_seen_this_lap = False

    def update(self, lap, fuel_liters, is_caution, on_pit_road):
        """Feed one telemetry tick in. Only records a data point when the
        lap counter actually increments, tagged by the flag state active
        for that tick. Laps where the car touched pit road (in-lap or
        out-lap) are skipped entirely - pit-limiter pace isn't
        representative of green/caution racing fuel burn and would skew
        a small rolling average badly."""
        if lap is None or fuel_liters is None:
            return

        if on_pit_road:
            self._pit_seen_this_lap = True

        if self._last_lap is None:
            self._last_lap = lap
            self._last_fuel_liters = fuel_liters
            self._pit_seen_this_lap = bool(on_pit_road)
            return

        if lap > self._last_lap:
            used = self._last_fuel_liters - fuel_liters
            if 0 < used < MAX_PLAUSIBLE_USE_LITERS and not self._pit_seen_this_lap:
                bucket = self._caution_usage if is_caution else self._green_usage
                bucket.append(used)
            self._last_lap = lap
            self._last_fuel_liters = fuel_liters
            self._pit_seen_this_lap = bool(on_pit_road)

    def estimate(self, fuel_liters, laps_remain, is_caution):
        """Return a strategy snapshot dict describing whether the fuel on
        board will make it to the end of the stage/race."""
        primary = self._caution_usage if is_caution else self._green_usage
        fallback = self._green_usage if is_caution else self._caution_usage
        rate = _avg(primary) or _avg(fallback)

        if rate is None or fuel_liters is None:
            return {
                "fuel_per_lap": None,
                "laps_of_fuel": None,
                "laps_remaining": laps_remain,
                "margin_laps": None,
                "status": "unknown",
            }

        laps_of_fuel = fuel_liters / rate
        margin = None if laps_remain is None else laps_of_fuel - laps_remain

        if margin is None:
            status = "unknown"
        elif margin < 0:
            status = "critical"
        elif margin < 1:
            status = "save"
        else:
            status = "ok"

        return {
            "fuel_per_lap": rate,
            "laps_of_fuel": laps_of_fuel,
            "laps_remaining": laps_remain,
            "margin_laps": margin,
            "status": status,
        }


def _avg(bucket):
    return sum(bucket) / len(bucket) if bucket else None
