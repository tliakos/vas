# vmod.md -- VASSAL Module Analyzer Skill

This skill provides the procedures and tooling for analyzing any VASSAL .vmod module file, along with its associated rulebooks, playbooks, and game collateral. The output is a complete game profile that enables AI-assisted play.

**Companion files:**
- `VASSAL.md` -- Deep engine context (architecture, file formats, command system)
- `vmod_analyzer.py` -- Standalone Python script for automated .vmod analysis

---

## When to Invoke This Skill

Invoke this skill when the user:
- Provides a .vmod file for analysis
- Provides a .vsav or .vlog file to parse
- Provides game rulebooks, playbooks, or reference PDFs
- Asks to onboard a new game for AI play
- Asks to understand what's inside a module

---

## Procedure 1: Analyze a .vmod File

### Step 1: Run the Automated Analyzer

```bash
python3 /Users/thomasliakos/vas/vmod_analyzer.py /path/to/module.vmod
```

For JSON output (machine-parseable):
```bash
python3 /Users/thomasliakos/vas/vmod_analyzer.py /path/to/module.vmod --json
```

This produces a structured report covering:
- Module metadata (game name, version, Vassal version)
- Player sides
- All maps with their boards, grids (hex/square/region/zoned), zones, and at-start stacks
- All prototypes with their traits, markers, and dynamic properties
- All piece definitions from piece palettes with traits, markers, and prototype references
- Predefined setups / scenarios (with embedded save analysis)
- Dice definitions
- Global properties
- Turn tracker structure
- Global key commands
- Image and sound asset counts

### Step 2: Extract the buildFile.xml for Deep Inspection

If the automated report needs deeper analysis:

```bash
# Create a working directory for the extracted module
mkdir -p /tmp/vmod_extract
cd /tmp/vmod_extract
unzip -o /path/to/module.vmod
```

Then read `buildFile.xml` directly for full XML inspection. Key things to look for beyond what the analyzer captures:

- **BeanShell expressions** in calculated properties and filters (these encode game logic)
- **Custom Java classes** referenced in the XML (modules can extend VASSAL with custom code)
- **Map overlay layers** and their draw order
- **Line-of-sight thread** configuration
- **Chart windows** (often contain CRT, TEC, and other game tables as images)

### Step 3: Catalog All Pieces

From the analyzer output, build a piece taxonomy:

1. **Resolve Prototype chains**: If piece A uses Prototype "Infantry" which itself uses Prototype "CommonUnit", flatten the full trait stack
2. **Group by Marker values**: Pieces with `Marker("Type","Infantry")` are infantry, etc.
3. **Identify properties that encode stats**: Markers named things like "CombatStrength", "MovementPoints", "Morale", "Range" carry the game-mechanical values
4. **Map images to counters**: The BasicPiece image plus Embellishment layers define what the piece looks like in each state

### Step 4: Understand the Map Geometry

From the grid data, build the coordinate translation:

**For HexGrid:**
- `dx`, `dy` = pixel dimensions of each hex cell
- `x0`, `y0` = pixel offset of the grid origin
- `sideways` = true means flat-topped hexes (columns are offset); false means pointy-topped (rows offset)
- Grid numbering tells you how hex coordinates are labeled (e.g., "A1", "0101", "1,1")

**Pixel-to-hex conversion (flat-top, sideways=true):**
```python
def pixel_to_hex(px, py, dx, dy, x0, y0):
    col = round((px - x0) / dx)
    row = round((py - y0) / dy)
    return col, row
```

**For SquareGrid:**
```python
def pixel_to_square(px, py, dx, dy, x0, y0):
    col = round((px - x0) / dx)
    row = round((py - y0) / dy)
    return col, row
```

**For RegionGrid:** Each region has an explicit name and (x,y) pixel center. Match piece positions to the nearest region center.

### Step 5: Analyze Embedded Scenarios

For each PredefinedSetup that references a .vsav file inside the .vmod:

```python
import zipfile, io

def extract_scenario_pieces(vmod_path, save_entry_path):
    """Extract piece data from an embedded scenario save."""
    with zipfile.ZipFile(vmod_path) as vmod_zf:
        save_data = vmod_zf.read(save_entry_path)
    
    with zipfile.ZipFile(io.BytesIO(save_data)) as save_zf:
        raw = save_zf.read("savedGame")
    
    # Deobfuscate
    text = raw.decode("utf-8")
    if text.startswith("!VCSK"):
        key = int(text[5:7], 16)
        plain = "".join(chr(int(text[i:i+2], 16) ^ key) for i in range(7, len(text)-1, 2))
    else:
        plain = text
    
    # Split commands on ESC separator
    commands = plain.split("\x1b")
    
    # Extract AddPiece commands: format is "+/id/type/state"
    pieces = []
    for cmd in commands:
        if cmd.startswith("+/"):
            parts = cmd[2:].split("/", 2)
            if len(parts) >= 3:
                piece_id = parts[0]
                piece_type = parts[1]
                piece_state = parts[2]
                pieces.append({
                    "id": piece_id,
                    "type": piece_type,
                    "state": piece_state,
                })
    return pieces
```

For each piece, the state string encodes the current position. The position is stored in the BasicPiece's state segment as `mapName;x;y;...`.

---

## Procedure 2: Analyze a .vsav / .vlog File

### Step 1: Deobfuscate

```python
def read_vassal_save(filepath):
    import zipfile
    with zipfile.ZipFile(filepath, 'r') as zf:
        raw = zf.read('savedGame')
    text = raw.decode('utf-8')
    if text.startswith('!VCSK'):
        key = int(text[5:7], 16)
        return ''.join(chr(int(text[i:i+2], 16) ^ key) for i in range(7, len(text)-1, 2))
    return text
```

### Step 2: Parse the Command Tree

```python
plain = read_vassal_save('game.vsav')
commands = plain.split('\x1b')  # Top-level command separator (ESC char)

for cmd in commands:
    if cmd == 'begin_save':
        print("--- Game state begin ---")
    elif cmd == 'end_save':
        print("--- Game state end ---")
    elif cmd.startswith('+/'):
        # AddPiece: +/pieceId/typeString/stateString
        parts = cmd[2:].split('/', 2)
        print(f"ADD PIECE: id={parts[0]}")
    elif cmd.startswith('-/'):
        # RemovePiece: -/pieceId
        print(f"REMOVE PIECE: id={cmd[2:]}")
    elif cmd.startswith('D/'):
        # ChangePiece: D/pieceId/newState/oldState
        parts = cmd[2:].split('/', 2)
        print(f"CHANGE PIECE: id={parts[0]}")
    elif cmd.startswith('M/'):
        # MovePiece: M/id/newMapId/newX/newY/newUnderId/oldMapId/oldX/oldY/oldUnderId/playerId
        parts = cmd[2:].split('/')
        if len(parts) >= 4:
            print(f"MOVE PIECE: id={parts[0]} to ({parts[2]},{parts[3]}) on {parts[1]}")
    elif cmd.startswith('LOG\t'):
        # Log entry (vlog only)
        print(f"LOG STEP: {cmd[4:80]}...")
```

### Step 3: Reconstruct Game State

From the decoded save, build a dictionary of all pieces:

```python
def reconstruct_game_state(save_path):
    plain = read_vassal_save(save_path)
    commands = plain.split('\x1b')
    
    pieces = {}  # id -> {type, state, map, x, y}
    
    for cmd in commands:
        if cmd.startswith('+/'):
            parts = cmd[2:].split('/', 2)
            if len(parts) >= 3:
                pid, ptype, pstate = parts[0], parts[1], parts[2]
                # Parse state for position: the BasicPiece state contains map;x;y
                # State is tab-separated matching the type's tab-separated trait chain
                state_parts = pstate.split('\t')
                # The BasicPiece state (last in chain) has format: map;x;y;gpId;...
                bp_state = state_parts[-1] if state_parts else ""
                bp_fields = bp_state.split(';')
                map_name = bp_fields[0] if len(bp_fields) > 0 else ""
                x = bp_fields[1] if len(bp_fields) > 1 else ""
                y = bp_fields[2] if len(bp_fields) > 2 else ""
                
                pieces[pid] = {
                    "type": ptype,
                    "state": pstate,
                    "map": map_name,
                    "x": x,
                    "y": y,
                }
    return pieces
```

---

## Procedure 3: Ingest Game Collateral (Rulebooks, Playbooks, PDFs)

When the user provides game documentation alongside a .vmod:

### Step 1: Read and Catalog Documents

Read each PDF and identify its type:
- **Rulebook**: Contains "rules", "sequence of play", "movement", "combat"
- **Playbook / Scenario Book**: Contains "scenario", "setup", "order of battle", "victory conditions"
- **Player Aid / Charts**: Contains tables (CRT, TEC), usually visual/tabular
- **Errata / Living Rules**: Contains corrections -- these supersede the base rulebook

### Step 2: Extract Structured Rules

For each rulebook, extract into a structured model:

```
GAME RULES MODEL:
  Turn Sequence:
    1. [Phase Name] - [Who acts] - [What happens]
    2. [Phase Name] - ...
  
  Movement:
    Base allowance: [by unit type]
    Terrain costs: [terrain -> cost per unit type]
    Stacking: [limits]
    ZOC: [entry/exit/stop rules]
  
  Combat:
    Initiation: [mandatory/voluntary, adjacency rules]
    Odds/Differential: [how calculated]
    CRT: [columns and results]
    Modifiers: [terrain, leader, flanking, etc.]
    Results: [retreat, eliminate, exchange, etc.]
  
  Special Rules:
    [Game-specific mechanics]
  
  Victory Conditions:
    [Per scenario]
```

### Step 3: Cross-Reference Module Data with Rules

Link the VASSAL module's piece properties to the rulebook's unit stats:

| Module Property (Marker/DynProp) | Rule Meaning |
|----------------------------------|--------------|
| `Marker("Type","...")` | Unit type classification |
| `Marker("CombatStrength","6")` | Attack/defense value per CRT |
| `Marker("MovementPoints","4")` | Movement allowance |
| `Marker("Side","...")` | Which player controls this unit |
| `DynamicProperty("Status")` | Current status (fresh/disrupted/routed) |
| `Embellishment` layers | Visual state (flipped, reduced, etc.) |

The specific Marker names vary per module -- the rulebook tells you what the numbers mean, the module tells you where they're stored.

### Step 4: Generate Game-Specific Skill File

After completing analysis, produce a game-specific .md file (separate from this one) containing:

```markdown
# [Game Name] -- AI Play Context

## Game Overview
[Brief description, era, scale, complexity]

## Sides
[List from PlayerRoster]

## Turn Sequence
[From rulebook, mapped to module's TurnTracker]

## Unit Types and Stats
[From piece catalog cross-referenced with rulebook]

## Map and Terrain
[From grid analysis + rulebook terrain rules]

## Movement Rules
[From rulebook, with costs per terrain per unit type]

## Combat Rules
[CRT, modifiers, results -- from rulebook]

## Scenarios
[From PredefinedSetups + scenario book]

## AI Strategy Notes
[Key strategic principles from any strategy guides provided]
```

---

## Procedure 4: Analyze a Save File in Context of a Module

When both a .vmod and a .vsav are available:

### Step 1: Analyze the .vmod first (Procedure 1)

This gives you the piece catalog, prototypes, map geometry, and grid system.

### Step 2: Parse the .vsav (Procedure 2)

This gives you all pieces with their current positions and states.

### Step 3: Map Pieces to Catalog

For each piece in the save:
1. Parse its type string to identify the Decorator chain
2. Match it to the piece catalog from the .vmod (by gpId or by type string matching)
3. Extract Marker values to identify the unit
4. Parse the state string to get current dynamic property values and embellishment layer states
5. Convert pixel position (x, y) to grid coordinates using the map's grid geometry

### Step 4: Produce a Game State Report

```
CURRENT GAME STATE:
  Turn: [from TurnTracker / Global Properties]
  Phase: [current phase]
  Active Player: [who is to move]

  [Map Name]:
    [Grid Location] - [Piece Name] ([Side]) [Status]
                      Stats: [combat/movement/morale from markers]
    [Grid Location] - [Piece Name] ([Side]) [Status]
    ...

  Global Properties:
    [Name] = [Value]
    ...
```

---

## Quick Reference: Trait ID Prefixes

| Prefix | Trait | Purpose |
|--------|-------|---------|
| `piece;` | BasicPiece | Core piece (image, name) |
| `basicName;` | BasicName | Display name override |
| `emb2;` / `emb;` | Embellishment | Multi-state image layers |
| `obs;` | Mask/Obscurable | Hidden from opponents |
| `hide;` | Invisible/Hideable | Completely invisible |
| `label;` | TextLabel | Text drawn on piece |
| `rotate;` | FreeRotator | Arbitrary rotation |
| `mark;` | Marker | Constant property (type has keys, state has values) |
| `PROP;` | DynamicProperty | Mutable property |
| `calcProp;` | CalculatedProperty | BeanShell expression property |
| `prototype;` | UsePrototype | Include traits from a Prototype |
| `immob;` | Immobilized | Cannot be moved |
| `delete;` | Delete | Can be deleted |
| `clone;` | Clone | Can be duplicated |
| `replace;` | Replace | Replace with another piece |
| `placemark;` | PlaceMarker | Place a new piece |
| `sendto;` | SendToLocation | Move to specific location |
| `return;` | ReturnToDeck | Send back to a deck |
| `globalkey;` | GlobalKeyCommand | Send keys to other pieces |
| `macro;` | TriggerAction | Conditional key command |
| `report;` | ReportState | Chat message on activation |
| `markmoved;` | MovementMarkable | Mark as moved |
| `footprint;` | Footprint | Movement trail |
| `restrict;` | Restricted | Restrict by player side |
| `hideCmd;` | RestrictCommands | Hide/disable menu items |
| `setprop;` | SetGlobalProperty | Modify global property |
| `setpieceprop;` | SetPieceProperty | Modify piece property |
| `playSound;` | PlaySound | Play audio |
| `button;` | ActionButton | Clickable button |
| `globalhotkey;` | GlobalHotKey | Fire global hotkey |
| `submenu;` | SubMenu | Organize right-click menu |
| `translate;` | Translate | Move by offset |
| `AreaOfEffect;` | AreaOfEffect | Highlight surrounding area |
| `mat;` | Mat | Mat (pieces ride on it) |
| `matPiece;` | MatCargo | Cargo (rides on a Mat) |
| `attach;` | Attachment | Piece-to-piece attachment |
| `table;` | TableInfo | Tabular data display |
| `border;` | BorderOutline | Custom border drawing |
| `cmt;` | Comment | Designer comment (no game effect) |

---

## Quick Reference: Command Encoding

| Command | Format | Example |
|---------|--------|---------|
| AddPiece | `+/pieceId/typeString/stateString` | `+/1234/emb2;...\tpiece;...;/Main Map;100;200;...` |
| RemovePiece | `-/pieceId` | `-/1234` |
| ChangePiece | `D/pieceId/newState/oldState` | `D/1234/newState.../oldState...` |
| MovePiece | `M/id/newMapId/newX/newY/newUnderId/oldMapId/oldX/oldY/oldUnderId/playerId` | `M/1234/Main Map/150/300/null/...` |
| BeginSave | `begin_save` | |
| EndSave | `end_save` | |
| LogStep | `LOG\t[encoded command]` | |

Top-level separator: `\x1b` (ESC, char 27)
Within-command separator: `/`
Piece type layer separator: `\t` (tab)
Trait field separator: `;` (most traits)

---

## Obfuscation Quick Reference

**Decode:**
```python
def deobfuscate(raw_bytes):
    t = raw_bytes.decode('utf-8')
    if not t.startswith('!VCSK'): return t
    key = int(t[5:7], 16)
    return ''.join(chr(int(t[i:i+2], 16) ^ key) for i in range(7, len(t)-1, 2))
```

**Encode:**
```python
import random
def obfuscate(plaintext):
    key = random.randint(0, 255)
    return ('!VCSK' + f'{key:02x}' + ''.join(f'{(ord(c)^key):02x}' for c in plaintext)).encode('utf-8')
```
