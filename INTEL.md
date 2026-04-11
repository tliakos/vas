# INTEL.md -- Cross-Game Intelligence

This is the **top-level accumulator**. It contains only distilled insights that apply across **multiple games**. Nothing gets promoted here until a second game confirms the pattern.

**Intelligence flows up:**
```
Scenario INTEL  →  Game INTEL  →  This file
(per-battle)       (per-game)     (universal, 2+ games required)
```

**Update protocol:**
- After every game onboarding: add a Game Log entry (Section 1 only)
- Patterns stay in the game-level INTEL until a second game confirms them
- Once confirmed by 2+ games: promote to Sections 2-4 with provenance tags
- Never store game-specific details here

---

## 1. Game Log

Registry of onboarded games. This is an index only -- game-specific intelligence lives in `games/<GameName>/INTEL.md`.

| # | Game | System Family | Onboarded | Game INTEL |
|---|------|--------------|-----------|------------|
| 1 | SPQR | Great Battles of History (GBoH) | 2026-04-10 | `games/SPQR/INTEL.md` |

---

## 2. Mechanical Patterns

Cross-game insights confirmed by 2+ games. *(Empty until a second game is onboarded.)*

**Candidates awaiting second confirmation** (from single-game INTEL files):
- Directional ZOC creates flanking opportunities
- Cohesion systems demand proactive withdrawal
- Activation systems reward sector focus
- Multi-board map modules need active board detection from save (BoardPicker setup commands)
- Hex grid parameters MUST be extracted from buildFile.xml, never guessed
- VASSAL state strings use nested SequenceEncoder escaping (each Decorator level adds backslashes)
- Leader Active/Finished state is in BasicPiece name suffix (/1 vs /2)
- Cohesion Hits / damage levels stored as Embellishment levels in OUTER->INNER chain order

---

## 3. AI Strategy Principles

Universal strategic insights confirmed by 2+ games. *(Empty until a second game is onboarded.)*

**Candidates awaiting second confirmation:**
- Calculate the rout/break threshold before committing to combat
- Cavalry with pursuit rules is a strategic commitment, not a tactical one
- Leader preservation is paramount in leader-dependent activation systems
- Screen with expendable light units
- Monte Carlo with N=300-500 iterations is sufficient for tactical decisions
- Adjacency + ZOC + matchup superiority are the 3 critical factors for tactical wargames
- AI should prefer FREE units for movement; LOCKED units for shock combat
- Asymmetric matchups (heavy vs light): heavy almost never voluntarily attacked by light; ZOC stalemates favor whoever can't be hurt

---

## 4. Module Pattern Recognition

Patterns in how VASSAL modules encode game data, confirmed by 2+ modules. *(Empty until a second module is analyzed.)*

**Candidates awaiting second confirmation:**
- DynamicProperty with short names for primary damage tracking
- Terse prototype names mapping to unit categories
- d10 configured as 1d10-1 for 0-9 results
