#!/usr/bin/env python3
"""
VASSAL Terrain System -- Generic terrain abstraction for any wargame.

A wargame's terrain typically has:
- Hex terrain types (Clear, Rough, Woods, Hills, Mountains, City, Marsh, etc.)
- Hexside features (Rivers, Streams, Walls, Ridges)
- Special features (Ford, Bridge, Road, Trail)
- Movement costs (per terrain type, per unit type)
- Combat modifiers (defender DRM, column shifts)
- LOS effects (blocks, hinders)

This module provides:
1. TerrainType: definition of a single terrain type
2. TerrainEffect: effect of terrain on movement or combat
3. TerrainSystem: complete terrain rules for a game
4. TerrainMap: per-hex terrain assignment for a specific board

Game-specific implementations subclass TerrainSystem with the game's
actual terrain types and rules. Vmod terrain extraction is limited
because terrain features are typically encoded as visual board images,
not as game data. Terrain must be either:
(a) Manually defined per board
(b) Inferred from board image analysis (vision-based)
(c) Provided by the game module via Zone definitions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable


# ---------------------------------------------------------------------------
# Movement cost result
# ---------------------------------------------------------------------------

class MoveResult:
    """The result of attempting to enter or cross a hex/hexside."""

    LEGAL = "legal"
    PROHIBITED = "prohibited"   # Cannot enter at all
    PARTIAL = "partial"         # Can enter but with cohesion hit / fatigue
    EXPENSIVE = "expensive"     # Costs all remaining MP

    def __init__(self, status, mp_cost=0, cohesion_hit=False, notes=""):
        self.status = status
        self.mp_cost = mp_cost
        self.cohesion_hit = cohesion_hit
        self.notes = notes

    def __repr__(self):
        return f"MoveResult({self.status}, mp={self.mp_cost})"


# ---------------------------------------------------------------------------
# Terrain type definition
# ---------------------------------------------------------------------------

@dataclass
class TerrainType:
    """A type of terrain (hex or hexside feature) and its game effects."""

    code: str                    # Short code: 'C', 'W', 'H', 'M' etc.
    name: str                    # Display name: 'Clear', 'Woods', 'Hills'
    is_hexside: bool = False     # True for rivers, walls etc.
    los_blocks: bool = False     # True if blocks line of sight
    los_hinders: bool = False    # True if degrades LOS
    elevation: int = 0           # Elevation level (0=ground)

    # Movement costs by unit type
    # key: unit_type code (e.g., 'INF', 'CAV', 'EL', 'PH', 'ALL')
    # value: MP cost or 'X' for prohibited or '+1' for additive
    move_costs: Dict[str, str] = field(default_factory=dict)

    # Combat modifiers when defender is in/behind this terrain
    # key: 'defender_drm', 'attacker_drm', 'column_shift'
    # value: integer modifier
    combat_modifiers: Dict[str, int] = field(default_factory=dict)

    # Cohesion hits incurred when entering (for fatiguing terrain)
    cohesion_on_entry: int = 0

    def get_move_cost(self, unit_type, base_cost=1):
        """Get the MP cost to enter this terrain for a given unit type."""
        cost_str = self.move_costs.get(unit_type, self.move_costs.get('ALL', str(base_cost)))
        if cost_str == 'X' or cost_str.upper() == 'PROHIBITED':
            return MoveResult(MoveResult.PROHIBITED, notes=f"{self.name} prohibited for {unit_type}")
        if cost_str == 'ALL':
            return MoveResult(MoveResult.EXPENSIVE, mp_cost=99, notes=f"{self.name} costs all MP")
        try:
            cost = int(cost_str)
            return MoveResult(MoveResult.LEGAL, mp_cost=cost,
                              cohesion_hit=(self.cohesion_on_entry > 0),
                              notes=self.name)
        except ValueError:
            return MoveResult(MoveResult.LEGAL, mp_cost=base_cost, notes=self.name)


# ---------------------------------------------------------------------------
# Terrain map: per-hex assignment
# ---------------------------------------------------------------------------

class TerrainMap:
    """Terrain assignments for a specific board.

    Maps hex coordinates to terrain types. Hexsides are stored
    separately for features like rivers and walls.
    """

    def __init__(self, board_name=""):
        self.board_name = board_name
        self.hex_terrain = {}        # (col, row) -> [TerrainType]
        self.hexside_terrain = {}    # (col1, row1, col2, row2) -> TerrainType
        self.elevation = {}          # (col, row) -> int

    def set_hex(self, col, row, terrain_type):
        """Set terrain for a single hex."""
        if (col, row) not in self.hex_terrain:
            self.hex_terrain[(col, row)] = []
        self.hex_terrain[(col, row)].append(terrain_type)

    def get_hex_terrains(self, col, row):
        """Get all terrain types in a hex (e.g., Hill + Woods)."""
        return self.hex_terrain.get((col, row), [])

    def set_hexside(self, c1, r1, c2, r2, terrain_type):
        """Set hexside terrain (e.g., river between two hexes)."""
        # Normalize: smaller coordinates first
        key = tuple(sorted([(c1, r1), (c2, r2)]))
        self.hexside_terrain[key] = terrain_type

    def get_hexside(self, c1, r1, c2, r2):
        """Get hexside terrain between two adjacent hexes."""
        key = tuple(sorted([(c1, r1), (c2, r2)]))
        return self.hexside_terrain.get(key)

    def set_elevation(self, col, row, level):
        self.elevation[(col, row)] = level

    def get_elevation(self, col, row):
        return self.elevation.get((col, row), 0)


# ---------------------------------------------------------------------------
# Terrain system: game's terrain rules
# ---------------------------------------------------------------------------

class TerrainSystem:
    """Complete terrain rules for a game.

    Each game has different terrain types and rules. Subclass and define
    self.terrain_types and self.unit_types in your game-specific class.
    """

    def __init__(self):
        self.terrain_types = {}      # code -> TerrainType
        self.unit_types = set()       # Valid unit type codes
        self.maps = {}                # board_name -> TerrainMap
        self._setup()

    def _setup(self):
        """Override in subclass to define terrain types and unit types."""
        pass

    def add_terrain_type(self, terrain_type):
        self.terrain_types[terrain_type.code] = terrain_type

    def get_terrain(self, code):
        return self.terrain_types.get(code)

    def get_map(self, board_name):
        if board_name not in self.maps:
            self.maps[board_name] = TerrainMap(board_name)
        return self.maps[board_name]

    def calculate_move_cost(self, board_name, from_col, from_row, to_col, to_row, unit_type):
        """Calculate the total MP cost to move from one hex to an adjacent hex.

        Includes:
        - Terrain type cost in destination hex (highest cost in stack)
        - Hexside feature cost
        - Elevation change
        - Cohesion hits for fatigue terrain
        """
        terrain_map = self.get_map(board_name)

        # Hexside cost
        hexside = terrain_map.get_hexside(from_col, from_row, to_col, to_row)
        hexside_cost = 0
        cohesion_on_entry = 0
        if hexside:
            hs_result = hexside.get_move_cost(unit_type)
            if hs_result.status == MoveResult.PROHIBITED:
                return hs_result
            hexside_cost = hs_result.mp_cost
            if hs_result.cohesion_hit:
                cohesion_on_entry += hexside.cohesion_on_entry

        # Destination hex terrain (use highest cost if multiple types)
        dest_terrains = terrain_map.get_hex_terrains(to_col, to_row)
        if not dest_terrains:
            # Default: clear terrain, 1 MP
            return MoveResult(MoveResult.LEGAL, mp_cost=1 + hexside_cost,
                              cohesion_hit=(cohesion_on_entry > 0),
                              notes="Clear")

        max_cost = 0
        prohibited = False
        notes = []
        for t in dest_terrains:
            r = t.get_move_cost(unit_type)
            if r.status == MoveResult.PROHIBITED:
                prohibited = True
                notes.append(f"{t.name} prohibited")
                break
            max_cost = max(max_cost, r.mp_cost)
            if r.cohesion_hit:
                cohesion_on_entry += t.cohesion_on_entry
            notes.append(t.name)

        if prohibited:
            return MoveResult(MoveResult.PROHIBITED, notes='; '.join(notes))

        # Elevation change
        from_elev = terrain_map.get_elevation(from_col, from_row)
        to_elev = terrain_map.get_elevation(to_col, to_row)
        elev_cost = abs(to_elev - from_elev)

        total = max_cost + hexside_cost + elev_cost
        return MoveResult(MoveResult.LEGAL, mp_cost=total,
                          cohesion_hit=(cohesion_on_entry > 0),
                          notes='; '.join(notes))

    def combat_modifier(self, board_name, defender_col, defender_row):
        """Get the combat DRM for a defender in this hex."""
        terrain_map = self.get_map(board_name)
        terrains = terrain_map.get_hex_terrains(defender_col, defender_row)
        total_drm = 0
        notes = []
        for t in terrains:
            drm = t.combat_modifiers.get('defender_drm', 0)
            if drm:
                total_drm += drm
                notes.append(f"{t.name}({drm:+d})")
        return total_drm, '; '.join(notes)

    def los_blocked(self, board_name, c1, r1, c2, r2):
        """Check if line of sight is blocked between two hexes.

        Simple version: any LOS-blocking terrain in either endpoint blocks.
        Real implementation would trace through intervening hexes.
        """
        terrain_map = self.get_map(board_name)
        for col, row in [(c1, r1), (c2, r2)]:
            for t in terrain_map.get_hex_terrains(col, row):
                if t.los_blocks:
                    return True, f"{t.name} at {col:02d}{row:02d}"
        return False, ""


# ---------------------------------------------------------------------------
# SPQR Terrain System (specific implementation)
# ---------------------------------------------------------------------------

class SPQRTerrain(TerrainSystem):
    """SPQR terrain rules from the Heraclea scenario pack."""

    def _setup(self):
        # Unit type codes used in SPQR move cost tables
        self.unit_types = {'PH', 'LG', 'HI', 'MI', 'LI', 'SK', 'CAV', 'EL', 'ALL'}

        # Clear terrain (default)
        clear = TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        )
        self.add_terrain_type(clear)

        # Rough terrain
        rough = TerrainType(
            code='R', name='Rough',
            move_costs={'PH': 'X', 'CAV': '2', 'EL': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
            cohesion_on_entry=1,
        )
        self.add_terrain_type(rough)

        # Woods
        woods = TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'PH': 'X', 'EL': 'X', 'CAV': '3', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
            cohesion_on_entry=1,
        )
        self.add_terrain_type(woods)

        # Hills
        hills = TerrainType(
            code='H', name='Hills', elevation=1,
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        )
        self.add_terrain_type(hills)

        # Heraclea-specific: Shallow River (River Siris)
        river = TerrainType(
            code='Sr', name='Shallow River',
            move_costs={
                'PH': '2', 'LG': '2', 'HI': '2', 'MI': '2', 'LI': '1',
                'SK': '1', 'CAV': '0', 'EL': '1', 'ALL': '1',
            },
            combat_modifiers={'defender_drm': 1, 'shock_modifier_2L': True},
            cohesion_on_entry=1,
        )
        self.add_terrain_type(river)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    ts = SPQRTerrain()
    print(f"SPQR terrain types: {len(ts.terrain_types)}")
    for code, t in ts.terrain_types.items():
        print(f"  [{code}] {t.name}")
        print(f"    Move costs: {t.move_costs}")
        if t.combat_modifiers:
            print(f"    Combat: {t.combat_modifiers}")
        if t.los_blocks:
            print(f"    BLOCKS LOS")

    # Demo: calculate move cost from clear to woods for infantry
    bn = 'Heraclea'
    tm = ts.get_map(bn)
    tm.set_hex(10, 10, ts.get_terrain('C'))
    tm.set_hex(10, 11, ts.get_terrain('W'))

    result = ts.calculate_move_cost(bn, 10, 10, 10, 11, 'LG')
    print(f"\nLG entering Woods (10,10 -> 10,11): {result}")
    print(f"  MP cost: {result.mp_cost}, cohesion: {result.cohesion_hit}, notes: {result.notes}")

    result = ts.calculate_move_cost(bn, 10, 10, 10, 11, 'PH')
    print(f"\nPhalanx entering Woods: {result}")
