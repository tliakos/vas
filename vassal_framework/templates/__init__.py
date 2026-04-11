"""
VASSAL framework templates -- Starter files for new game implementations.

To onboard a new game, copy these template files to your game directory:

    games/<GameName>/
        <game>_lib/
            __init__.py
            terrain.py     <- copy from terrain_template.py
            combat.py      <- copy from combat_template.py
            units.py       <- copy from units_template.py
            runner.py      <- copy from runner_template.py

Then edit each file to implement your game's specific:
- Terrain types and movement costs
- Combat resolution rules (CRT, modifiers, etc.)
- Side classification (which images = which side)
- Unit type code mappings

See games/SPQR/spqr_lib/ for a complete reference implementation.
"""
