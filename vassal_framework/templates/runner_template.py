#!/usr/bin/env python3
"""
TEMPLATE: Game-specific AI runner.

Copy this file to games/<GameName>/<game>_lib/runner.py and customize:
1. Update the imports to use your game's lib
2. Update find_vmod() if needed
3. Update analyze_leader() with any game-specific output

Refer to games/SPQR/spqr_lib/runner.py for a complete example.
"""

import sys
import os

# Add project root to path so framework imports work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vassal_framework import (
    ModuleGrid, GameState, UnitScanner, Battlefield, detect_active_boards,
    AIDecisionEngine,
)

# Replace MyGame with your game name
from games.MyGame.mygame_lib.terrain import MyGameTerrain
from games.MyGame.mygame_lib.combat import MyGameCombat
from games.MyGame.mygame_lib.units import (
    my_game_side_classifier, calibrate_grid,
)


def find_vmod(game_dir='games/MyGame'):
    """Auto-detect the .vmod in the game directory."""
    full_dir = os.path.join(PROJECT_ROOT, game_dir)
    for f in os.listdir(full_dir):
        if f.endswith('.vmod'):
            return os.path.join(full_dir, f)
    return None


def analyze(save_path, leader_name=None, mc_iterations=300):
    """Run AI analysis on a save file."""
    vmod_path = find_vmod()
    if not vmod_path:
        print("ERROR: No .vmod found")
        return

    # Load game state
    mg = ModuleGrid.from_vmod(vmod_path)
    calibrate_grid(mg)

    state = GameState()
    state.load_from_file(save_path)

    # Scan units with game-specific side classifier
    scanner = UnitScanner(
        mg,
        active_boards=detect_active_boards(state),
        side_classifier=my_game_side_classifier,
    )
    units = scanner.scan(state)
    bf = Battlefield(units)

    # Show summary
    bf.summarize()

    # Game-specific systems + AI
    terrain = MyGameTerrain()
    combat = MyGameCombat()
    ai = AIDecisionEngine(
        combat_system=combat,
        terrain_system=terrain,
        mc_iterations=mc_iterations,
    )

    # Analyze leaders
    if leader_name:
        leader = next((l for l in bf.leaders() if leader_name.lower() in l.name.lower()), None)
        if leader:
            options = ai.evaluate_leader_turn(bf, leader, max_options=5)
            for i, opt in enumerate(options):
                print(f"{i+1}. {opt.name} EV={opt.expected_value:.2f}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 -m games.MyGame.mygame_lib.runner <save.vsav> [leader]")
        sys.exit(1)
    analyze(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
