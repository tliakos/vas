#!/usr/bin/env python3
"""
TEMPLATE: WW2 unit type schemas (Allied vs Axis).

For games with WW2 nationalities. Adjust prefixes to match your game's
image filename conventions.
"""

# Allied unit prefixes (US, UK, Soviet, French, etc.)
ALLIED_PREFIXES = [
    'US-', 'UK-', 'GB-', 'SU-', 'FR-', 'PL-', 'CA-', 'AU-', 'NZ-',
]

# Axis unit prefixes (German, Italian, Japanese, etc.)
AXIS_PREFIXES = [
    'GE-', 'IT-', 'JP-', 'HU-', 'RO-', 'FN-', 'BG-',
]

WW2_UNIT_TYPES = {
    'INF': 'Infantry',
    'INF-MTN': 'Mountain Infantry',
    'INF-PARA': 'Paratrooper',
    'INF-MAR': 'Marine',
    'INF-SS': 'SS Infantry',
    'INF-VOLK': 'Volksgrenadier',
    'INF-GRD': 'Guards Infantry',
    'CAV': 'Cavalry',
    'MECH': 'Mechanized Infantry',
    'ARM': 'Armor',
    'ARM-LT': 'Light Tank',
    'ARM-MED': 'Medium Tank',
    'ARM-HVY': 'Heavy Tank',
    'TD': 'Tank Destroyer',
    'AT': 'Anti-Tank',
    'ARTY': 'Artillery',
    'ARTY-LT': 'Light Artillery',
    'ARTY-MED': 'Medium Artillery',
    'ARTY-HVY': 'Heavy Artillery',
    'AAA': 'Anti-Aircraft',
    'ENG': 'Engineer',
    'REC': 'Reconnaissance',
    'HQ': 'Headquarters',
    'AIR-FTR': 'Fighter',
    'AIR-BMR': 'Bomber',
    'AIR-FB': 'Fighter-Bomber',
    'NAV': 'Naval',
}

# Estimated unit stats by type (for Monte Carlo simulation)
WW2_UNIT_STATS = {
    'INF':       {'strength': 4, 'morale': 5, 'rout_points': 4},
    'INF-MTN':   {'strength': 4, 'morale': 6, 'rout_points': 4},
    'INF-PARA':  {'strength': 5, 'morale': 7, 'rout_points': 5},
    'INF-MAR':   {'strength': 5, 'morale': 6, 'rout_points': 5},
    'INF-SS':    {'strength': 5, 'morale': 8, 'rout_points': 5},
    'INF-GRD':   {'strength': 5, 'morale': 7, 'rout_points': 5},
    'CAV':       {'strength': 3, 'morale': 5, 'rout_points': 3},
    'MECH':      {'strength': 5, 'morale': 6, 'rout_points': 5},
    'ARM':       {'strength': 6, 'morale': 6, 'rout_points': 6},
    'ARM-LT':    {'strength': 4, 'morale': 5, 'rout_points': 4},
    'ARM-MED':   {'strength': 6, 'morale': 6, 'rout_points': 6},
    'ARM-HVY':   {'strength': 8, 'morale': 7, 'rout_points': 8},
    'TD':        {'strength': 5, 'morale': 5, 'rout_points': 5},
    'AT':        {'strength': 3, 'morale': 5, 'rout_points': 3},
    'ARTY':      {'strength': 4, 'morale': 4, 'rout_points': 4},
    'AAA':       {'strength': 2, 'morale': 4, 'rout_points': 2},
    'ENG':       {'strength': 3, 'morale': 6, 'rout_points': 3},
    'REC':       {'strength': 2, 'morale': 6, 'rout_points': 2},
    'HQ':        {'strength': 1, 'morale': 7, 'rout_points': 10},
}


def allied_axis_classifier(image_filename):
    """Classify a piece as Allied or Axis based on image filename prefix."""
    if not image_filename:
        return 'Unknown'
    for prefix in ALLIED_PREFIXES:
        if image_filename.startswith(prefix):
            return 'Allied'
    for prefix in AXIS_PREFIXES:
        if image_filename.startswith(prefix):
            return 'Axis'
    return 'Unknown'


def get_unit_stats(unit_type_code):
    """Get estimated unit stats for AI simulation."""
    return WW2_UNIT_STATS.get(unit_type_code, {
        'strength': 4, 'morale': 5, 'rout_points': 4,
    })
