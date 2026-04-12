# SETUP -- Getting started with VAS on any machine

Cross-platform setup guide for the VAS (VASSAL AI System) framework.
Works on macOS, Windows, and Linux.

## Prerequisites

| Component | Purpose | Where to get it |
|---|---|---|
| **Python 3.10+** | Run the AI scripts | python.org or `brew install python3` (Mac) / Microsoft Store (Windows) |
| **Git** | Clone repos | git-scm.com |
| **VASSAL 3.7+** | Play the game, load .vsav/.vlog | vassalengine.org (Java app, all platforms) |
| **Game .vmod** | The VASSAL module for your game | Publisher website or VASSAL module library |

## Installation

### 1. Clone the repos

```bash
# Framework (public)
git clone https://github.com/tliakos/vas.git
cd vas

# Game-specific AI (private -- requires access)
git clone https://github.com/tliakos/vasai-games.git games
```

### 2. Place game files

VASSAL module files (.vmod) and rulebook PDFs are NOT tracked in git
(they're large and copyrighted). Place them manually:

```bash
# Example for SPQR:
cp ~/Downloads/SPQR_Deluxe_v2.9alt.vmod games/SPQR/
cp ~/Downloads/SPQR_rulebook.pdf games/SPQR/          # optional
```

### 3. Verify the setup

```bash
# Quick check: import the framework
python3 -c "from vassal_framework import ModuleGrid; print('OK')"

# Full validation of a game:
python3 -m vassal_framework.validation SPQR --save games/SPQR/scenarios/heraclea/hera-004.vsav
```

## How to play against the AI

### The play loop

```
1. VASSAL: Load your scenario (.vsav)
2. VASSAL: Play YOUR turn (move units, resolve combat, save)
3. AI:     Run the AI on the saved file
4. VASSAL: Load the AI's .vlog to step through its moves
5. VASSAL: Load the AI's .vsav to continue from the post-AI state
6. Go to step 2
```

### Running the AI

**Option A: Run Python scripts directly (no API key needed)**

The AI logic is baked into the game-specific Python code. Just run it:

```bash
# Analyze a leader's activation
python3 -m games.SPQR.spqr_lib.runner games/SPQR/scenarios/heraclea/hera-004.vsav Falco

# Run a full turn with combat resolution, dice, pursuit, rout movement
python3 games/SPQR/scenarios/heraclea/run_falco_turn.py
```

Output:
- `roman_falco.vsav` -- board state after AI's moves (load to continue)
- `roman_falco.vlog` -- step-through game log with dice, moves, state changes
- `roman_moves.json` -- machine-readable order data

**Option B: Interactive with Claude Code (more flexible)**

Claude Code can read saves, reason about the board, and handle novel
situations the scripts don't cover yet.

| Platform | How to get Claude Code |
|---|---|
| **macOS / Windows** | Download desktop app from claude.ai/download |
| **Browser** | Go to claude.ai/code (no install) |
| **Terminal (Mac/Linux/WSL)** | `npm install -g @anthropic-ai/claude-code` |

Then open Claude Code in the `vas/` directory and ask:

> "Load hera-005.vsav and play the Epirote turn. Write roman_falco.vsav."

Claude Code reads the save through the framework, makes tactical decisions
using the SPQR-specific AI module, and generates the output files.

Requires: Anthropic API key or Claude subscription.

### Loading the AI's output in VASSAL

1. **Open VASSAL** and load the game module (.vmod)
2. **File > Load Saved Game** -- choose `roman_falco.vlog`
3. **Step Forward** (arrow key or button) to replay each command:
   - Dice rolls execute via MutableProperty updates
   - Pieces move via M/ commands
   - COH Hits change via D/ commands
   - Chat narration explains each step with rule references
4. When done reviewing, **File > Load Saved Game** -- choose `roman_falco.vsav`
5. Continue playing from the post-AI board state

## Windows-specific notes

- Use **PowerShell** or **Command Prompt** for running scripts
- Replace `/` with `\` in file paths:
  ```powershell
  python games\SPQR\spqr_lib\runner.py games\SPQR\scenarios\heraclea\hera-004.vsav Falco
  ```
- If `python3` is not found, try `python` (Windows installs as `python`)
- For Claude Code CLI on Windows, use **WSL** (Windows Subsystem for Linux):
  ```powershell
  wsl --install
  # Then in WSL:
  npm install -g @anthropic-ai/claude-code
  ```
- The desktop app and web app work natively on Windows

## What the .vlog contains

The AI-generated .vlog file is a proper VASSAL game log with executable
commands, not just text. When you step through it in VASSAL:

| Command | What happens in VASSAL |
|---|---|
| `MutableProperty` | Dice roll result updates (Pre Shock, Shock Att, TQ Check) |
| `D/` (ChangePiece) | COH Hit markers appear on damaged units |
| `M/` (MovePiece) | Pieces physically move (pursuit, rout movement) |
| `CHAT` | Narration with rule references (8.41, 8.42, 8.45, etc.) |

## Onboarding a new game

See `ONBOARDING.md` and `STARTHERE.md` for details. Quick summary:

1. Place the .vmod in `games/<GameName>/`
2. Run the auto-generator: `python3 -m vassal_framework.autogen <GameName>`
3. Customize the generated `<game>_lib/` modules (terrain, combat, units)
4. Add `sequences.py`, `tactics.py`, `optional_rules.py` for full AI
5. Validate: `python3 -m vassal_framework.validation <GameName>`

## Project structure

```
vas/                          -- Framework (public repo: tliakos/vas)
├── vassal_framework/         -- Generic hex math, save parsing, AI engine
├── vassal_move.py            -- Legacy move generator
├── SETUP.md                  -- This file
├── ONBOARDING.md             -- How to add a new game
├── STARTHERE.md              -- Quick orientation
└── games/                    -- Game-specific AI (private repo: tliakos/vasai-games)
    └── SPQR/
        ├── spqr_lib/         -- Python AI: terrain, combat, sequences, tactics
        ├── scenarios/        -- .vsav, .vlog, INTEL.md
        └── SPQR.md           -- Game overview
```
