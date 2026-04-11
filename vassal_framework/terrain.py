#!/usr/bin/env python3
"""
VASSAL Terrain System -- Generic terrain abstraction (no game-specific code).

This module provides the abstract base classes for terrain systems. Each
game has its own terrain types and rules; subclass TerrainSystem in a
game-specific library to implement them.

See `games/SPQR/spqr_lib/terrain.py` for an example implementation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Movement cost result
# ---------------------------------------------------------------------------

class MoveResult:
    """The result of attempting to enter or cross a hex/hexside."""

    LEGAL = "legal"
    PROHIBITED = "prohibited"
    PARTIAL = "partial"
    EXPENSIVE = "expensive"

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
    """A type of terrain (hex or hexside feature) and its game effects.

    Attributes:
      code: short code identifier ('C', 'W', 'H', etc.)
      name: display name
      is_hexside: True for rivers, walls, etc.
      los_blocks: True if blocks line of sight
      los_hinders: True if degrades LOS but doesn't block
      elevation: elevation level (0=ground)
      move_costs: dict of unit_type_code -> str ('1', 'X' for prohibited, 'ALL' for all MP)
      combat_modifiers: dict of modifier_name -> int
      cohesion_on_entry: cohesion hits inflicted when entering this terrain
    """

    code: str
    name: str
    is_hexside: bool = False
    los_blocks: bool = False
    los_hinders: bool = False
    elevation: int = 0
    move_costs: Dict[str, str] = field(default_factory=dict)
    combat_modifiers: Dict[str, int] = field(default_factory=dict)
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

    Maps hex coordinates to terrain types. Hexsides stored separately
    for features like rivers and walls.
    """

    def __init__(self, board_name=""):
        self.board_name = board_name
        self.hex_terrain = {}
        self.hexside_terrain = {}
        self.elevation = {}

    def set_hex(self, col, row, terrain_type):
        if (col, row) not in self.hex_terrain:
            self.hex_terrain[(col, row)] = []
        self.hex_terrain[(col, row)].append(terrain_type)

    def get_hex_terrains(self, col, row):
        return self.hex_terrain.get((col, row), [])

    def set_hexside(self, c1, r1, c2, r2, terrain_type):
        key = tuple(sorted([(c1, r1), (c2, r2)]))
        self.hexside_terrain[key] = terrain_type

    def get_hexside(self, c1, r1, c2, r2):
        key = tuple(sorted([(c1, r1), (c2, r2)]))
        return self.hexside_terrain.get(key)

    def set_elevation(self, col, row, level):
        self.elevation[(col, row)] = level

    def get_elevation(self, col, row):
        return self.elevation.get((col, row), 0)


# ---------------------------------------------------------------------------
# Terrain system: abstract base class
# ---------------------------------------------------------------------------

class TerrainSystem:
    """Abstract base class for game terrain rules.

    Subclass and override `_setup()` to define terrain types and unit types.
    """

    def __init__(self):
        self.terrain_types = {}
        self.unit_types = set()
        self.maps = {}
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
        """Calculate the total MP cost to move from one hex to an adjacent hex."""
        terrain_map = self.get_map(board_name)

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

        dest_terrains = terrain_map.get_hex_terrains(to_col, to_row)
        if not dest_terrains:
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
        """Check if line of sight is blocked between two hexes."""
        terrain_map = self.get_map(board_name)
        for col, row in [(c1, r1), (c2, r2)]:
            for t in terrain_map.get_hex_terrains(col, row):
                if t.los_blocks:
                    return True, f"{t.name} at {col:02d}{row:02d}"
        return False, ""
