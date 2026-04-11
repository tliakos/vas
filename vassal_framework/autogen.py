#!/usr/bin/env python3
"""
VASSAL Game Library Auto-Generator.

Takes a .vmod file, analyzes its structure, and generates a complete
games/<GameName>/<game>_lib/ Python package customized to what it found.

What gets auto-generated:
- terrain.py: starter terrain types based on detected game era
- combat.py: combat system stub matching the detected pattern
- units.py: side classifier with detected unit prefixes, unit type maps
- runner.py: CLI wiring
- __init__.py: package init
- <GameName>.md: game context document
- INTEL.md: cross-scenario intelligence stub
- SESSION.md: session log template
- scenarios/ directory

What requires manual completion (marked with TODO):
- Movement costs (need rulebook)
- Combat resolution tables (need rulebook)
- Victory conditions (need rulebook)
- Specific scenario calibrations

Usage:
    python3 -m vassal_framework.autogen <path/to/game.vmod> [--name GameName]
    python3 -m vassal_framework.autogen games/SPQR/SPQR_Deluxe_v2.9alt.vmod --name SPQR2
"""

import os
import sys
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

# Allow standalone execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from vassal_framework.grid import ModuleGrid


# ---------------------------------------------------------------------------
# Game system family detection
# ---------------------------------------------------------------------------

# Patterns that suggest specific game system families
SYSTEM_FAMILY_PATTERNS = {
    'GBoH': {
        'keywords': ['cohesion', 'troop quality', 'momentum', 'tq check',
                     'shock', 'phalanx', 'hastati', 'principes'],
        'description': 'Great Battles of History (ancients with cohesion shock)',
        'combat_type': 'cohesion_shock',
        'reference_game': 'SPQR',
    },
    'OCS': {
        'keywords': ['supply', 'fuel', 'ammo', 'truck', 'sp', 'reserve mode'],
        'description': 'Operational Combat Series (WWII operational with supply)',
        'combat_type': 'odds_crt',
        'reference_game': 'OCS_Tunisia',
    },
    'SCS': {
        'keywords': ['standard combat series'],
        'description': 'Standard Combat Series (operational simplified)',
        'combat_type': 'odds_crt',
        'reference_game': 'SCS_Bastogne',
    },
    'ASL': {
        'keywords': ['squad', 'morale', 'broken', 'fanatic', 'leader',
                     'firepower', 'ifp', 'ife'],
        'description': 'Advanced Squad Leader (tactical WWII)',
        'combat_type': 'ifd',
        'reference_game': 'ASL_StarterKit',
    },
    'CDG': {
        'keywords': ['op points', 'event card', 'reshuffle', 'discard'],
        'description': 'Card-Driven Game',
        'combat_type': 'card',
        'reference_game': 'PathsOfGlory',
    },
    'COIN': {
        'keywords': ['eligibility', 'faction', 'limited op', 'support',
                     'opposition', 'population', 'propaganda round'],
        'description': 'Counterinsurgency (4-faction asymmetric)',
        'combat_type': 'card',
        'reference_game': 'Cuba_Libre',
    },
    'CWBS': {
        'keywords': ['fatigue', 'straggler', 'brigade', 'wing', 'corps'],
        'description': 'Civil War Brigade Series',
        'combat_type': 'odds_crt',
        'reference_game': 'CWBS_Gettysburg',
    },
    'GENERIC_OPERATIONAL': {
        'keywords': ['movement allowance', 'combat strength', 'zoc'],
        'description': 'Generic operational wargame',
        'combat_type': 'odds_crt',
        'reference_game': None,
    },
}


def detect_system_family(metadata, buildfile_xml):
    """Detect which game system family a vmod most likely belongs to.

    Searches the metadata description and buildFile content for
    family-specific keywords.
    """
    text = (metadata.get('description', '') + ' ' +
            metadata.get('name', '') + ' ' +
            buildfile_xml[:50000]).lower()

    scores = {}
    for family, info in SYSTEM_FAMILY_PATTERNS.items():
        score = sum(1 for kw in info['keywords'] if kw in text)
        if score > 0:
            scores[family] = score

    if not scores:
        return 'GENERIC_OPERATIONAL'

    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Vmod analysis for autogen
# ---------------------------------------------------------------------------

def analyze_vmod(vmod_path):
    """Extract everything autogen needs from a vmod file."""
    with zipfile.ZipFile(vmod_path) as zf:
        # Module metadata
        metadata = {}
        if 'moduledata' in zf.namelist():
            md_xml = zf.read('moduledata').decode('utf-8', errors='replace')
            try:
                root = ET.fromstring(md_xml)
                for child in root:
                    metadata[child.tag] = (child.text or '').strip()
            except ET.ParseError:
                pass

        # Build file
        bf_name = 'buildFile.xml' if 'buildFile.xml' in zf.namelist() else 'buildFile'
        buildfile_xml = zf.read(bf_name).decode('utf-8', errors='replace')

        # Image filenames -- used to detect unit type prefixes
        image_files = [n for n in zf.namelist() if n.startswith('images/')]
        image_basenames = [os.path.basename(f) for f in image_files]

    # Module grid
    module_grid = ModuleGrid.from_vmod(vmod_path)

    # Detect system family
    family = detect_system_family(metadata, buildfile_xml)

    # Detect unit type prefixes from image filenames
    # Look for patterns like "LG-", "RC-", "INF-"
    prefix_pattern = re.compile(r'^([A-Z]{2,4})[-_]')
    prefix_counter = Counter()
    for img in image_basenames:
        m = prefix_pattern.match(img)
        if m:
            prefix_counter[m.group(1)] += 1

    common_prefixes = [p for p, c in prefix_counter.most_common(20) if c >= 3]

    # Detect player sides from PlayerRoster
    sides = []
    side_pattern = re.search(
        r'<VASSAL\.build\.module\.PlayerRoster[^>]*>(.*?)</VASSAL\.build\.module\.PlayerRoster>',
        buildfile_xml, re.DOTALL
    )
    if side_pattern:
        roster = side_pattern.group(1)
        sides = re.findall(r'<entry>([^<]+)</entry>', roster)

    # Find scenario count from PredefinedSetup
    scenarios = re.findall(
        r'<VASSAL\.build\.module\.PredefinedSetup[^>]*name="([^"]+)"[^>]*file="([^"]+)"',
        buildfile_xml
    )

    # Find dice config
    dice = re.findall(
        r'<VASSAL\.build\.module\.DiceButton[^>]*name="([^"]+)"[^>]*nDice="([^"]+)"[^>]*nSides="([^"]+)"',
        buildfile_xml
    )

    # Detect dynamic property names (might indicate cohesion/damage tracking)
    dyn_props = set(re.findall(r'<VASSAL\.build\.module\.properties\.GlobalProperty[^>]*name="([^"]+)"', buildfile_xml))

    return {
        'metadata': metadata,
        'family': family,
        'family_info': SYSTEM_FAMILY_PATTERNS[family],
        'module_grid': module_grid,
        'unit_prefixes': common_prefixes,
        'sides': sides,
        'scenarios': scenarios,
        'dice': dice,
        'dynamic_properties': sorted(dyn_props),
        'image_count': len(image_basenames),
    }


# ---------------------------------------------------------------------------
# Code generators
# ---------------------------------------------------------------------------

def generate_init_py(game_name, lib_name):
    """Generate the package __init__.py."""
    return f'''"""
{game_name}-specific library extending vassal_framework.

Auto-generated by vassal_framework.autogen.
Edit the individual modules to refine behavior for this game.
"""

__version__ = "1.0.0"

from games.{game_name}.{lib_name}.terrain import {game_name}Terrain
from games.{game_name}.{lib_name}.combat import {game_name}Combat
from games.{game_name}.{lib_name}.units import (
    {game_name.lower()}_side_classifier,
    {game_name.upper()}_UNIT_TYPES,
    {game_name.upper()}_SIDE_PREFIXES,
)

__all__ = [
    '{game_name}Terrain',
    '{game_name}Combat',
    '{game_name.lower()}_side_classifier',
    '{game_name.upper()}_UNIT_TYPES',
    '{game_name.upper()}_SIDE_PREFIXES',
]
'''


def generate_terrain_py(game_name, family_info, module_grid):
    """Generate terrain.py based on detected family and grid info."""
    # Get list of board names
    board_names = []
    for map_name, boards in module_grid.maps.items():
        for bn in boards.keys():
            board_names.append(bn)

    family_name = family_info['description']

    # Different terrain catalogs by family
    if 'GBoH' in str(family_info) or 'ancients' in family_name.lower():
        terrain_setup = '''        # Unit type codes used in movement tables
        self.unit_types = {'PH', 'LG', 'HI', 'MI', 'LI', 'SK', 'CAV', 'EL', 'ALL'}

        # Clear terrain (default)
        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Rough terrain
        self.add_terrain_type(TerrainType(
            code='R', name='Rough',
            move_costs={'PH': 'X', 'CAV': '2', 'EL': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
            cohesion_on_entry=1,
        ))

        # Woods (blocks LOS, prohibited to phalanx and elephants)
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'PH': 'X', 'EL': 'X', 'CAV': '3', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
            cohesion_on_entry=1,
        ))

        # Hills (elevation 1, hinders LOS)
        self.add_terrain_type(TerrainType(
            code='H', name='Hills', elevation=1,
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # River (hexside, varies by unit type)
        self.add_terrain_type(TerrainType(
            code='Sr', name='Shallow River', is_hexside=True,
            move_costs={
                'PH': '2', 'LG': '2', 'HI': '2', 'MI': '2', 'LI': '1',
                'SK': '1', 'CAV': '0', 'EL': '1', 'ALL': '1',
            },
            combat_modifiers={'defender_drm': 1},
            cohesion_on_entry=1,
        ))

        # TODO: Add scenario-specific terrain (camps, fortifications, etc.)'''
    elif 'WWII' in family_name or 'WW2' in family_name or 'OCS' in family_info.get('reference_game', '') or 'SCS' in family_info.get('reference_game', ''):
        terrain_setup = '''        # Unit type codes used in movement tables
        self.unit_types = {'INF', 'CAV', 'ARM', 'MECH', 'ARTY', 'HQ', 'AIR', 'ALL'}

        # Clear terrain
        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Woods
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'INF': '2', 'CAV': '2', 'ARM': '3', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Hills
        self.add_terrain_type(TerrainType(
            code='H', name='Hills', elevation=1,
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Town/Village
        self.add_terrain_type(TerrainType(
            code='T', name='Town',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # City (stronger defensive bonus)
        self.add_terrain_type(TerrainType(
            code='Ci', name='City',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -3},
        ))

        # River (hexside)
        self.add_terrain_type(TerrainType(
            code='R', name='River', is_hexside=True,
            move_costs={'ARM': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': 1},
        ))

        # Road (reduces cost when following)
        self.add_terrain_type(TerrainType(
            code='Rd', name='Road',
            move_costs={'ALL': '1'},
        ))

        # Marsh / Swamp
        self.add_terrain_type(TerrainType(
            code='M', name='Marsh',
            move_costs={'ARM': 'X', 'ALL': '3'},
            combat_modifiers={'defender_drm': -1, 'attacker_drm': -1},
        ))

        # TODO: Add scenario-specific terrain (bunkers, minefields, etc.)'''
    else:
        # Generic operational template
        terrain_setup = '''        # Unit type codes used in movement tables
        self.unit_types = {'INF', 'CAV', 'ARM', 'ARTY', 'ALL'}

        # Clear terrain
        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Woods (TODO: verify cost from rulebook)
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Hills
        self.add_terrain_type(TerrainType(
            code='H', name='Hills', elevation=1,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Town/City
        self.add_terrain_type(TerrainType(
            code='T', name='Town',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # TODO: Add game-specific terrain types from rulebook'''

    boards_comment = '\n'.join(f'#   - {b}' for b in board_names[:20])
    if not boards_comment:
        boards_comment = '#   (no boards detected)'

    return f'''#!/usr/bin/env python3
"""
{game_name} terrain system -- inherits from vassal_framework.terrain.

Auto-generated by vassal_framework.autogen for {family_name}.

Detected boards in this module:
{boards_comment}

TODO: Refine terrain types based on the game's rulebook.
TODO: Add scenario-specific terrain assignments via TerrainMap.set_hex().
"""

from vassal_framework.terrain import TerrainSystem, TerrainType


class {game_name}Terrain(TerrainSystem):
    """Terrain rules for {game_name}.

    Auto-generated baseline. Customize _setup() with values from the rulebook.
    """

    def _setup(self):
{terrain_setup}


if __name__ == '__main__':
    ts = {game_name}Terrain()
    print(f"{game_name} terrain types: {{len(ts.terrain_types)}}")
    for code, t in ts.terrain_types.items():
        print(f"  [{{code}}] {{t.name}}")
        print(f"    Move costs: {{t.move_costs}}")
        if t.combat_modifiers:
            print(f"    Combat: {{t.combat_modifiers}}")
'''


def generate_combat_py(game_name, family_info):
    """Generate combat.py based on detected combat type."""
    combat_type = family_info.get('combat_type', 'odds_crt')
    family_name = family_info['description']

    if combat_type == 'cohesion_shock':
        return _gen_cohesion_combat(game_name, family_name)
    elif combat_type == 'odds_crt':
        return _gen_odds_combat(game_name, family_name)
    elif combat_type == 'card':
        return _gen_card_combat(game_name, family_name)
    else:
        return _gen_odds_combat(game_name, family_name)  # default


def _gen_cohesion_combat(game_name, family_name):
    return f'''#!/usr/bin/env python3
"""
{game_name} combat system -- Cohesion Shock (GBoH-style).

Auto-generated by vassal_framework.autogen for {family_name}.
TODO: Refine the SHOCK_CRT and WEAPON_SUPERIORITY tables from the game's rulebook.
"""

import random
from vassal_framework.combat import CombatSystem, CombatResult, CombatType


class {game_name}Combat(CombatSystem):
    """Cohesion Shock combat resolver.

    Auto-generated baseline using SPQR-derived CRT. Customize the
    SHOCK_CRT and WEAPON_SUPERIORITY tables for {game_name}.
    """

    combat_type = CombatType.COHESION_SHOCK

    # Shock CRT (Size ratio columns, d10 results)
    # Format: column -> [(dr, attacker_hits, defender_hits) for d10 0-9]
    # TODO: Replace with the actual CRT from {game_name}'s rulebook
    SHOCK_CRT = {{
        '1:5':  [(0,4,0),(1,3,0),(2,3,0),(3,3,1),(4,3,1),(5,2,1),(6,2,1),(7,2,2),(8,2,2),(9,1,2)],
        '1:4':  [(0,4,0),(1,3,0),(2,3,1),(3,3,1),(4,2,1),(5,2,2),(6,2,2),(7,2,2),(8,1,2),(9,1,3)],
        '1:3':  [(0,4,1),(1,3,1),(2,3,1),(3,2,2),(4,2,2),(5,2,2),(6,1,2),(7,1,3),(8,1,3),(9,0,3)],
        '1:2':  [(0,3,1),(1,3,1),(2,3,2),(3,2,2),(4,2,2),(5,2,2),(6,1,3),(7,1,3),(8,0,3),(9,0,4)],
        '1:1':  [(0,3,2),(1,3,2),(2,2,2),(3,2,2),(4,2,3),(5,1,3),(6,1,3),(7,1,4),(8,0,4),(9,0,4)],
        '2:1':  [(0,2,2),(1,2,3),(2,2,3),(3,1,3),(4,1,3),(5,1,4),(6,0,4),(7,0,4),(8,0,5),(9,0,5)],
        '3:1':  [(0,2,3),(1,1,3),(2,1,4),(3,1,4),(4,0,4),(5,0,4),(6,0,5),(7,0,5),(8,0,6),(9,0,6)],
        '4:1':  [(0,1,3),(1,1,4),(2,1,4),(3,0,4),(4,0,5),(5,0,5),(6,0,5),(7,0,6),(8,0,6),(9,0,7)],
        '5:1':  [(0,1,4),(1,0,4),(2,0,5),(3,0,5),(4,0,5),(5,0,6),(6,0,6),(7,0,7),(8,0,7),(9,0,8)],
    }}

    # Weapon Superiority Chart: (attacker_type, defender_type) -> (col_shift, sup_type)
    # TODO: Customize for {game_name}'s unit matchups
    WEAPON_SUPERIORITY = {{
        # Add (att_type, def_type): (shift, 'AS'|'DS'|'none') entries here
    }}

    def calculate_size_ratio(self, attacker_size, defender_size):
        """Calculate Shock CRT column. Round in favor of defender."""
        if defender_size == 0:
            return '5:1'
        ratio = attacker_size / defender_size
        if ratio >= 5: return '5:1'
        if ratio >= 4: return '4:1'
        if ratio >= 3: return '3:1'
        if ratio >= 2: return '2:1'
        if ratio >= 1: return '1:1'
        if ratio >= 0.5: return '1:2'
        if ratio >= 0.34: return '1:3'
        if ratio >= 0.25: return '1:4'
        return '1:5'

    def determine_weapon_superiority(self, attacker_type, defender_type):
        return self.WEAPON_SUPERIORITY.get((attacker_type, defender_type), (0, 'none'))

    def resolve(self, attacker, defender, modifiers=None, dr=None,
                attacker_size=1, defender_size=1,
                attacker_type='', defender_type='',
                position='frontal', **kwargs):
        result = CombatResult()
        modifiers = modifiers or []

        col = self.calculate_size_ratio(attacker_size, defender_size)
        weapon_shift, weapon_sup = self.determine_weapon_superiority(attacker_type, defender_type)
        total_shift = weapon_shift + sum(m.column_shift for m in modifiers)

        cols = list(self.SHOCK_CRT.keys())
        if col in cols:
            idx = cols.index(col)
            new_idx = max(0, min(len(cols) - 1, idx + total_shift))
            actual_col = cols[new_idx]
        else:
            actual_col = col

        if dr is None:
            dr = random.randint(0, 9)
        modified_dr = dr + sum(m.value for m in modifiers)
        modified_dr = max(0, min(9, modified_dr))
        result.raw_die_rolls = [dr]
        result.column_used = actual_col

        crt_row = self.SHOCK_CRT[actual_col][modified_dr]
        att_hits = crt_row[1]
        def_hits = crt_row[2]

        # Position superiority doubles defender hits (flank/rear attack)
        if position in ('flank', 'rear'):
            def_hits *= 2
            result.superiority = 'AS (Position)'
        elif weapon_sup == 'AS':
            def_hits *= 2
            result.superiority = 'AS (Weapon)'
        elif weapon_sup == 'DS':
            att_hits *= 2
            result.superiority = 'DS (Weapon)'

        result.attacker_hits = att_hits
        result.defender_hits = def_hits
        return result
'''


def _gen_odds_combat(game_name, family_name):
    return f'''#!/usr/bin/env python3
"""
{game_name} combat system -- Odds-based CRT.

Auto-generated by vassal_framework.autogen for {family_name}.
TODO: Customize the CRT with values from {game_name}'s rulebook.
"""

import random
from vassal_framework.combat import CombatSystem, CombatResult, CombatType


class {game_name}Combat(CombatSystem):
    """Odds-based CRT combat resolver.

    Auto-generated baseline. Customize the CRT for {game_name}.
    """

    combat_type = CombatType.ODDS_CRT

    # Combat Results Table
    # Format: column -> [result_code for d6 1-6]
    # Codes: AE/AR/AR2/DR/DR2/DE/EX/NE
    # TODO: Replace with the actual CRT from {game_name}'s rulebook
    CRT = {{
        '1:3': ['AE', 'AE', 'AR', 'AR', 'NE', 'NE'],
        '1:2': ['AE', 'AR', 'AR', 'NE', 'NE', 'DR'],
        '1:1': ['AR', 'AR', 'NE', 'NE', 'DR', 'DR'],
        '2:1': ['AR', 'NE', 'NE', 'DR', 'DR', 'DE'],
        '3:1': ['NE', 'NE', 'DR', 'DR', 'DE', 'DE'],
        '4:1': ['NE', 'DR', 'DR', 'DE', 'DE', 'DE'],
        '5:1': ['DR', 'DR', 'DE', 'DE', 'DE', 'DE'],
        '6:1': ['DR', 'DE', 'DE', 'DE', 'DE', 'DE'],
    }}

    def calculate_odds(self, attacker_strength, defender_strength):
        """Calculate odds column. Round in favor of defender."""
        if defender_strength == 0:
            return '6:1'
        ratio = attacker_strength / defender_strength
        if ratio >= 6: return '6:1'
        if ratio >= 5: return '5:1'
        if ratio >= 4: return '4:1'
        if ratio >= 3: return '3:1'
        if ratio >= 2: return '2:1'
        if ratio >= 1: return '1:1'
        if ratio >= 0.5: return '1:2'
        return '1:3'

    def resolve(self, attacker, defender, modifiers=None, dr=None,
                attacker_strength=1, defender_strength=1, **kwargs):
        result = CombatResult()
        modifiers = modifiers or []

        col = self.calculate_odds(attacker_strength, defender_strength)
        cols = list(self.CRT.keys())
        if col in cols:
            shift = sum(m.column_shift for m in modifiers)
            idx = cols.index(col)
            new_idx = max(0, min(len(cols) - 1, idx + shift))
            actual_col = cols[new_idx]
        else:
            actual_col = col

        if dr is None:
            dr = random.randint(1, 6)
        modified_dr = dr + sum(m.value for m in modifiers)
        modified_dr = max(1, min(6, modified_dr))
        result.raw_die_rolls = [dr]
        result.column_used = actual_col

        crt_result = self.CRT[actual_col][modified_dr - 1]
        result.notes.append(f"CRT: {{actual_col}} col, DR={{dr}} -> {{crt_result}}")

        if crt_result == 'AE':
            result.attacker_eliminated = True
            result.attacker_hits = 99
        elif crt_result == 'AR':
            result.attacker_retreats = 1
            result.attacker_hits = 1
        elif crt_result == 'AR2':
            result.attacker_retreats = 2
            result.attacker_hits = 1
        elif crt_result == 'DR':
            result.defender_retreats = 1
            result.defender_hits = 1
        elif crt_result == 'DR2':
            result.defender_retreats = 2
            result.defender_hits = 1
        elif crt_result == 'DE':
            result.defender_eliminated = True
            result.defender_hits = 99
        elif crt_result == 'EX':
            result.attacker_hits = 1
            result.defender_hits = 1

        return result
'''


def _gen_card_combat(game_name, family_name):
    return f'''#!/usr/bin/env python3
"""
{game_name} combat system -- Card-Driven.

Auto-generated by vassal_framework.autogen for {family_name}.
TODO: Implement card-driven combat resolution from {game_name}'s rulebook.
Card-driven games typically resolve combat via card play, not dice tables.
"""

from vassal_framework.combat import CombatSystem, CombatResult, CombatType


class {game_name}Combat(CombatSystem):
    """Card-driven combat resolver.

    Auto-generated stub. Card-driven games need significant customization
    because combat is resolved via played cards, not standard CRTs.
    """

    combat_type = CombatType.CARD

    def resolve(self, attacker, defender, modifiers=None, dr=None, **kwargs):
        result = CombatResult()
        result.notes.append("Card-driven combat -- implement with game-specific card logic")
        # TODO: Implement {game_name}'s card-driven combat resolution
        return result
'''


def generate_units_py(game_name, sides, unit_prefixes, family_info):
    """Generate units.py with detected sides and unit prefixes."""
    # Try to detect "your side" prefixes from the most common ones
    # In SPQR, the player's side has more units typically
    # We list them all and let the user/customizer pick
    prefixes_list = ',\n    '.join(f"'{p}-'" for p in unit_prefixes)
    if not prefixes_list:
        prefixes_list = "# TODO: Add detected prefixes here"

    sides_str = sides if sides else ['Side1', 'Side2']
    side1 = sides_str[0] if sides_str else 'Side1'
    side2 = sides_str[1] if len(sides_str) > 1 else 'Side2'

    return f'''#!/usr/bin/env python3
"""
{game_name}-specific unit classification.

Auto-generated by vassal_framework.autogen.

Detected sides from PlayerRoster: {sides if sides else "(none detected)"}
Detected unit prefixes: {unit_prefixes[:10]}

TODO: Refine the side classifier to match {game_name}'s actual side conventions.
TODO: Verify and adjust the unit type code mappings.
"""

# Image filename prefixes that identify {side1} pieces
# TODO: Verify which prefixes belong to which side by examining the .vmod images
{game_name.upper()}_SIDE_PREFIXES = [
    {prefixes_list}
]

# Map unit type codes to human-readable names
# TODO: Adjust to match {game_name}'s actual unit types
{game_name.upper()}_UNIT_TYPES = {{
{_format_unit_types(unit_prefixes)}
}}

# Estimated unit stats (used by AI Monte Carlo)
# TODO: Replace with actual stats from counter images / rulebook
{game_name.upper()}_UNIT_STATS = {{
{_format_unit_stats(unit_prefixes)}
}}

# Side names from the game
{game_name.upper()}_SIDES = {sides_str!r}


def {game_name.lower()}_side_classifier(image_filename):
    """Classify a piece by side from its image filename.

    Returns: side name from {game_name.upper()}_SIDES
    """
    if not image_filename:
        return 'Unknown'
    for prefix in {game_name.upper()}_SIDE_PREFIXES:
        if image_filename.startswith(prefix):
            return '{side1}'
    return '{side2}'


def get_unit_stats(unit_type_code):
    """Get estimated unit stats for AI simulation."""
    return {game_name.upper()}_UNIT_STATS.get(unit_type_code, {{
        'size': 4, 'tq': 5, 'rout_points': 4,
    }})


# Per-board grid calibration
# TODO: Run validation to find correct max_cols for each board
{game_name.upper()}_BOARD_MAX_COLS = {{
    # 'BoardName': 46,
}}


def calibrate_grid(module_grid):
    """Apply game-specific grid calibration."""
    for map_name, boards in module_grid.maps.items():
        for board_name, board in boards.items():
            if board.grid and board_name in {game_name.upper()}_BOARD_MAX_COLS:
                board.grid.max_cols = {game_name.upper()}_BOARD_MAX_COLS[board_name]
                board.grid.max_rows = {game_name.upper()}_BOARD_MAX_COLS[board_name]
    return module_grid
'''


def _format_unit_types(prefixes):
    """Generate the UNIT_TYPES dict body."""
    if not prefixes:
        return "    # 'INF': 'Infantry',  # TODO: Add unit types"
    lines = []
    for p in prefixes[:15]:
        lines.append(f"    '{p}': '{p} Unit',  # TODO: refine name")
    return '\n'.join(lines)


def _format_unit_stats(prefixes):
    """Generate the UNIT_STATS dict body."""
    if not prefixes:
        return "    # 'INF': {'size': 4, 'tq': 5, 'rout_points': 4},"
    lines = []
    for p in prefixes[:10]:
        lines.append(f"    '{p}': {{'size': 4, 'tq': 5, 'rout_points': 4}},")
    return '\n'.join(lines)


def generate_runner_py(game_name, lib_name):
    """Generate the CLI runner."""
    return f'''#!/usr/bin/env python3
"""
{game_name} AI Runner -- Command-line tool for AI analysis.

Auto-generated by vassal_framework.autogen.
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from vassal_framework import (
    ModuleGrid, GameState, UnitScanner, Battlefield, detect_active_boards,
    AIDecisionEngine,
)
from games.{game_name}.{lib_name}.terrain import {game_name}Terrain
from games.{game_name}.{lib_name}.combat import {game_name}Combat
from games.{game_name}.{lib_name}.units import (
    {game_name.lower()}_side_classifier, calibrate_grid,
)


def find_vmod():
    """Auto-detect the .vmod in this game's directory."""
    game_dir = os.path.join(PROJECT_ROOT, 'games', '{game_name}')
    for f in os.listdir(game_dir):
        if f.endswith('.vmod'):
            return os.path.join(game_dir, f)
    return None


def analyze(save_path, leader_name=None, mc_iterations=300):
    vmod_path = find_vmod()
    if not vmod_path:
        print("ERROR: No .vmod found in games/{game_name}/")
        return

    print(f"Module: {{os.path.basename(vmod_path)}}")
    print(f"Save:   {{os.path.basename(save_path)}}")

    mg = ModuleGrid.from_vmod(vmod_path)
    calibrate_grid(mg)

    state = GameState()
    state.load_from_file(save_path)

    scanner = UnitScanner(
        mg,
        active_boards=detect_active_boards(state),
        side_classifier={game_name.lower()}_side_classifier,
    )
    units = scanner.scan(state)
    bf = Battlefield(units)

    bf.summarize()

    print()
    print("=== LEADERS ===")
    for ldr in bf.leaders():
        cr = f"CR{{ldr.command_range}}" if ldr.command_range else "?"
        status = "FINISHED" if ldr.is_finished else "ACTIVE"
        print(f"  [{{ldr.side[:1]}}] {{ldr.name:30s}} {{ldr.hex_id() or '?':5s}} {{cr:5s}} {{status}}")

    terrain = {game_name}Terrain()
    combat = {game_name}Combat()
    ai = AIDecisionEngine(
        combat_system=combat,
        terrain_system=terrain,
        mc_iterations=mc_iterations,
    )

    if leader_name:
        leader = next((l for l in bf.leaders() if leader_name.lower() in l.name.lower()), None)
        if leader:
            print(f"\\n=== {{leader.name}} at {{leader.hex_id()}} ===")
            options = ai.evaluate_leader_turn(bf, leader, max_options=5)
            for i, opt in enumerate(options):
                print(f"  {{i+1}}. {{opt.name}} EV={{opt.expected_value:.2f}} | {{opt.risk}}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 -m games.{game_name}.{lib_name}.runner <save.vsav> [leader]")
        sys.exit(1)
    analyze(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
'''


def generate_game_md(game_name, analysis):
    """Generate the GameName.md context document."""
    metadata = analysis['metadata']
    family_info = analysis['family_info']
    sides = analysis['sides']
    scenarios = analysis['scenarios']
    dice = analysis['dice']

    scenarios_table = '\n'.join(
        f"| {name} | {file} |" for name, file in scenarios[:30]
    ) if scenarios else "| (none detected) | |"

    dice_str = ', '.join(f"{n}d{s}" for _, n, s in dice) if dice else "(none)"

    return f'''# {game_name} -- AI Play Context

**System Family:** {family_info['description']}
**Auto-generated by:** `vassal_framework.autogen`
**Module:** {metadata.get('name', 'Unknown')}
**Version:** {metadata.get('version', 'Unknown')}
**VASSAL Version:** {metadata.get('VassalVersion', 'Unknown')}

---

## Game Overview

{metadata.get('description', '*No description in module metadata.*')}

---

## Sides

{', '.join(sides) if sides else '*No sides detected in PlayerRoster.*'}

---

## Maps and Boards

Detected boards in this module:

{chr(10).join('- ' + bn for boards in analysis['module_grid'].maps.values() for bn in boards.keys())}

---

## Scenarios

| Name | Setup File |
|------|-----------|
{scenarios_table}

---

## Dice Configuration

{dice_str}

---

## Detected Unit Type Prefixes

These prefixes were found in the module's image filenames:

{', '.join(analysis['unit_prefixes']) if analysis['unit_prefixes'] else '(none detected)'}

---

## Onboarding Status

This file is the **auto-generated baseline**. To complete the onboarding:

- [ ] Read the rulebook and verify terrain types in `{game_name.lower()}_lib/terrain.py`
- [ ] Verify the combat system matches the rulebook in `{game_name.lower()}_lib/combat.py`
- [ ] Refine the side classifier in `{game_name.lower()}_lib/units.py`
- [ ] Calibrate per-board `max_cols` values for hex grid descend math
- [ ] Test the AI runner on a save file
- [ ] Update this file with actual game stats, victory conditions, and AI strategy notes

---

## AI Play

```bash
python3 -m games.{game_name}.{game_name.lower()}_lib.runner <save.vsav> [leader_name]
```
'''


def generate_intel_md(game_name):
    return f'''# {game_name} -- Cross-Scenario INTEL

Auto-generated by `vassal_framework.autogen`. This file accumulates
intelligence about {game_name} across all scenarios played.

---

## Scenarios Onboarded

*(none yet)*

---

## Validated Tactical Patterns

*(populated by play sessions)*

---

## Game-Specific Insights

*(populated as the AI plays this game)*
'''


def generate_session_md(game_name):
    return f'''# {game_name} -- Session Log

Auto-generated by `vassal_framework.autogen`. This file logs gameplay
sessions for {game_name}.

---

## Session History

| Session | Date | Scenario | Side | Result | Notes |
|---------|------|----------|------|--------|-------|
| (none yet) | | | | | |
'''


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def autogen(vmod_path, output_dir=None, game_name=None, force=False):
    """Generate a complete game library from a vmod file.

    Args:
      vmod_path: path to the .vmod file
      output_dir: where to write game files (default: games/<GameName>/)
      game_name: name for the game (default: derived from vmod filename)
      force: overwrite existing files

    Returns:
      Path to the generated game directory
    """
    print(f"=" * 70)
    print(f"VASSAL Auto-Generator")
    print(f"=" * 70)
    print(f"Source vmod: {vmod_path}")
    print()

    # Determine game name
    if not game_name:
        base = os.path.basename(vmod_path)
        game_name = re.sub(r'[^A-Za-z0-9]', '', base.split('.')[0])
        game_name = re.sub(r'(Deluxe|Module|v\d+|alt)', '', game_name, flags=re.I)

    print(f"Game name: {game_name}")
    lib_name = f"{game_name.lower()}_lib"

    # Determine output directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if not output_dir:
        output_dir = os.path.join(project_root, 'games', game_name)

    print(f"Output directory: {output_dir}")
    print()

    # Analyze the vmod
    print("Analyzing vmod structure...")
    analysis = analyze_vmod(vmod_path)

    print(f"  Detected system family: {analysis['family']}")
    print(f"  Combat type: {analysis['family_info']['combat_type']}")
    print(f"  Sides: {analysis['sides']}")
    print(f"  Unit prefixes detected: {len(analysis['unit_prefixes'])}")
    print(f"  Scenarios: {len(analysis['scenarios'])}")
    print(f"  Boards: {sum(len(b) for b in analysis['module_grid'].maps.values())}")
    print()

    # Create directory structure
    lib_dir = os.path.join(output_dir, lib_name)
    scenarios_dir = os.path.join(output_dir, 'scenarios')
    os.makedirs(lib_dir, exist_ok=True)
    os.makedirs(scenarios_dir, exist_ok=True)

    # Generate files
    files_to_write = {
        os.path.join(lib_dir, '__init__.py'): generate_init_py(game_name, lib_name),
        os.path.join(lib_dir, 'terrain.py'): generate_terrain_py(
            game_name, analysis['family_info'], analysis['module_grid']
        ),
        os.path.join(lib_dir, 'combat.py'): generate_combat_py(
            game_name, analysis['family_info']
        ),
        os.path.join(lib_dir, 'units.py'): generate_units_py(
            game_name, analysis['sides'], analysis['unit_prefixes'], analysis['family_info']
        ),
        os.path.join(lib_dir, 'runner.py'): generate_runner_py(game_name, lib_name),
        os.path.join(output_dir, f'{game_name}.md'): generate_game_md(game_name, analysis),
        os.path.join(output_dir, 'INTEL.md'): generate_intel_md(game_name),
        os.path.join(output_dir, 'SESSION.md'): generate_session_md(game_name),
    }

    written_count = 0
    skipped_count = 0
    for filepath, content in files_to_write.items():
        if os.path.exists(filepath) and not force:
            skipped_count += 1
            print(f"  SKIP (exists): {os.path.relpath(filepath, project_root)}")
            continue
        with open(filepath, 'w') as f:
            f.write(content)
        written_count += 1
        print(f"  WROTE: {os.path.relpath(filepath, project_root)}")

    print()
    print(f"Generated: {written_count} files | Skipped: {skipped_count}")
    print()
    print(f"=" * 70)
    print("NEXT STEPS")
    print(f"=" * 70)
    print(f"1. Review {os.path.relpath(lib_dir, project_root)}/")
    print(f"2. Edit terrain.py with rulebook movement costs")
    print(f"3. Edit combat.py with rulebook CRT (or keep cohesion shock default)")
    print(f"4. Verify side classifier in units.py")
    print(f"5. Run validation:")
    print(f"   python3 -m vassal_framework.validation {game_name}")
    print(f"6. Test AI runner:")
    print(f"   python3 -m games.{game_name}.{lib_name}.runner <save.vsav>")

    return output_dir


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Auto-generate a game library from a .vmod')
    parser.add_argument('vmod', help='Path to .vmod file')
    parser.add_argument('--name', help='Game name (default: derived from filename)')
    parser.add_argument('--output', help='Output directory (default: games/<GameName>/)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing files')
    args = parser.parse_args()

    if not os.path.isfile(args.vmod):
        print(f"ERROR: vmod not found: {args.vmod}")
        sys.exit(1)

    autogen(args.vmod, args.output, args.name, args.force)


if __name__ == '__main__':
    main()
