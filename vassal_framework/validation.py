#!/usr/bin/env python3
"""
VASSAL Game Library Validator.

Tests a generated games/<GameName>/<game>_lib/ package by running a series
of checks: imports succeed, vmod loads, units detected, hex coordinates
sensible, AI runs end-to-end.

Usage:
    python3 -m vassal_framework.validation <GameName>
    python3 -m vassal_framework.validation SPQR
    python3 -m vassal_framework.validation SPQR --save games/SPQR/scenarios/heraclea/hera-004.vsav
"""

import os
import sys
import importlib
import traceback
from dataclasses import dataclass, field
from typing import List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@dataclass
class CheckResult:
    """Result of a single validation check."""
    name: str
    status: str  # 'pass', 'fail', 'warn', 'skip'
    message: str = ""
    details: List[str] = field(default_factory=list)

    def emoji(self):
        return {'pass': '[OK]', 'fail': '[FAIL]', 'warn': '[WARN]', 'skip': '[SKIP]'}.get(self.status, '[?]')


class ValidationReport:
    """Aggregated validation results."""

    def __init__(self, game_name):
        self.game_name = game_name
        self.checks = []

    def add(self, check):
        self.checks.append(check)

    def passed(self):
        return sum(1 for c in self.checks if c.status == 'pass')

    def failed(self):
        return sum(1 for c in self.checks if c.status == 'fail')

    def warnings(self):
        return sum(1 for c in self.checks if c.status == 'warn')

    def total(self):
        return len(self.checks)

    def is_passing(self):
        return self.failed() == 0

    def print_summary(self):
        print()
        print("=" * 70)
        print(f"VALIDATION REPORT: {self.game_name}")
        print("=" * 70)
        for c in self.checks:
            print(f"  {c.emoji()} {c.name}")
            if c.message:
                print(f"       {c.message}")
            for d in c.details:
                print(f"       - {d}")
        print()
        print(f"Results: {self.passed()} passed, {self.failed()} failed, {self.warnings()} warnings")
        print("=" * 70)


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

def check_directory_structure(game_name, report):
    """Check that the game directory exists with required structure."""
    game_dir = os.path.join(PROJECT_ROOT, 'games', game_name)
    lib_name = f"{game_name.lower()}_lib"
    lib_dir = os.path.join(game_dir, lib_name)

    required = [
        ('Game directory', game_dir, True),
        ('Library directory', lib_dir, True),
        ('Library __init__.py', os.path.join(lib_dir, '__init__.py'), True),
        ('terrain.py', os.path.join(lib_dir, 'terrain.py'), True),
        ('combat.py', os.path.join(lib_dir, 'combat.py'), True),
        ('units.py', os.path.join(lib_dir, 'units.py'), True),
        ('runner.py', os.path.join(lib_dir, 'runner.py'), True),
        (f'{game_name}.md', os.path.join(game_dir, f'{game_name}.md'), False),
        ('INTEL.md', os.path.join(game_dir, 'INTEL.md'), False),
        ('scenarios/', os.path.join(game_dir, 'scenarios'), False),
    ]

    for name, path, required_check in required:
        if os.path.exists(path):
            report.add(CheckResult(name, 'pass'))
        else:
            status = 'fail' if required_check else 'warn'
            report.add(CheckResult(name, status, f"Missing: {os.path.relpath(path, PROJECT_ROOT)}"))


def check_imports(game_name, report):
    """Check that the game's lib modules can be imported."""
    lib_name = f"{game_name.lower()}_lib"

    modules_to_check = [
        ('terrain', f'games.{game_name}.{lib_name}.terrain', f'{game_name}Terrain'),
        ('combat', f'games.{game_name}.{lib_name}.combat', f'{game_name}Combat'),
        ('units', f'games.{game_name}.{lib_name}.units', f'{game_name.lower()}_side_classifier'),
    ]

    imported = {}
    for label, module_path, expected_attr in modules_to_check:
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, expected_attr):
                report.add(CheckResult(
                    f'Import {label}', 'pass', f'{module_path}.{expected_attr} found'
                ))
                imported[label] = mod
            else:
                report.add(CheckResult(
                    f'Import {label}', 'warn',
                    f'Module imports but missing {expected_attr}'
                ))
                imported[label] = mod
        except Exception as e:
            report.add(CheckResult(
                f'Import {label}', 'fail', f'{type(e).__name__}: {e}'
            ))

    return imported


def check_vmod_load(game_name, report):
    """Check that the game's .vmod can be loaded."""
    game_dir = os.path.join(PROJECT_ROOT, 'games', game_name)
    if not os.path.isdir(game_dir):
        report.add(CheckResult('VMOD load', 'skip', 'Game directory missing'))
        return None

    vmod_files = [f for f in os.listdir(game_dir) if f.endswith('.vmod')]
    if not vmod_files:
        report.add(CheckResult('VMOD load', 'fail', 'No .vmod file in game directory'))
        return None

    vmod_path = os.path.join(game_dir, vmod_files[0])
    try:
        from vassal_framework import ModuleGrid
        mg = ModuleGrid.from_vmod(vmod_path)
        n_maps = len(mg.maps)
        n_boards = sum(len(b) for b in mg.maps.values())
        report.add(CheckResult(
            'VMOD load', 'pass',
            f'{vmod_files[0]}: {n_maps} maps, {n_boards} boards'
        ))
        return mg, vmod_path
    except Exception as e:
        report.add(CheckResult('VMOD load', 'fail', f'{type(e).__name__}: {e}'))
        return None


def check_grid_extraction(game_name, module_grid, report):
    """Check that grid parameters were extracted from the vmod."""
    if not module_grid:
        report.add(CheckResult('Grid extraction', 'skip', 'No module grid loaded'))
        return

    boards_with_grid = 0
    total_boards = 0
    for boards in module_grid.maps.values():
        for b in boards.values():
            total_boards += 1
            if b.grid:
                boards_with_grid += 1

    if boards_with_grid == 0:
        report.add(CheckResult(
            'Grid extraction', 'fail',
            f'0 of {total_boards} boards have grid parameters'
        ))
    elif boards_with_grid < total_boards:
        report.add(CheckResult(
            'Grid extraction', 'warn',
            f'{boards_with_grid} of {total_boards} boards have grids'
        ))
    else:
        report.add(CheckResult(
            'Grid extraction', 'pass',
            f'{boards_with_grid} of {total_boards} boards have grids'
        ))


def check_terrain_system(game_name, imported, report):
    """Check that the game's TerrainSystem instantiates correctly."""
    if 'terrain' not in imported:
        report.add(CheckResult('Terrain system', 'skip', 'terrain module not imported'))
        return None

    try:
        TerrainClass = getattr(imported['terrain'], f'{game_name}Terrain')
        ts = TerrainClass()
        n_types = len(ts.terrain_types)
        if n_types == 0:
            report.add(CheckResult(
                'Terrain system', 'warn',
                'TerrainSystem instantiated but has 0 terrain types'
            ))
        else:
            report.add(CheckResult(
                'Terrain system', 'pass',
                f'{n_types} terrain types defined: {list(ts.terrain_types.keys())}'
            ))
        return ts
    except Exception as e:
        report.add(CheckResult(
            'Terrain system', 'fail', f'{type(e).__name__}: {e}'
        ))
        return None


def check_combat_system(game_name, imported, report):
    """Check that the game's CombatSystem instantiates and resolves a test combat."""
    if 'combat' not in imported:
        report.add(CheckResult('Combat system', 'skip', 'combat module not imported'))
        return None

    try:
        CombatClass = getattr(imported['combat'], f'{game_name}Combat')
        cs = CombatClass()

        # Try a test combat
        try:
            result = cs.resolve(None, None,
                                attacker_size=5, defender_size=5,
                                attacker_strength=5, defender_strength=5,
                                attacker_type='INF', defender_type='INF',
                                position='frontal', dr=3)
            report.add(CheckResult(
                'Combat system', 'pass',
                f'CombatSystem resolves test combat: {result.summary()[:60]}'
            ))
        except Exception as e:
            report.add(CheckResult(
                'Combat system', 'warn',
                f'Instantiated but resolve() failed: {type(e).__name__}: {e}'
            ))
        return cs
    except Exception as e:
        report.add(CheckResult(
            'Combat system', 'fail', f'{type(e).__name__}: {e}'
        ))
        return None


def check_unit_scanner(game_name, module_grid, vmod_path, imported, save_path, report):
    """Check that unit scanning works on a save file."""
    if not save_path:
        report.add(CheckResult('Unit scanner', 'skip', 'No save file provided for testing'))
        return None

    if not os.path.isfile(save_path):
        report.add(CheckResult('Unit scanner', 'fail', f'Save file not found: {save_path}'))
        return None

    try:
        from vassal_framework import GameState, UnitScanner, Battlefield, detect_active_boards

        state = GameState()
        state.load_from_file(save_path)

        # Get the side classifier
        side_classifier = None
        if 'units' in imported:
            side_classifier = getattr(imported['units'], f'{game_name.lower()}_side_classifier', None)
            calibrate = getattr(imported['units'], 'calibrate_grid', None)
            if calibrate:
                calibrate(module_grid)

        scanner = UnitScanner(
            module_grid,
            active_boards=detect_active_boards(state),
            side_classifier=side_classifier,
        )
        units = scanner.scan(state)
        bf = Battlefield(units)

        details = [
            f'{len(units)} total units detected',
            f'{len(bf.leaders())} leaders',
        ]
        for side, units_list in bf._by_side.items():
            combat = sum(1 for u in units_list if not u.is_leader)
            leaders = sum(1 for u in units_list if u.is_leader)
            details.append(f'{side}: {combat} combat, {leaders} leaders')

        if len(units) == 0:
            report.add(CheckResult('Unit scanner', 'fail', '0 units detected'))
        elif len(bf.leaders()) == 0:
            report.add(CheckResult(
                'Unit scanner', 'warn',
                f'{len(units)} units but 0 leaders detected', details=details
            ))
        else:
            report.add(CheckResult(
                'Unit scanner', 'pass',
                f'{len(units)} units, {len(bf.leaders())} leaders', details=details
            ))
        return bf
    except Exception as e:
        report.add(CheckResult(
            'Unit scanner', 'fail',
            f'{type(e).__name__}: {e}',
            details=[traceback.format_exc().splitlines()[-2]]
        ))
        return None


def check_ai_evaluation(game_name, battlefield, terrain_sys, combat_sys, report):
    """Check that the AI can evaluate at least one leader's turn."""
    if not battlefield or not terrain_sys or not combat_sys:
        report.add(CheckResult('AI evaluation', 'skip', 'Missing prerequisites'))
        return

    try:
        from vassal_framework import AIDecisionEngine

        leaders = battlefield.leaders()
        active_leaders = [l for l in leaders if not l.is_finished]
        if not active_leaders:
            report.add(CheckResult(
                'AI evaluation', 'warn', 'No active leaders to evaluate'
            ))
            return

        ai = AIDecisionEngine(combat_system=combat_sys, terrain_system=terrain_sys, mc_iterations=50)
        leader = active_leaders[0]
        options = ai.evaluate_leader_turn(battlefield, leader, max_options=3)

        if not options:
            report.add(CheckResult(
                'AI evaluation', 'warn',
                f'AI evaluated {leader.name} but found no options'
            ))
        else:
            details = [f'{opt.name} (EV={opt.expected_value:.2f})' for opt in options[:3]]
            report.add(CheckResult(
                'AI evaluation', 'pass',
                f'AI evaluated {leader.name}: {len(options)} options',
                details=details
            ))
    except Exception as e:
        report.add(CheckResult(
            'AI evaluation', 'fail',
            f'{type(e).__name__}: {e}',
            details=[traceback.format_exc().splitlines()[-2]]
        ))


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def validate(game_name, save_path=None):
    """Run all validation checks on a game's library.

    Args:
      game_name: name of the game (matches games/<GameName>/)
      save_path: optional .vsav for end-to-end testing

    Returns:
      ValidationReport
    """
    report = ValidationReport(game_name)

    print(f"Validating game: {game_name}")
    if save_path:
        print(f"Test save: {save_path}")
    print()

    # 1. Directory structure
    check_directory_structure(game_name, report)

    # 2. Imports
    imported = check_imports(game_name, report)

    # 3. VMOD load
    vmod_result = check_vmod_load(game_name, report)
    module_grid = vmod_result[0] if vmod_result else None
    vmod_path = vmod_result[1] if vmod_result else None

    # 4. Grid extraction
    check_grid_extraction(game_name, module_grid, report)

    # 5. Terrain system
    terrain_sys = check_terrain_system(game_name, imported, report)

    # 6. Combat system
    combat_sys = check_combat_system(game_name, imported, report)

    # 7. Unit scanner (if save provided)
    if save_path:
        battlefield = check_unit_scanner(
            game_name, module_grid, vmod_path, imported, save_path, report
        )

        # 8. AI evaluation (if scanner worked)
        if battlefield:
            check_ai_evaluation(game_name, battlefield, terrain_sys, combat_sys, report)

    report.print_summary()
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate a game library')
    parser.add_argument('game_name', help='Name of the game (matches games/<GameName>/)')
    parser.add_argument('--save', help='Optional .vsav file for end-to-end testing')
    args = parser.parse_args()

    report = validate(args.game_name, args.save)
    sys.exit(0 if report.is_passing() else 1)


if __name__ == '__main__':
    main()
