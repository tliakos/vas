# LEARNING.md -- Hex & Counter Wargame Knowledge Framework

This is the **static baseline** for hex-and-counter wargame knowledge. Sections 1-9 cover universal mechanics. Section 10 is the template for onboarding new games. Section 11 is the AI decision framework. Section 12 points to the INTEL system where accumulating intelligence lives.

**Update protocol:** Baseline sections (1-9, 11) are updated only when a new game introduces mechanics not already covered. Accumulating intelligence (game logs, cross-game patterns, session lessons) goes in the **INTEL file hierarchy** -- see Section 12.

---

## 1. What Hex & Counter Wargames Are

Hex-and-counter wargames simulate military conflicts using:
- A **hex grid map** representing terrain (each hex ~1-5 miles, varying by scale)
- **Cardboard counters** representing military units (with printed stats)
- **Rules** governing movement, combat, supply, and victory
- A **turn structure** where players alternate actions

The genre spans ancient warfare to modern conflicts, at scales from tactical (squad-level) to strategic (theater-level).

---

## 2. Universal Hex Grid Concepts

### 2.1 Hex Geometry

Every hex has **six sides** and **six vertices**. Two common orientations:
- **Flat-top (grain horizontal)**: Columns are straight, rows stagger. VASSAL: `sideways=true`
- **Pointy-top (grain vertical)**: Rows are straight, columns stagger. VASSAL: `sideways=false`

### 2.2 Hex Numbering

Most wargames use a **column-row** system:
- `CCRR` format: Column (2 digits) + Row (2 digits). Example: `0312` = column 3, row 12
- `CC.RR` format: Same with a separator. Example: `03.12`
- Some games use letter-number: `A1`, `B2`, etc.

**VASSAL stores positions as pixel coordinates (x, y)**, not hex IDs. The grid configuration (dx, dy, x0, y0, numbering) translates between them.

### 2.3 Hex Adjacency

Each hex has exactly 6 adjacent hexes. Standard hex directions:
```
Flat-top:        Pointy-top:
  NW  NE            N
 W    E          NW    NE
  SW  SE         SW    SE
                    S
```

### 2.4 Hexsides

The border between two hexes. Terrain features can apply to hexsides (rivers, walls, ridges). A unit crossing a hexside pays movement costs for both the terrain of the hex entered AND any hexside features.

### 2.5 Hex Distance (Range)

The number of hexes between two hexes, counting the shortest path. For flat-top hexes:
```python
def hex_distance(col1, row1, col2, row2):
    """Offset coordinate distance for flat-top hex grids."""
    # Convert to cube coordinates
    x1 = col1
    z1 = row1 - (col1 + (col1 & 1)) // 2
    y1 = -x1 - z1
    
    x2 = col2
    z2 = row2 - (col2 + (col2 & 1)) // 2
    y2 = -x2 - z2
    
    return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))
```

---

## 3. Universal Counter Reading

### 3.1 Standard Counter Layout

Most counters display:
```
+------------------+
| [Unit Symbol]    |
| [Unit ID/Name]   |
|                  |
| [CF]  [Size] [MF]|
+------------------+
```

- **Unit Symbol**: NATO symbol or game-specific icon indicating unit type
- **Unit ID**: Division/regiment/battalion name or number
- **CF**: Combat Factor (attack and/or defense strength)
- **Size**: Unit size indicator (see below)
- **MF**: Movement Factor (movement points available per turn)

### 3.2 Common Unit Sizes (NATO)

| Symbol | Size | Typical Strength |
|--------|------|-----------------|
| `...` | Regiment | 2000-5000 |
| `xx` | Division | 10000-20000 |
| `xxx` | Corps | 30000-50000 |
| `I` | Company | 100-200 |
| `II` | Battalion | 500-1000 |
| `III` | Regiment | 2000-5000 |

### 3.3 Common Unit Types

| Category | Types | Characteristics |
|----------|-------|-----------------|
| **Infantry** | Light, Heavy, Mechanized, Airborne, Marine | High defense, lower movement, good in rough terrain |
| **Armor** | Tank, Assault Gun, Tank Destroyer | High attack, good movement on open terrain, weak in rough |
| **Cavalry** | Horse, Mechanized, Recon | Fast movement, moderate combat |
| **Artillery** | Field, Heavy, AA, Rocket | Ranged fire support, cannot attack adjacent, bombardment |
| **Leaders** | Generals, Commanders | Command radius, combat modifiers, activation |
| **Special** | Engineers, Supply, HQ, Air | Specialized functions |

### 3.4 Counter States

In VASSAL, counter states are typically modeled as:
- **Embellishment layers**: Flipped (reduced), disrupted, routed, spent, etc.
- **Dynamic Properties**: Strength values, ammo, morale level
- **Markers**: Fixed unit classification data

---

## 4. Universal Turn Structure

Most hex-and-counter wargames follow variations of this turn structure:

### 4.1 IGO-UGO (I Go, You Go)

The most common structure. One player is the "phasing player" for a full turn:

```
GAME TURN:
  Player A Turn:
    1. Administrative Phase (reinforcements, weather, supply check)
    2. Movement Phase (move units up to their movement allowance)
    3. Combat Phase (resolve attacks on adjacent enemy units)
    4. Exploitation Phase (some units move again after combat)
    5. Rally Phase (recover disrupted/routed units)
  Player B Turn:
    [Same phases]
```

### 4.2 Alternating Impulse

Players alternate individual actions within a turn:
```
Turn:
  Impulse 1: Player A activates one formation
  Impulse 2: Player B activates one formation
  ...until both pass
```

### 4.3 Chit-Pull / Random Activation

Formation/command chits are drawn randomly from a cup:
```
Turn:
  Draw chit -> that formation activates (move + fight)
  Draw chit -> that formation activates
  ...until cup is empty
```

---

## 5. Universal Movement Rules

### 5.1 Movement Points (MP)

Each unit has a Movement Factor (MF). Moving costs MP per terrain type:

| Terrain | Typical MP Cost | Notes |
|---------|----------------|-------|
| Clear/Open | 1 | Base cost |
| Woods/Forest | 2 | +1 for rough |
| Rough/Hills | 2 | Elevation change |
| Mountain | 3-4 | Difficult terrain |
| Swamp/Marsh | 3-All | Often prohibitive for vehicles |
| Road | 1/2 or 1/3 | Reduced cost when following road |
| River (hexside) | +1 to +All | Crossing cost, may require bridge |
| City/Town | 1-2 | Depends on game |

### 5.2 Zone of Control (ZOC)

The six hexes adjacent to a combat unit. ZOC rules vary by game but common patterns:

- **Rigid ZOC**: Must stop when entering enemy ZOC. Cannot move directly from one enemy ZOC hex to another.
- **Fluid ZOC**: Can enter enemy ZOC freely but must stop. Can exit by paying extra MP.
- **Directional ZOC**: ZOC extends only into a unit's Front hexes, not all 6 adjacent hexes. Used in GBoH and other tactical games with facing rules.
- **No ZOC**: Some games don't use ZOC (or only for certain units).
- **ZOC effects on retreat**: Retreating into enemy ZOC may cause elimination.
- **ZOC and supply**: Enemy ZOC may block supply lines.

### 5.3 Stacking

Most games limit how many units can occupy a single hex:
- **Counter limit**: e.g., 3 units per hex
- **Size limit**: e.g., one division equivalent per hex
- **Mixed limits**: Different limits by unit type

Stacking is usually checked at the **end** of movement, not during.

### 5.4 Special Movement Types

| Type | Description |
|------|-------------|
| **Strategic Movement** | Double/triple movement but cannot enter enemy ZOC |
| **Rail Movement** | Move along rail lines at very high speed |
| **Sea Movement** | Amphibious/naval transport |
| **Air Transport** | Airlift to distant locations |
| **Forced March** | Extra movement with risk of attrition |
| **Retreat** | Involuntary movement after combat |
| **Advance After Combat** | Move into hex vacated by defeated enemy |

---

## 6. Universal Combat Rules

### 6.1 Odds-Based Combat (CRT)

The most common system. Compare attacker strength to defender strength as a ratio:

```
Attacker Total Strength : Defender Total Strength = Odds

Example: 12 attack vs 4 defense = 3:1 odds
```

Odds are typically rounded **down** in favor of the defender (e.g., 11:4 = 2:1, not 3:1).

### 6.2 The Combat Results Table (CRT)

A matrix indexed by odds column and die roll:

```
Die  | 1:2 | 1:1 | 2:1 | 3:1 | 4:1 | 5:1 | 6:1+
-----+-----+-----+-----+-----+-----+-----+------
  1  | AE  | AR  | AR  | DR  | DR  | DR  | DE
  2  | AE  | AR  | DR  | DR  | DR  | DE  | DE
  3  | AR  | DR  | DR  | DR  | DE  | DE  | DE
  4  | AR  | DR  | DR  | DE  | DE  | DE  | DE
  5  | DR  | DR  | DE  | DE  | DE  | DE  | DE
  6  | DR  | EX  | EX  | DE  | DE  | DE  | DE
```

Common results:
- **AE** = Attacker Eliminated
- **AR** = Attacker Retreats (1-3 hexes)
- **DR** = Defender Retreats (1-3 hexes)
- **DE** = Defender Eliminated
- **EX** = Exchange (both lose equal steps)
- **NE** = No Effect
- **DRM** = Die Roll Modifier shifts the roll up/down

### 6.3 Differential-Based Combat

Some games use strength difference instead of ratio:
```
Attacker Total - Defender Total = Differential
```

### 6.4 Common Combat Modifiers

| Modifier | Effect | Source |
|----------|--------|--------|
| **Terrain** | Defender bonus (column shift left or DRM) | Defender in woods, city, mountain |
| **River** | Attacker penalty for attacking across river | Hexside terrain |
| **Leadership** | DRM or column shift | Leader present with attacking/defending units |
| **Flanking** | Attacker bonus when attacking from multiple sides | Multi-hex attack geometry |
| **Supply** | Penalty for out-of-supply units | Supply rules |
| **Fortification** | Defender bonus | Prepared positions |
| **Air/Naval Support** | Attacker bonus | Support assets |
| **Combined Arms** | Bonus for mixing unit types | Infantry + armor attacking together |

### 6.5 Step Losses

Many units have two sides: **full strength** and **reduced**. Taking a "step loss" means flipping to the reduced side. A second step loss eliminates the unit. Multi-step units (corps, armies) may have more gradations.

In VASSAL, step losses are typically modeled with **Embellishment** layers (flipping the counter to show the reduced side).

**Alternative: Cohesion Hit systems** (used in GBoH and similar tactical games): Damage is tracked as cumulative Cohesion Hits against a Troop Quality (TQ) rating, using markers or Dynamic Properties. A unit routs when hits equal or exceed TQ. This is more granular than binary step loss and creates a richer attrition model.

---

## 7. Universal Supply Rules

Supply ensures units can fight effectively:

### 7.1 Supply Sources
- Map edge hexes designated as supply sources
- Ports, airfields, depots
- HQ units

### 7.2 Supply Lines
A path of hexes from the unit to a supply source, usually:
- Cannot pass through enemy-occupied hexes
- Cannot pass through enemy ZOC (unless friendly-occupied)
- Has a maximum length (in hexes or MP)

### 7.3 Out of Supply Effects
- Reduced combat strength (halved attack, sometimes defense)
- Reduced movement
- Cannot receive replacements
- May suffer attrition (step losses) over multiple turns

---

## 8. Common Game System Families

These are the major wargame system families. Each family shares core rules across multiple games (different battles/campaigns). Understanding a system family means you can play any game in it with minimal additional learning.

### 8.1 Great Battles of History (GBoH) / Ancient Warfare
**Publisher:** GMT Games
**Scale:** Tactical (individual units = cohorts, maniples, squadrons)
**Key games:** Alexander, Caesar, Cataphract, Samurai, and others
**Distinctive mechanics:**
- **Momentum/Trump activation**: Leaders activate by Initiative order; active player can chain additional Orders Phases via Momentum DR; opponent can Trump to interrupt
- **Cohesion Hit system**: Cumulative damage tracked against Troop Quality (TQ); unit routs when hits >= TQ
- **Directional facing and ZOC**: Units face a specific direction; ZOC extends into Front hexes only
- **Shock Combat**: Melee resolved via Size ratio + d10 + Position/Weapon Superiority; Superiority doubles opponent's hits
- **Missile fire**: Ranged combat using Missile Range and Results Table; missile supply tracked (Low/No)
- **Leader-dependent command**: Units need Individual Orders or Line Commands from activated leaders to move/fight
- **Orderly Withdrawal and Manipular Line Extension**: Reactive defensive maneuvers
- **Elephant Rampage**: Routed elephants move randomly damaging everything in path
- **Cavalry Pursuit**: Mandatory post-shock pursuit, potentially removing cavalry from battle
- **Phalanx formation rules**: Double-depth, facing restrictions, flank vulnerability

### 8.2 Advanced Squad Leader (ASL) / Tactical WWII
**Publisher:** MMP (Multi-Man Publishing)
**Scale:** Tactical (individual squads, vehicles)
**Key games:** ASL Starter Kits, full ASL system
**Distinctive mechanics:**
- Extremely detailed infantry/vehicle combat
- Line of sight, terrain effects at the tactical level
- Morale/breaking system
- Sequence of play with defensive fire opportunities
- Vehicle armor penetration tables

### 8.3 Operational Combat Series (OCS)
**Publisher:** The Gamers / MMP
**Scale:** Operational (divisions, regiments)
**Key games:** Tunisia, Case Blue, Burma, Sicily
**Distinctive mechanics:**
- Supply points as a trackable resource (fuel, ammo, food)
- HQ-based supply distribution
- Exploitation phase with specific unit qualifications
- Air operations (patrol, interception, ground support)
- Detailed truck/rail logistics

### 8.4 Standard Combat Series (SCS)
**Publisher:** The Gamers / MMP
**Scale:** Operational (simplified)
**Key games:** Bastogne, Afrika, Ardennes
**Distinctive mechanics:**
- Streamlined OCS -- simpler supply, same combat feel
- Fewer unit types, faster play
- Good entry point for operational games

### 8.5 Civil War Brigade Series (CWBS)
**Publisher:** The Gamers / MMP
**Scale:** Tactical-operational (brigades)
**Key games:** Gettysburg, Shiloh, Antietam
**Distinctive mechanics:**
- Chit-pull activation by wing/division
- Fatigue and stragglers
- Leader casualty system
- Artillery fire zones

### 8.6 Great Campaigns of the American Civil War (GCACW)
**Publisher:** MMP
**Scale:** Operational (brigades/divisions)
**Key games:** Stonewall Jackson's Way, Here Come the Rebels, Roads to Gettysburg
**Distinctive mechanics:**
- Activation by leader initiative rating
- March and fatigue system
- Reconnaissance and fog of war
- Leader personalities affecting command

### 8.7 Panzer Grenadier Series
**Publisher:** Avalanche Press
**Scale:** Tactical (platoons)
**Key games:** Eastern Front, Desert Rats, Elsenborn Ridge
**Distinctive mechanics:**
- Morale-centric system
- Leaders crucial for activation
- Opportunity fire
- Combined arms tactics

### 8.8 The Gamers: Tactical Combat Series (TCS)
**Publisher:** The Gamers / MMP
**Scale:** Tactical (platoons/companies)
**Distinctive mechanics:**
- Op sheets (pre-planned operations)
- SOP (standard operating procedures)
- Detailed fire combat

### 8.9 Corps Command Series
**Publisher:** Various (Lock 'n Load, Compass)
**Scale:** Operational-strategic
**Distinctive mechanics:**
- Card-driven events
- Operational tempo
- Simplified logistics

### 8.10 Card-Driven Games (CDG)
**Publisher:** GMT, Compass
**Key games:** Paths of Glory, Hannibal, Wilderness War, Twilight Struggle
**Distinctive mechanics:**
- Hand of cards used for events OR operations (not both)
- Strategic decision: play card for its event or for ops points?
- Variable turn order based on card play
- Campaign cards vs battle cards

### 8.11 COIN Series (Counter-Insurgency)
**Publisher:** GMT Games
**Key games:** Cuba Libre, A Distant Plain, Fire in the Lake, Gandhi
**Distinctive mechanics:**
- 4-player asymmetric factions
- Event card determines order of action
- Each faction has unique operations and special abilities
- Population/support control victory
- Propaganda rounds for victory checking

---

## 9. Terrain Types Across Games

### 9.1 Universal Terrain Categories

| Category | Examples | Movement Effect | Combat Effect |
|----------|----------|----------------|--------------|
| **Open** | Clear, plains, desert | Base cost (1 MP) | No modifier |
| **Rough** | Woods, forest, jungle, bocage | +1 to +2 MP | Defender bonus |
| **Elevation** | Hills, ridges, mountains | +1 to +3 MP | Defender bonus, LOS blocking |
| **Urban** | City, town, village | 1-2 MP | Strong defender bonus |
| **Water** | River, stream, lake, ocean | Hexside cost or impassable | Attacker penalty across water |
| **Fortification** | Trench, bunker, fortress | None (already built) | Strong defender bonus |
| **Road** | Road, highway, trail, rail | Reduced MP (1/2, 1/3) | Usually none |
| **Marsh** | Swamp, marsh, paddy | High cost, often vehicle-prohibited | Attacker and defender penalties |

### 9.2 Line of Sight (LOS)

Relevant mainly in tactical games. LOS is traced from hex center to hex center:
- **Blocked** by higher elevation, woods, buildings
- **Hindered** by some intervening terrain (partial blocks)
- Some games use a "LOS thread" tool (VASSAL has `LOS_Thread` support)

---

## 10. Creating Game-Specific .md Files

When onboarding a specific game, create a dedicated .md file following this template. The game-specific file should reference this LEARNING.md for shared concepts and VASSAL.md for engine mechanics.

### 10.1 Game-Specific .md Template

```markdown
# [Game Name] -- AI Play Context

**System Family:** [from Section 8, e.g., "Great Battles of History"]
**Publisher:** [publisher name]
**Scale:** [tactical/operational/strategic]
**Map Type:** [hex grid, point-to-point, area]
**Base references:** LEARNING.md (shared wargame concepts), VASSAL.md (engine)

## Game Overview
[Brief description: conflict, era, what makes this game unique]

## Sides
[List from VASSAL PlayerRoster analysis]

## Turn Sequence of Play
[Exact phases from the rulebook, mapped to VASSAL TurnTracker]
1. [Phase] - [Who acts] - [What happens]
2. ...

## Unit Types and Stats
[From piece catalog + rulebook cross-reference]
| Unit Name | Type | Attack | Defense | Movement | Morale | Special |
|-----------|------|--------|---------|----------|--------|---------|

## Map and Terrain
[Grid type, terrain types present, terrain effects chart]
| Terrain | MP Cost (Inf) | MP Cost (Cav) | MP Cost (Vehicle) | Combat DRM |
|---------|---------------|---------------|-------------------|------------|

## Movement Rules
[Game-specific movement rules, referencing LEARNING.md Section 5 for shared concepts]
- ZOC rules: [rigid/fluid/none, specifics]
- Stacking: [limits]
- Special movement: [forced march, strategic move, etc.]

## Combat Rules
[CRT or differential, with full table if possible]
- Odds calculation: [ratio/differential, rounding]
- Modifiers: [terrain DRM, leader DRM, flanking, etc.]
- Results: [what each result means]

## Supply Rules
[If applicable]

## Victory Conditions
[Per scenario]

## Scenarios
[List from VASSAL PredefinedSetup analysis]
| Scenario | Turns | Sides | Key Objectives |
|----------|-------|-------|----------------|

## AI Strategy Notes
[Key principles for this specific game]
- Opening strategy
- Key terrain to control
- Common tactical patterns
- Tempo and initiative management

## VASSAL Module Mapping
[How module pieces/properties map to game concepts]
| Module Property | Game Meaning |
|----------------|--------------|
| Marker("Type") values | Unit classification |
| DynamicProperty("...") | Mutable game stat |
| Embellishment layers | Unit state (fresh/reduced/disrupted) |
| Grid numbering | Hex ID format |
```

### 10.2 Process for Creating a Game-Specific .md

1. **Run the vmod analyzer** on the game's .vmod file (see vmod.md)
2. **Read the rulebook PDF** and extract rules per LEARNING.md categories
3. **Cross-reference**: Map Marker properties to unit stats, grid to terrain, TurnTracker to sequence of play
4. **Read the scenario book** for starting setups and victory conditions
5. **Identify the system family** from Section 8 to pre-load shared mechanical knowledge
6. **Fill in the template** above with game-specific data
7. **Validate**: Parse an embedded scenario .vsav, enumerate all pieces, verify the piece catalog matches the OOB from the scenario book
8. **Update INTEL.md** (root): Add a Game Log entry. Promote any universal insights to the cross-game sections. Also update **LEARNING.md** baseline sections (1-9, 11) if the game introduced mechanics not already covered.
9. **Create game INTEL**: `games/<GameName>/INTEL.md` with cross-scenario patterns seeded from rules analysis.
10. **Create scenario directory**: `games/<GameName>/scenarios/` with per-scenario INTEL files created when sessions begin (use `TEMPLATE_INTEL.md` as starting point).

---

## 11. AI Decision-Making Framework

When playing as the AI opponent, apply this hierarchy:

### 11.1 Strategic Level
- What are the victory conditions? Focus all decisions toward them.
- What is the current turn relative to the game length? Manage tempo.
- Where are the key terrain objectives? Control them.

### 11.2 Operational Level
- Which units are in supply? Prioritize keeping them supplied.
- Where can I concentrate force for favorable odds? Mass for attack.
- Where am I weak? Screen or reinforce before the opponent exploits.
- Can I cut the opponent's supply lines?

### 11.3 Tactical Level
- Attack at the best odds available (3:1 or better preferred)
- Use terrain for defense (woods, cities, behind rivers)
- Maintain a reserve (don't commit everything at once)
- Protect flanks (avoid being surrounded)
- Use ZOC to slow the enemy advance
- Leaders should be with the most important formations

### 11.4 Combat Decision
When choosing whether to attack:
- **Attack** if odds are 3:1+ with favorable terrain/modifiers
- **Consider** attack at 2:1 if the objective is critical
- **Avoid** attacks at 1:1 or worse unless desperate
- **Never** attack at 1:2 unless forced by the rules
- Always calculate the worst-case result and ensure it's survivable

### 11.5 Movement Priorities
1. Reinforce threatened positions
2. Move toward victory objectives
3. Cut enemy supply lines
4. Concentrate for planned attacks
5. Screen weak points with minimal forces
6. Move reserves to flexible central positions

---

## 12. Intelligence System

Accumulating intelligence from game onboarding and play sessions is stored in the **INTEL file hierarchy**, not in this document. LEARNING.md is the static baseline; INTEL files are the living intelligence.

```
INTEL.md (root)                         -- Cross-game patterns
  games/<GameName>/INTEL.md             -- Cross-scenario patterns per game
    games/<GameName>/scenarios/<Name>/INTEL.md  -- Per-scenario learnings
```

**Flow:** Scenario insights promote to game INTEL → game insights promote to root INTEL → root INTEL informs all future games.

**When onboarding a new game** (Step 8 of Section 10.2): update INTEL.md with a Game Log entry and any universal insights. Also update LEARNING.md baseline sections (1-9, 11) if the new game introduced mechanics not yet covered.

See `INTEL.md` for the current state of accumulated intelligence.
