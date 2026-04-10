# STARTHERE.md -- Quick Start Guide

Set up any VASSAL game for AI-assisted play in 4 steps.

---

## Prerequisites

- Python 3 installed
- This repository cloned / files present
- VASSAL installed (for human player side)

---

## Step 1: Gather Your Game Files

Create a directory for your game under this project:

```
mkdir -p /Users/thomasliakos/vas/games/<GameName>/
```

Place the following files in that directory:

| File | Required | Description |
|------|----------|-------------|
| `*.vmod` | **Yes** | The VASSAL module file for the game |
| Rules PDF(s) | **Yes** | The game's rulebook (living rules preferred) |
| Scenario / Playbook PDF | Recommended | Scenario setups, victory conditions, OOB |
| Player aids / Charts | Recommended | CRT, TEC, stacking charts, reference cards |
| Errata | If available | Rule corrections (supersede the rulebook) |

Example:
```
games/MyWargame/
  MyWargame.vmod
  MyWargame_Rules.pdf
  MyWargame_Scenarios.pdf
  MyWargame_Charts.pdf
```

---

## Step 2: Analyze the Module

Run the analyzer on the .vmod file:

```bash
python3 /Users/thomasliakos/vas/vmod_analyzer.py games/<GameName>/*.vmod
```

This outputs:
- Game name and version
- Player sides
- Maps, boards, grids (hex/square/region)
- All piece definitions with traits and properties
- Prototypes
- Scenarios (predefined setups)
- Dice, global properties, turn tracker

For machine-readable output:
```bash
python3 /Users/thomasliakos/vas/vmod_analyzer.py games/<GameName>/*.vmod --json > games/<GameName>/analysis.json
```

---

## Step 3: Generate the Game-Specific Skill File

Ask Claude to create a `<GameName>.md` file by providing:

1. The vmod analyzer output (from Step 2)
2. The rulebook PDF(s)
3. The scenario/playbook PDF(s)

Prompt:
> "Analyze this module and these rulebooks. Create a game-specific .md file following the template in LEARNING.md Section 10. Cross-reference the module's pieces and properties with the rulebook's unit stats, terrain, and combat rules."

Claude will:
- Produce a `<GameName>.md` in `games/<GameName>/` with:
  - Turn sequence mapped to the module's TurnTracker
  - Unit catalog (module pieces linked to rulebook stats)
  - Terrain effects (grid geometry + rulebook TEC)
  - Combat rules (CRT + modifiers)
  - Scenario setups and victory conditions
  - AI strategy notes
- **Update LEARNING.md** -- append a Game Log entry (Section 12) and expand any baseline sections with new mechanics, terrain types, or AI insights from this game

---

## Step 4: Play

### Play Mode A: File Exchange (Manual)

The simplest mode. Human and AI trade save files.

**Human Turn:**
1. Open VASSAL, load the .vmod module
2. Start a new game or load a scenario
3. Play your turn, then save: File > Save Game As > `games/<GameName>/current.vsav`

**AI Turn:**
4. Give Claude the save file:
   > "Here is the current save file. Play the AI's turn as [side]."
5. Claude analyzes, plays with full explainability, and returns a new .vsav
6. Load the AI's save in VASSAL to see its moves
7. Repeat

### Play Mode B: PBEM / Hot-Seat (Automated)

`vassal_pbem.py` manages turn exchange via save files with three sub-modes:

```bash
# Analyze a save file (see what's in it)
python3 vassal_pbem.py info games/SPQR/current.vsav

# Process a single AI turn
python3 vassal_pbem.py turn --input current.vsav --output ai_response.vsav --side "Carthaginian"

# Watch a folder and auto-process new saves as they appear
python3 vassal_pbem.py watch --dir games/SPQR/ --side "Carthaginian"
```

**PBEM workflow (email/share):**
1. Human plays turn in VASSAL, saves `turn3_human.vsav`
2. Sends the file (email, shared drive, Discord, etc.)
3. Run: `python3 vassal_pbem.py turn --input turn3_human.vsav --output turn3_ai.vsav --side "Carthaginian"`
4. The tool extracts game state and writes an analysis JSON for Claude to process
5. Claude generates moves, writes the response .vsav
6. Send `turn3_ai.vsav` back to the human

**Hot-seat workflow (same machine):**
1. Both players share a `games/<GameName>/` folder
2. Human saves to the folder after their turn
3. `vassal_pbem.py watch` detects the new save and auto-prepares the AI turn
4. Claude processes it and writes the response
5. Human loads the response in VASSAL

### Play Mode: Live Server

VASSAL supports live online play via its server. `vassal_bridge.py` connects to a VASSAL server as a player, enabling real-time AI play.

**Start the bridge:**
```bash
# Connect to the official VASSAL server
python3 vassal_bridge.py --module "SPQR" --player "Claude_AI" --room "AI Game"

# Connect to a local/private server
python3 vassal_bridge.py --module "SPQR" --player "Claude_AI" --host localhost --port 5050

# Listen-only mode (observe and log commands)
python3 vassal_bridge.py --module "SPQR" --player "Observer" --listen-only --log game.log
```

**How it works:**
1. The bridge connects to the VASSAL server (default: game.vassalengine.org:5050) using the same TCP protocol as the VASSAL client
2. It registers as a player and joins a room
3. The human player opens VASSAL normally and joins the same room
4. When the human makes moves, the bridge receives the encoded Command strings
5. Claude processes the commands (same format as save files) and generates response moves
6. The bridge sends the AI's commands back through the server
7. The human's VASSAL client receives and executes them in real-time

**Protocol:** Text-based TCP on port 5050. Messages are line-delimited. Game commands travel via `FWD\t<path>\t<message>` frames. Large messages are zlib-compressed and base64-encoded (prefixed `!ZIP!`). The bridge handles all encoding/compression transparently.

**Bridge commands (interactive):**
- `/join <room>` -- Join a different room
- `/chat <message>` -- Send a chat message (appears in VASSAL chat window)
- `/log` -- Show received command count
- `/dump` -- Display the last received command
- `/quit` -- Disconnect

**For programmatic use** (from Claude or another script):
```python
from vassal_bridge import VassalBridge

bridge = VassalBridge(
    host="game.vassalengine.org", port=5050,
    module_name="SPQR", player_name="Claude_AI", room_name="AI Game",
    on_game_command=lambda cmd: process_opponent_move(cmd),
)
bridge.connect()
bridge.send_game_command(ai_move_command_string)
```

### Explainability

Every AI action is logged with:
- **Rule reference**: The specific rule number justifying the action
- **Reasoning**: WHY the AI chose this move (strategic/tactical rationale)
- **Alternatives considered**: What other options existed and why they were rejected
- **Outcome**: What happened (dice results, Cohesion Hits, routs, etc.)

This makes the AI a transparent, auditable opponent. The full session log (with per-phase detail) is in `games/<GameName>/SESSION.md`.

---

## File Reference

| File | Purpose |
|------|---------|
| `STARTHERE.md` | This guide (you are here) |
| `VASSAL.md` | Deep VASSAL engine context (architecture, file formats, commands) |
| `vmod.md` | Operational skill for .vmod/.vsav/.vlog analysis |
| `vmod_analyzer.py` | Python script to auto-analyze any .vmod |
| `vassal_bridge.py` | Python bridge for live server play (connects to VASSAL server) |
| `vassal_pbem.py` | PBEM / hot-seat turn manager (process turns via save files) |
| `LEARNING.md` | Hex & counter wargame knowledge base (static baseline) |
| `INTEL.md` | Cross-game intelligence accumulator (grows with every game and session) |
| `games/<GameName>/<GameName>.md` | Game-specific rules, units, terrain, strategy (you create per game) |
| `games/<GameName>/INTEL.md` | Cross-scenario intelligence for that game (grows with play) |
| `games/<GameName>/SESSION.md` | Turn-by-turn session log |
| `games/<GameName>/scenarios/<Name>/INTEL.md` | Per-scenario learnings (grows per battle) |
| `games/<GameName>/*.vmod` | VASSAL module for the game |
| `games/<GameName>/*.pdf` | Rulebooks, playbooks, charts |
| `games/<GameName>/*.vsav` | Save files exchanged during play |

---

## Directory Structure

```
vas/
  STARTHERE.md            <-- You are here
  VASSAL.md               <-- Engine deep context
  vmod.md                 <-- Module/save analysis skill
  vmod_analyzer.py        <-- Automated analyzer
  LEARNING.md             <-- Wargame knowledge base
  vassal/                 <-- VASSAL engine source code
  games/
    <GameName>/
      <GameName>.vmod     <-- Module file
      <GameName>.md       <-- Game-specific AI context
      INTEL.md            <-- Cross-scenario intelligence (grows with play)
      SESSION.md          <-- Turn-by-turn session log
      scenarios/
        <ScenarioName>/
          INTEL.md         <-- Per-scenario learnings
      *.pdf               <-- Rules, scenarios, charts
      current.vsav        <-- Active game save
```
