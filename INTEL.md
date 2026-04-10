# INTEL.md -- Cross-Game Intelligence

This is the **top-level accumulator**. It contains only distilled insights that apply across multiple games. It gets smarter every time a game is onboarded or a session is completed.

**Intelligence flows up:**
```
Scenario INTEL  →  Game INTEL  →  This file
(per-battle)       (per-game)     (universal)
```

**Update protocol:**
- After every game onboarding: add a Game Log entry
- After game INTEL accumulates cross-scenario patterns: promote the universal ones here
- Never store game-specific details here -- those stay in `games/<GameName>/INTEL.md`

---

## 1. Game Log

Each entry records what was onboarded and what new knowledge it contributed.

### 1.1 SPQR (Great Battles of History)
- **Onboarded:** 2026-04-10
- **Files:** `games/SPQR/SPQR.md`, `games/SPQR/INTEL.md`
- **System family:** Great Battles of History (GBoH)
- **New mechanics contributed to baseline:**
  - Directional ZOC (front-only) → LEARNING.md Section 5.2
  - Cohesion Hit systems → LEARNING.md Section 6.5
  - Momentum/Trump activation → LEARNING.md Section 8.1
- **LEARNING.md sections updated:** 5.2, 6.5, 8.1

---

## 2. Mechanical Patterns

Cross-game insights about how different game mechanics behave. Each entry is tagged with which games confirmed it.

- **Directional ZOC creates flanking opportunities.** Games with front-only ZOC reward maneuver far more than 6-hex ZOC games. The AI should always look for flank/rear approaches. *(Confirmed: SPQR)*
- **Cohesion systems demand proactive withdrawal.** When damage is gradual (cumulative hits vs. a threshold), you must pull units back *before* they break, not after. Binary step-loss games are more forgiving. *(Confirmed: SPQR)*
- **Activation systems reward sector focus.** In games where you activate formations individually (not move-everything-then-fight), concentrate effort on one sector per activation. Spreading thin wastes tempo. *(Confirmed: SPQR)*

---

## 3. AI Strategy Principles

Universal strategic insights validated by play across games.

- **Calculate the rout threshold.** Before committing any unit to combat, know how many more hits it can absorb before breaking. Never shock attack with a unit that can't survive the worst-case result. *(Confirmed: SPQR)*
- **Cavalry is a strategic commitment.** In games with pursuit mechanics, winning cavalry may leave the battle for multiple turns. Commit cavalry only when the positional gain justifies temporary loss. *(Confirmed: SPQR)*
- **Leader preservation is paramount.** In leader-dependent activation systems, losing the commanding leader cripples the entire army. Keep leaders stacked with strong units, not exposed. *(Confirmed: SPQR)*
- **Screen with expendables.** Deploy skirmishers/light units forward to absorb initial contact and buy time for the main line. Accept their loss. *(Confirmed: SPQR)*

---

## 4. Module Pattern Recognition

Patterns in how VASSAL modules encode game data. Speeds up future module analysis.

- **DynamicProperty for damage tracking.** GMT GBoH modules use DynProp "c" for Cohesion Hits. Other systems likely use similar single-letter or short-name DynProps for the primary damage mechanic. *(Confirmed: SPQR)*
- **Terse prototype names.** SPQR uses "1", "dbl", "lead", "el", "tir", "arty". Expect similar terseness in other modules -- prototype names map to unit categories, not descriptive labels. *(Confirmed: SPQR)*
- **d10 offset for 0-9.** SPQR configures dice as 1d10-1 to produce 0-9 (where 0 = zero). Watch for this pattern in other GBoH modules. *(Confirmed: SPQR)*
