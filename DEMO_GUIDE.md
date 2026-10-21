# Coldline demo guide

How to run Coldline and simulate genuine and non-genuine alerts during a presentation. For the full runbook see [README.md](README.md); for the architecture see [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md).

## 1. One-time setup (PowerShell, from the repository root)

Prerequisites: Python 3.11+ and Node.js 24.15+.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm.cmd ci
npm.cmd run build      # needed only for the single-port option below
cd ..
```

Use `npm.cmd` if the PowerShell execution policy blocks `npm`. On macOS/Linux use `.venv/bin/python` and `npm`.

If `run.py` reports *Node.js 24.15+ is required*, either install Node 24.15+ on PATH or extract the official Node 24 zip (for Windows, `node-v24.x.x-win-x64.zip` from nodejs.org) so that `.runtime\node\node.exe` exists. The launcher checks that location first; `.runtime/` is git-ignored.

## 2. Run the application

**Recommended for the demo.** A steady fleet means only the patterns you trigger cross the threshold:

```powershell
.venv\Scripts\python.exe run.py --live --baseline steady --db presentation-01.db
```

Open **http://127.0.0.1:3000**. Use a new `--db` filename for each clean run.

**If the launcher refuses your Node version.** The backend serves the built UI on a single port:

```powershell
.venv\Scripts\python.exe -m backend.cli live-demo --baseline steady --db presentation-01.db
```

Open **http://127.0.0.1:8000**.

Sign in as **`nimbus.demo`** or **`alpine.demo`**. Passwords are generated on the first launch, saved to `config/demo-passwords.local.json` (git-ignored) and reused afterwards. They are also printed in the terminal. To choose your own, edit that file (minimum 8 characters) and restart. Operator and device API keys are still regenerated on each launch.

Other modes:

- **Historical replay** of the 54 case-study readings, which produces 2 incidents: `.venv\Scripts\python.exe run.py`
- **Seed temperatures replayed live**, where T-01 and T-05 open incidents on their own: `.venv\Scripts\python.exe run.py --live`

Press **Ctrl+C** to stop.

## 3. Simulate the scenarios

Use the **Simulate a real-time pattern** panel on the dashboard. Pick a truck, then a pattern. In this demo profile, an incident needs 30 s above 8 °C and recovers after 20 s of normal readings.

| # | Pattern | Type | Expected result | Duration |
|---|---|---|---|---|
| 1 | Compressor failure | Genuine | Incident opens, then recovers | ~100 s |
| 2 | Marginal sustained excursion | Genuine | Incident opens even though only slightly warm | ~100 s |
| 3 | Door-open spike | Non-genuine | No incident | ~60 s |
| 4 | Single-sample sensor glitch (25 °C) | Non-genuine | No incident | ~50 s |
| 5 | Warm readings broken by a telemetry gap | Non-genuine | No incident (continuity not proven) | ~100 s |

### Suggested script

1. Start **Compressor failure on T-01** and **Door-open spike on T-02** together. This contrasts a real alert with a false alarm.
2. When T-01's incident appears (after about 40 s), open it and show the evidence chart and explanation. Then **Acknowledge** it with a note. This shows who acknowledged and when, the timeline, and the notification deliveries.
3. Run **Marginal sustained on T-03**, **Sensor glitch on T-04** and **Telemetry gap on T-05**.
4. Each run shows *Expected*, *Observed* and a verdict: **As expected** or **Mismatch — review**.
5. Sign out and sign in as **`alpine.demo`** to show customer isolation.

### Notes

- A truck cannot start a new pattern while it has an open incident or a running pattern. Use another truck or wait for recovery.
- Escalation in this profile fires 1 minute after an incident opens, if nobody has acknowledged it. The demo patterns usually recover sooner, so expect escalation only on incidents that stay open longer.
- In this profile, notifications go to the backend terminal log. They are also listed in the incident dialog.

## 4. Optional: trigger patterns from a script

```powershell
$h = @{ "X-API-Key" = "<printed Nimbus operator key>" }
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/demo/scenarios -Headers $h `
  -ContentType application/json -Body '{"truck_id":"T-02","scenario":"sensor_glitch"}'
```

Scenario IDs: `compressor_failure`, `marginal_sustained`, `door_open_spike`, `sensor_glitch`, `telemetry_gap`. List runs and their verdicts with `GET /api/v1/demo/scenarios`.
