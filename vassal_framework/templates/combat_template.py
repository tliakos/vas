#!/usr/bin/env python3
"""
TEMPLATE: Game-specific combat system.

Copy this file to games/<GameName>/<game>_lib/combat.py and customize.

Three common combat patterns:

1. ODDS-BASED CRT (most common in modern wargames):
   - Calculate odds: attacker_strength / defender_strength
   - Look up column on CRT
   - Roll d6 (or 2d6) and apply modifiers
   - Result is one of: AE, AR, DR, DE, EX, NE

2. DIFFERENTIAL CRT:
   - Calculate difference: attacker - defender
   - Use difference as column index
   - Roll dice and apply

3. COHESION SHOCK (GBoH-style):
   - Size ratio determines column
   - Apply position superiority (flank/rear)
   - Apply weapon system superiority
   - Roll d10
   - Result is X(Y) hits to attacker(defender)

This template implements an ODDS-BASED CRT. See
games/SPQR/spqr_lib/combat.py for a Cohesion Shock example.
"""

import random
from vassal_framework.combat import CombatSystem, CombatResult, CombatType


class MyGameCombat(CombatSystem):
    """Combat resolver for [GameName] -- ODDS-BASED CRT example."""

    combat_type = CombatType.ODDS_CRT

    # Combat Results Table (CRT)
    # Format: column_label -> [(die_roll, result_code) for d6 1-6]
    # Result codes:
    #   AE = Attacker Eliminated
    #   AR = Attacker Retreats
    #   AR2 = Attacker Retreats 2 hexes
    #   DR = Defender Retreats
    #   DR2 = Defender Retreats 2 hexes
    #   DE = Defender Eliminated
    #   EX = Exchange (both lose 1 step)
    #   NE = No Effect
    CRT = {
        '1:3': ['AE', 'AE', 'AR', 'AR', 'NE', 'NE'],
        '1:2': ['AE', 'AR', 'AR', 'NE', 'NE', 'DR'],
        '1:1': ['AR', 'AR', 'NE', 'NE', 'DR', 'DR'],
        '2:1': ['AR', 'NE', 'NE', 'DR', 'DR', 'DE'],
        '3:1': ['NE', 'NE', 'DR', 'DR', 'DE', 'DE'],
        '4:1': ['NE', 'DR', 'DR', 'DE', 'DE', 'DE'],
        '5:1': ['DR', 'DR', 'DE', 'DE', 'DE', 'DE'],
    }

    def calculate_odds(self, attacker_strength, defender_strength):
        """Calculate odds column. Round DOWN in favor of defender."""
        if defender_strength == 0:
            return '5:1'
        ratio = attacker_strength / defender_strength
        if ratio >= 5: return '5:1'
        if ratio >= 4: return '4:1'
        if ratio >= 3: return '3:1'
        if ratio >= 2: return '2:1'
        if ratio >= 1: return '1:1'
        if ratio >= 0.5: return '1:2'
        return '1:3'

    def resolve(self, attacker, defender, modifiers=None, dr=None,
                attacker_strength=1, defender_strength=1, **kwargs):
        """Resolve combat using odds-based CRT."""
        result = CombatResult()
        modifiers = modifiers or []

        # Determine odds column
        col = self.calculate_odds(attacker_strength, defender_strength)
        result.column_used = col

        # Apply column shifts from modifiers
        cols = list(self.CRT.keys())
        if col in cols:
            shift = sum(m.column_shift for m in modifiers)
            idx = cols.index(col)
            new_idx = max(0, min(len(cols) - 1, idx + shift))
            actual_col = cols[new_idx]
        else:
            actual_col = col

        # Roll d6 with DRM
        if dr is None:
            dr = random.randint(1, 6)
        modified_dr = dr + sum(m.value for m in modifiers)
        modified_dr = max(1, min(6, modified_dr))
        result.raw_die_rolls = [dr]

        # Look up result
        crt_result = self.CRT[actual_col][modified_dr - 1]
        result.notes.append(f"CRT: {actual_col} col, DR={dr} -> {crt_result}")

        # Apply result
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
        # NE: no hits

        return result
