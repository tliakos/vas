#!/usr/bin/env python3
"""
VASSAL Unit Scanner -- Generic unit detection and state extraction.

Walks a VASSAL game state, identifies every combat unit, leader, and marker,
and extracts:
- Position (pixel + hex on the correct board)
- Unit type and side
- Cohesion Hits (current damage)
- Embellishment levels (flipped/not, missile state, etc.)
- Leader stats (Command Range from AreaOfEffect)

Built on top of vassal_grid.py for accurate hex math.
"""

import re
import sys
from collections import defaultdict
from vassal_framework.grid import ModuleGrid


# ---------------------------------------------------------------------------
# Unit classification
# ---------------------------------------------------------------------------

# Roman unit prefixes (SPQR-specific but used generically)
ROMAN_PREFIXES = ['LG-', 'RC-', 'LI-Vel', 'LI-ASVel', 'HI-Tri', 'HI-ASTri']
EPIROTE_PREFIXES = []  # Everything else by default

# Unit type lookup
UNIT_TYPE_PATTERNS = {
    'PH-': 'Phalanx (PH)',
    'HI-': 'Heavy Infantry (HI)',
    'LG-': 'Legion (LG)',
    'MI-': 'Medium Infantry (MI)',
    'LI-': 'Light Infantry (LI)',
    'SK-': 'Skirmisher (SK)',
    'VE-': 'Velites (VE)',
    'HC-': 'Heavy Cavalry (HC)',
    'LC-': 'Light Cavalry (LC)',
    'RC-': 'Roman Cavalry (RC)',
    'EL-': 'Elephant (EL)',
    'CH-': 'Chariot (CH)',
    'LN-': 'Lancer (LN)',
    'TR-': 'Triarii (TR)',
}


# ---------------------------------------------------------------------------
# Unit data class
# ---------------------------------------------------------------------------

class Unit:
    """A combat unit or leader on the battlefield."""

    def __init__(self):
        self.pid = ''
        self.name = ''
        self.image = ''
        self.unit_type = ''      # Type code (PH, HI, LG, RC, LC, etc.)
        self.side = ''            # 'Roman' or 'Epirote' (or game-specific)
        self.map_name = ''        # Map name
        self.board_name = ''      # Board name on that map
        self.pixel_x = 0
        self.pixel_y = 0
        self.hex_col = None       # Hex column number
        self.hex_row = None       # Hex row number
        self.cohesion_hits = 0    # Current damage
        self.is_leader = False
        self.command_range = None # Leaders only
        self.is_finished = False  # Leader Finished/Active state
        self.flipped = False      # Combat unit reduced/flipped state
        self.missile_low = False
        self.missile_no = False
        self.routed = False
        self.engaged = False
        self.has_moved = False
        self.raw_type = ''
        self.raw_state = ''

    def hex_id(self):
        if self.hex_col is None: return None
        return f"{self.hex_col:02d}{self.hex_row:02d}"

    def __repr__(self):
        h = self.hex_id() or "?"
        ch = f" CH={self.cohesion_hits}" if self.cohesion_hits else ""
        flip = " (FINISHED)" if self.is_finished else ""
        return f"<{self.side[0]} {self.name} @{h}{ch}{flip}>"


# ---------------------------------------------------------------------------
# Unit scanner
# ---------------------------------------------------------------------------

def detect_active_boards(game_state):
    """Parse the BoardPicker setup commands in a save to find which boards are loaded.

    Returns: dict {map_name: board_name} for currently active boards.
    The save contains commands like 'Main MapBoardPicker\\tHeraclea\\t0\\t0'.
    """
    active = {}
    full_cmd = '\x1b'.join(game_state.pre_commands + game_state.post_commands)
    # Pattern: "<MapName>BoardPicker\t<BoardName>\t<X>\t<Y>"
    # Stop board name at \t (end-of-field), not just whitespace
    matches = re.findall(r'([\w\s]+)BoardPicker\t([^\t]+)\t', full_cmd)
    for map_name, board_name in matches:
        active[map_name.strip()] = board_name.strip()
    return active


class UnitScanner:
    """Scans a GameState and extracts a complete unit registry with hex positions."""

    def __init__(self, module_grid: ModuleGrid, side_classifier=None,
                 active_boards=None):
        """
        module_grid: ModuleGrid instance for the loaded vmod
        side_classifier: optional function(image_filename) -> side string
        active_boards: dict {map_name: board_name} indicating which board is loaded
                       on each map. Auto-detected from save if not provided.
        """
        self.module_grid = module_grid
        self.side_classifier = side_classifier or self._default_classifier
        self.active_boards = active_boards or {}

    @staticmethod
    def _default_classifier(image):
        """Default side classification based on image filename prefix."""
        for p in ROMAN_PREFIXES:
            if image.startswith(p):
                return 'Roman'
        return 'Epirote'

    def scan(self, game_state):
        """Scan a GameState object and return a list of Unit instances."""
        # Auto-detect active boards if not provided
        if not self.active_boards:
            self.active_boards = detect_active_boards(game_state)

        units = []
        for pid, (ptype, pstate) in game_state.pieces.items():
            unit = self._parse_piece(pid, ptype, pstate, game_state)
            if unit:
                units.append(unit)
        return units

    def _parse_piece(self, pid, ptype, pstate, game_state):
        """Parse a single piece (AddPiece command) into a Unit."""
        # Skip pieces with no images / not actual units
        imgs = re.findall(r'([\w.-]+\.(?:png|gif|jpg))', ptype)
        is_leader = 'AreaOfEffect' in ptype

        unit = Unit()
        unit.pid = pid
        unit.raw_type = ptype
        unit.raw_state = pstate

        # Position
        map_name, x, y = game_state.get_piece_position(pid)
        unit.map_name = map_name
        unit.pixel_x = x
        unit.pixel_y = y

        # Skip pieces with no position
        if not map_name or x == 0:
            return None

        # Determine board and hex coordinates
        # Use the active board for this map (from save file's BoardPicker setup)
        board = None
        if map_name in self.active_boards:
            board_name = self.active_boards[map_name]
            board = self.module_grid.get_board(map_name, board_name)
        if board is None:
            board = self.module_grid.find_board_for_pixel(map_name, x, y)
        if board:
            unit.board_name = board.name
            hex_result = board.pixel_to_hex(x, y)
            if hex_result:
                unit.hex_col, unit.hex_row = hex_result

        # Identify unit type from BasicPiece (the innermost trait)
        bp_match = re.search(r'piece;.*?;.*?;([^;]*);([^;/]+)(?:/(\d+))?', pstate)
        if bp_match:
            piece_image = bp_match.group(1)
            piece_name = bp_match.group(2)
            flip_indicator = bp_match.group(3)

            unit.image = piece_image
            unit.name = piece_name

            # Leaders have name in piece state ending with /1 (front) or /2 (back/Finished)
            if is_leader:
                unit.is_leader = True
                if flip_indicator == '2':
                    unit.is_finished = True

        # Filter: identify real combat unit images (LG-, RC-, etc.) vs markers
        unit_imgs = [i for i in imgs if 'Marker' not in i and 'Highlight' not in i
                     and 'finished' not in i.lower() and 'eliteused' not in i.lower()
                     and 'Routed' not in i and 'Trumped' not in i]

        # Skip pure marker pieces (no unit image, not a leader)
        if not unit_imgs and not is_leader:
            return None

        # Skip markers that masquerade as units (e.g., Engaged marker)
        slot_match = re.search(r'PieceSlot:([^;\\]+)', pstate)
        slot_name = slot_match.group(1) if slot_match else ''
        pure_markers = {'Trumped', 'Engaged', 'Rallied', 'In pursuit', 'In Column',
                        'Turn', 'Break pursuit', 'Uncontrolled advance', 'Rout Levels',
                        'PW', 'NO PW', 'Withdrawal levels', 'Highlight Unit'}
        # Only filter if not a leader, has no unit image, and slot is a marker
        if slot_name in pure_markers and not unit_imgs and not is_leader:
            return None

        # Set image and name from type if not already set
        if not unit.image and unit_imgs:
            unit.image = unit_imgs[0]
            # Derive name from image
            unit.name = unit_imgs[0].replace('-B.png', '').replace('-F.png', '').replace('.png', '')

        # Determine side first (uses coded image)
        if is_leader:
            # Leaders: derive side from piece image filename in state
            if 'RomanLeader' in pstate:
                unit.side = 'Roman'
            elif 'MacedonLeader' in pstate or 'Greek' in pstate[:500]:
                unit.side = 'Epirote'
            else:
                unit.side = 'Unknown'
        else:
            # Combat units: classify based on coded image (LG-, RC-, HC-, etc.)
            # Prefer the coded image (e.g., LG-ASCo-XV-B.png) over the descriptive one
            coded_img = None
            for i in unit_imgs:
                if re.match(r'^[A-Z]{2}-', i):  # Two-letter unit type prefix
                    coded_img = i
                    break
            classify_img = coded_img or (unit_imgs[0] if unit_imgs else '')
            unit.side = self.side_classifier(classify_img)
            # Set the coded image as the primary if found
            if coded_img:
                unit.image = coded_img
                unit.name = coded_img.replace('-B.png', '').replace('-F.png', '').replace('.png', '')

        # Classify unit type from the coded image (after we've set it)
        if unit.image:
            for prefix, type_name in UNIT_TYPE_PATTERNS.items():
                if unit.image.startswith(prefix):
                    unit.unit_type = type_name
                    break

        # Extract Command Range from AreaOfEffect trait (leaders only)
        if is_leader:
            aoe_match = re.search(r'AreaOfEffect;[^;]*;\d+;(\d+);', ptype)
            if aoe_match:
                unit.command_range = int(aoe_match.group(1))

        # Extract Cohesion Hits
        # The state segment immediately AFTER the BasicPiece (piece;...) segment
        # contains the COH Hits embellishment level as a small integer
        unit.cohesion_hits = self._extract_cohesion_hits(pstate)

        # Detect status flags from state
        if 'Routed' in slot_name:
            unit.routed = True
        if 'Engaged' in slot_name:
            unit.engaged = True

        return unit

    def _extract_cohesion_hits(self, pstate):
        """Extract Cohesion Hits from the piece state.

        TODO: Cohesion Hits is stored in a deeply nested embellishment that
        requires expanding all prototype references in the type to find the
        correct state segment offset. Returns 0 for now -- the user should
        provide cohesion hit values manually until this is implemented.

        The COH_Hits prototype contains:
          emb2;;LEVEL;;Increase COH Hits;...;Marker_COH Hit 1.png,...
        where LEVEL is 0-8 corresponding to current hits.
        """
        # Search the state for the COH Hits emb2 segment
        state_parts = pstate.split('\t')
        for sp in state_parts:
            if 'COH Hit' in sp and sp.startswith('emb2;'):
                # Format: emb2;NAME;LEVEL;...
                # Parse out LEVEL (the value after the second semicolon)
                fields = sp.split(';')
                if len(fields) >= 3:
                    try:
                        return int(fields[2])
                    except (ValueError, IndexError):
                        pass
        return 0


# ---------------------------------------------------------------------------
# Hex math helpers
# ---------------------------------------------------------------------------

def hex_distance_offset(c1, r1, c2, r2):
    """Hex distance using cube coordinates from offset (col, row) input."""
    # Odd-q vertical (sideways flat-top in VASSAL terms)
    x1 = c1
    z1 = r1 - (c1 - (c1 & 1)) // 2
    y1 = -x1 - z1
    x2 = c2
    z2 = r2 - (c2 - (c2 & 1)) // 2
    y2 = -x2 - z2
    return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))


def hex_neighbors(col, row):
    """Get the 6 neighbors of a hex (offset coordinates, sideways/odd-q)."""
    if col % 2 == 0:
        return [
            (col + 1, row), (col + 1, row - 1),
            (col - 1, row), (col - 1, row - 1),
            (col, row - 1), (col, row + 1),
        ]
    else:
        return [
            (col + 1, row), (col + 1, row + 1),
            (col - 1, row), (col - 1, row + 1),
            (col, row - 1), (col, row + 1),
        ]


# ---------------------------------------------------------------------------
# Battlefield: high-level query interface
# ---------------------------------------------------------------------------

class Battlefield:
    """High-level interface to query the battlefield state."""

    def __init__(self, units):
        self.units = units
        self._by_hex = defaultdict(list)
        self._by_pid = {}
        self._by_side = defaultdict(list)
        self._leaders = []
        for u in units:
            self._by_pid[u.pid] = u
            self._by_side[u.side].append(u)
            if u.hex_col is not None:
                self._by_hex[(u.hex_col, u.hex_row)].append(u)
            if u.is_leader:
                self._leaders.append(u)

    def at_hex(self, col, row):
        """All units at a specific hex."""
        return self._by_hex.get((col, row), [])

    def at_hex_str(self, hex_str):
        """All units at a hex by string ID like '2607'."""
        col = int(hex_str[:2])
        row = int(hex_str[2:])
        return self.at_hex(col, row)

    def by_side(self, side):
        """All units of a side."""
        return self._by_side.get(side, [])

    def leaders(self, side=None, finished=None):
        """All leaders, optionally filtered by side and finished state."""
        result = self._leaders
        if side is not None:
            result = [l for l in result if l.side == side]
        if finished is not None:
            result = [l for l in result if l.is_finished == finished]
        return result

    def in_command_range(self, leader, hex_dist=None):
        """All units within a leader's command range."""
        if hex_dist is None:
            hex_dist = leader.command_range or 3
        if leader.hex_col is None:
            return []
        result = []
        for u in self.units:
            if u.hex_col is None: continue
            if u.is_leader: continue
            d = hex_distance_offset(leader.hex_col, leader.hex_row, u.hex_col, u.hex_row)
            if d <= hex_dist:
                result.append((u, d))
        return result

    def adjacent_enemies(self, unit):
        """All enemy units adjacent to a given unit."""
        if unit.hex_col is None: return []
        result = []
        for nc, nr in hex_neighbors(unit.hex_col, unit.hex_row):
            for u2 in self.at_hex(nc, nr):
                if u2.side != unit.side and not u2.is_leader:
                    result.append(u2)
        return result

    def is_in_zoc(self, unit):
        """Check if a unit is in any enemy ZOC.

        ZOC extends into Front hexes only per Rule 7.21 (in SPQR), but we
        approximate by checking adjacency. Skirmishers without missiles
        and routed/leader pieces don't exert ZOC.
        """
        for enemy in self.adjacent_enemies(unit):
            # Skirmishers and routed don't exert ZOC
            if 'SK-' in (enemy.image or ''): continue
            if enemy.routed: continue
            return True
        return False

    def summarize(self):
        """Print a battlefield summary."""
        print(f"Total units: {len(self.units)}")
        for side, units in self._by_side.items():
            combat = sum(1 for u in units if not u.is_leader)
            leaders = sum(1 for u in units if u.is_leader)
            print(f"  {side}: {combat} combat units, {leaders} leaders")

        damaged = [u for u in self.units if u.cohesion_hits > 0 and not u.is_leader]
        if damaged:
            print(f"\n  Damaged units ({len(damaged)}):")
            for u in damaged:
                print(f"    {u.side[:1]} {u.name:25s} {u.hex_id()}: {u.cohesion_hits} hits")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 vassal_units.py <module.vmod> <save.vsav>")
        sys.exit(1)

    from vassal_framework.save_io import GameState

    mg = ModuleGrid.from_vmod(sys.argv[1])

    # Calibrate hex grid max_cols for any boards (default 46 works for SPQR)
    for map_name, boards in mg.maps.items():
        for board in boards.values():
            if board.grid:
                board.grid.max_cols = 46
                board.grid.max_rows = 46

    state = GameState()
    state.load_from_file(sys.argv[2])

    # Auto-detect which boards are loaded
    active = detect_active_boards(state)
    print(f"Active boards: {active}")

    scanner = UnitScanner(mg, active_boards=active)
    units = scanner.scan(state)

    bf = Battlefield(units)
    bf.summarize()

    print("\nLeaders:")
    for ldr in bf.leaders():
        cr = f"CR{ldr.command_range}" if ldr.command_range else "?"
        status = "FINISHED" if ldr.is_finished else "ACTIVE"
        print(f"  [{ldr.side[:1]}] {ldr.name:30s} {ldr.hex_id() or '?':5s} {cr:5s} {status}")

    print("\nDamaged combat units:")
    damaged = [u for u in units if u.cohesion_hits > 0 and not u.is_leader]
    for u in damaged[:30]:
        print(f"  [{u.side[:1]}] {u.name:25s} {u.hex_id() or '?':5s} hits={u.cohesion_hits}")
