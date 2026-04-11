#!/usr/bin/env python3
"""
TEMPLATE: Game-specific terrain system.

Copy this file to games/<GameName>/<game>_lib/terrain.py and customize:
1. Add your game's terrain types in _setup()
2. Set movement costs per unit type
3. Set combat modifiers (defender_drm, column_shift)
4. Set LOS effects (los_blocks, los_hinders)
5. Set elevation for hills/mountains

Refer to games/SPQR/spqr_lib/terrain.py for a complete example.
"""

from vassal_framework.terrain import TerrainSystem, TerrainType


class MyGameTerrain(TerrainSystem):
    """Terrain rules for [GameName]."""

    def _setup(self):
        # Define unit type codes used in your game's movement tables
        self.unit_types = {'INF', 'CAV', 'ARM', 'ARTY', 'HQ', 'ALL'}

        # Clear terrain (every game has this)
        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Woods (typical: blocks LOS, +1 MP, defender +1 DRM)
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'ALL': '2', 'ARM': '3'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Hills (elevation 1, hinders LOS)
        self.add_terrain_type(TerrainType(
            code='H', name='Hills', elevation=1,
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Town/City (strong defensive bonus)
        self.add_terrain_type(TerrainType(
            code='T', name='Town',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # River (hexside feature, +1 MP to cross)
        self.add_terrain_type(TerrainType(
            code='R', name='River',
            is_hexside=True,
            move_costs={'ALL': '2', 'ARM': 'X'},  # Armor cannot cross
            combat_modifiers={'defender_drm': 1},
        ))

        # Add more terrain types as needed for your game...
