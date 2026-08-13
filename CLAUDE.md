# iRacing AI Spotter

An iRacing **oval-racing** spotter and AI coaching tool. Local-first: a
Python backend reads live telemetry from iRacing's SDK, a Flask API
serves it as JSON, and a transparent HTML/CSS/JS overlay displays it
for streaming.

## Scope

- **Oval racing only.** Do not build or assume road-course logic
  (chicanes, elevation-driven corner logic, road-course-style pit
  entry/exit, etc.).
- Track geometry assumptions: banking, long sweeping corners (often
  spanning a large % of lap distance, not sharp discrete apexes),
  oval-style pit road entry/exit. Covers everything from short bullring
  ovals to superspeedways/quad-ovals (e.g. Chicagoland - see corner
  detection notes below).
- **Long-term goal: sellable product**, not just a personal tool. Keep
  modules cleanly separated and avoid tightly coupling components, so
  licensing/auth can be added later without a rewrite.

## Data source

iRacing SDK live telemetry via shared memory, through `pyirsdk`
(Windows-only). Two independent read-only connections exist on
purpose - see Architecture below.

## Architecture

```
backend/
  irsdk_client.py       # read-only SDK wrapper - fuel/tire spotter
  fuel_strategy.py       # green/caution-aware fuel burn tracking, laps-of-fuel estimate
  server.py              # Flask JSON API (127.0.0.1:5000) - telemetry + fuel strategy
  print_telemetry.py     # standalone console script (original Step 1 build)

  coaching/               # AI coaching module - separate, in progress
    telemetry_reader.py   # own read-only SDK connection (independent of irsdk_client.py)
    corner_detector.py    # auto-detects corner entry/apex/exit zones from steering
                           # (smoothed + hysteresis - see Known Quirks)
    reference_lap.py      # tracks fastest *clean* lap each session as the reference
    lap_analyzer.py        # buffers lap samples, computes per-corner deltas vs reference
    run_coaching_logger.py # standalone script - logs deltas to console/file (current phase)
    logs/                  # gitignored - per-run session logs

frontend/
  index.html / style.css / app.js   # transparent overlay: lap times, fuel %,
                                     # tire temps (°F), flags, fuel strategy panel
```

**The fuel/tire spotter and the coaching module are deliberately
separate systems** - separate SDK connections, separate files, no
shared imports. When working on one, don't modify the other unless the
task explicitly requires it; ask first if a change seems to need to
cross that boundary.

Repo: `github.com/Jmayeu18/iRacing-AI-Spotter`, `main` branch.

## Known telemetry quirks

- **Tire temps only refresh on pit stops / exiting the car** - a
  deliberate iRacing SDK restriction, not a bug. They will not visibly
  change lap-to-lap while out on track.
- **Clean-lap criteria** (used by both fuel strategy and coaching
  reference-lap selection, implemented independently in each module):
  - Pit road or yellow/caution flag at any point during the lap →
    excluded from fuel-per-lap averaging / not reference-eligible.
  - Car **stopped on the racing surface** mid-lap (not on pit road,
    e.g. parking out on track to exit the session) → hard-excluded
    from the coaching module entirely (not logged as a real lap,
    never reference-eligible). Detected via near-zero speed while
    `on_pit_road` is false.
  - Car went **off-track** (off the racing surface, via
    `PlayerTrackSurface`) at any point → not reference-eligible, but
    still logged/compared and flagged low-confidence rather than
    discarded, since a messy-but-legal lap is still useful context.
- Corner auto-detection is steering-angle-based (smoothed + hysteresis
  thresholds) rather than assuming a fixed corner count - a track like
  Chicagoland (quad-oval) detects as 2 continuous corner complexes
  (turns 1-2, turns 3-4), not 4 discrete corners, which is correct for
  that track's actual geometry.

## Coaching module status

**Phase 1 (in progress/validated):** corner detection + reference lap
+ per-corner delta logging to console/file. No voice yet - this phase
exists specifically to verify detection/comparison accuracy against
real driving before adding anything real-time on top.

**Planned next (design decisions made, not yet built):**
- Live voice callouts after corner exit (never mid-corner) via cloud
  TTS - provider not yet finalized (ElevenLabs vs OpenAI TTS were the
  options under discussion).
- Post-session natural-language report via LLM - provider not yet
  finalized (Anthropic vs OpenAI were the options under discussion).
- Push-to-talk Q&A.
- Post-session telemetry dashboard.

Corner detection method (auto-calibrate from the driver's own laps,
vs. manual per-track config) was already decided in favor of
auto-calibration - implemented in `corner_detector.py`.
