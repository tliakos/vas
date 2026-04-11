#!/usr/bin/env python3
"""
TEMPLATE: WW2 operational terrain (regimental/divisional).

For games like OCS (Operational Combat Series), SCS (Standard Combat Series),
ETO, A World at War.
Movement units: INF (infantry), MECH (mechanized), ARMOR, REC (recon),
                ARTY (artillery), HQ
"""

from vassal_framework.terrain import TerrainSystem, TerrainType


class WW2OperationalTerrain(TerrainSystem):
    """Terrain catalog for WW2 operational games."""

    def _setup(self):
        self.unit_types = {'INF', 'MECH', 'ARMOR', 'REC', 'ARTY', 'HQ', 'AIR', 'ALL'}

        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Forest -- difficult for mechanized
        self.add_terrain_type(TerrainType(
            code='F', name='Forest',
            los_blocks=True,
            move_costs={'ARMOR': '3', 'MECH': '2', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Hills
        self.add_terrain_type(TerrainType(
            code='H', name='Hills', elevation=1,
            move_costs={'ARMOR': '2', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Mountains
        self.add_terrain_type(TerrainType(
            code='M', name='Mountains', elevation=2,
            move_costs={'ARMOR': 'X', 'ALL': '3'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Town
        self.add_terrain_type(TerrainType(
            code='T', name='Town',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # City -- big defensive bonus
        self.add_terrain_type(TerrainType(
            code='Ci', name='City',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -3},
        ))

        # Major City
        self.add_terrain_type(TerrainType(
            code='MC', name='Major City',
            move_costs={'ALL': '3'},
            combat_modifiers={'defender_drm': -4},
        ))

        # Marsh / Swamp
        self.add_terrain_type(TerrainType(
            code='Sw', name='Swamp',
            move_costs={'ARMOR': 'X', 'MECH': 'X', 'ALL': '3'},
            combat_modifiers={'defender_drm': -1, 'attacker_drm': -1},
        ))

        # Desert
        self.add_terrain_type(TerrainType(
            code='D', name='Desert',
            move_costs={'ALL': '1'},
        ))

        # River (hexside) -- major obstacle
        self.add_terrain_type(TerrainType(
            code='R', name='River', is_hexside=True,
            move_costs={'ARMOR': 'X', 'MECH': '3', 'ALL': '3'},
            combat_modifiers={'defender_drm': 2},
        ))

        # Major River (impassable except at bridges)
        self.add_terrain_type(TerrainType(
            code='MR', name='Major River', is_hexside=True,
            move_costs={'ALL': 'X'},
        ))

        # Bridge
        self.add_terrain_type(TerrainType(
            code='B', name='Bridge', is_hexside=True,
            move_costs={'ALL': '1'},
        ))

        # Ford
        self.add_terrain_type(TerrainType(
            code='Fo', name='Ford', is_hexside=True,
            move_costs={'ARMOR': '2', 'ALL': '2'},
        ))

        # Road
        self.add_terrain_type(TerrainType(
            code='Rd', name='Road',
            move_costs={'ALL': '1'},
        ))

        # Highway / Improved Road
        self.add_terrain_type(TerrainType(
            code='Hw', name='Highway',
            move_costs={'ALL': '1'},
        ))

        # Rail
        self.add_terrain_type(TerrainType(
            code='Rl', name='Railroad',
            move_costs={'ALL': '1'},
        ))

        # Fortification (concrete bunker, Maginot, etc.)
        self.add_terrain_type(TerrainType(
            code='Fr', name='Fortification',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -3},
        ))

        # Coast (limits options)
        self.add_terrain_type(TerrainType(
            code='Co', name='Coast',
            move_costs={'ALL': '1'},
        ))
