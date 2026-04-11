# VASSAL AI Opponent Framework

An AI opponent system for [VASSAL](https://vassalengine.org) board games. Uses Claude as the AI engine to analyze game state, apply game rules, and play turns with full explainability.

## What It Does

- Parses any VASSAL module (.vmod) and extracts all game components
- Reads/writes save files (.vsav) and log files (.vlog)
- Plays as an AI opponent in hex-and-counter wargames
- Explains every move with rule references and strategic reasoning
- Learns from each session and improves across scenarios and games

## Three Ways to Play

| Mode | Tool | How It Works |
|------|------|-------------|
| **File Exchange** | Manual | Human saves .vsav, gives to Claude, Claude returns .vsav |
| **PBEM / Hot-Seat** | `vassal_pbem.py` | Automated turn processing via save files (email, shared folder, or watch mode) |
| **Live Server** | `vassal_bridge.py` | Connects to the VASSAL server for real-time online play |

## Quick Start

```bash
# 1. Set up a game
mkdir -p games/MyGame
# Copy your .vmod and rulebook PDFs into games/MyGame/

# 2. Analyze the module
python3 vmod_analyzer.py games/MyGame/MyGame.vmod

# 3. Ask Claude to create the game-specific context file
#    (provide the analyzer output + rulebook PDFs)

# 4. Play
#    Option A: File exchange (give Claude a .vsav, get one back)
#    Option B: PBEM auto-process
python3 vassal_pbem.py turn --input game.vsav --output ai_turn.vsav --side "Opponent"
#    Option C: Live server
python3 vassal_bridge.py --module "MyGame" --player "Claude_AI" --room "AI Game"
```

See `STARTHERE.md` for the full step-by-step guide.

## Project Structure

```
README.md               You are here
STARTHERE.md            Full onboarding guide
ONBOARDING.md           How knowledge flows across games (READ BEFORE ADDING GAMES)
VASSAL.md               VASSAL engine deep context
LEARNING.md             Hex & counter wargame knowledge base (static baseline)
INTEL.md                Cross-game intelligence (grows with each game/session)
vmod.md                 Module/save analysis skill reference

vassal_framework/       PURE FRAMEWORK PACKAGE (no game-specific code)
  __init__.py
  grid.py               Hex/square grid math
  units.py              Unit detection and battlefield queries
  terrain.py            TerrainSystem abstract base
  combat.py             CombatSystem abstract base
  montecarlo.py         Probabilistic outcome simulation
  ai.py                 AI decision engine
  save_io.py            .vsav/.vlog read/write
  templates/            Starter files for new games
    terrain_template.py
    combat_template.py
    units_template.py
    runner_template.py

vmod_analyzer.py        Standalone .vmod analyzer
vassal_bridge.py        Live server bridge (TCP)
vassal_pbem.py          PBEM / hot-seat turn manager
vassal_*.py             Compatibility shims for old imports

games/                  GAME DIRECTORIES (gitignored)
  <GameName>/
    <gamename>_lib/     Game-specific Python package
      __init__.py
      terrain.py        Inherits TerrainSystem
      combat.py         Inherits CombatSystem
      units.py          Side classifier + unit type maps
      runner.py         CLI runner
    <GameName>.vmod
    <GameName>.md       Game-specific context document
    INTEL.md            Cross-scenario intelligence
    SESSION.md          Session log
    scenarios/
      <ScenarioName>/
        INTEL.md
    *.pdf
```

## Explainability

Every AI action is logged per-phase with:
- **Rule reference**: Specific rule number (e.g., "8.41: Shock Combat procedure")
- **Reasoning**: Why this move (strategic and tactical rationale)
- **Outcome**: Dice results, combat resolution, resulting game state
- **Assessment**: Position improved or deteriorated, lessons learned

The opponent can read the full session log and understand exactly what the AI did and why.

## Intelligence System

Three-tier learning hierarchy:
1. **Scenario INTEL** -- What worked in a specific battle
2. **Game INTEL** -- Patterns across scenarios of the same game
3. **Root INTEL** -- Universal patterns across all games

Insights flow upward. The AI gets smarter with every session played.

## Requirements

- Python 3.6+
- VASSAL 3.7+ (for the human player side)
- No additional Python packages required (uses only stdlib)

## Onboarded Games

Games are user-supplied (gitignored). See `INTEL.md` Game Log for the current registry.

## License

The framework code is provided as-is. VASSAL is LGPLv2. Game modules and rulebooks are property of their respective publishers.
