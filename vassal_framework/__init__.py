"""
VASSAL AI Framework -- Generic foundation for any VASSAL board game.

This package contains pure framework code: hex/grid math, unit detection,
abstract terrain and combat systems, Monte Carlo simulation, and the AI
decision engine. None of the modules in this package contain game-specific
code (no SPQR-specific terrain types, no Cannae-specific units, etc.).

Game-specific implementations live in `games/<GameName>/<game>_lib/` and
inherit from the abstract base classes in this package.

## Architecture

```
Layer 6: ai             AIDecisionEngine, MoveOption
Layer 5: montecarlo     MonteCarloSimulator, SimState, Move
Layer 4: combat         CombatSystem (abstract)
         terrain        TerrainSystem (abstract)
Layer 3: units          UnitScanner, Battlefield, Unit
Layer 2: grid           ModuleGrid, HexGridConfig, Board
Layer 1: save_io        GameState, save/load
```

## Quick start

```python
from vassal_framework import grid, units, save_io
from games.SPQR.spqr_lib import terrain, combat

# Load game
mg = grid.ModuleGrid.from_vmod('games/SPQR/SPQR.vmod')
state = save_io.GameState()
state.load_from_file('save.vsav')

# Game-specific systems
terrain_sys = terrain.SPQRTerrain()
combat_sys = combat.SPQRCombat()

# Generic pipeline
scanner = units.UnitScanner(mg, active_boards=units.detect_active_boards(state))
battlefield = units.Battlefield(scanner.scan(state))
```

## Onboarding a new game

See `vassal_framework/templates/` for starter files. Copy them to
`games/<GameName>/<game>_lib/` and customize the terrain types,
combat resolution, and unit type mappings for your specific game.
"""

__version__ = "1.0.0"

# Re-export key classes for convenient imports
from vassal_framework.grid import ModuleGrid, HexGridConfig, Board
from vassal_framework.save_io import GameState, deobfuscate, obfuscate, read_all_zip_entries
from vassal_framework.units import (
    UnitScanner, Battlefield, Unit,
    detect_active_boards, hex_distance_offset, hex_neighbors,
)
from vassal_framework.terrain import (
    TerrainSystem, TerrainType, TerrainMap, MoveResult,
)
from vassal_framework.combat import (
    CombatSystem, CombatResult, CombatModifier, CombatType,
)
from vassal_framework.montecarlo import (
    MonteCarloSimulator, SimState, SimUnit, Move, SimulationResult,
)
from vassal_framework.ai import AIDecisionEngine, MoveOption

__all__ = [
    # Grid
    'ModuleGrid', 'HexGridConfig', 'Board',
    # Save IO
    'GameState', 'deobfuscate', 'obfuscate', 'read_all_zip_entries',
    # Units
    'UnitScanner', 'Battlefield', 'Unit',
    'detect_active_boards', 'hex_distance_offset', 'hex_neighbors',
    # Terrain
    'TerrainSystem', 'TerrainType', 'TerrainMap', 'MoveResult',
    # Combat
    'CombatSystem', 'CombatResult', 'CombatModifier', 'CombatType',
    # Monte Carlo
    'MonteCarloSimulator', 'SimState', 'SimUnit', 'Move', 'SimulationResult',
    # AI
    'AIDecisionEngine', 'MoveOption',
]
