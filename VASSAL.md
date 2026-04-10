# VASSAL Engine -- Deep Context for AI-Assisted Play

## 1. What VASSAL Is

VASSAL (originally "Virtual Advanced Squad Leader") is an open-source (LGPLv2) game engine written in Java for building and playing online adaptations of board games, card games, and wargames. Created in 1999 by Rodney Kinney, it now supports hundreds of game modules. It runs on Windows, macOS, and Linux via Java 11+.

**Key capabilities:**
- Live online play via the VASSAL server or peer-to-peer connections
- Play By Email (PBEM) via .vlog log files
- Hot-seat and solitaire play
- A Module Editor for creating game adaptations without programming

**Source repository:** `github.com/vassalengine/vassal` (the full source is cloned locally at `./vassal/`)

---

## 2. Architecture Overview

VASSAL is a Maven multi-module Java project (version 3.8.0-SNAPSHOT):

```
vassal-parent (pom)
  vassal-app      -- The engine itself (all runtime code)
  vassal-doc      -- Designer's Guide, Reference Manual, User Guide
  vassal-deprecation -- Deprecation annotations
  release-prepare -- Release packaging
```

### 2.1 Package Map (vassal-app `src/main/java/VASSAL/`)

| Package | Purpose |
|---------|---------|
| `build/` | Module structure, XML config, component tree. **GameModule** is the root singleton. |
| `build/module/` | All first-class module components: Map, GameState, BasicLogger, PlayerRoster, DiceButton, Chatter, TurnTracker, GlobalOptions, Inventory, PredefinedSetup, etc. |
| `build/module/map/` | Map-related: boards, grids (hex, square, irregular), zones, deck viewers, line-of-sight, highlights. |
| `build/module/properties/` | Global Properties system (module-level, map-level, zone-level mutable properties). |
| `build/module/metadata/` | .vmod/.vsav metadata reading/writing (module name, version, Vassal version). |
| `build/widget/` | UI widgets including PieceSlot (palette piece definitions). |
| `command/` | **The Command Pattern** -- core of all game state synchronization. |
| `counters/` | **Game piece model** -- BasicPiece, all Traits (Decorators), Stack, Deck. |
| `chat/` | Networking: server connections, rooms, P2P, message boards. |
| `chat/node/` | Node-based server client (the primary online play mechanism). |
| `chat/peer2peer/` | Direct peer-to-peer connections. |
| `launch/` | Entry points: Player, Editor, ModuleManager, Launcher. |
| `script/` | BeanShell expression engine for calculated properties and filters. |
| `tools/` | Utilities: DataArchive (ZIP wrapper), SequenceEncoder, image handling, IO. |
| `tools/io/` | ZipArchive, ObfuscatingOutputStream, DeobfuscatingInputStream. |
| `i18n/` | Internationalization / localization. |
| `configure/` | Configuration UI (the Editor's property panels). |
| `preferences/` | User preferences system. |
| `property/` | Property interfaces and persistent properties. |
| `search/` | Module search functionality. |

### 2.2 Entry Points

| Mode | Main Class | CLI Usage |
|------|-----------|-----------|
| **Play a game** | `VASSAL.launch.Player` | `java -cp vassal.jar VASSAL.launch.Player /path/to/module.vmod` |
| **Edit a module** | `VASSAL.launch.Editor` | `java -cp vassal.jar VASSAL.launch.Editor --edit /path/to/module.vmod` |
| **Module Manager** | `VASSAL.launch.ModuleManager` | Default launch (the GUI hub) |

---

## 3. The Command Pattern (Core of Everything)

**This is the single most important architectural concept in VASSAL.**

Every game state change is represented as a `Command` object. Commands are:
1. **Executed** locally (to apply the change)
2. **Encoded** to ASCII strings (via `CommandEncoder.encode()`)
3. **Transmitted** to other players over the network, or written to save/log files
4. **Decoded** back from strings (via `CommandEncoder.decode()`)
5. **Executed** on the receiving client to replicate the change

### 3.1 Core Command Types

| Command Class | What It Does |
|--------------|--------------|
| `AddPiece` | Adds a GamePiece to the game (undo = RemovePiece) |
| `RemovePiece` | Removes a GamePiece from the game |
| `ChangePiece` | Changes a piece's state (the workhorse -- any trait state change) |
| `MovePiece` | Moves a piece to a new position/map |
| `NullCommand` | No-op, used as a placeholder |
| `AlertCommand` | Displays a message to the user |
| `PlayAudioClipCommand` | Plays a sound |
| `FlareCommand` | Shows a flare on the map |
| `ConditionalCommand` | Executes only if conditions are met (e.g., version check) |
| `SetPersistentPropertyCommand` | Sets a persistent property on a piece |

### 3.2 Command Composition

Commands are **composable** via `Command.append()`. A compound command executes all its children in sequence. This is how a single "turn" can contain dozens of piece moves, state changes, and side effects all bundled together.

### 3.3 The Encode/Decode Chain

`GameModule` is the central dispatch for encoding/decoding. It maintains an array of registered `CommandEncoder` instances and tries each in turn:

```
GameModule.encode(Command c)
  -> tries each CommandEncoder.encode(c) until one succeeds
  -> for compound commands, encodes each sub-command separated by COMMAND_SEPARATOR
  -> returns a single ASCII string

GameModule.decode(String s)
  -> splits on COMMAND_SEPARATOR
  -> for each sub-string, tries each CommandEncoder.decode() until one succeeds
  -> returns a compound Command tree
```

The `SequenceEncoder` class handles field-level serialization within commands using configurable separator characters.

---

## 4. The Game Piece Model

### 4.1 The Decorator Pattern

A game piece in VASSAL is **not** a single object. It is a chain of `Decorator` objects (called **Traits**) wrapping an innermost `BasicPiece`. This follows the Gang-of-Four Decorator Pattern.

```
[outermost Trait] -> [Trait] -> [Trait] -> ... -> [BasicPiece]
```

When a method (e.g., `draw()`, `keyEvent()`, `getProperty()`) is called on a piece, it flows from the **outermost** trait inward. Each trait can intercept, modify, or pass through the call. This is why trait order matters -- **outer traits can affect/restrict inner traits**.

### 4.2 BasicPiece

The innermost element. It holds:
- **Basic name** and **image**
- **Position** (x, y coordinates on a Map)
- **Unique ID** (assigned by GameState)
- **Location properties**: CurrentMap, CurrentBoard, CurrentZone, CurrentX, CurrentY, LocationName
- **Persistent properties** (key-value pairs that survive serialization)

### 4.3 Key Trait Types (Decorators)

| Trait Class | Purpose |
|-------------|---------|
| `Embellishment` | Layer images (multi-state visual overlays, e.g., flipped/unflipped) |
| `FreeRotator` | Arbitrary rotation of the piece image |
| `Labeler` | Text label drawn on the piece |
| `DynamicProperty` | A named property whose value can change during play |
| `Marker` | A fixed property -- type defines key names, state holds values |
| `CalculatedProperty` | Property computed via BeanShell expression |
| `Hideable` | "Invisible" trait -- hide piece from opponents |
| `Obscurable` | "Mask" trait -- show a different image to opponents (fog of war) |
| `Immobilized` | Prevent moving the piece |
| `Delete` | Allow deleting the piece |
| `Clone` | Allow duplicating the piece |
| `Replace` | Replace this piece with another |
| `PlaceMarker` | Place a new piece at this location |
| `SendToLocation` | Move piece to a specific location |
| `ReturnToDeck` | Send piece back to a deck |
| `CounterGlobalKeyCommand` | Send key commands to other pieces matching a filter |
| `TriggerAction` | Fire key commands conditionally |
| `ReportState` | Report a message to the chat when activated |
| `MovementMarkable` | Mark the piece as having moved |
| `Footprint` | Movement trail |
| `RestrictCommands` | Hide/disable menu items conditionally |
| `Restricted` | Restrict access by player side |
| `UsePrototype` | Include traits from a Prototype definition |
| `PlaySound` | Play a sound on activation |
| `GlobalHotKey` | Fire a global hotkey |
| `SetGlobalProperty` | Modify a Global Property |
| `ActionButton` | A clickable button on the piece image |
| `Mat` / `MatCargo` | Mat/cargo relationships (pieces that ride on other pieces) |
| `Attachment` | Piece-to-piece attachment system |
| `SubMenu` | Organize right-click menu into submenus |
| `NonRectangular` | Custom click boundary shape |
| `Pivot` | Rotate around an off-center point |
| `Translate` | Move piece by a fixed offset |
| `PropertySheet` | Spreadsheet-style property editor |
| `TableInfo` | Tabular data display |

### 4.4 Piece Serialization

Each piece has two serialized forms:
- **Type** (`getType()`): Fixed configuration that doesn't change during play (image names, menu text, etc.)
- **State** (`getState()`): Mutable game state (position, dynamic property values, layer levels, etc.)

Both are serialized as strings using `SequenceEncoder`. The full piece definition is the concatenation of all Decorator types/states from outermost to innermost.

### 4.5 Stacks and Decks

- **Stack**: A group of pieces at the same location. Pieces in a stack share a position and are drawn overlapping.
- **Deck**: A special Stack with card-game behavior (shuffle, draw, face-down display).

---

## 5. File Formats

### 5.1 .vmod (Module)

A **.vmod** file is a **ZIP archive** containing:

| Entry | Purpose |
|-------|---------|
| `buildFile.xml` | The module definition -- an XML tree defining the entire module structure (maps, boards, piece definitions, toolbar buttons, etc.) |
| `images/` | All image files (board images, piece images, icons) |
| `sounds/` | Sound files |
| `help/` | Documentation files |
| `moduledata` | Module metadata (XML with module name, version, Vassal version) |

The `buildFile.xml` is parsed by `VASSAL.build.Builder` and drives the construction of the entire module component tree rooted at `GameModule`.

### 5.2 .vsav (Saved Game)

A **.vsav** file is a **ZIP archive** containing:

| Entry | Purpose |
|-------|---------|
| `savedGame` | The game state -- an **obfuscated** ASCII string |
| `moduledata` | Save metadata (module name, module version, Vassal version, description) |

**The savedGame entry format:**
1. The raw bytes start with the header `!VCSK` followed by a key byte
2. The remaining bytes are XOR-obfuscated with that key (each content byte is XOR'd with the key, then hex-encoded as two ASCII characters)
3. After deobfuscation, you get a **plain-text ASCII string** which is a serialized Command tree
4. This string, when passed to `GameModule.decode()`, produces a Command that when `execute()`d will restore the entire game state

**The deobfuscated content is structured as:**
```
begin_save\COMMAND_SEP\
  [version check commands]\COMMAND_SEP\
  [AddPiece commands for every piece on every map]\COMMAND_SEP\
  [GameComponent restore commands (player roster, turn tracker, notes, etc.)]\COMMAND_SEP\
end_save
```

The `COMMAND_SEPARATOR` is `\x1b` (ESC character, decimal 27) at the top level (within GameModule's encode/decode). Within individual commands, fields use different separators via SequenceEncoder.

### 5.3 .vlog (Log File)

A **.vlog** file has the **identical format** to .vsav, but the serialized Command tree also includes `LogCommand` entries interleaved after the initial save state. Each LogCommand wraps a game action (move, dice roll, etc.) that can be "stepped through" during replay.

**Structure:**
```
begin_save\...\end_save\COMMAND_SEP\
  LOG\t[encoded command 1]\COMMAND_SEP\
  LOG\t[encoded command 2]\COMMAND_SEP\
  ...
```

### 5.4 The Obfuscation Layer

The `ObfuscatingOutputStream` / `DeobfuscatingInputStream` pair provide simple XOR obfuscation:
- **Header**: `!VCSK` (5 bytes ASCII)
- **Key**: 1 random byte, hex-encoded as 2 ASCII chars
- **Body**: Each byte of the plaintext is XOR'd with the key byte, then hex-encoded as 2 uppercase ASCII hex chars

This is **not encryption** -- it exists solely to prevent casual hand-editing of save files. It is trivially reversible.

**To deobfuscate a savedGame entry:**
```python
def deobfuscate(data: bytes) -> str:
    text = data.decode('utf-8')
    assert text[:5] == '!VCSK'
    key = int(text[5:7], 16)
    plaintext = []
    for i in range(7, len(text), 2):
        byte_val = int(text[i:i+2], 16) ^ key
        plaintext.append(chr(byte_val))
    return ''.join(plaintext)
```

**To obfuscate plaintext back:**
```python
import random
def obfuscate(plaintext: str) -> bytes:
    key = random.randint(0, 255)
    result = f'!VCSK{key:02x}'
    for ch in plaintext:
        result += f'{(ord(ch) ^ key):02x}'
    return result.encode('utf-8')
```

---

## 6. Module Structure (buildFile.xml)

The module is defined as a tree of `Buildable` components in XML. The root element corresponds to `GameModule`. Key child elements include:

```xml
<VASSAL.build.GameModule name="MyGame" version="1.0">
  <VASSAL.build.module.GlobalOptions/>
  <VASSAL.build.module.Map mapName="Main Map">
    <VASSAL.build.module.map.boardPicker.BoardPicker>
      <VASSAL.build.module.map.boardPicker.Board name="Board" image="board.png"/>
    </VASSAL.build.module.map.boardPicker.BoardPicker>
    <!-- grids, zones, etc. -->
  </VASSAL.build.module.Map>
  <VASSAL.build.module.PieceWindow>
    <VASSAL.build.widget.PieceSlot>
      <!-- piece definition (type string) -->
    </VASSAL.build.widget.PieceSlot>
  </VASSAL.build.module.PieceWindow>
  <VASSAL.build.module.PrototypesContainer>
    <VASSAL.build.module.PrototypeDefinition name="Infantry"/>
  </VASSAL.build.module.PrototypesContainer>
  <VASSAL.build.module.PlayerRoster>
    <!-- side definitions -->
  </VASSAL.build.module.PlayerRoster>
  <VASSAL.build.module.DiceButton name="2d6"/>
  <!-- ... -->
</VASSAL.build.GameModule>
```

---

## 7. Networking Model

### 7.1 Server-Based (Primary)

VASSAL operates a central server infrastructure via `NodeClient` / `OfficialNodeClient`. Players connect to the VASSAL server, join "rooms" organized by module. Game state synchronization happens through encoded Command strings sent over the server connection.

### 7.2 Peer-to-Peer

The `P2PClient` class enables direct connections between players without a central server. Uses `DirectPeerPool` for peer discovery.

### 7.3 Play By Email (PBEM)

The **most relevant mode for AI play**. Players take turns:
1. Load a .vsav (saved game) or .vlog (log file)
2. Make their moves (all actions are logged as Commands)
3. Save a new .vlog file and send it to the opponent
4. The opponent loads the .vlog, steps through the recorded moves, then takes their own turn

### 7.4 Hybrid Client

`HybridClient` / `DynamicClient` can switch between server modes transparently.

---

## 8. How an AI Agent Can Interact with VASSAL

### 8.1 File-Based Interaction (Most Viable)

The PBEM workflow is the natural integration point for an AI:

1. **Read a .vsav or .vlog file:**
   - Unzip the file
   - Deobfuscate the `savedGame` entry (XOR with key byte)
   - Parse the resulting ASCII command string
   - The command tree describes every piece, its position, all properties, and the full game state

2. **Understand the game state:**
   - Parse `AddPiece` commands to enumerate all pieces on all maps
   - Each piece's type string reveals its Trait stack (capabilities, images, properties)
   - Each piece's state string reveals its current state (position, dynamic property values, embellishment layers, etc.)
   - Parse other restore commands for global properties, turn tracker state, player roster, etc.

3. **Generate moves:**
   - Construct new Command strings representing the AI's moves
   - These would typically be `MovePiece` (change position) and `ChangePiece` (change state) commands
   - Append them as LOG entries after the restore state

4. **Write a new .vsav or .vlog file:**
   - Serialize the updated command tree
   - Obfuscate with XOR
   - Package into a ZIP with the `savedGame` entry and metadata

### 8.2 Parsing Piece Data

A piece's **type** string encodes its full Decorator (Trait) chain. Layers are separated by `\t` (tab), from outermost to innermost:
```
emb2;[embellishment config]\tobs;[mask config]\tpiece;[cloneKey];[deleteKey];[imageName];[pieceName]
```

Each trait type has its own prefix (e.g., `emb2;`, `obs;`, `mark;`) and serialization format. The `BasicCommandEncoder.createDecorator()` method maps type prefixes to Decorator classes. See `BasicCommandEncoder.java` for the full registry.

A piece's **state** string encodes all mutable data. Layers are also `\t`-separated, matching the type string 1:1 from outermost to innermost:
```
[embellishment state]\t[mask state]\t[mapName];[x];[y];[gpId];[basicPieceState]
```

The BasicPiece state (innermost) contains the piece's current map, pixel position, and game piece ID.

### 8.3 Limitations

- **No headless API**: VASSAL has no REST API, no headless mode, no programmatic game-play interface. It is a GUI application.
- **Module-specific**: Each game module defines its own pieces, maps, and rules. The AI must understand the specific module.
- **Rule enforcement**: VASSAL does **not** enforce game rules. It is a virtual tabletop -- players enforce rules themselves. This means the AI must independently know and apply the game's rules.
- **No built-in AI**: VASSAL has no AI player framework. Any AI must be external.

### 8.4 Practical AI Workflow

1. **Human plays their turn** in VASSAL, saves a .vsav file
2. **AI receives the .vsav**, deobfuscates and parses the game state
3. **AI analyzes the board**: piece positions (grid coordinates), unit properties (from Marker/DynamicProperty traits), terrain, turn state
4. **AI applies game rules** (from the rulebook) to determine legal moves
5. **AI selects moves** based on strategy
6. **AI generates a new .vsav** (or .vlog with logged moves) containing the updated game state
7. **Human loads the AI's save file** to see the AI's moves and take their next turn

---

## 9. Key Source Code Files Reference

| File | Purpose |
|------|---------|
| `build/GameModule.java` | Central singleton, command dispatch, encode/decode hub |
| `build/module/GameState.java` | Game state tracking, save/load (.vsav), piece registry |
| `build/module/BasicLogger.java` | VLOG logging, step-forward replay, undo system |
| `build/module/BasicCommandEncoder.java` | Maps command strings to Command objects, contains the Decorator factory |
| `command/Command.java` | Abstract base for all commands, composite pattern |
| `command/CommandEncoder.java` | Interface for serializing/deserializing Commands |
| `command/AddPiece.java` | Adds a piece to the game |
| `command/ChangePiece.java` | Changes a piece's state |
| `command/MovePiece.java` | Moves a piece |
| `command/RemovePiece.java` | Removes a piece |
| `counters/GamePiece.java` | Interface for all pieces and traits |
| `counters/BasicPiece.java` | Innermost piece (holds name, image, position, properties) |
| `counters/Decorator.java` | Abstract base for all Traits (Decorator pattern) |
| `counters/Stack.java` | Stack of pieces at one location |
| `counters/Deck.java` | Card deck (shuffleable stack) |
| `tools/DataArchive.java` | ZIP wrapper for .vmod files |
| `tools/SequenceEncoder.java` | Field-level serialization utility |
| `tools/io/ObfuscatingOutputStream.java` | XOR obfuscation for save files |
| `tools/io/DeobfuscatingInputStream.java` | XOR deobfuscation for loading saves |
| `tools/io/ZipArchive.java` | ZIP file read/write |
| `chat/node/NodeClient.java` | Server-based multiplayer client |
| `launch/Player.java` | Player mode entry point |
| `launch/Editor.java` | Editor mode entry point |

---

## 10. Building and Running

```bash
# Full build (in ./vassal/)
./mvnw clean package

# Quick compile only (skip tests, checks, docs)
./mvnw clean package -DskipTests=true -Dcheckstyle.skip=true \
  -Dspotbugs.skip=true -Dmaven.javadoc.skip=true \
  -Dasciidoctor.skip=true -Dclirr.skip=true

# Run Player mode
java -cp vassal-app/target/vassal-app-3.8.0-SNAPSHOT.jar VASSAL.launch.Player /path/to/module.vmod

# Run Editor mode
java -cp vassal-app/target/vassal-app-3.8.0-SNAPSHOT.jar VASSAL.launch.Editor --edit /path/to/module.vmod
```

---

## 11. Working with Save Files Programmatically

### 11.1 Reading a .vsav File (Python Example)

```python
import zipfile
import io

def read_vassal_save(filepath):
    """Read and deobfuscate a VASSAL save file."""
    with zipfile.ZipFile(filepath, 'r') as zf:
        with zf.open('savedGame') as f:
            data = f.read().decode('utf-8')

    # Check for obfuscation header
    if data.startswith('!VCSK'):
        key = int(data[5:7], 16)
        plaintext = []
        for i in range(7, len(data), 2):
            byte_val = int(data[i:i+2], 16) ^ key
            plaintext.append(chr(byte_val))
        return ''.join(plaintext)
    else:
        return data  # Not obfuscated (very old files)

# The returned string contains the full serialized command tree
# Split on \x1b (COMMAND_SEPARATOR = ESC) for top-level commands
commands = read_vassal_save('game.vsav').split('\x1b')
```

### 11.2 Writing a .vsav File (Python Example)

```python
import zipfile
import random

def write_vassal_save(filepath, command_string, metadata_xml=None):
    """Write an obfuscated VASSAL save file."""
    key = random.randint(0, 255)
    obfuscated = f'!VCSK{key:02x}'
    for ch in command_string:
        obfuscated += f'{(ord(ch) ^ key):02x}'

    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('savedGame', obfuscated.encode('utf-8'))
        if metadata_xml:
            zf.writestr('moduledata', metadata_xml)
```

### 11.3 Parsing the Command String

The top-level structure after deobfuscation:
```
begin_save [SEP] [subcommands...] [SEP] end_save
```

Where `[SEP]` is `\x1b` (ESC). Each subcommand is one of:
- `begin_save` / `end_save` -- game state boundaries (SetupCommand)
- `+/id/type/state` -- AddPiece (adds a piece; `id` is the piece ID, `type` is the tab-separated trait chain, `state` is the tab-separated state chain)
- `-/id` -- RemovePiece
- `D/id/newState/oldState` -- ChangePiece (changes a piece's mutable state)
- `M/id/newMapId/newX/newY/newUnderId/oldMapId/oldX/oldY/oldUnderId/playerId` -- MovePiece
- Other game component restore commands (turn tracker, player roster, notes, etc.)

The `/` character is the PARAM_SEPARATOR within these command strings (escaped via SequenceEncoder when it appears in data).

---

## 12. The SequenceEncoder Format

VASSAL's universal serialization tool. Given a separator character, it encodes multiple fields into a single string, escaping the separator and backslash characters.

**Encoding rules:**
- The delimiter character within a field is escaped as `\` + delimiter (backslash before the delimiter itself)
- Backslash is escaped as `\\`
- Null/empty fields may be represented as empty segments
- When the delimiter cannot appear in primitive-type values (numbers, booleans), escaping is skipped for performance

**Example with `;` separator:**
```
field1;field2;field3;...
```

Different command types use different separator characters at different nesting levels.

---

## 13. Analyzing Any .vmod Module File

When a .vmod file is received, the following systematic analysis procedure extracts everything needed to understand and play the game.

### 13.1 Step 1: Unpack the Archive

A .vmod is a ZIP file. Extract and inventory its contents:

```python
import zipfile, os

def unpack_vmod(vmod_path, extract_to):
    with zipfile.ZipFile(vmod_path, 'r') as zf:
        zf.extractall(extract_to)
        return zf.namelist()
```

**Expected contents:**

| Entry | Purpose |
|-------|---------|
| `buildFile.xml` (or `buildFile`) | The module definition -- **the most important file** |
| `moduledata` | XML metadata: module name, version, Vassal version |
| `images/*.png` (or `.gif`, `.jpg`, `.svg`) | Piece images, board art, icons, overlays |
| `sounds/*.wav` (or `.mp3`, `.ogg`) | Audio clips for game events |
| `help/` | Optional bundled documentation |
| `*.vsav` | Predefined setup / scenario save files embedded in the module |

### 13.2 Step 2: Parse moduledata

```xml
<data>
  <version>1.0</version>
  <VassalVersion>3.7.12</VassalVersion>
  <name>Game Name</name>
  <description>Module description text</description>
</data>
```

Extract: game name, module version, Vassal engine version it was built with.

### 13.3 Step 3: Parse buildFile.xml (The Module Definition)

This is the complete structural blueprint of the game. It is an XML tree rooted at `VASSAL.build.GameModule` (or `VASSAL.launch.BasicModule` for old modules). Parse it to extract the following:

#### 13.3.1 Module-Level Attributes

```xml
<VASSAL.build.GameModule name="Game Name" version="1.0"
    VassalVersion="3.7.12" nextPieceSlotId="1234" description="...">
```

- `name` -- game title
- `version` -- module version
- `nextPieceSlotId` -- auto-increment ID counter for piece slots (important for generating valid new pieces)

#### 13.3.2 Player Sides (PlayerRoster)

```xml
<VASSAL.build.module.PlayerRoster>
  <entry><side>Axis</side></entry>
  <entry><side>Allies</side></entry>
  <entry><side>Solo</side></entry>
</VASSAL.build.module.PlayerRoster>
```

Extract all playable sides. The AI will be assigned one of these.

#### 13.3.3 Maps and Boards

```xml
<VASSAL.build.module.Map mapName="Main Map" ...>
  <VASSAL.build.module.map.BoardPicker ...>
    <VASSAL.build.module.map.boardPicker.Board name="Board" image="board.png" .../>
  </VASSAL.build.module.map.BoardPicker>
</VASSAL.build.module.Map>
```

For each Map, extract:
- **Map name** (used in piece location data)
- **Boards** within the map (names, image filenames)
- **Grid type and geometry** (see below)
- **At-Start Stacks** (SetupStack -- pieces placed at game start)
- **Zones** (named regions with their own properties/grids)

**Private Maps** (`VASSAL.build.module.PrivateMap`) are player-specific (e.g., player hands).
**Player Hands** (`VASSAL.build.module.PlayerHand`) are special private maps.

#### 13.3.4 Grid Systems

Grids define the coordinate system for piece placement. Types:

| XML Element | Grid Type | Key Attributes |
|-------------|-----------|----------------|
| `HexGrid` | Hex grid (flat-top or pointy-top) | `dx`, `dy` (hex dimensions), `x0`, `y0` (origin offset), `sideways` (orientation), `color`, `visible` |
| `SquareGrid` | Square/rectangular grid | `dx`, `dy` (cell size), `x0`, `y0` (origin) |
| `RegionGrid` | Irregular / point-to-point | Named `Region` children with explicit `(x,y)` coordinates |
| `ZonedGrid` | Multi-zone (each zone can have its own sub-grid) | Contains `Zone` children, each with own grid |

**Grid Numbering** (sub-element of grids):
- `HexGridNumbering` / `SquareGridNumbering` / `RegularGridNumbering`
- Attributes: `stagger`, `hType` (numeric/alpha), `vType`, `hOff`, `vOff`, `hDescend`, `vDescend`, `sep` (separator like "-" or "."), `first` (row-first or column-first)

**This is critical for translating pixel coordinates (from save files) to game-meaningful locations (hex IDs, region names, etc.).**

#### 13.3.5 Piece Palettes and PieceSlots

Pieces are defined in the module's piece palette:

```xml
<VASSAL.build.module.PieceWindow ...>
  <VASSAL.build.widget.ListWidget entryName="Infantry">
    <VASSAL.build.widget.PieceSlot entryName="1st Infantry" gpId="123" height="60" width="60">
      [piece type definition string]
    </VASSAL.build.widget.PieceSlot>
  </VASSAL.build.widget.ListWidget>
</VASSAL.build.module.PieceWindow>
```

The text content of each `PieceSlot` element is the full **type string** of the piece -- the serialized Decorator chain. Parse this to understand what traits each piece has.

Each PieceSlot has a `gpId` (game piece ID) that uniquely identifies the piece definition.

#### 13.3.6 Prototypes

Prototypes are reusable trait bundles referenced by multiple pieces:

```xml
<VASSAL.build.module.PrototypesContainer>
  <VASSAL.build.module.PrototypeDefinition name="Standard Infantry" description="...">
    [trait definition string]
  </VASSAL.build.module.PrototypeDefinition>
</VASSAL.build.module.PrototypesContainer>
```

When a piece has a `UsePrototype` trait, it includes all traits from the named Prototype. **Always resolve Prototypes first** to understand the full trait stack of any piece.

#### 13.3.7 At-Start Stacks (SetupStack)

Pre-placed pieces on maps at game start:

```xml
<VASSAL.build.module.map.SetupStack name="Stack Name" owningBoard="Board"
    useGridLocation="true" location="A1" x="123" y="456">
  <VASSAL.build.widget.PieceSlot ...>
    [piece type string]
  </VASSAL.build.widget.PieceSlot>
</VASSAL.build.module.map.SetupStack>
```

These define the **initial piece layout** before any scenario setup. Extract board name, grid location or pixel coordinates, and the piece definitions.

#### 13.3.8 Predefined Setups (Scenarios)

```xml
<VASSAL.build.module.PredefinedSetup name="Scenario 1" file="setups/scenario1.vsav"
    useFile="true" isMenu="false" description="..."/>
```

These reference embedded .vsav files inside the .vmod that define specific scenario starting positions. The `file` attribute points to a save file within the ZIP archive. Parse these the same way as any .vsav (deobfuscate + decode command tree).

#### 13.3.9 Dice and Randomization

```xml
<VASSAL.build.module.DiceButton name="2d6" nDice="2" nSides="6"
    reportTotal="true" .../>
<VASSAL.build.module.SpecialDiceButton name="Combat Die">
  <VASSAL.build.module.SpecialDie ...>
    <VASSAL.build.module.SpecialDieFace .../>
  </VASSAL.build.module.SpecialDie>
</VASSAL.build.module.SpecialDiceButton>
```

Extract all dice definitions: number of dice, sides, special faces, reporting formats.

#### 13.3.10 Global Properties

```xml
<VASSAL.build.module.properties.GlobalProperties>
  <VASSAL.build.module.properties.GlobalProperty ...
      name="TurnNumber" initialValue="1" .../>
</VASSAL.build.module.properties.GlobalProperties>
```

Also at Map level and Zone level. These track game-wide state (turn number, phase, weather, etc.).

#### 13.3.11 Turn Tracker

```xml
<VASSAL.build.module.turn.TurnTracker ...>
  <VASSAL.build.module.turn.CounterTurnLevel name="Turn" start="1" .../>
  <VASSAL.build.module.turn.ListTurnLevel name="Phase">
    <VASSAL.build.module.turn.TurnLevel value="Movement"/>
    <VASSAL.build.module.turn.TurnLevel value="Combat"/>
    <VASSAL.build.module.turn.TurnLevel value="Rally"/>
  </VASSAL.build.module.turn.ListTurnLevel>
</VASSAL.build.module.turn.TurnTracker>
```

Defines the game's turn/phase structure. Extract all phases and their sequence.

#### 13.3.12 Global Key Commands

```xml
<VASSAL.build.module.GlobalKeyCommand ...
    name="Flip All" description="..." .../>
<VASSAL.build.module.StartupGlobalKeyCommand .../>
```

These define toolbar buttons that send key commands to sets of pieces matching a filter. Understand what automation the module provides.

### 13.4 Step 4: Build a Piece Catalog

After parsing buildFile.xml, construct a complete catalog:

```
For each PieceSlot and Prototype:
  1. Parse the type string into its Decorator chain
  2. Identify the BasicPiece (innermost): image name, piece name
  3. Walk outward through each Trait:
     - Marker traits: extract property name + value (these are labels like "Type=Infantry")
     - DynamicProperty traits: extract property name + initial value + possible values
     - Embellishment traits: extract layer names, images, activation keys
     - UsePrototype traits: resolve and inline the referenced Prototype
     - All other traits: note their presence and configuration
  4. Categorize the piece by its Marker values (unit type, nationality, strength, etc.)
```

**The Marker traits are the key to semantics** -- they map VASSAL pieces to game concepts. A piece with Marker keys "Type" and "Side" (set to values "HeavyInfantry" and "Roman" in the piece state) is a Roman Heavy Infantry unit. Note: in the type string (buildFile.xml), Markers contain only the property **names** (`mark;Type,Side`). The actual **values** are stored in the piece's state string and are visible when parsing save files or when inspecting pieces at runtime.

### 13.5 Step 5: Map the Image Assets

Cross-reference piece image filenames from the type strings against the `images/` directory in the .vmod:
- Board images show the playing surface (terrain, hex grid, regions)
- Piece images show unit counters, cards, markers
- Overlay images show terrain features, status markers

If provided, board images can be read visually to understand terrain layout.

### 13.6 Step 6: Extract Embedded Saves (Scenarios)

For each PredefinedSetup that references a `.vsav` file:
1. Extract the .vsav from within the .vmod ZIP
2. Deobfuscate and parse per Section 11
3. This gives the exact starting piece placement for that scenario
4. Cross-reference piece IDs from the save against the piece catalog

---

## 14. Ingesting Rulebooks, Playbooks, and Game Collateral

When the user provides game documentation (PDFs, text files, images), the following procedure builds the rule knowledge needed for AI play.

### 14.1 Document Types and What to Extract

| Document Type | What to Extract |
|--------------|-----------------|
| **Rulebook** | Turn sequence, movement rules, combat rules, stacking limits, terrain effects, supply rules, special rules, victory conditions |
| **Playbook / Scenario Book** | Scenario-specific setup (sides, OOB, special rules, victory conditions, map sections in play) |
| **Player Aid / Reference Card** | Combat Results Tables (CRT), Terrain Effects Charts (TEC), movement costs, modifiers |
| **Stacking Charts** | Maximum units per hex/location by type |
| **Errata / Living Rules** | Rule corrections and clarifications (supersede the base rulebook) |
| **Strategy Guides** | Opening strategies, tactical principles, common mistakes |
| **Order of Battle (OOB)** | Unit listings with stats (strength, movement, morale, type) |

### 14.2 Systematic Rule Extraction

For each rulebook, extract and organize:

**A. Turn Sequence of Play**
- All phases in order (e.g., Command Phase -> Movement Phase -> Combat Phase -> Rally Phase)
- What happens in each phase
- Which player acts in each phase (alternating, simultaneous, phasing/non-phasing)
- Mandatory vs. optional actions per phase

**B. Movement Rules**
- Base movement allowance by unit type
- Terrain movement costs (per terrain type per unit type)
- Road/trail bonuses
- Stacking limits (per hex/location)
- Zone of Control (ZOC) rules -- entry, exit, stopping
- Special movement (strategic movement, forced march, retreat)

**C. Combat Rules**
- How combat is initiated (mandatory, voluntary, which units)
- How odds/differential is calculated
- The Combat Results Table (CRT) -- all columns and results
- Die roll modifiers (terrain, leadership, flanking, supply)
- Result meanings (retreat, elimination, exchange, disruption, rout)
- Advance after combat rules

**D. Unit Properties**
- How to read a counter (what each number/symbol means)
- Unit types and their special capabilities
- Leader/command rules
- Morale/quality ratings

**E. Terrain**
- Terrain types and their effects on movement and combat
- Line of sight rules
- Elevation/height rules

**F. Victory Conditions**
- Per-scenario victory conditions
- Point scoring
- Sudden death conditions
- Time limits (number of turns)

### 14.3 Building a Game-Specific Knowledge Model

After extracting rules, build a structured model:

```
Game: [Name]
  Sides: [list]
  Turn Structure:
    Phase 1: [name] - [who acts] - [what happens]
    Phase 2: ...
  Unit Types:
    [Type]: movement=[n], combat=[n], morale=[n], special=[notes]
  Terrain Types:
    [Type]: move_cost=[n], combat_modifier=[n], LOS=[blocks/clear]
  CRT:
    [odds_column]: [die_results -> outcomes]
  Stacking: [max per hex]
  ZOC: [rules]
  Victory: [conditions per scenario]
```

### 14.4 Linking Module Data to Rules

The final step connects VASSAL module data to rule knowledge:

1. **Piece Markers -> Unit Stats**: A piece with `Marker("CombatStrength","6")` maps to a unit with 6 combat strength per the rules
2. **Map Grid -> Terrain**: Hex coordinates on the board image correspond to terrain types from the rules
3. **Global Properties -> Game State**: Properties like "TurnNumber", "CurrentPhase" map to the turn sequence
4. **Dice Definitions -> CRT**: The module's dice match the CRT dice requirements
5. **Embellishment Layers -> Status**: Layer states (flipped, disrupted, routed) map to rule-defined statuses

---

## 15. AI Opponent: Generic Operational Workflow

### 15.1 Game Onboarding (One-Time Per Game)

```
1. Receive .vmod file
   -> Unpack and analyze per Section 13
   -> Build piece catalog, map geometry, grid system

2. Receive rulebook/playbook PDFs
   -> Extract rules per Section 14
   -> Build game knowledge model

3. Link module to rules
   -> Map piece Markers to unit stats
   -> Map grid locations to terrain
   -> Map turn tracker to turn sequence
   -> Map dice to CRT/resolution tables

4. Produce a game-specific skill file (separate .md)
   -> Contains the game knowledge model
   -> References this VASSAL.md for engine mechanics
   -> Includes scenario-specific setup and victory conditions
```

### 15.2 Per-Turn Play Loop

```
1. Receive .vsav or .vlog from human player
   -> Deobfuscate (Section 5.4 / Section 11)
   -> Decode command tree
   -> Reconstruct full game state:
      - All pieces with positions, properties, trait states
      - Turn/phase tracker state
      - Global property values
      - Whose turn it is

2. Analyze the board position
   -> Enumerate AI's pieces and their stats
   -> Enumerate opponent's pieces and their stats
   -> Assess terrain, supply, positioning
   -> Identify threats and opportunities

3. Determine legal moves per game rules
   -> Apply movement rules (costs, ZOC, stacking)
   -> Identify mandatory actions (required attacks, etc.)
   -> Enumerate all legal options

4. Select moves based on strategy
   -> Evaluate positions (material, positional, tempo)
   -> Select best move(s) per game-appropriate heuristics
   -> Resolve any required dice rolls (generate random results, apply CRT)

5. Generate updated game state
   -> Construct Command strings for each action:
      - MovePiece commands for movement
      - ChangePiece commands for state changes (flipping, disruption, etc.)
      - AddPiece/RemovePiece for reinforcements/eliminations
   -> Update turn tracker / global properties as needed

6. Package and return
   -> Obfuscate the command string
   -> Write new .vsav (or .vlog with logged steps)
   -> Return file to human player with a summary of moves taken
```

### 15.3 What Claude Can Do

- **Parse any .vmod**: Extract buildFile.xml, enumerate all pieces, maps, grids, properties, prototypes, scenarios
- **Parse any .vsav/.vlog**: Deobfuscate, decode, reconstruct game state
- **Read rulebook PDFs**: Extract turn sequence, movement, combat, victory conditions
- **Cross-reference module + rules**: Map piece data to game semantics
- **Reason about game state**: Analyze positions, evaluate options, select moves
- **Generate valid save files**: Construct properly formatted and obfuscated .vsav output

### 15.4 Current Limitations

- **No real-time play**: Claude operates turn-by-turn via files, not through the live VASSAL GUI
- **No visual board rendering**: Claude reads piece data from serialized commands; it cannot render or "see" the graphical board. Board images can be read for terrain reference, but the authoritative game state is always the serialized data.
- **Rule ambiguity**: Complex edge cases in rules may need human adjudication
- **Module complexity**: Modules with extensive BeanShell scripting or deeply custom traits may need additional analysis
- **Dice transparency**: When the AI rolls dice, results should be reported clearly for the human to verify fairness

---

## 16. Glossary

| Term | Meaning |
|------|---------|
| **Module (.vmod)** | A ZIP containing the game definition (XML + assets) |
| **Extension (.vmdx)** | An add-on to a module (extra scenarios, pieces) |
| **Save (.vsav)** | A snapshot of the complete game state |
| **Log (.vlog)** | A save + recorded moves for step-through replay |
| **buildFile.xml** | The XML module definition inside a .vmod |
| **Trait** | A Decorator attached to a game piece providing specific behavior |
| **Prototype** | A reusable set of Traits that can be included in multiple pieces |
| **PieceSlot** | A piece definition in the module's palette |
| **GamePiece** | Any piece, trait, stack, or deck -- implements the GamePiece interface |
| **BasicPiece** | The innermost core of every piece |
| **Decorator** | The abstract base class for all Traits |
| **Command** | An object representing a game state change |
| **CommandEncoder** | Serializes/deserializes Commands to/from strings |
| **GameModule** | The singleton root of the module component tree |
| **GameState** | Manages all pieces and handles save/load |
| **BasicLogger** | Handles VLOG recording and playback |
| **Map** | A playing surface (can be multiple per module) |
| **Board** | A background image within a Map |
| **Grid** | Hex, square, region, or zoned grid overlaid on a Board |
| **HexGrid** | Hexagonal grid with `dx`/`dy` dimensions and numbering |
| **SquareGrid** | Square/rectangular grid |
| **RegionGrid** | Irregular / point-to-point grid with named Regions |
| **ZonedGrid** | Multi-zone grid where each Zone has its own sub-grid |
| **Zone** | A named region within a grid (can have its own properties) |
| **Stack** | A group of pieces at the same location |
| **Deck** | A shuffleable stack (for card games) |
| **DrawPile** | The map-level component that defines a Deck's location and behavior |
| **SetupStack** | Pieces pre-placed on a map at game start |
| **PredefinedSetup** | A scenario starting position (embedded .vsav) |
| **Global Property** | A named value accessible from anywhere (module/map/zone level) |
| **Dynamic Property** | A piece-level property that can change during play |
| **Marker** | A piece-level property -- type string has key names, state string has values (key for piece semantics) |
| **Embellishment** | A multi-state image layer on a piece |
| **Prototype** | A named, reusable bundle of Traits |
| **UsePrototype** | A Trait that includes all Traits from a named Prototype |
| **PBEM** | Play By Email -- asynchronous play via .vlog files |
| **BeanShell** | The expression language used for calculated properties and filters |
| **CRT** | Combat Results Table -- resolves combat via dice + odds/modifiers |
| **TEC** | Terrain Effects Chart -- terrain impacts on movement and combat |
| **ZOC** | Zone of Control -- hexes adjacent to enemy units with special rules |
| **OOB** | Order of Battle -- listing of all units and their stats for a scenario |
| **gpId** | Game Piece ID -- unique identifier for a piece definition in the module |
