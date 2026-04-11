#!/usr/bin/env python3
"""
VASSAL Monte Carlo Simulator -- Probabilistic outcome evaluation.

Given a battlefield state and a proposed move/combat sequence, runs N
simulations sampling random outcomes (dice rolls, combat results) and
returns probability distributions over outcomes.

This is the foundation of AI decision-making: instead of evaluating a
single deterministic outcome, the AI evaluates the EXPECTED VALUE of
each possible move and picks the best one.

Usage:
    sim = MonteCarloSimulator(combat_system=SPQRCombat())
    moves = [
        Move('shock', attacker_id=..., defender_id=..., position='flank'),
        Move('move', unit_id=..., to_hex=(27, 8)),
    ]
    result = sim.evaluate_sequence(battlefield, moves, n_iterations=1000)
    print(result.expected_value)
    print(result.win_probability)
    print(result.risk_assessment)
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from copy import deepcopy


# ---------------------------------------------------------------------------
# Move and Action representation
# ---------------------------------------------------------------------------

@dataclass
class Move:
    """A single proposed action."""
    action: str  # 'move', 'shock', 'fire', 'rally', 'hold'
    unit_id: Optional[str] = None
    to_hex: Optional[tuple] = None
    target_id: Optional[str] = None
    position: str = 'frontal'  # for shock attacks
    notes: str = ""
    rule_ref: str = ""

    def __repr__(self):
        s = f"{self.action.upper()}"
        if self.unit_id: s += f" {self.unit_id[:8]}"
        if self.to_hex: s += f" -> {self.to_hex[0]:02d}{self.to_hex[1]:02d}"
        if self.target_id: s += f" vs {self.target_id[:8]}"
        return s


@dataclass
class SimulationResult:
    """Aggregated results from N Monte Carlo simulations."""
    n_iterations: int
    sequences_evaluated: int = 0

    # Expected outcomes
    avg_attacker_hits_dealt: float = 0.0
    avg_defender_hits_taken: float = 0.0
    avg_units_lost_attacker: float = 0.0
    avg_units_lost_defender: float = 0.0
    avg_rout_points_lost_attacker: float = 0.0
    avg_rout_points_lost_defender: float = 0.0

    # Probabilities
    win_probability: float = 0.0       # P(victory by end of sequence)
    catastrophe_probability: float = 0.0  # P(losing major units)
    optimal_probability: float = 0.0    # P(best-case outcome)

    # Distributions
    outcome_distribution: Dict = field(default_factory=dict)
    risk_assessment: str = ""

    def summary(self):
        return (
            f"Monte Carlo ({self.n_iterations} iterations):\n"
            f"  Avg attacker hits dealt:  {self.avg_attacker_hits_dealt:.1f}\n"
            f"  Avg defender hits taken:  {self.avg_defender_hits_taken:.1f}\n"
            f"  Avg attacker units lost:  {self.avg_units_lost_attacker:.2f}\n"
            f"  Avg defender units lost:  {self.avg_units_lost_defender:.2f}\n"
            f"  Win probability:          {self.win_probability*100:.1f}%\n"
            f"  Catastrophe probability:  {self.catastrophe_probability*100:.1f}%\n"
            f"  Risk: {self.risk_assessment}"
        )


# ---------------------------------------------------------------------------
# Lightweight battlefield state for simulation
# ---------------------------------------------------------------------------

class SimUnit:
    """Lightweight unit representation for fast simulation."""
    __slots__ = ['id', 'side', 'unit_type', 'size', 'tq', 'hits',
                 'col', 'row', 'is_routed', 'is_eliminated', 'rout_points']

    def __init__(self, id, side, unit_type, size, tq, hits=0,
                 col=0, row=0, rout_points=1):
        self.id = id
        self.side = side
        self.unit_type = unit_type
        self.size = size
        self.tq = tq
        self.hits = hits
        self.col = col
        self.row = row
        self.is_routed = False
        self.is_eliminated = False
        self.rout_points = rout_points

    def take_hits(self, hits):
        """Apply cohesion hits and check for rout/elimination."""
        self.hits += hits
        if self.hits >= self.tq:
            self.is_routed = True
            return 'routed'
        return 'damaged'

    def copy(self):
        u = SimUnit(self.id, self.side, self.unit_type, self.size, self.tq,
                    self.hits, self.col, self.row, self.rout_points)
        u.is_routed = self.is_routed
        u.is_eliminated = self.is_eliminated
        return u


class SimState:
    """Lightweight game state for fast Monte Carlo iteration."""

    def __init__(self):
        self.units = {}  # id -> SimUnit
        self.attacker_rp = 0
        self.defender_rp = 0
        self.attacker_withdrawal = 100
        self.defender_withdrawal = 100

    def copy(self):
        s = SimState()
        s.units = {pid: u.copy() for pid, u in self.units.items()}
        s.attacker_rp = self.attacker_rp
        s.defender_rp = self.defender_rp
        s.attacker_withdrawal = self.attacker_withdrawal
        s.defender_withdrawal = self.defender_withdrawal
        return s

    def add_unit(self, unit):
        self.units[unit.id] = unit

    def get_side_units(self, side):
        return [u for u in self.units.values() if u.side == side and not u.is_eliminated]

    def total_rp(self, side):
        """Total rout points lost by a side."""
        return sum(u.rout_points for u in self.units.values()
                   if u.side == side and (u.is_routed or u.is_eliminated))

    def is_withdrawn(self, side):
        if side == 'attacker':
            return self.total_rp(side) >= self.attacker_withdrawal
        return self.total_rp(side) >= self.defender_withdrawal


# ---------------------------------------------------------------------------
# Monte Carlo simulator
# ---------------------------------------------------------------------------

class MonteCarloSimulator:
    """Runs Monte Carlo simulations of move sequences."""

    def __init__(self, combat_system=None, seed=None):
        self.combat_system = combat_system
        if seed is not None:
            random.seed(seed)

    def evaluate_sequence(self, initial_state, moves, n_iterations=1000):
        """Evaluate a sequence of moves N times and return aggregate results.

        initial_state: SimState
        moves: list of Move
        n_iterations: number of Monte Carlo runs
        """
        result = SimulationResult(n_iterations=n_iterations)

        attacker_hits_total = 0
        defender_hits_total = 0
        attacker_units_lost = 0
        defender_units_lost = 0
        attacker_rp_lost = 0
        defender_rp_lost = 0
        wins = 0
        catastrophes = 0
        outcome_counts = {}

        for _ in range(n_iterations):
            sim = initial_state.copy()
            iteration_a_hits = 0
            iteration_d_hits = 0
            iteration_a_lost = 0
            iteration_d_lost = 0

            for move in moves:
                self._apply_move(sim, move)

            # Count outcomes
            for u in sim.units.values():
                if u.side == 'attacker':
                    iteration_a_hits += u.hits
                    if u.is_routed or u.is_eliminated:
                        iteration_a_lost += 1
                else:
                    iteration_d_hits += u.hits
                    if u.is_routed or u.is_eliminated:
                        iteration_d_lost += 1

            attacker_hits_total += iteration_a_hits
            defender_hits_total += iteration_d_hits
            attacker_units_lost += iteration_a_lost
            defender_units_lost += iteration_d_lost
            attacker_rp_lost += sim.total_rp('attacker')
            defender_rp_lost += sim.total_rp('defender')

            # Win/loss check
            if sim.is_withdrawn('defender'):
                wins += 1
            if sim.is_withdrawn('attacker'):
                catastrophes += 1

            # Track distribution
            outcome_key = (iteration_a_lost, iteration_d_lost)
            outcome_counts[outcome_key] = outcome_counts.get(outcome_key, 0) + 1

        # Compute aggregates
        result.avg_attacker_hits_dealt = defender_hits_total / n_iterations
        result.avg_defender_hits_taken = attacker_hits_total / n_iterations
        result.avg_units_lost_attacker = attacker_units_lost / n_iterations
        result.avg_units_lost_defender = defender_units_lost / n_iterations
        result.avg_rout_points_lost_attacker = attacker_rp_lost / n_iterations
        result.avg_rout_points_lost_defender = defender_rp_lost / n_iterations
        result.win_probability = wins / n_iterations
        result.catastrophe_probability = catastrophes / n_iterations

        # Risk assessment
        if result.catastrophe_probability > 0.30:
            result.risk_assessment = "HIGH RISK - significant chance of disaster"
        elif result.catastrophe_probability > 0.15:
            result.risk_assessment = "MODERATE RISK"
        elif result.avg_units_lost_attacker > result.avg_units_lost_defender:
            result.risk_assessment = "Trade unfavorable to attacker"
        elif result.avg_units_lost_defender > result.avg_units_lost_attacker * 1.5:
            result.risk_assessment = "FAVORABLE - defender takes heavy losses"
        else:
            result.risk_assessment = "Acceptable trade"

        result.outcome_distribution = outcome_counts
        return result

    def _apply_move(self, sim, move):
        """Apply a single move to the simulation state."""
        if move.action == 'move':
            unit = sim.units.get(move.unit_id)
            if unit and not unit.is_eliminated:
                if move.to_hex:
                    unit.col, unit.row = move.to_hex

        elif move.action == 'shock':
            attacker = sim.units.get(move.unit_id)
            defender = sim.units.get(move.target_id)
            if attacker and defender and not attacker.is_eliminated and not defender.is_eliminated:
                if self.combat_system:
                    cr = self.combat_system.resolve(
                        None, None,
                        attacker_size=attacker.size,
                        defender_size=defender.size,
                        attacker_type=attacker.unit_type,
                        defender_type=defender.unit_type,
                        position=move.position,
                    )
                    # Apply hits
                    attacker.take_hits(cr.attacker_hits)
                    defender.take_hits(cr.defender_hits)

        elif move.action == 'fire':
            # Missile fire (simpler than shock)
            target = sim.units.get(move.target_id)
            if target:
                # Roll a d10 - if low, hit
                if random.randint(0, 9) <= 4:
                    target.take_hits(1)

        elif move.action == 'hold':
            pass  # No state change

        elif move.action == 'rally':
            unit = sim.units.get(move.unit_id)
            if unit:
                unit.hits = max(0, unit.hits - 2)

    def compare_options(self, initial_state, options, n_iterations=500):
        """Compare multiple move sequence options and rank them.

        options: list of (name, [moves]) tuples
        Returns: list of (name, SimulationResult) sorted by best EV
        """
        results = []
        for name, moves in options:
            result = self.evaluate_sequence(initial_state, moves, n_iterations)
            results.append((name, result))

        # Sort by win probability descending, then by avg defender losses
        results.sort(key=lambda x: (
            -x[1].win_probability,
            -x[1].avg_units_lost_defender,
            x[1].avg_units_lost_attacker,
        ))
        return results


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from vassal_combat import SPQRCombat

    sim_combat = SPQRCombat()
    mc = MonteCarloSimulator(combat_system=sim_combat)

    # Build a test scenario:
    # 1 Roman LG (size 5, TQ 6) vs 1 Macedonian PH (size 7, TQ 7)
    state = SimState()
    state.attacker_withdrawal = 30
    state.defender_withdrawal = 25

    state.add_unit(SimUnit('lg1', 'attacker', 'LG', 5, 6, rout_points=5))
    state.add_unit(SimUnit('ph1', 'defender', 'PH', 7, 7, rout_points=7))
    state.add_unit(SimUnit('ph2', 'defender', 'PH', 7, 7, rout_points=7))

    # Option A: Frontal attack
    option_a = [Move('shock', unit_id='lg1', target_id='ph1', position='frontal')]
    # Option B: Flank attack
    option_b = [Move('shock', unit_id='lg1', target_id='ph1', position='flank')]
    # Option C: Hold
    option_c = [Move('hold')]

    results = mc.compare_options(state, [
        ('Frontal attack', option_a),
        ('Flank attack', option_b),
        ('Hold position', option_c),
    ], n_iterations=2000)

    print("=== Move Comparison ===")
    for name, r in results:
        print(f"\n--- {name} ---")
        print(r.summary())
