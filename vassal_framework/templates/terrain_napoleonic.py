#!/usr/bin/env python3
"""
TEMPLATE: Napoleonic linear warfare terrain.

For games like La Bataille, Vive l'Empereur, Napoleon's Last Battles.
Movement units: INF (infantry), CAV (cavalry), HC (heavy cav), LC (light cav),
                ARTY (artillery), HORSE_ART (horse artillery)
"""

from vassal_framework.terrain import TerrainSystem, TerrainType


class NapoleonicTerrain(TerrainSystem):
    """Terrain catalog for Napoleonic linear warfare games."""

    def _setup(self):
        self.unit_types = {'INF', 'CAV', 'HC', 'LC', 'ARTY', 'HORSE_ART', 'GUARD', 'ALL'}

        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Wheat / Crops -- minor cover
        self.add_terrain_type(TerrainType(
            code='Wh', name='Wheat',
            los_hinders=True,
            move_costs={'ALL': '1'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Woods / Forest -- blocks LOS, no charge
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'CAV': '3', 'HC': '3', 'ARTY': 'X', 'ALL': '2'},
            combat_modifiers={'defender_drm': -2, 'no_cavalry_charge': 1},
        ))

        # Hill -- elevation
        self.add_terrain_type(TerrainType(
            code='H', name='Hill', elevation=1,
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Steep Hill / Ridge
        self.add_terrain_type(TerrainType(
            code='SH', name='Steep Hill', elevation=2,
            move_costs={'ARTY': 'X', 'CAV': '3', 'ALL': '3'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Village / Town -- strong defensive
        self.add_terrain_type(TerrainType(
            code='V', name='Village',
            move_costs={'ARTY': '2', 'ALL': '2'},
            combat_modifiers={'defender_drm': -2, 'no_cavalry_charge': 1},
        ))

        # City -- very strong defense
        self.add_terrain_type(TerrainType(
            code='Ci', name='City',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -3, 'no_cavalry_charge': 1},
        ))

        # Stream (hexside) -- minor delay
        self.add_terrain_type(TerrainType(
            code='St', name='Stream', is_hexside=True,
            move_costs={'ARTY': '2', 'ALL': '1'},
        ))

        # River (hexside) -- major obstacle
        self.add_terrain_type(TerrainType(
            code='R', name='River', is_hexside=True,
            move_costs={'ARTY': 'X', 'ALL': '3'},
            combat_modifiers={'defender_drm': 1},
        ))

        # Bridge -- crosses river without penalty
        self.add_terrain_type(TerrainType(
            code='B', name='Bridge', is_hexside=True,
            move_costs={'ALL': '1'},
        ))

        # Road -- reduced cost (in addition to terrain)
        self.add_terrain_type(TerrainType(
            code='Rd', name='Road',
            move_costs={'ALL': '1'},
        ))

        # Marsh / Swamp
        self.add_terrain_type(TerrainType(
            code='Mr', name='Marsh',
            move_costs={'CAV': 'X', 'HC': 'X', 'ARTY': 'X', 'ALL': '3'},
            combat_modifiers={'defender_drm': -1, 'attacker_drm': -1},
        ))

        # Sunken Road
        self.add_terrain_type(TerrainType(
            code='SR', name='Sunken Road',
            move_costs={'ALL': '1'},
            combat_modifiers={'defender_drm': -2},
        ))
