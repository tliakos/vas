# ONBOARDING.md -- How to Add a New Game to the Framework

This document explains the **complete onboarding process** for adding a new wargame to the framework, and **how knowledge is shared and accumulated across games** of any era (ancients, medieval, Napoleonic, ACW, WW2, modern).

---

## The Three Layers of Knowledge

The framework accumulates knowledge at three distinct layers, and **each layer has different rules for what belongs in it**:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: UNIVERSAL                                              │
│  vassal_framework/* + LEARNING.md + INTEL.md (root)              │
│                                                                  │
│  Things that are TRUE FOR ANY HEX-AND-COUNTER WARGAME:           │
│   - Hex grid math (HexGridConfig handles any orientation)        │
│   - Unit detection and adjacency                                 │
│   - ZOC and movement abstractions                                │
│   - Combat result types (CombatResult, modifiers)                │
│   - Monte Carlo simulation framework                             │
│   - AI decision ranking algorithms                               │
│   - Universal tactical principles (focus fire, screen, reserve)  │
└─────────────────────────────────────────────────────────────────┘
              ↑ promoted from below when validated
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: GENRE / SYSTEM FAMILY                                  │
│  LEARNING.md Section 8 + cross-genre patterns                    │
│                                                                  │
│  Things that are TRUE FOR A SPECIFIC GENRE OR SYSTEM FAMILY:     │
│   - GBoH ancients: cohesion hits, momentum, troop quality        │
│   - WWII operational: supply, refit, fuel/ammo tracks            │
│   - Napoleonic linear: formation changes, fatigue, morale        │
│   - COIN: 4-faction asymmetric, eligibility cylinder             │
│   - CDG: hand management, event vs ops decision                  │
│   - Tactical (squad-level): LOS in detail, fire and movement     │
└─────────────────────────────────────────────────────────────────┘
              ↑ promoted from below when validated
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: GAME-SPECIFIC                                          │
│  games/<GameName>/<game>_lib/ + games/<GameName>/INTEL.md        │
│                                                                  │
│  Things that are SPECIFIC TO ONE GAME:                           │
│   - SPQR-specific terrain types (Shallow River Siris)            │
│   - SPQR shock CRT and Superiority chart                         │
│   - Specific unit type mappings (LG, RC, HC, PH)                 │
│   - Scenario victory conditions                                  │
│   - Map-specific calibration (max_cols=46 for Heraclea board)    │
└─────────────────────────────────────────────────────────────────┘
              ↑ promoted from below when validated
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: SCENARIO-SPECIFIC                                      │
│  games/<GameName>/scenarios/<Name>/INTEL.md + SESSION.md         │
│                                                                  │
│  Things that are SPECIFIC TO ONE SCENARIO:                       │
│   - Heraclea: River Siris hexside, Pyrrhus has elephants         │
│   - Specific OOB and starting positions                          │
│   - Scenario victory conditions and withdrawal levels            │
│   - Tactical patterns observed in actual play sessions           │
└─────────────────────────────────────────────────────────────────┘
```

**Key principle:** Patterns are **promoted upward** when they are validated by additional games or scenarios. A tactical insight from one Heraclea session stays in that scenario's INTEL until 2+ scenarios in the same game confirm it; then it moves up to the game level. After 2+ games in the same family confirm it, it moves to the genre level.

---

## Auto-Generation: The Fast Path

For most games, you can use the **auto-generator** to create a working baseline
in seconds, then refine the rules manually:

```bash
# Step 1: Drop the .vmod into a new directory
mkdir games/MyGame
cp /path/to/MyGame.vmod games/MyGame/

# Step 2: Auto-generate the lib
python3 -m vassal_framework.autogen games/MyGame/MyGame.vmod --name MyGame

# Step 3: Validate the generated lib
python3 -m vassal_framework.validation MyGame

# Step 4: Validate end-to-end with a save file
python3 -m vassal_framework.validation MyGame --save games/MyGame/test.vsav

# Step 5: Refine the generated terrain.py and combat.py with rulebook values
# (the auto-generator marks unknowns with TODO comments)

# Step 6: Run the AI
python3 -m games.MyGame.mygame_lib.runner games/MyGame/test.vsav
```

### What auto-generation produces

The auto-generator produces a complete working baseline:

```
games/MyGame/
  MyGame.vmod                  ← you provide this
  MyGame.md                    ← auto-generated context document
  INTEL.md                     ← auto-generated cross-scenario intelligence
  SESSION.md                   ← auto-generated session log template
  scenarios/                   ← empty, ready for per-scenario INTEL
  mygame_lib/
    __init__.py
    terrain.py                 ← auto-generated based on detected era/family
    combat.py                  ← auto-generated based on detected combat type
    units.py                   ← auto-generated with detected sides and prefixes
    runner.py                  ← auto-generated CLI tool
```

### What auto-generation gets right

- Game system family detection (GBoH, OCS, ASL, CDG, COIN, etc.)
- Combat type selection (cohesion shock, odds CRT, differential, card-driven)
- Hex grid extraction (already worked from `vassal_framework.grid`)
- Side detection from PlayerRoster
- Unit type prefix detection from image filenames
- Scenario list from PredefinedSetup elements
- Dice configuration

### What auto-generation cannot get right (requires rulebook)

- Specific movement costs per terrain per unit type
- Exact CRT values for the game's combat resolution
- Unit stats (strength, morale, TQ) -- these are on counter images
- Victory conditions and withdrawal levels
- Special rules and exceptions
- Per-board grid calibration values

These are marked with `# TODO:` comments in the auto-generated files for manual refinement.

### Validation

`vassal_framework.validation` runs comprehensive checks:

1. **Directory structure** -- all required files present
2. **Imports** -- all modules import without errors
3. **VMOD load** -- the .vmod parses correctly
4. **Grid extraction** -- per-board grid parameters detected
5. **Terrain system** -- TerrainSystem instantiates with terrain types
6. **Combat system** -- CombatSystem resolves a test combat
7. **Unit scanner** (with --save) -- units detected from a real save
8. **AI evaluation** (with --save) -- AI runs on at least one leader

The validator reports `[OK]`, `[WARN]`, or `[FAIL]` per check with details.

---

## Available Templates

The framework provides multiple templates for common game patterns:

### Terrain templates (`vassal_framework/templates/`)
- `terrain_template.py` -- generic starting point
- `terrain_ancients.py` -- GBoH-style ancient warfare (PH/LG/HI/MI/LI/SK/CAV/EL)
- `terrain_napoleonic.py` -- Napoleonic linear (INF/CAV/HC/LC/ARTY)
- `terrain_ww2_tactical.py` -- WW2 squad-level (squads, half-squads, vehicles)
- `terrain_ww2_operational.py` -- WW2 operational (INF/MECH/ARMOR/REC/ARTY)

### Combat templates
- `combat_template.py` -- generic odds-based CRT
- `combat_differential.py` -- differential CRT (attacker - defender)
- `combat_ifd.py` -- Infantry Firepower (ASL-style)
- (cohesion shock is auto-generated by autogen for GBoH games)

### Unit templates
- `units_template.py` -- generic side classifier
- `units_ww2.py` -- Allied/Axis classification with WW2 unit type schema

These templates can be copied to `games/<GameName>/<game>_lib/` as a starting point,
or the auto-generator can produce them customized to your specific vmod.

---

## What Goes Where When You Onboard a New Game

When you onboard a new game (e.g., "Twilight Struggle" or "OCS Tunisia"):

### Step 1: Identify the genre/system family
Look at LEARNING.md Section 8 (Game System Families). Is it:
- **GBoH** (Great Battles of History) → Ancients with cohesion shock
- **OCS** (Operational Combat Series) → WWII operational with supply
- **SCS** (Standard Combat Series) → Operational simplified
- **ASL** (Advanced Squad Leader) → Tactical WWII
- **CDG** (Card-Driven Game) → Strategic with hand management
- **COIN** → Asymmetric counterinsurgency
- **CWBS / GCACW** → American Civil War
- Other → New family, document it

The genre tells you which **abstractions in the framework will already work**.

### Step 2: Create the game directory and library
```
games/
  <GameName>/
    <gamename>_lib/        # All game-specific Python code
      __init__.py
      terrain.py           # Inherits TerrainSystem
      combat.py            # Inherits CombatSystem
      units.py             # Side classifier + unit type maps
      runner.py            # CLI runner
    <GameName>.md          # Human-readable game context (template in LEARNING.md)
    INTEL.md               # Cross-scenario intelligence
    SESSION.md             # Live session log template
    scenarios/             # Per-scenario subdirectories
      Cannae/
        INTEL.md           # Scenario-specific learnings
```

### Step 3: Implement the game-specific Python modules
Copy from `vassal_framework/templates/` and customize:
- `terrain_template.py` → terrain types, movement costs, combat modifiers
- `combat_template.py` → choose CRT pattern (odds / differential / cohesion)
- `units_template.py` → image prefixes, unit type codes, side classifier
- `runner_template.py` → CLI tool wiring everything together

### Step 4: Calibrate the hex grid
Use known starting positions from the scenario book to verify the framework's hex extraction matches what you see in VASSAL. If it doesn't:
- Set `max_cols` and `max_rows` for descend math
- Document the calibration in your game's `units.py`

### Step 5: Identify what new things this game teaches the framework

This is the **critical step for cross-game knowledge accumulation**. After implementing the basics, ask:

| Question | If yes, where does the knowledge go? |
|----------|--------------------------------------|
| Does it use a new combat resolution pattern? | Add the pattern type to `vassal_framework/combat.py CombatType` enum. The implementation stays in the game lib. |
| Does it have a new terrain category not seen before? | Add the category code to `vassal_framework/terrain.py` documentation. Implementation stays in game lib. |
| Does it introduce a mechanic that other games might use? (supply, fatigue, command radius, fog of war) | Add an abstract base class to the framework. Game-specific implementations inherit. |
| Is it just specific values for known mechanics? | Stays purely in the game lib. |

### Step 6: Update LEARNING.md and INTEL.md

After onboarding, update:

**LEARNING.md** (only if new universal knowledge was learned):
- Section 8 (game system families): add the new family or expand existing
- Sections 1-9 (universal mechanics): expand only if a fundamentally new mechanic was discovered

**INTEL.md** (root, cross-game accumulator):
- Section 1 (Game Log): always add the new game with its system family
- Sections 2-4 (patterns): only if a pattern is now confirmed by 2+ games

**games/<GameName>/INTEL.md**:
- Game-specific patterns (always)

---

## How Cross-Game Knowledge Sharing Actually Works

Here's a concrete example showing how knowledge flows across games:

### Day 1: SPQR is onboarded
- Discover GBoH Cohesion Shock is encoded in framework as CombatType.COHESION_SHOCK
- SPQR-specific shock CRT lives in `games/SPQR/spqr_lib/combat.py`
- Heraclea-specific tactical insight ("RC vs LC is AS") goes in `games/SPQR/scenarios/Heraclea/INTEL.md`
- SPQR-level insight ("manipular stacking is decisive") goes in `games/SPQR/INTEL.md`

### Day 2: User onboards Alexander (also GBoH)
- Implementer copies `games/SPQR/spqr_lib/combat.py` as starting point because it's the same system family
- Adjusts the unit type codes (Alexander has Companions, sarissai phalanxes, etc.)
- Discovers that "RC vs LC is AS" pattern ALSO holds for "Companion Cavalry vs Light Cavalry"
- This is now confirmed by 2 games → **promoted to root INTEL.md**:
  > "In ancient warfare systems, heavy cavalry has Attack Superiority over light cavalry"

### Day 3: User onboards Wilderness War (CDG)
- Different system family entirely
- Does NOT have cohesion combat -- uses card-driven mechanics
- New `WildernessWarCombat` subclasses `CombatSystem` with `CombatType.CARD`
- Discovers card draw mechanics. If significant: **add CombatType.CARD example to framework docs**.

### Day 4: User onboards The Operational Combat Series (OCS): Tunisia
- WWII operational
- Has SUPPLY -- a mechanic SPQR didn't have
- Implementer creates `games/OCS_Tunisia/ocs_lib/supply.py`
- BUT supply is a UNIVERSAL operational concept. So the framework gets a new abstract base:
  - `vassal_framework/supply.py` -- abstract `SupplySystem` base class
- OCS Tunisia's specific supply rules subclass it

### Day 5: User onboards SCS Bastogne (also operational, simpler)
- Already has the framework's `SupplySystem` from OCS work
- Subclasses it with Bastogne-specific rules
- Confirms that "supply lines through enemy ZOC are blocked unless friendly-occupied" applies to BOTH OCS and SCS
- This is now confirmed by 2 games in the same family → moves to LEARNING.md Section 7 (Universal Supply Rules)

---

## The Promotion Rules

| From | To | When |
|------|----|------|
| Scenario INTEL | Game INTEL | Pattern confirmed by 2+ scenarios in the same game |
| Game INTEL | Root INTEL | Pattern confirmed by 2+ games (any genre) |
| Root INTEL | LEARNING.md | Pattern is so universal it's a baseline truth |
| Game lib code | Framework abstract base | Mechanic exists in 2+ games -- abstract it |
| Framework abstract | Built-in concrete | Almost never -- frameworks should stay abstract |

**Hard rule**: nothing in `vassal_framework/` may import from `games/`. Knowledge flows up via documentation and refactoring, not via runtime dependencies.

---

## Genre-Specific Onboarding Notes

### Ancient warfare (GBoH, etc.)
- Use `CombatType.COHESION_SHOCK`
- Reference `games/SPQR/` as the template
- Likely uses: troop quality, momentum activation, position superiority, weapon system superiority
- Likely doesn't need: supply tracking, fog of war, complex LOS

### WW2 tactical (ASL, Combat Commander)
- Use `CombatType.ODDS_CRT` or differential
- Need detailed LOS implementation (multiple terrain levels)
- Need fire-and-movement sequence of play
- Vehicle armor penetration as separate mechanic

### WW2 operational (OCS, SCS)
- Use `CombatType.ODDS_CRT`
- Need SupplySystem (when first onboarded)
- Need fuel/ammo tracking (OCS) or simplified (SCS)
- Air operations as separate subsystem

### Napoleonic linear (La Bataille, Vive l'Empereur)
- Use `CombatType.ODDS_CRT` or differential
- Formation changes critical
- Morale and fatigue tracking
- Cavalry charges as special procedure

### Card-driven (CDG, COIN)
- Use `CombatType.CARD`
- Hand management state in addition to board state
- Event vs ops decision is the main strategic axis
- Different "AI" model -- evaluate cards instead of moves

### American Civil War (CWBS, GCACW)
- Use `CombatType.ODDS_CRT`
- Brigade-level activation (CWBS) or leader initiative (GCACW)
- Fatigue and stragglers
- Leader casualty system

---

## Function Reuse Across Games

When you implement a new game and find yourself copying code from another game, that's a signal to **promote the code to the framework**.

Common reusable functions across games:
- **Hex math** -- already in framework
- **Adjacency / ZOC** -- already in framework
- **Side classification** -- generic via callback (each game provides its own classifier)
- **Movement cost calculation** -- generic in `TerrainSystem.calculate_move_cost()`
- **Stacking limit checks** -- TODO: add generic version
- **Supply line tracing** -- TODO: add when first game needs it
- **Line of sight** -- TODO: add generic LOS tracer
- **Leader command radius checks** -- already generic in `Battlefield.in_command_range()`
- **Fog of war / hidden movement** -- TODO: add when first game needs it

When you build one of these for a new game, **promote it to the framework** so all future games benefit.

---

## Self-Learning Loop

The framework gets smarter every time a game is onboarded or a session is played:

```
NEW GAME ONBOARDED
  ↓
  Implements game lib in games/<Game>/<game>_lib/
  ↓
  Discovers new patterns
  ↓
  Updates games/<Game>/INTEL.md
  ↓
  If pattern is universal: promote to root INTEL.md or LEARNING.md
  ↓
  If new abstraction needed: add base class to framework
  ↓
  Future games inherit/reuse the new framework piece
```

```
SESSION PLAYED
  ↓
  Logs decisions and outcomes in games/<Game>/SESSION.md
  ↓
  Identifies tactical patterns
  ↓
  Updates games/<Game>/scenarios/<Scenario>/INTEL.md
  ↓
  After multiple sessions: promote to game INTEL
  ↓
  After multiple games: promote to root INTEL
```

This is the **self-learning system**. Every game makes the framework more capable for the next game. Every session makes the AI smarter for the next session.
