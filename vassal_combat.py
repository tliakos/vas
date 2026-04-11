#!/usr/bin/env python3
"""
VASSAL Combat System -- Generic combat resolution for any wargame.

Wargame combat systems vary widely:
- Odds-based CRT (e.g., 3:1 column with d6) -- standard ASL/SCS/OCS style
- Differential CRT (attacker - defender = column) -- some classic games
- Cohesion shock combat (e.g., GBoH/SPQR) -- size ratio + superiority + d10
- Card-driven combat (e.g., COIN, CDG) -- card play resolves outcomes

This module provides:
1. CombatType: Enum of combat types
2. CombatModifier: A single modifier (terrain, leader, position, etc.)
3. CombatResult: The outcome of a combat
4. CombatSystem: Abstract combat resolver
5. SPQRCombat: SPQR-specific implementation (Cohesion Shock)

Each game's combat system subclasses CombatSystem and implements
resolve() with the game's specific resolution logic.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import random


# ---------------------------------------------------------------------------
# Combat types
# ---------------------------------------------------------------------------

class CombatType(Enum):
    ODDS_CRT = "odds_crt"             # Attacker:Defender ratio CRT
    DIFFERENTIAL = "differential"     # Attacker - Defender = column
    COHESION_SHOCK = "cohesion_shock" # Size ratio + Superiority (GBoH style)
    MISSILE = "missile"               # Ranged fire
    CARD = "card"                     # Card-driven


# ---------------------------------------------------------------------------
# Combat result
# ---------------------------------------------------------------------------

@dataclass
class CombatResult:
    """The outcome of a single combat."""

    attacker_hits: int = 0
    defender_hits: int = 0
    attacker_eliminated: bool = False
    defender_eliminated: bool = False
    attacker_routs: bool = False
    defender_routs: bool = False
    attacker_retreats: int = 0  # Hexes to retreat
    defender_retreats: int = 0
    leader_casualty: bool = False
    notes: List[str] = field(default_factory=list)
    raw_die_rolls: List[int] = field(default_factory=list)
    column_used: str = ""
    superiority: str = ""

    def summary(self):
        s = []
        if self.column_used:
            s.append(f"Column {self.column_used}")
        if self.raw_die_rolls:
            s.append(f"DR={','.join(str(r) for r in self.raw_die_rolls)}")
        s.append(f"Hits: A{self.attacker_hits}/D{self.defender_hits}")
        if self.attacker_eliminated: s.append("ATTACKER ELIMINATED")
        if self.defender_eliminated: s.append("DEFENDER ELIMINATED")
        if self.attacker_routs: s.append("Attacker routs")
        if self.defender_routs: s.append("Defender routs")
        return ' | '.join(s)


# ---------------------------------------------------------------------------
# Combat modifier
# ---------------------------------------------------------------------------

@dataclass
class CombatModifier:
    """A modifier affecting combat resolution."""
    name: str
    value: int = 0          # DRM (positive = favors attacker, negative = favors defender)
    column_shift: int = 0   # CRT column shift
    superiority: bool = False  # Position superiority (doubles defender hits in shock)
    source: str = ""        # 'terrain', 'leader', 'position', 'weapon', 'flank', etc.

    def __repr__(self):
        parts = [self.name]
        if self.value: parts.append(f"DRM{self.value:+d}")
        if self.column_shift: parts.append(f"shift{self.column_shift:+d}")
        if self.superiority: parts.append("AS/DS")
        return ' '.join(parts)


# ---------------------------------------------------------------------------
# Generic combat system
# ---------------------------------------------------------------------------

class CombatSystem:
    """Abstract combat resolver. Subclass for specific games."""

    combat_type = CombatType.ODDS_CRT

    def resolve(self, attacker, defender, modifiers=None, dr=None):
        """Resolve a combat. Override in subclass.

        attacker: Unit or list of Units
        defender: Unit
        modifiers: list of CombatModifier
        dr: optional pre-rolled die value (for testing/MC simulation)

        Returns: CombatResult
        """
        raise NotImplementedError("Override resolve() in subclass")

    def calculate_modifiers(self, attacker, defender, terrain_system=None, board_name=""):
        """Calculate all applicable modifiers for a combat.

        Returns: list of CombatModifier
        """
        modifiers = []

        # Terrain modifier (defender's hex)
        if terrain_system and board_name and defender.hex_col is not None:
            drm, notes = terrain_system.combat_modifier(
                board_name, defender.hex_col, defender.hex_row
            )
            if drm:
                modifiers.append(CombatModifier(
                    name=f"Terrain ({notes})", value=drm, source='terrain'
                ))

        return modifiers


# ---------------------------------------------------------------------------
# SPQR Cohesion Shock Combat
# ---------------------------------------------------------------------------

class SPQRCombat(CombatSystem):
    """SPQR / Great Battles of History shock combat resolution.

    Procedure (per SPQR rules section 8.4):
    1. Pre-Shock TQ Check (units marked MUST CHECK)
    2. Leader Casualty Check (if leader stacked with combat unit)
    3. The Charge: Determine Position Superiority (Frontal/Flank/Rear)
    4. Clash of Spears and Swords: Determine Weapon System Superiority
    5. Shock Resolution: Use Shock CRT
       - Column = Size ratio (Attacker:Defender)
       - DR = d10 (0-9)
       - Result = X(Y) where X=attacker hits, Y=defender hits
       - Superiority doubles opponent's hits
    6. Collapse: If hits >= TQ, unit routs
    """

    combat_type = CombatType.COHESION_SHOCK

    # Shock CRT (Size ratio columns, d10 results)
    # Each entry: (col_label, [(dr, attacker_hits, defender_hits) for d10 0-9])
    # This is a simplified representative table - actual SPQR CRT is more complex
    SHOCK_CRT = {
        '1:5':  [(0, 4, 0), (1, 3, 0), (2, 3, 0), (3, 3, 1), (4, 3, 1),
                 (5, 2, 1), (6, 2, 1), (7, 2, 2), (8, 2, 2), (9, 1, 2)],
        '1:4':  [(0, 4, 0), (1, 3, 0), (2, 3, 1), (3, 3, 1), (4, 2, 1),
                 (5, 2, 2), (6, 2, 2), (7, 2, 2), (8, 1, 2), (9, 1, 3)],
        '1:3':  [(0, 4, 1), (1, 3, 1), (2, 3, 1), (3, 2, 2), (4, 2, 2),
                 (5, 2, 2), (6, 1, 2), (7, 1, 3), (8, 1, 3), (9, 0, 3)],
        '1:2':  [(0, 3, 1), (1, 3, 1), (2, 3, 2), (3, 2, 2), (4, 2, 2),
                 (5, 2, 2), (6, 1, 3), (7, 1, 3), (8, 0, 3), (9, 0, 4)],
        '1:1':  [(0, 3, 2), (1, 3, 2), (2, 2, 2), (3, 2, 2), (4, 2, 3),
                 (5, 1, 3), (6, 1, 3), (7, 1, 4), (8, 0, 4), (9, 0, 4)],
        '2:1':  [(0, 2, 2), (1, 2, 3), (2, 2, 3), (3, 1, 3), (4, 1, 3),
                 (5, 1, 4), (6, 0, 4), (7, 0, 4), (8, 0, 5), (9, 0, 5)],
        '3:1':  [(0, 2, 3), (1, 1, 3), (2, 1, 4), (3, 1, 4), (4, 0, 4),
                 (5, 0, 4), (6, 0, 5), (7, 0, 5), (8, 0, 6), (9, 0, 6)],
        '4:1':  [(0, 1, 3), (1, 1, 4), (2, 1, 4), (3, 0, 4), (4, 0, 5),
                 (5, 0, 5), (6, 0, 5), (7, 0, 6), (8, 0, 6), (9, 0, 7)],
        '5:1':  [(0, 1, 4), (1, 0, 4), (2, 0, 5), (3, 0, 5), (4, 0, 5),
                 (5, 0, 6), (6, 0, 6), (7, 0, 7), (8, 0, 7), (9, 0, 8)],
    }

    # Shock Superiority Chart (simplified)
    # Returns column shift and superiority type
    WEAPON_SUPERIORITY = {
        # (attacker_type, defender_type) -> (shift, sup_type)
        ('LG', 'PH'): (0, 'none'),       # Legion vs Phalanx: parity (Phalanx better frontal)
        ('LG', 'HI'): (0, 'AS'),          # Legion attack superior vs HI
        ('LG', 'MI'): (1, 'AS'),
        ('LG', 'LI'): (2, 'AS'),
        ('PH', 'LG'): (1, 'none'),        # Phalanx vs Legion: column shift right (favorable for PH)
        ('PH', 'HI'): (0, 'none'),
        ('HI', 'LI'): (1, 'AS'),
        ('RC', 'LC'): (0, 'AS'),          # Roman Cav vs Light Cav: AS
        ('RC', 'HC'): (0, 'none'),        # RC vs HC: parity
        ('LC', 'RC'): (-2, 'DS'),         # LC attacking RC: very disadvantaged
        ('LC', 'LG'): (-2, 'DS'),
        ('HC', 'RC'): (1, 'AS'),          # HC vs RC: AS
    }

    def determine_position_superiority(self, attack_hex, defender_hex, defender_facing=None):
        """Determine if attacker has Position Superiority (flank/rear attack).

        For now, assume frontal unless explicitly told otherwise.
        Real implementation needs facing data from save file.
        """
        return 'frontal'  # TODO: parse facing from rotate trait state

    def determine_weapon_superiority(self, attacker_type, defender_type):
        """Look up weapon system superiority on the Shock Superiority Chart."""
        key = (attacker_type, defender_type)
        if key in self.WEAPON_SUPERIORITY:
            return self.WEAPON_SUPERIORITY[key]
        return (0, 'none')

    def calculate_size_ratio(self, attacker_size, defender_size):
        """Calculate the Shock CRT column from Size ratio.

        Per SPQR rule 8.46: Round in favor of defender (down for attacker).
        """
        if defender_size == 0:
            return '5:1'
        ratio = attacker_size / defender_size
        if ratio >= 5: return '5:1'
        if ratio >= 4: return '4:1'
        if ratio >= 3: return '3:1'
        if ratio >= 2: return '2:1'
        if ratio >= 1: return '1:1'
        if ratio >= 0.5: return '1:2'
        if ratio >= 0.34: return '1:3'
        if ratio >= 0.25: return '1:4'
        return '1:5'

    def resolve(self, attacker, defender, modifiers=None, dr=None,
                attacker_size=1, defender_size=1,
                attacker_type='LG', defender_type='LG',
                position='frontal'):
        """Resolve an SPQR shock combat.

        attacker, defender: Unit objects (or None for testing)
        modifiers: list of CombatModifier
        dr: optional pre-rolled d10 (0-9), random if None
        attacker_size, defender_size: combat strength values
        attacker_type, defender_type: unit type codes
        position: 'frontal', 'flank', 'rear'
        """
        result = CombatResult()
        modifiers = modifiers or []

        # 1. Calculate Size Ratio column
        col = self.calculate_size_ratio(attacker_size, defender_size)
        result.column_used = col

        # 2. Apply weapon superiority
        weapon_shift, weapon_sup = self.determine_weapon_superiority(attacker_type, defender_type)

        # 3. Apply column shifts from modifiers
        total_shift = weapon_shift + sum(m.column_shift for m in modifiers)

        # Shift the column
        cols = list(self.SHOCK_CRT.keys())
        if col in cols:
            idx = cols.index(col)
            new_idx = max(0, min(len(cols) - 1, idx + total_shift))
            actual_col = cols[new_idx]
        else:
            actual_col = col
        result.column_used = f"{col} -> {actual_col}" if actual_col != col else col

        # 4. Roll d10 (0-9) and apply DRM
        if dr is None:
            dr = random.randint(0, 9)
        modified_dr = dr + sum(m.value for m in modifiers)
        modified_dr = max(0, min(9, modified_dr))
        result.raw_die_rolls = [dr]

        # 5. Look up CRT result
        crt_row = self.SHOCK_CRT[actual_col][modified_dr]
        att_hits = crt_row[1]
        def_hits = crt_row[2]

        # 6. Apply Position Superiority (per Rule 8.46)
        # Position superiority doubles defender hits
        position_sup = (position == 'flank' or position == 'rear')
        if position_sup:
            def_hits *= 2
            result.superiority = 'AS (Position)'
            result.notes.append(f"Flank/rear attack: defender hits doubled")
        elif weapon_sup == 'AS':
            def_hits *= 2
            result.superiority = 'AS (Weapon)'
            result.notes.append(f"Weapon AS: defender hits doubled")
        elif weapon_sup == 'DS':
            att_hits *= 2
            result.superiority = 'DS (Weapon)'
            result.notes.append(f"Weapon DS: attacker hits doubled")

        result.attacker_hits = att_hits
        result.defender_hits = def_hits
        result.notes.append(f"DR={dr} on column {actual_col}")

        return result

    def expected_value(self, attacker_size, defender_size, attacker_type, defender_type,
                       position='frontal', n_simulations=1000):
        """Run Monte Carlo to estimate expected outcome.

        Returns: dict with average attacker/defender hits, win rates, etc.
        """
        results = []
        for _ in range(n_simulations):
            r = self.resolve(None, None,
                             attacker_size=attacker_size, defender_size=defender_size,
                             attacker_type=attacker_type, defender_type=defender_type,
                             position=position)
            results.append(r)

        avg_att = sum(r.attacker_hits for r in results) / len(results)
        avg_def = sum(r.defender_hits for r in results) / len(results)
        att_eliminated_pct = sum(1 for r in results if r.attacker_hits >= 5) / len(results)
        def_eliminated_pct = sum(1 for r in results if r.defender_hits >= 5) / len(results)

        return {
            'avg_attacker_hits': round(avg_att, 2),
            'avg_defender_hits': round(avg_def, 2),
            'attacker_destroyed_pct': round(att_eliminated_pct * 100, 1),
            'defender_destroyed_pct': round(def_eliminated_pct * 100, 1),
            'simulations': n_simulations,
        }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    spqr = SPQRCombat()

    print("=== SPQR Shock Combat Test ===\n")

    # Roman Legion attacking Phalanx (frontal)
    print("Roman LG (size 5) attacking Macedonian PH (size 7), frontal:")
    r = spqr.resolve(None, None, attacker_size=5, defender_size=7,
                     attacker_type='LG', defender_type='PH', position='frontal',
                     dr=5)
    print(f"  {r.summary()}")

    # Same combat, flanking attack
    print("\nSame combat, FLANK attack:")
    r = spqr.resolve(None, None, attacker_size=5, defender_size=7,
                     attacker_type='LG', defender_type='PH', position='flank',
                     dr=5)
    print(f"  {r.summary()}")

    # RC vs LC (favorable for Roman)
    print("\nRC (size 4) attacking LC (size 3), frontal:")
    r = spqr.resolve(None, None, attacker_size=4, defender_size=3,
                     attacker_type='RC', defender_type='LC', position='frontal',
                     dr=5)
    print(f"  {r.summary()}")

    # LC vs RC (futile)
    print("\nLC attacking RC (futile attack):")
    r = spqr.resolve(None, None, attacker_size=3, defender_size=4,
                     attacker_type='LC', defender_type='RC', position='frontal',
                     dr=5)
    print(f"  {r.summary()}")

    # Monte Carlo: average outcome of LG vs PH frontal
    print("\n=== Monte Carlo: LG (size 5) vs PH (size 7) frontal ===")
    ev = spqr.expected_value(5, 7, 'LG', 'PH', 'frontal', 5000)
    for k, v in ev.items():
        print(f"  {k}: {v}")

    # Same matchup but FLANK
    print("\n=== Monte Carlo: LG (size 5) vs PH (size 7) FLANK ===")
    ev = spqr.expected_value(5, 7, 'LG', 'PH', 'flank', 5000)
    for k, v in ev.items():
        print(f"  {k}: {v}")
