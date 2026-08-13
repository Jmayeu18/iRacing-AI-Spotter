/**
 * app.js - iRacing AI Spotter overlay
 *
 * Polls the local Flask JSON API every 100ms and renders lap times,
 * fuel, tire temps, and flags into the overlay. Pure DOM updates, no
 * frameworks, so it stays lightweight enough for an OBS browser source.
 */

const API_URL = "http://127.0.0.1:5000/telemetry";
const POLL_MS = 100;

// Tire temp -> color gradient (Fahrenheit). The SDK reports tire temps in
// Celsius regardless of the sim's display-unit setting, so we convert for
// display. These thresholds are generic defaults for a glanceable
// "cold/optimal/hot" read; tune per car/tire compound.
const TIRE_COLD_F = 140;
const TIRE_OPTIMAL_F = 194;
const TIRE_HOT_F = 248;
const COLOR_COLD = [0x39, 0x87, 0xe5]; // --seq-blue
const COLOR_OPTIMAL = [0x0c, 0xa3, 0x0c]; // --status-good
const COLOR_HOT = [0xd0, 0x3b, 0x3b]; // --status-critical

function cToF(tempC) {
  return tempC === null || tempC === undefined ? null : (tempC * 9) / 5 + 32;
}

// Order matters: first matching active flag wins the banner.
// (Higher-priority/rarer flags first so e.g. a caution doesn't get
// buried behind a plain green.)
const FLAG_PRIORITY = [
  { key: "red", label: "Red Flag", css: "flag-red" },
  { key: "caution_waving", label: "Caution", css: "flag-caution" },
  { key: "caution", label: "Caution", css: "flag-caution" },
  { key: "yellow_waving", label: "Yellow", css: "flag-yellow" },
  { key: "yellow", label: "Yellow", css: "flag-yellow" },
  { key: "checkered", label: "Checkered", css: "flag-checkered" },
  { key: "white", label: "White Flag", css: "flag-white" },
  { key: "green", label: "Green Flag", css: "flag-green" },
];

// Text + CSS class shown per fuel_strategy.status value from the API.
const FUEL_STATUS = {
  ok: { text: "Fuel OK", css: "fuel-ok" },
  save: { text: "Save Fuel", css: "fuel-save" },
  critical: { text: "Won't Make It - Save Now", css: "fuel-critical" },
  unknown: { text: "Collecting data...", css: "fuel-unknown" },
};

const el = {
  overlay: document.getElementById("overlay"),
  status: document.getElementById("status"),
  flagBanner: document.getElementById("flag-banner"),
  lapNumber: document.getElementById("lap-number"),
  lastLap: document.getElementById("last-lap"),
  bestLap: document.getElementById("best-lap"),
  fuelFill: document.getElementById("fuel-fill"),
  fuelPct: document.getElementById("fuel-pct"),
  tires: {
    lf: document.getElementById("tire-lf"),
    rf: document.getElementById("tire-rf"),
    lr: document.getElementById("tire-lr"),
    rr: document.getElementById("tire-rr"),
  },
  lapsOfFuel: document.getElementById("laps-of-fuel"),
  lapsRemaining: document.getElementById("laps-remaining"),
  fuelStatus: document.getElementById("fuel-status"),
};

/** Format seconds as m:ss.mmm; returns a placeholder for missing/invalid values. */
function formatLapTime(seconds) {
  if (seconds === null || seconds === undefined || seconds <= 0) {
    return "--:--.---";
  }
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return `${minutes}:${rest.toFixed(3).padStart(6, "0")}`;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function lerpColor(c1, c2, t) {
  return [lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t)];
}

/** Map a tire temperature (Fahrenheit) to a cold(blue) -> optimal(green) -> hot(red) color. */
function tireColor(tempF) {
  if (tempF === null || tempF === undefined) {
    return "var(--text-muted)";
  }
  let rgb;
  if (tempF <= TIRE_COLD_F) {
    rgb = COLOR_COLD;
  } else if (tempF >= TIRE_HOT_F) {
    rgb = COLOR_HOT;
  } else if (tempF <= TIRE_OPTIMAL_F) {
    const t = (tempF - TIRE_COLD_F) / (TIRE_OPTIMAL_F - TIRE_COLD_F);
    rgb = lerpColor(COLOR_COLD, COLOR_OPTIMAL, t);
  } else {
    const t = (tempF - TIRE_OPTIMAL_F) / (TIRE_HOT_F - TIRE_OPTIMAL_F);
    rgb = lerpColor(COLOR_OPTIMAL, COLOR_HOT, t);
  }
  return `rgb(${rgb.map((v) => Math.round(v)).join(",")})`;
}

function renderFuelStrategy(strategy) {
  if (!strategy) {
    strategy = { laps_of_fuel: null, laps_remaining: null, status: "unknown" };
  }

  el.lapsOfFuel.textContent =
    strategy.laps_of_fuel === null || strategy.laps_of_fuel === undefined
      ? "--"
      : strategy.laps_of_fuel.toFixed(1);
  el.lapsRemaining.textContent =
    strategy.laps_remaining === null || strategy.laps_remaining === undefined
      ? "--"
      : strategy.laps_remaining;

  const info = FUEL_STATUS[strategy.status] || FUEL_STATUS.unknown;
  el.fuelStatus.textContent = info.text;
  el.fuelStatus.className = `fuel-status ${info.css}`;
}

function renderFlags(flags) {
  const active = FLAG_PRIORITY.find((f) => flags && flags[f.key]);
  if (!active) {
    el.flagBanner.classList.add("hidden");
    return;
  }
  el.flagBanner.textContent = active.label;
  el.flagBanner.className = `flag-banner ${active.css}`;
}

function renderTire(node, tempC) {
  const tempF = cToF(tempC);
  node.textContent = tempF === null ? "--" : Math.round(tempF);
  node.style.color = tireColor(tempF);
}

function render(data) {
  if (!data || !data.connected) {
    el.overlay.classList.remove("connected");
    el.overlay.classList.add("disconnected");
    el.status.textContent = "Waiting for iRacing...";
    return;
  }

  el.overlay.classList.remove("disconnected");
  el.overlay.classList.add("connected");

  el.lapNumber.textContent = data.lap.current_lap ?? "-";
  el.lastLap.textContent = formatLapTime(data.lap.last_lap_time);
  el.bestLap.textContent = formatLapTime(data.lap.best_lap_time);

  const fuelPct = data.fuel.level_pct;
  const pctDisplay = fuelPct === null || fuelPct === undefined ? null : fuelPct * 100;
  el.fuelPct.textContent = pctDisplay === null ? "--%" : `${pctDisplay.toFixed(1)}%`;
  el.fuelFill.style.width = `${Math.max(0, Math.min(100, pctDisplay ?? 0))}%`;
  el.fuelFill.style.backgroundColor =
    pctDisplay !== null && pctDisplay <= 15 ? "var(--status-critical)" : "var(--status-good)";

  renderTire(el.tires.lf, data.tires.lf.avg);
  renderTire(el.tires.rf, data.tires.rf.avg);
  renderTire(el.tires.lr, data.tires.lr.avg);
  renderTire(el.tires.rr, data.tires.rr.avg);

  renderFuelStrategy(data.fuel_strategy);
  renderFlags(data.flags);
}

async function poll() {
  try {
    const res = await fetch(API_URL, { cache: "no-store" });
    const data = await res.json();
    render(data);
  } catch (err) {
    // Backend not reachable yet (server not started, or between restarts).
    render(null);
  }
}

setInterval(poll, POLL_MS);
poll();
