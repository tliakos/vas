#!/usr/bin/env python3
"""
TEMPLATE: Differential CRT combat (attacker_strength - defender_strength = column).

For games like SPI's classics, some Avalanche Press, some Decision Games.
"""

import random
from vassal_framework.combat import CombatSystem, CombatResult, CombatType


class DifferentialCombat(CombatSystem):
    """Differential CRT combat resolver."""

    combat_type = CombatType.DIFFERENTIAL

    # Differential CRT
    # Format: differential_range -> [result_code for d6 1-6]
    CRT = {
        '-7+': ['AE', 'AE', 'AE', 'AE', 'AR', 'AR'],
        '-6 to -5': ['AE', 'AE', 'AR', 'AR', 'AR', 'NE'],
        '-4 to -3': ['AE', 'AR', 'AR', 'NE', 'NE', 'NE'],
        '-2 to -1': ['AR', 'AR', 'NE', 'NE', 'NE', 'DR'],
        '0': ['AR', 'NE', 'NE', 'NE', 'DR', 'DR'],
        '1 to 2': ['NE', 'NE', 'NE', 'DR', 'DR', 'DE'],
        '3 to 4': ['NE', 'NE', 'DR', 'DR', 'DE', 'DE'],
        '5 to 6': ['NE', 'DR', 'DR', 'DE', 'DE', 'DE'],
        '7+': ['DR', 'DR', 'DE', 'DE', 'DE', 'DE'],
    }

    def calculate_differential(self, attacker_strength, defender_strength):
        """Calculate the column from strength differential."""
        diff = attacker_strength - defender_strength
        if diff <= -7: return '-7+'
        if diff <= -5: return '-6 to -5'
        if diff <= -3: return '-4 to -3'
        if diff <= -1: return '-2 to -1'
        if diff == 0: return '0'
        if diff <= 2: return '1 to 2'
        if diff <= 4: return '3 to 4'
        if diff <= 6: return '5 to 6'
        return '7+'

    def resolve(self, attacker, defender, modifiers=None, dr=None,
                attacker_strength=1, defender_strength=1, **kwargs):
        result = CombatResult()
        modifiers = modifiers or []

        col = self.calculate_differential(attacker_strength, defender_strength)
        result.column_used = col

        if dr is None:
            dr = random.randint(1, 6)
        modified_dr = dr + sum(m.value for m in modifiers)
        modified_dr = max(1, min(6, modified_dr))
        result.raw_die_rolls = [dr]

        crt_result = self.CRT[col][modified_dr - 1]
        result.notes.append(f"Differential CRT: {col}, DR={dr} -> {crt_result}")

        # Apply result codes
        if crt_result == 'AE':
            result.attacker_eliminated = True
        elif crt_result == 'AR':
            result.attacker_retreats = 1
            result.attacker_hits = 1
        elif crt_result == 'DR':
            result.defender_retreats = 1
            result.defender_hits = 1
        elif crt_result == 'DE':
            result.defender_eliminated = True

        return result
