#!/usr/bin/env python3
"""
TEMPLATE: Infantry Firepower (IFP/IFD) combat -- ASL-style.

For tactical games where you fire a stream of dice and the result is the
final firepower (FP) cross-referenced against the target's morale.

Used by Advanced Squad Leader, Squad Battles, etc.
"""

import random
from vassal_framework.combat import CombatSystem, CombatResult, CombatType


class IFDCombat(CombatSystem):
    """Infantry Firepower (IFD/IFP) tactical combat resolver."""

    combat_type = CombatType.ODDS_CRT  # Reuse ODDS_CRT enum

    # Infantry Fire Table (simplified)
    # Format: firepower_column -> [result_code for 2d6 sum 2-12]
    # Codes: K (kill), KIA, MC (morale check), NMC (no MC), PTC (pin task check)
    IFT = {
        '1':  ['NE', 'NE', 'NE', 'NE', 'NE', 'NMC', 'NMC', 'PTC', 'PTC', 'NE', 'NE'],
        '2':  ['NE', 'NE', 'NMC', 'NMC', 'NMC', 'PTC', 'PTC', '1MC', '1MC', 'NE', 'NE'],
        '4':  ['NMC', 'NMC', 'PTC', 'PTC', '1MC', '1MC', '1MC', '2MC', '2MC', 'PTC', 'NMC'],
        '6':  ['PTC', 'PTC', '1MC', '1MC', '1MC', '2MC', '2MC', '3MC', 'KIA', '1MC', 'PTC'],
        '8':  ['1MC', '1MC', '2MC', '2MC', '2MC', '3MC', '3MC', 'KIA', 'KIA', '2MC', '1MC'],
        '12': ['2MC', '2MC', '3MC', '3MC', '3MC', 'KIA', 'KIA', 'KIA', 'K', '3MC', '2MC'],
        '16': ['3MC', '3MC', 'KIA', 'KIA', 'KIA', 'K', 'K', 'K', 'K', 'KIA', '3MC'],
        '20+':['KIA', 'KIA', 'K', 'K', 'K', 'K', 'K', 'K', 'K', 'K', 'KIA'],
    }

    def get_firepower_column(self, fp):
        """Map raw firepower to IFT column."""
        if fp >= 20: return '20+'
        if fp >= 16: return '16'
        if fp >= 12: return '12'
        if fp >= 8: return '8'
        if fp >= 6: return '6'
        if fp >= 4: return '4'
        if fp >= 2: return '2'
        return '1'

    def resolve(self, attacker, defender, modifiers=None, dr=None,
                firepower=1, target_morale=7, **kwargs):
        result = CombatResult()
        modifiers = modifiers or []

        col = self.get_firepower_column(firepower)
        result.column_used = col

        # Roll 2d6
        if dr is None:
            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            dr = d1 + d2
        else:
            d1, d2 = (dr // 2), (dr - dr // 2)
        modified_dr = dr + sum(m.value for m in modifiers)
        modified_dr = max(2, min(12, modified_dr))
        result.raw_die_rolls = [d1, d2]

        ift_result = self.IFT[col][modified_dr - 2]
        result.notes.append(f"IFT: FP{col}, 2d6={dr} -> {ift_result}")

        # Apply result
        if ift_result == 'K':
            result.defender_eliminated = True
            result.defender_hits = 99
        elif ift_result == 'KIA':
            result.defender_hits = 2
        elif ift_result.endswith('MC'):
            # Morale check -- in real ASL this is a check, here we approximate
            # If target_morale is poor, the unit might break
            mc_severity = int(ift_result[0])
            if random.randint(2, 12) > target_morale + mc_severity:
                result.defender_routs = True
                result.defender_hits = 1
        elif ift_result == 'PTC':
            # Pin task check
            if random.randint(2, 12) > target_morale:
                result.defender_hits = 1

        return result
