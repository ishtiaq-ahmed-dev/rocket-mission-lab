# Real-Time Fidelity, Pad Separation, and Visual Telemetry Revision

**Date:** 2026-10-23  
**Status:** Completed and Verified  
**Scope:** Pad circle markings, > 1 km pad separation enforcement, 1:1 real-time playback clock, ISS Orbital Systems & NVIDIA Isaac Sim branding.

---

## 1. Pad Circle Terminology & High-Fidelity Markings

### Problem
Previously, pad textures contained confusing or obscured labels ("RECOVERY", "TAKEOFF" placed under the 3D hold-down rings or colliding with the center geometry), and lacked explicit distinction between the launch and touchdown sites.

### Resolution
- **Takeoff Pad (Pad 01):**
  - **Upper Center Text:** Bold, prominent `TAKEOFF` (135px yellow text) placed cleanly above the central flame trench and hold-down ring.
  - **Lower Center Text:** `LAUNCH PAD` (85px clean white text).
  - **Top Arc:** `TAKEOFF PAD 01` with subtitle `ISS ORBITAL SYSTEMS · NVIDIA SIMULATOR`.
  - **Outer Safety Boundary:** Alternating yellow/black hazard chevron stripes (radius 930px).
  - **Bottom Coordinates:** `TAKEOFF COMPLEX 01 · PAD A · COORD [X, Y] · DOWNRANGE SEPARATION > 1,000 M`.

- **Landing Pad (Pad 01):**
  - **Upper Center Text:** Bold, prominent `LANDING` (135px emerald `#79dfb5` text) placed cleanly above the touchdown cross.
  - **Lower Center Text:** `LANDING ZONE` (85px clean white text).
  - **Top Arc:** `LANDING PAD 01` with subtitle `ISS ORBITAL SYSTEMS · NVIDIA SIMULATOR`.
  - **Concentric Guide Rings:** Precision distance rings at 20m, 15m, 10m, and 5m.
  - **Central Cross:** Prominent white landing bullseye cross.
  - **Scorch FX:** Realistic radial retro-propulsion exhaust scorch gradient.
  - **Bottom Coordinates:** `LANDING ZONE 01 · TOUCHDOWN TARGET · COORD [X, Y] · DOWNRANGE RECOVERY > 1,000 M`.

---

## 2. Mandatory > 1 km Pad Separation Enforcement

### Requirement
Takeoff Pad and Landing Pad must be separated by more than 1 km (> 1,000 m).

### Implementation
- **Default Flight Plan (`frontend/src/store.ts`):**
  - Launch site: `[0, 0]`
  - Landing site: `[1200, 400]`
  - Separation altitude: `1,500 m`
  - Resulting surface transfer: $\sqrt{1200^2 + 400^2} \approx 1,264.91\text{ m}$ (1.26 km), which strictly exceeds the 1 km requirement.

- **Flight Plan Editor (`frontend/src/FlightPlanEditor.tsx`):**
  - Live distance calculation: `distance = Math.hypot(plan.launch[0] - plan.landing[0], plan.launch[1] - plan.landing[1])`.
  - Display format: Displays in kilometers (e.g. `1.26 km transfer (> 1 km nominal)`).
  - Validation Warning: If distance < 1,000 m, triggers a warning banner with an automatic one-click fix:
    `"Enforce nominal 1.26 km separation"`.
  - Quick Presets:
    1. Standard Pad: `[1200, 400]` (1.26 km)
    2. Downrange: `[2500, 0]` (2.5 km)
    3. Long-Range: `[5000, 1000]` (5.1 km)
    *(Zero-distance / return-to-launch preset removed to satisfy minimum separation constraints).*

- **Mission Control Site Panel (`frontend/src/MissionControl.tsx`):**
  - Live surface transfer distance formatted in kilometers with nominal validation status:
    `"1.26 km surface transfer (> 1 km nominal)"`.
  - Site tiles labelled explicitly as **TAKEOFF SITE** and **LANDING SITE**.

---

## 3. Exact Real-Time Playback Synchronization (1:1)

### Timing Contract
- The simulation physics integrates with $\Delta t = 0.02\text{ s} \times 5 = 0.1\text{ s}$ per control substep.
- The browser playback clock (`frontend/src/frameScheduler.ts`) advances by `(now - previous) / 1000 * speed`.
- At default `speed = 1.0`, exactly 1.0 second of physical simulation time elapses per 1.0 second of wall-clock time.
- **UI Enhancements:**
  - Transport bar explicitly displays `1:1 REAL TIME` status badge next to timecode.
  - Playback speed dropdown clearly designates `1.0× (Real Time)`.
  - Profile chart foot displays: `"... physical duration (1:1 Real Time)"`.

---

## 4. Realistic Graphics & ISS / NVIDIA Simulator Branding

- **Application Header:** Branded as `ISS Orbital Systems · Omniverse Rocket Simulator`.
- **Rocket Body Livery:** Features United States aerospace designation, `ISS ORBITAL SYSTEMS · NVIDIA SIMULATOR`, and booster designation `ISS-01 OMNIVERSE`.
- **Pad Textures:** High-resolution procedural textures with realistic concrete expansion joints, surface noise, scorch marks, and aerospace stencil lettering.

---

## 5. Verification Matrix

| Test Suite | Commands | Result |
| :--- | :--- | :--- |
| Frontend Typecheck & Build | `npm run build` | Passed (zero errors, bundle generated) |
| Frontend Unit Tests | `npm run test` (vitest) | 15 / 15 test files passed (47 tests) |
| Backend Python Tests | `python -m pytest` | 100 / 100 tests passed |
