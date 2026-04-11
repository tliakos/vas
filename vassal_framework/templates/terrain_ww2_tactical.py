#!/usr/bin/env python3
"""
TEMPLATE: WW2 tactical terrain (squad-level).

For games like ASL, Combat Commander, Conflict of Heroes, Lock 'n Load.
Movement units: SQUAD (infantry squad), HALF (half-squad), VEHICLE (any vehicle),
                AT (anti-tank), ARTY (artillery), LEADER
"""

from vassal_framework.terrain import TerrainSystem, TerrainType


class WW2TacticalTerrain(TerrainSystem):
    """Terrain catalog for WW2 tactical (squad-level) games."""

    def _setup(self):
        self.unit_types = {'SQUAD', 'HALF', 'VEHICLE', 'AT', 'ARTY', 'LEADER', 'ALL'}

        # Open ground
        self.add_terrain_type(TerrainType(
            code='OG', name='Open Ground',
            move_costs={'ALL': '1'},
        ))

        # Grain (concealment)
        self.add_terrain_type(TerrainType(
            code='Gr', name='Grain',
            los_hinders=True,
            move_costs={'ALL': '1'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Brush
        self.add_terrain_type(TerrainType(
            code='Br', name='Brush',
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Woods
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'VEHICLE': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Building (wood)
        self.add_terrain_type(TerrainType(
            code='Bw', name='Wooden Building',
            los_blocks=True,
            move_costs={'VEHICLE': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Building (stone)
        self.add_terrain_type(TerrainType(
            code='Bs', name='Stone Building',
            los_blocks=True,
            move_costs={'VEHICLE': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -3},
        ))

        # Hill (elevation 1)
        self.add_terrain_type(TerrainType(
            code='H1', name='Hill (Level 1)', elevation=1,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Hill (elevation 2)
        self.add_terrain_type(TerrainType(
            code='H2', name='Hill (Level 2)', elevation=2,
            move_costs={'ALL': '3'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Foxhole / entrenchment
        self.add_terrain_type(TerrainType(
            code='Fx', name='Foxhole',
            move_costs={'ALL': '1'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Trench
        self.add_terrain_type(TerrainType(
            code='Tr', name='Trench',
            move_costs={'VEHICLE': 'X', 'ALL': '1'},
            combat_modifiers={'defender_drm': -3},
        ))

        # Wire
        self.add_terrain_type(TerrainType(
            code='Wi', name='Wire',
            is_hexside=True,
            move_costs={'VEHICLE': '2', 'ALL': '3'},
        ))

        # Minefield
        self.add_terrain_type(TerrainType(
            code='Mn', name='Minefield',
            move_costs={'ALL': '2'},
            cohesion_on_entry=2,
        ))

        # Road -- enables vehicle movement bonus
        self.add_terrain_type(TerrainType(
            code='Rd', name='Road',
            move_costs={'ALL': '1', 'VEHICLE': '1'},
        ))

        # Stream (hexside)
        self.add_terrain_type(TerrainType(
            code='St', name='Stream', is_hexside=True,
            move_costs={'VEHICLE': '2', 'ALL': '1'},
        ))

        # River (hexside)
        self.add_terrain_type(TerrainType(
            code='R', name='River', is_hexside=True,
            move_costs={'VEHICLE': 'X', 'ALL': '3'},
        ))

        # Bocage (hedgerow)
        self.add_terrain_type(TerrainType(
            code='Bc', name='Bocage', is_hexside=True,
            los_blocks=True,
            move_costs={'VEHICLE': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Rubble (from destroyed buildings)
        self.add_terrain_type(TerrainType(
            code='Ru', name='Rubble',
            move_costs={'VEHICLE': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))
