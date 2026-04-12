#!/usr/bin/env python3
"""
VASSAL Play Manager -- Generic phased play for any wargame.

Manages the file-based play loop between AI and human opponent:

  1. AI generates an action (attack, move, fire)
  2. Framework STOPS at an opponent decision point (rout, retreat, react)
  3. Opponent loads the save in VASSAL, makes their decisions, saves
  4. AI loads the opponent's save and continues (advance, pursue, exploit)

This module is GAME-AGNOSTIC. It handles:
  - Sequential file naming (step numbering)
  - Game state tracking across sessions (game_tracker.json)
  - Phase transitions and handoff detection
  - Save/load at each phase boundary

Game-specific libs define WHICH phases their game uses and WHAT the
opponent decides at each handoff. See PhaseDefinition.

Usage:
    from vassal_framework.play import PlayManager, Phase

    pm = PlayManager(scenario_dir='games/SPQR/scenarios/heraclea',
                     scenario_prefix='hera')
    pm.start_phase('attack', side='roman', leader='Falco')
    # ... AI does work ...
    pm.write_save(game_state, extras)
    pm.handoff_to_opponent(pending_actions=[...])

    # Later, after opponent saves:
    pm.continue_from_opponent('hera-006-epirote-rout.vsav')
    pm.start_phase('advance', side='roman', leader='Falco')
    # ... AI advances ...
    pm.write_save(game_state, extras)
    pm.finish_activation()
"""

import os
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from enum import Enum


# ---------------------------------------------------------------------------
# Phase definitions
# ---------------------------------------------------------------------------

class PhaseType(Enum):
    """Who acts in this phase."""
    AI = 'ai'
    OPPONENT = 'opponent'
    EITHER = 'either'


@dataclass
class PhaseDefinition:
    """Defines a single phase in the play sequence.

    Game libs register these to describe their game's phase structure.
    The framework uses them to know when to stop and hand off.

    Example for SPQR:
      PhaseDefinition('attack', PhaseType.AI,
          description='AI issues orders, rolls dice, applies CH',
          next_phase='opponent_rout',
          generates=['vsav', 'vlog', 'pending.json'])
      PhaseDefinition('opponent_rout', PhaseType.OPPONENT,
          description='Opponent moves routed units',
          next_phase='advance',
          opponent_instruction='Move your routed units, then save.')
      PhaseDefinition('advance', PhaseType.AI,
          description='AI advances/pursues into vacated hexes',
          next_phase=None,
          generates=['vsav', 'vlog'])
    """
    name: str
    actor: PhaseType
    description: str = ''
    next_phase: Optional[str] = None
    generates: List[str] = field(default_factory=list)
    opponent_instruction: str = ''


# ---------------------------------------------------------------------------
# Game Tracker -- persistent state across sessions
# ---------------------------------------------------------------------------

@dataclass
class ActivationRecord:
    """Record of one leader/unit activation."""
    leader: str
    step_start: int
    step_end: Optional[int] = None
    status: str = 'in_progress'  # in_progress, attack_complete, waiting, complete
    orders_issued: int = 0


@dataclass
class GameTracker:
    """Persistent game state that survives across sessions.

    Stored as game_tracker.json in the scenario directory.
    """
    scenario: str = ''
    turn: int = 1
    current_step: int = 0
    current_phase: str = ''
    side_to_act: str = ''
    activations_this_turn: List[Dict] = field(default_factory=list)
    pending_actions: List[Dict] = field(default_factory=list)
    leaders_finished: List[str] = field(default_factory=list)
    ocs_used: Dict[str, int] = field(default_factory=dict)
    rp_lost: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def next_step(self):
        self.current_step += 1
        return self.current_step

    def save(self, path):
        with open(path, 'w') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return cls()
        with open(path) as f:
            data = json.load(f)
        return cls(**data)


# ---------------------------------------------------------------------------
# Play Manager
# ---------------------------------------------------------------------------

class PlayManager:
    """Manages the phased play loop for any wargame.

    Handles file naming, step counting, phase transitions, and opponent
    handoffs. Game-specific libs register their phase definitions.
    """

    def __init__(self, scenario_dir, scenario_prefix, phases=None):
        """
        Args:
          scenario_dir: path to the scenario directory (e.g., games/SPQR/scenarios/heraclea)
          scenario_prefix: filename prefix (e.g., 'hera')
          phases: list of PhaseDefinition objects (game-specific)
        """
        self.scenario_dir = scenario_dir
        self.prefix = scenario_prefix
        self.phases = {p.name: p for p in (phases or [])}
        self.tracker_path = os.path.join(scenario_dir, 'game_tracker.json')
        self.tracker = GameTracker.load(self.tracker_path)
        self._current_activation = None

    def step_filename(self, step, side, leader, phase, ext):
        """Generate a filename for a given step.

        Format: {prefix}-{NNN}-{side}-{leader}-{phase}.{ext}
        """
        leader_clean = leader.lower().replace(' ', '_').replace('(', '').replace(')', '')
        return f"{self.prefix}-{step:03d}-{side}-{leader_clean}-{phase}.{ext}"

    def step_path(self, step, side, leader, phase, ext):
        """Full path for a step file."""
        return os.path.join(self.scenario_dir, self.step_filename(step, side, leader, phase, ext))

    def opponent_save_path(self, step, side, phase='rout'):
        """Expected path where opponent saves their file."""
        return os.path.join(self.scenario_dir,
                            f"{self.prefix}-{step:03d}-{side}-{phase}.vsav")

    # ---- Activation lifecycle ---------------------------------------------

    def start_activation(self, leader_name, side):
        """Begin a new leader activation. Increments step counter."""
        step = self.tracker.next_step()
        self._current_activation = ActivationRecord(
            leader=leader_name, step_start=step)
        self.tracker.current_phase = 'attack'
        self.tracker.side_to_act = side
        self.tracker.save(self.tracker_path)
        return step

    def current_step(self):
        return self.tracker.current_step

    def start_phase(self, phase_name, side, leader):
        """Transition to a named phase."""
        self.tracker.current_phase = phase_name
        self.tracker.side_to_act = side
        self.tracker.save(self.tracker_path)

    def handoff_to_opponent(self, opponent_side, pending_actions,
                            instruction=''):
        """Stop AI execution and hand off to the opponent.

        Writes the pending actions to a JSON file and updates the tracker.
        The opponent loads the .vsav in VASSAL, acts, and saves.
        """
        step = self.tracker.current_step
        leader = self._current_activation.leader if self._current_activation else 'unknown'

        self.tracker.current_phase = 'waiting_for_opponent'
        self.tracker.side_to_act = opponent_side
        self.tracker.pending_actions = pending_actions
        self.tracker.save(self.tracker_path)

        # Write pending.json for the opponent
        pending_path = self.step_path(step, 'roman', leader, 'pending', 'json')
        pending_data = {
            'step': step,
            'waiting_for': opponent_side,
            'instruction': instruction or self._default_instruction(pending_actions),
            'actions_required': pending_actions,
            'save_as': self.opponent_save_path(step + 1, opponent_side).split('/')[-1],
        }
        with open(pending_path, 'w') as f:
            json.dump(pending_data, f, indent=2)

        if self._current_activation:
            self._current_activation.status = 'waiting'

        return pending_path

    def continue_from_opponent(self, opponent_save_path):
        """Resume after opponent has saved their file.

        Returns the path to load.
        """
        if not os.path.exists(opponent_save_path):
            raise FileNotFoundError(
                f"Opponent save not found: {opponent_save_path}\n"
                f"The opponent needs to load the attack .vsav in VASSAL, "
                f"move their routed/retreating units, and save."
            )
        self.tracker.next_step()
        self.tracker.current_phase = 'advance'
        self.tracker.pending_actions = []
        self.tracker.save(self.tracker_path)
        return opponent_save_path

    def finish_activation(self, leader_name=None):
        """Mark the current activation as complete."""
        if leader_name:
            self.tracker.leaders_finished.append(leader_name)
        if self._current_activation:
            self._current_activation.status = 'complete'
            self._current_activation.step_end = self.tracker.current_step
            self.tracker.activations_this_turn.append(
                asdict(self._current_activation))
        self._current_activation = None
        self.tracker.current_phase = 'between_activations'
        self.tracker.save(self.tracker_path)

    def finish_turn(self):
        """End the current game turn."""
        self.tracker.turn += 1
        self.tracker.activations_this_turn = []
        self.tracker.leaders_finished = []
        self.tracker.save(self.tracker_path)

    # ---- Helpers ----------------------------------------------------------

    def _default_instruction(self, pending_actions):
        parts = []
        routs = [a for a in pending_actions if a.get('type') == 'rout']
        retreats = [a for a in pending_actions if a.get('type') == 'retreat']
        if routs:
            names = ', '.join(a.get('unit', '?') for a in routs)
            parts.append(f"Rout these units: {names}")
        if retreats:
            names = ', '.join(a.get('unit', '?') for a in retreats)
            parts.append(f"Retreat these units: {names}")
        parts.append("Move them in VASSAL, then save.")
        return ' '.join(parts)

    def get_status(self):
        """Human-readable status string."""
        t = self.tracker
        lines = [
            f"Scenario: {t.scenario}",
            f"Turn: {t.turn}",
            f"Step: {t.current_step}",
            f"Phase: {t.current_phase}",
            f"Side to act: {t.side_to_act}",
            f"Leaders finished: {', '.join(t.leaders_finished) or 'none'}",
            f"Activations this turn: {len(t.activations_this_turn)}",
        ]
        if t.pending_actions:
            lines.append(f"Pending: {len(t.pending_actions)} actions for opponent")
        return '\n'.join(lines)
