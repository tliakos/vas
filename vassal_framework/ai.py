#!/usr/bin/env python3
"""
VASSAL AI Decision Engine -- Move evaluation and ranking.

This engine is GAME-AGNOSTIC. It does not know about leaders, hexes,
or any specific activation model. Game libs plug in:

  - activation_generator: enumerates ActivationContext objects from a
    battlefield. An "activation" is a generic turn opportunity --
    a leader issuing orders (GBoH), a formation activating (OCS), a card
    being played (CDG), a faction taking an Op (COIN), or a whole-side
    impulse (IGOUGO).

  - candidate_generator: given an ActivationContext, returns candidate
    MoveOption sequences (the actual actions the AI is considering).

  - scorer: optional, computes expected_value from a SimulationResult.
    Different game families care about different things (units lost,
    territory held, victory points, morale).

The framework provides default scorers and a simple leader-based
activation generator for GBoH-style games. New games override the
parts that don't fit.
"""

import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Any
from itertools import combinations, product

from vassal_framework.units import Battlefield, Unit, hex_distance_offset, hex_neighbors
from vassal_framework.montecarlo import MonteCarloSimulator, SimState, SimUnit, Move, SimulationResult


# ---------------------------------------------------------------------------
# Activation context -- generic "turn opportunity"
# ---------------------------------------------------------------------------

@dataclass
class ActivationContext:
    """A generic 'turn opportunity' for one side to take actions.

    This is the abstraction that lets the framework support any activation
    model. The game lib's activation_generator returns a list of these.

    Fields:
      side: which side is acting ('Roman', 'Allied', 'Axis', etc.)
      kind: free-form label for the activation type
        ('leader', 'formation', 'phase', 'card', 'faction_op', 'impulse', ...)
      description: human-readable description ("Falco activates", "Card: Charge!")
      actor: optional Unit that drives the activation (e.g., a leader)
      members: optional list of Units that participate (e.g., a formation)
      n_actions: how many discrete actions are allowed (orders/MPs/etc.)
      metadata: game-specific extras (card name, faction state, phase, ...)
    """
    side: str
    kind: str = 'generic'
    description: str = ''
    actor: Optional[Unit] = None
    members: Optional[List[Unit]] = None
    n_actions: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Move evaluation
# ---------------------------------------------------------------------------

@dataclass
class MoveOption:
    """A candidate move sequence with its evaluation."""
    name: str
    moves: List[Move]
    description: str = ""
    rule_refs: List[str] = field(default_factory=list)
    expected_value: float = 0.0
    win_probability: float = 0.0
    risk: str = ""
    notes: List[str] = field(default_factory=list)
    sim_result: Optional[SimulationResult] = None

    def __repr__(self):
        return f"<MoveOption '{self.name}' EV={self.expected_value:.2f} Win={self.win_probability*100:.0f}% {self.risk}>"


# ---------------------------------------------------------------------------
# Default scorer
# ---------------------------------------------------------------------------

def default_scorer(sim_result: SimulationResult) -> float:
    """Generic EV: reward damage dealt, penalize damage taken.

    Game libs can replace with one that cares about VPs, terrain held, etc.
    """
    return (
        sim_result.avg_units_lost_defender * 5
        - sim_result.avg_units_lost_attacker * 3
        + sim_result.avg_attacker_hits_dealt * 0.5
        - sim_result.avg_defender_hits_taken * 0.3
    )


# ---------------------------------------------------------------------------
# Default activation generators (built-in helpers for common patterns)
# ---------------------------------------------------------------------------

def leader_activation_generator(battlefield: Battlefield, side: Optional[str] = None,
                                default_n_actions: int = 3) -> List[ActivationContext]:
    """Default for GBoH-style games: one ActivationContext per active leader.

    Use this in games where leaders activate and issue orders. For games
    without leaders, supply your own activation_generator.
    """
    contexts = []
    for ldr in battlefield.leaders(side=side, finished=False):
        contexts.append(ActivationContext(
            side=ldr.side,
            kind='leader',
            description=f"{ldr.name} activates (CR{ldr.command_range or '?'})",
            actor=ldr,
            n_actions=default_n_actions,
        ))
    return contexts


def whole_side_activation_generator(battlefield: Battlefield,
                                    side: str) -> List[ActivationContext]:
    """Default for IGOUGO games: one ActivationContext for the whole side.

    Use this for phase-based games where a side activates all its units
    in sequence per phase.
    """
    members = [u for u in battlefield.by_side(side) if not u.is_leader]
    return [ActivationContext(
        side=side,
        kind='impulse',
        description=f"{side} player turn",
        members=members,
        n_actions=len(members),
    )]


# ---------------------------------------------------------------------------
# AI Decision Engine
# ---------------------------------------------------------------------------

class AIDecisionEngine:
    """The AI's brain. Evaluates activation options and recommends the best ones.

    The engine is GAME-AGNOSTIC. The game lib supplies callbacks that
    handle all game-specific decisions:

    Args:
      combat_system: game-specific CombatSystem subclass instance
      terrain_system: game-specific TerrainSystem subclass instance
      mc_iterations: Monte Carlo iterations per move evaluation
      unit_stats_provider: callback (unit_type_code) -> {size, tq, rout_points}
      activation_generator: callback (battlefield) -> List[ActivationContext]
        Determines what activation opportunities exist (leaders, formations,
        cards, phases, factions, etc.). If None, defaults to a leader-based
        generator for backward compatibility.
      candidate_generator: callback (battlefield, ActivationContext)
                                  -> List[MoveOption]
        Produces candidate action sequences for a given activation. REQUIRED
        if you call evaluate_activation; the framework cannot guess your
        game's actions.
      scorer: optional callback (SimulationResult) -> float
        Computes expected_value. If None, uses default_scorer (loss/damage
        based). Game libs that care about VPs/territory should override.
    """

    def __init__(self, combat_system=None, terrain_system=None,
                 mc_iterations=500, unit_stats_provider=None,
                 activation_generator=None, candidate_generator=None,
                 scorer=None):
        self.combat_system = combat_system
        self.terrain_system = terrain_system
        self.mc_iterations = mc_iterations
        self.simulator = MonteCarloSimulator(combat_system=combat_system)
        self.unit_stats_provider = unit_stats_provider or self._default_stats
        self.activation_generator = activation_generator
        self.candidate_generator = candidate_generator
        self.scorer = scorer or default_scorer

    # ---- Public API: generic activation evaluation ------------------------

    def list_activations(self, battlefield, side=None):
        """Return all currently legal ActivationContext objects.

        If activation_generator is set, calls it. Otherwise falls back to
        leader_activation_generator for GBoH-style games.
        """
        if self.activation_generator:
            ctxs = self.activation_generator(battlefield)
        else:
            ctxs = leader_activation_generator(battlefield)
        if side is not None:
            ctxs = [c for c in ctxs if c.side == side]
        return ctxs

    def evaluate_activation(self, battlefield, context, max_options=5):
        """Evaluate options for any activation context, return top-N.

        Works for leaders, formations, cards, factions, impulses --
        anything the candidate_generator can produce options for.
        """
        if not self.candidate_generator:
            # Fall back to built-in leader/hex candidate generator if a leader
            # context was passed (backward compatibility)
            if context.kind == 'leader' and context.actor:
                candidates = self._builtin_leader_candidates(battlefield, context)
            else:
                raise ValueError(
                    "AIDecisionEngine has no candidate_generator. "
                    "Provide one in the constructor for non-leader activations."
                )
        else:
            candidates = self.candidate_generator(battlefield, context)

        sim_state = self._battlefield_to_simstate(battlefield, context.side)
        evaluated = []
        for cand in candidates:
            sim_result = self.simulator.evaluate_sequence(
                sim_state, cand.moves, n_iterations=self.mc_iterations
            )
            cand.expected_value = self.scorer(sim_result)
            cand.win_probability = sim_result.win_probability
            cand.risk = sim_result.risk_assessment
            cand.sim_result = sim_result
            evaluated.append(cand)

        evaluated.sort(key=lambda x: (
            -x.expected_value,
            x.sim_result.catastrophe_probability if x.sim_result else 0,
        ))
        return evaluated[:max_options]

    # ---- Backward-compatible leader API -----------------------------------

    def evaluate_leader_turn(self, battlefield, leader, max_options=5):
        """Backward-compatible: evaluate a leader's activation.

        New code should use evaluate_activation() with an ActivationContext.
        This wrapper builds a leader context and dispatches.
        """
        if not leader.is_leader or leader.is_finished:
            return []
        ctx = ActivationContext(
            side=leader.side,
            kind='leader',
            description=f"{leader.name} activates",
            actor=leader,
            n_actions=3,
        )
        return self.evaluate_activation(battlefield, ctx, max_options=max_options)

    def _builtin_leader_candidates(self, battlefield, context):
        """Default candidate generator for leader-style activations.

        Works only when:
          - context.actor is a leader Unit
          - the game uses hex-grid movement
          - 'shock' and 'move' make sense as actions

        Game libs should supply their own candidate_generator if any of
        these assumptions don't hold.
        """
        leader = context.actor
        side = context.side
        in_range = battlefield.in_command_range(leader)
        controllable = [(u, d) for u, d in in_range if u.side == side]
        candidates = []

        candidates.append(MoveOption(
            name="HOLD",
            moves=[Move('hold', notes='Issue no orders')],
            description="Activate leader, issue no orders. Conserve tempo.",
            rule_refs=[],
        ))

        free_units, zoc_units = [], []
        for u, d in controllable:
            if u.is_leader: continue
            if battlefield.is_in_zoc(u):
                zoc_units.append(u)
            else:
                free_units.append(u)

        for unit in zoc_units[:3]:
            adj_enemies = battlefield.adjacent_enemies(unit)
            for enemy in adj_enemies[:2]:
                candidates.append(MoveOption(
                    name=f"SHOCK {unit.name}->{enemy.name}",
                    moves=[Move('shock', unit_id=unit.pid, target_id=enemy.pid,
                                position='frontal')],
                    description=f"{unit.name} at {unit.hex_id()} shocks "
                                f"{enemy.name} at {enemy.hex_id()}",
                ))
                candidates.append(MoveOption(
                    name=f"SHOCK {unit.name}->{enemy.name} (FLANK)",
                    moves=[Move('shock', unit_id=unit.pid, target_id=enemy.pid,
                                position='flank')],
                    description=f"{unit.name} flank attacks {enemy.name}",
                    notes=['Position superiority'],
                ))

        for unit in free_units[:3]:
            for nc, nr in hex_neighbors(unit.hex_col, unit.hex_row):
                occupants = battlefield.at_hex(nc, nr)
                blocked = any(o.side != side and not o.is_leader for o in occupants)
                if blocked:
                    continue
                candidates.append(MoveOption(
                    name=f"MOVE {unit.name} to {nc:02d}{nr:02d}",
                    moves=[Move('move', unit_id=unit.pid, to_hex=(nc, nr))],
                    description=f"{unit.name} moves from {unit.hex_id()} to {nc:02d}{nr:02d}",
                ))

        return candidates

    @staticmethod
    def _default_stats(unit_type_code):
        """Generic default stats when no game-specific provider is supplied.

        Returns neutral mid-range values. Game-specific libs should provide
        their own unit_stats_provider for accurate Monte Carlo evaluation.
        """
        return {'size': 4, 'tq': 5, 'rout_points': 4}

    def _battlefield_to_simstate(self, battlefield, ai_side):
        """Convert a Battlefield to a SimState for Monte Carlo.

        Uses self.unit_stats_provider to map unit type codes to stats.
        Each unit's `unit_type` field is parsed for a code like (PH), (LG),
        or used directly if it's a bare code.
        """
        import re

        sim = SimState()
        sim.attacker_withdrawal = 100  # TODO: from scenario
        sim.defender_withdrawal = 100

        for u in battlefield.units:
            if u.is_leader: continue
            sim_side = 'attacker' if u.side == ai_side else 'defender'

            # Extract unit type code from the unit type string
            unit_type_code = ''
            if u.unit_type:
                m = re.search(r'\(([A-Z_]+)\)', u.unit_type)
                if m:
                    unit_type_code = m.group(1)
                else:
                    unit_type_code = u.unit_type

            # Get stats from the game-specific provider
            stats = self.unit_stats_provider(unit_type_code)
            size = stats.get('size', 4)
            tq = stats.get('tq', 5)
            rp = stats.get('rout_points', size)

            sim_unit = SimUnit(
                id=u.pid, side=sim_side, unit_type=unit_type_code,
                size=size, tq=tq, hits=u.cohesion_hits,
                col=u.hex_col or 0, row=u.hex_row or 0,
                rout_points=rp,
            )
            sim.add_unit(sim_unit)

        return sim


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    print("vassal_framework.ai is a library module.")
    print("Use it via game-specific runners:")
    print("  python3 -m games.<GameName>.<game>_lib.runner <save.vsav> <leader>")
    print()
    print("Or import in your own script:")
    print("  from vassal_framework.ai import AIDecisionEngine")
    sys.exit(0)
