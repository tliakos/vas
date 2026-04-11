#!/usr/bin/env python3
"""
VASSAL AI Decision Engine -- Move evaluation and ranking.

Given a battlefield state and a leader to activate, this engine:
1. Enumerates all legal moves for units in command range
2. Generates candidate move sequences (single moves, combinations)
3. Runs Monte Carlo simulation on each candidate
4. Ranks options by expected value with risk assessment
5. Returns top-N recommendations with full explainability

This is the brain that drives AI play. Game-specific rules are passed in
via the rules engine; the decision logic is generic.
"""

import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from itertools import combinations, product

from vassal_units import Battlefield, Unit, hex_distance_offset, hex_neighbors
from vassal_montecarlo import MonteCarloSimulator, SimState, SimUnit, Move, SimulationResult


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
# AI Decision Engine
# ---------------------------------------------------------------------------

class AIDecisionEngine:
    """The AI's brain. Evaluates moves and recommends the best ones."""

    def __init__(self, combat_system=None, terrain_system=None, mc_iterations=500):
        self.combat_system = combat_system
        self.terrain_system = terrain_system
        self.mc_iterations = mc_iterations
        self.simulator = MonteCarloSimulator(combat_system=combat_system)

    def evaluate_leader_turn(self, battlefield, leader, max_options=5):
        """Evaluate all options for activating a leader and return top-N.

        Args:
          battlefield: Battlefield instance with current game state
          leader: Unit (leader) being activated
          max_options: number of top options to return

        Returns:
          List of MoveOption objects, sorted best-to-worst
        """
        if not leader.is_leader:
            return []

        if leader.is_finished:
            return []  # Can't activate Finished leader

        # Get units in command range
        in_range = battlefield.in_command_range(leader)
        side = leader.side
        controllable = [(u, d) for u, d in in_range if u.side == side]

        # Generate candidate move options
        candidates = self._generate_candidates(battlefield, leader, controllable)

        # Build a SimState from the battlefield for Monte Carlo
        sim_state = self._battlefield_to_simstate(battlefield, side)

        # Evaluate each candidate
        evaluated = []
        for cand in candidates:
            sim_result = self.simulator.evaluate_sequence(
                sim_state, cand.moves, n_iterations=self.mc_iterations
            )
            cand.expected_value = (
                sim_result.avg_units_lost_defender * 5
                - sim_result.avg_units_lost_attacker * 3
                + sim_result.avg_attacker_hits_dealt * 0.5
                - sim_result.avg_defender_hits_taken * 0.3
            )
            cand.win_probability = sim_result.win_probability
            cand.risk = sim_result.risk_assessment
            cand.sim_result = sim_result
            evaluated.append(cand)

        # Sort by EV descending, with risk as tiebreaker
        evaluated.sort(key=lambda x: (
            -x.expected_value,
            x.sim_result.catastrophe_probability if x.sim_result else 0,
        ))

        return evaluated[:max_options]

    def _generate_candidates(self, battlefield, leader, controllable):
        """Generate candidate move sequences for this leader."""
        candidates = []
        side = leader.side

        # The number of orders the leader can issue = Initiative rating
        # Default to 3 if we can't determine
        n_orders = 3  # TODO: extract from leader stats

        # Option 1: HOLD - issue no orders
        hold = MoveOption(
            name="HOLD",
            moves=[Move('hold', notes='Issue no orders')],
            description="Activate leader, issue no orders. Conserve tempo.",
            rule_refs=["5.21"],
        )
        candidates.append(hold)

        # Option 2: Each adjacent enemy that can be shocked - try shock attacks
        free_units = []
        zoc_units = []
        for u, d in controllable:
            if u.is_leader: continue
            if battlefield.is_in_zoc(u):
                zoc_units.append(u)
            else:
                free_units.append(u)

        # Generate shock options for ZOC-locked units (already adjacent)
        for unit in zoc_units[:3]:  # Cap to top 3 to avoid explosion
            adj_enemies = battlefield.adjacent_enemies(unit)
            for enemy in adj_enemies[:2]:
                # Determine position (default frontal, TODO: detect facing)
                position = 'frontal'

                option = MoveOption(
                    name=f"SHOCK {unit.name}->{enemy.name}",
                    moves=[Move('shock', unit_id=unit.pid, target_id=enemy.pid,
                                position=position, rule_ref='8.42')],
                    description=f"{unit.name} at {unit.hex_id()} shocks {enemy.name} at {enemy.hex_id()}",
                    rule_refs=['8.42', '8.46'],
                )
                candidates.append(option)

                # Also try flank attack version
                if position != 'flank':
                    flank_option = MoveOption(
                        name=f"SHOCK {unit.name}->{enemy.name} (FLANK)",
                        moves=[Move('shock', unit_id=unit.pid, target_id=enemy.pid,
                                    position='flank', rule_ref='8.46')],
                        description=f"{unit.name} flank attacks {enemy.name}",
                        rule_refs=['8.46'],
                        notes=['Position superiority doubles defender hits'],
                    )
                    candidates.append(flank_option)

        # Generate movement options for free units
        for unit in free_units[:3]:
            # Find adjacent empty hexes
            for nc, nr in hex_neighbors(unit.hex_col, unit.hex_row):
                # Check destination
                occupants = battlefield.at_hex(nc, nr)
                blocked = any(o.side != side and not o.is_leader for o in occupants)
                if blocked:
                    continue

                option = MoveOption(
                    name=f"MOVE {unit.name} to {nc:02d}{nr:02d}",
                    moves=[Move('move', unit_id=unit.pid, to_hex=(nc, nr),
                                rule_ref='6.11')],
                    description=f"{unit.name} moves from {unit.hex_id()} to {nc:02d}{nr:02d}",
                    rule_refs=['6.11'],
                )
                candidates.append(option)

        return candidates

    def _battlefield_to_simstate(self, battlefield, ai_side):
        """Convert a Battlefield to a SimState for Monte Carlo."""
        sim = SimState()
        sim.attacker_withdrawal = 100  # TODO: from scenario
        sim.defender_withdrawal = 100

        for u in battlefield.units:
            if u.is_leader: continue
            # Map side to attacker/defender from AI's perspective
            sim_side = 'attacker' if u.side == ai_side else 'defender'

            # Estimate size and TQ from unit type (TODO: read from counter)
            size_map = {
                'PH': 7, 'HI': 5, 'LG': 5, 'MI': 4, 'LI': 3,
                'SK': 2, 'HC': 5, 'LC': 4, 'RC': 5, 'EL': 6,
            }
            tq_map = {
                'PH': 7, 'HI': 6, 'LG': 6, 'MI': 5, 'LI': 5,
                'SK': 4, 'HC': 7, 'LC': 5, 'RC': 6, 'EL': 7,
            }

            unit_type_code = ''
            if u.unit_type:
                # Extract code from "Phalanx (PH)" -> "PH"
                import re
                m = re.search(r'\(([A-Z]+)\)', u.unit_type)
                if m:
                    unit_type_code = m.group(1)

            size = size_map.get(unit_type_code, 4)
            tq = tq_map.get(unit_type_code, 5)

            sim_unit = SimUnit(
                id=u.pid, side=sim_side, unit_type=unit_type_code,
                size=size, tq=tq, hits=u.cohesion_hits,
                col=u.hex_col or 0, row=u.hex_row or 0,
                rout_points=size,  # Approximate RP = size
            )
            sim.add_unit(sim_unit)

        return sim


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/Users/thomasliakos/vas')
    from vassal_grid import ModuleGrid
    from vassal_units import UnitScanner, detect_active_boards
    from vassal_combat import SPQRCombat
    from vassal_terrain import SPQRTerrain
    from vassal_move import GameState

    if len(sys.argv) < 4:
        print("Usage: python3 vassal_ai.py <module.vmod> <save.vsav> <leader_name>")
        sys.exit(1)

    # Load module and game state
    mg = ModuleGrid.from_vmod(sys.argv[1])
    for boards in mg.maps.values():
        for b in boards.values():
            if b.grid:
                b.grid.max_cols = 46
                b.grid.max_rows = 46

    state = GameState()
    state.load_from_file(sys.argv[2])

    scanner = UnitScanner(mg, active_boards=detect_active_boards(state))
    units = scanner.scan(state)
    bf = Battlefield(units)

    # Find the leader
    leader_name = sys.argv[3]
    leader = next((l for l in bf.leaders() if leader_name.lower() in l.name.lower()), None)
    if not leader:
        print(f"Leader '{leader_name}' not found")
        sys.exit(1)

    print(f"Evaluating turn for: {leader.name} at {leader.hex_id()} (CR{leader.command_range})")
    print()

    # Build AI engine
    combat = SPQRCombat()
    terrain = SPQRTerrain()
    ai = AIDecisionEngine(combat_system=combat, terrain_system=terrain, mc_iterations=300)

    # Evaluate
    options = ai.evaluate_leader_turn(bf, leader, max_options=10)

    print(f"=== TOP {len(options)} MOVE OPTIONS ===\n")
    for i, opt in enumerate(options):
        print(f"{i+1}. {opt.name}")
        print(f"   Description: {opt.description}")
        print(f"   Rule refs: {', '.join(opt.rule_refs)}")
        print(f"   EV: {opt.expected_value:.2f} | Win%: {opt.win_probability*100:.1f}% | {opt.risk}")
        if opt.sim_result:
            r = opt.sim_result
            print(f"   Avg dmg dealt: {r.avg_attacker_hits_dealt:.1f} | Avg dmg taken: {r.avg_defender_hits_taken:.1f}")
        print()
