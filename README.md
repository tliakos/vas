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
STARTHERE.md            Full onboarding guide (start here for detailed steps)
VASSAL.md               VASSAL engine deep context (architecture, file formats)
LEARNING.md             Hex & counter wargame knowledge base (static baseline)
INTEL.md                Cross-game intelligence (grows with each game and session)
vmod.md                 Module/save analysis skill reference
vmod_analyzer.py        Automated .vmod module analyzer
vassal_bridge.py        Live server bridge (TCP protocol client)
vassal_pbem.py          PBEM / hot-seat turn manager
games/                  Game directories (one per game, gitignored)
  <GameName>/
    <GameName>.vmod     VASSAL module file
    <GameName>.md       Game rules, units, terrain, AI strategy
    INTEL.md            Cross-scenario intelligence for this game
    SESSION.md          Turn-by-turn session log with explainability
    scenarios/          Per-scenario intelligence
    *.pdf               Rulebooks, playbooks, charts
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

## Currently Onboarded Games

| Game | System | Status |
|------|--------|--------|
| SPQR | Great Battles of History (GBoH) | Onboarded, ready to play |

## License

The framework code is provided as-is. VASSAL is LGPLv2. Game modules and rulebooks are property of their respective publishers.
