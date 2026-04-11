#!/usr/bin/env python3
"""
VASSAL Combat System -- Generic combat resolution (no game-specific code).

This module provides the abstract base classes for combat systems.
Each game has its own combat resolution rules; subclass CombatSystem
in a game-specific library to implement them.

See `games/SPQR/spqr_lib/combat.py` for an example implementation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


# ---------------------------------------------------------------------------
# Combat types (for all games)
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
    attacker_retreats: int = 0
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
# Abstract combat system
# ---------------------------------------------------------------------------

class CombatSystem:
    """Abstract combat resolver.

    Subclass for specific games. Override resolve() and
    optionally expected_value() and calculate_modifiers().
    """

    combat_type = CombatType.ODDS_CRT

    def resolve(self, attacker, defender, modifiers=None, dr=None, **kwargs):
        """Resolve a combat. Override in subclass.

        Args:
          attacker: Unit or list of Units
          defender: Unit
          modifiers: list of CombatModifier
          dr: optional pre-rolled die value (for testing/MC simulation)
          **kwargs: game-specific parameters (size, type, position, etc.)

        Returns: CombatResult
        """
        raise NotImplementedError("Override resolve() in subclass")

    def calculate_modifiers(self, attacker, defender, terrain_system=None, board_name=""):
        """Calculate all applicable modifiers for a combat.

        Default implementation only handles terrain. Override for
        game-specific modifiers (Charisma, weapon superiority, etc.).
        """
        modifiers = []

        if terrain_system and board_name and defender.hex_col is not None:
            drm, notes = terrain_system.combat_modifier(
                board_name, defender.hex_col, defender.hex_row
            )
            if drm:
                modifiers.append(CombatModifier(
                    name=f"Terrain ({notes})", value=drm, source='terrain'
                ))

        return modifiers

    def expected_value(self, *args, n_simulations=1000, **kwargs):
        """Run Monte Carlo to estimate expected outcome.

        Default implementation runs N simulations of resolve() and aggregates.
        Override for game-specific evaluation metrics.
        """
        results = []
        for _ in range(n_simulations):
            r = self.resolve(None, None, **kwargs)
            results.append(r)

        avg_att = sum(r.attacker_hits for r in results) / len(results)
        avg_def = sum(r.defender_hits for r in results) / len(results)

        return {
            'avg_attacker_hits': round(avg_att, 2),
            'avg_defender_hits': round(avg_def, 2),
            'simulations': n_simulations,
        }
