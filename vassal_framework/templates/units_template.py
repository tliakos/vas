#!/usr/bin/env python3
"""
TEMPLATE: Game-specific unit classification.

Copy this file to games/<GameName>/<game>_lib/units.py and customize:
1. Define which image filename prefixes belong to which side
2. Define unit type code mappings
3. Define estimated unit stats (until counter image parsing is built)

Refer to games/SPQR/spqr_lib/units.py for a complete example.
"""

# Image filename prefixes that identify "your side" pieces
# Adjust based on your game's image naming conventions
MY_SIDE_PREFIXES = [
    'US-',      # US units in WW2 games
    'UK-',      # British units
    # Add more as needed
]

# Map unit type codes to human-readable names
MY_GAME_UNIT_TYPES = {
    'INF': 'Infantry',
    'CAV': 'Cavalry',
    'ARM': 'Armor',
    'ARTY': 'Artillery',
    'HQ': 'Headquarters',
    # Add more as needed
}

# Estimated unit stats (used by AI Monte Carlo until counter parsing is built)
# Adjust to match your game's actual stat ranges
MY_GAME_UNIT_STATS = {
    'INF': {'strength': 4, 'morale': 5, 'rout_points': 4},
    'CAV': {'strength': 3, 'morale': 6, 'rout_points': 3},
    'ARM': {'strength': 6, 'morale': 6, 'rout_points': 6},
    'ARTY': {'strength': 5, 'morale': 4, 'rout_points': 5},
    'HQ': {'strength': 2, 'morale': 7, 'rout_points': 10},
}


def my_game_side_classifier(image_filename):
    """Classify a piece by side from its image filename.

    Returns: 'MySide' or 'OpponentSide' (or your game's side names)
    """
    if not image_filename:
        return 'Unknown'
    for prefix in MY_SIDE_PREFIXES:
        if image_filename.startswith(prefix):
            return 'MySide'
    return 'OpponentSide'


def get_unit_stats(unit_type_code):
    """Get estimated unit stats for AI simulation."""
    return MY_GAME_UNIT_STATS.get(unit_type_code, {
        'strength': 4, 'morale': 5, 'rout_points': 4,
    })


# Per-board grid calibration (max_cols for descend math)
# Use vassal_grid.calibrate_max_columns() against known starting positions
# from the scenario book to find the correct value for each board.
MY_BOARD_MAX_COLS = {
    # 'BoardName': max_columns_value,
}


def calibrate_grid(module_grid):
    """Apply game-specific grid calibration to a ModuleGrid."""
    for map_name, boards in module_grid.maps.items():
        for board_name, board in boards.items():
            if board.grid and board_name in MY_BOARD_MAX_COLS:
                board.grid.max_cols = MY_BOARD_MAX_COLS[board_name]
                board.grid.max_rows = MY_BOARD_MAX_COLS[board_name]
    return module_grid
