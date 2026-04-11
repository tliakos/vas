#!/usr/bin/env python3
"""
TEMPLATE: Ancient warfare terrain (GBoH-style).

For games like SPQR, Alexander the Great, Cataphract, Caesar, Samurai.
Movement units: PH (phalanx), LG (legion), HI (heavy inf), MI (medium),
                LI (light inf), SK (skirmisher), CAV, EL (elephant)
"""

from vassal_framework.terrain import TerrainSystem, TerrainType


class AncientsTerrain(TerrainSystem):
    """Terrain catalog for ancient warfare games."""

    def _setup(self):
        self.unit_types = {'PH', 'LG', 'HI', 'MI', 'LI', 'SK', 'CAV', 'EL', 'ALL'}

        # Clear (default)
        self.add_terrain_type(TerrainType(
            code='C', name='Clear',
            move_costs={'ALL': '1'},
        ))

        # Rough -- prohibited to phalanx and elephants, costs cohesion
        self.add_terrain_type(TerrainType(
            code='R', name='Rough',
            move_costs={'PH': 'X', 'EL': 'X', 'CAV': '2', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
            cohesion_on_entry=1,
        ))

        # Woods -- blocks LOS, prohibited to PH/EL
        self.add_terrain_type(TerrainType(
            code='W', name='Woods',
            los_blocks=True,
            move_costs={'PH': 'X', 'EL': 'X', 'CAV': '3', 'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
            cohesion_on_entry=1,
        ))

        # Hills -- elevation 1, hinders LOS
        self.add_terrain_type(TerrainType(
            code='H', name='Hills', elevation=1,
            los_hinders=True,
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -1},
        ))

        # Mountains -- impassable to most
        self.add_terrain_type(TerrainType(
            code='M', name='Mountains', elevation=2,
            los_blocks=True,
            move_costs={'PH': 'X', 'CAV': 'X', 'EL': 'X', 'ALL': '3'},
            combat_modifiers={'defender_drm': -2},
            cohesion_on_entry=1,
        ))

        # Marsh / Swamp
        self.add_terrain_type(TerrainType(
            code='Mr', name='Marsh',
            move_costs={'PH': 'X', 'EL': 'X', 'CAV': '3', 'ALL': '3'},
            combat_modifiers={'defender_drm': -1, 'attacker_drm': -1},
            cohesion_on_entry=1,
        ))

        # Stream (hexside) -- minor obstacle
        self.add_terrain_type(TerrainType(
            code='St', name='Stream', is_hexside=True,
            move_costs={'ALL': '1'},
        ))

        # Shallow River (hexside)
        self.add_terrain_type(TerrainType(
            code='Sr', name='Shallow River', is_hexside=True,
            move_costs={
                'PH': '2', 'LG': '2', 'HI': '2', 'MI': '2', 'LI': '1',
                'SK': '1', 'CAV': '0', 'EL': '1', 'ALL': '1',
            },
            combat_modifiers={'defender_drm': 1},
            cohesion_on_entry=1,
        ))

        # River (hexside) -- major obstacle
        self.add_terrain_type(TerrainType(
            code='Rv', name='River', is_hexside=True,
            move_costs={'PH': 'X', 'EL': 'X', 'CAV': '3', 'ALL': '3'},
            combat_modifiers={'defender_drm': 2},
            cohesion_on_entry=2,
        ))

        # Roman Camp -- defensive fortification
        self.add_terrain_type(TerrainType(
            code='Camp', name='Roman Camp',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))

        # Town/Village
        self.add_terrain_type(TerrainType(
            code='T', name='Town',
            move_costs={'ALL': '2'},
            combat_modifiers={'defender_drm': -2},
        ))
