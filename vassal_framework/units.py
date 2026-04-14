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
#
# This module is GAME-AGNOSTIC. It provides the abstract Unit, UnitScanner,
# and Battlefield classes. Game-specific unit types, side classifiers, and
# stat mappings live in games/<GameName>/<game>_lib/units.py.
#
# UnitScanner accepts callbacks:
#   - side_classifier(image_filename) -> side string
#   - unit_type_classifier(image_filename) -> unit_type code (optional)
#   - is_skirmisher(unit) -> bool (optional, for ZOC rules)
#
# These callbacks let each game implement its own classification logic
# without polluting the framework with game-specific codes.


# ---------------------------------------------------------------------------
# Unit data class
# ---------------------------------------------------------------------------

class Unit:
    """A combat unit or leader on the battlefield."""

    def __init__(self):
        self.pid = ''
        self.name = ''
        self.image = ''
        self.unit_type = ''      # Game-specific type code (set by unit_type_classifier)
        self.side = ''            # Game-specific side (set by side_classifier)
        self.map_name = ''        # Map name
        self.board_name = ''      # Board name on that map
        self.pixel_x = 0
        self.pixel_y = 0
        self.hex_col = None       # Hex column number
        self.hex_row = None       # Hex row number
        self.cohesion_hits = 0    # Current damage
        self.is_leader = False
        self.command_range = None # Leaders only: hex radius for orders
        self.initiative = None    # Leaders only: number of orders per activation
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
    """Scans a GameState and extracts a complete unit registry with hex positions.

    This class is GAME-AGNOSTIC. To make it work for a specific game, pass:

      side_classifier: function(image_filename) -> side string
        Maps a piece's image filename to its side. REQUIRED for any game
        that has more than one player side. Without this, all units are
        classified as 'Unknown'.

      unit_type_classifier: function(image_filename) -> type_code (optional)
        Maps a piece's image filename to its unit type code (e.g., 'INF',
        'PH', 'ARM'). If None, unit_type is left empty.

      is_skirmisher_check: function(unit) -> bool (optional)
        Returns True if the unit is a skirmisher (doesn't exert ZOC).
        If None, ZOC checks consider all combat units to exert ZOC.
    """

    def __init__(self, module_grid: ModuleGrid,
                 side_classifier=None,
                 unit_type_classifier=None,
                 is_skirmisher_check=None,
                 active_boards=None):
        self.module_grid = module_grid
        self.side_classifier = side_classifier or self._default_classifier
        self.unit_type_classifier = unit_type_classifier
        self.is_skirmisher_check = is_skirmisher_check
        self.active_boards = active_boards or {}

    @staticmethod
    def _default_classifier(image):
        """Default classifier returns 'Unknown'.

        Game libs MUST provide their own side_classifier to get meaningful
        side classification.
        """
        return 'Unknown'

    def scan(self, game_state):
        """Scan a GameState object and return a list of Unit instances.

        Two-pass: first pass extracts Unit objects. Second pass walks the
        full piece list looking for status-marker pieces (Engaged, etc.)
        and propagates their state to co-located units.
        """
        # Auto-detect active boards if not provided
        if not self.active_boards:
            self.active_boards = detect_active_boards(game_state)

        units = []
        for pid, (ptype, pstate) in game_state.pieces.items():
            unit = self._parse_piece(pid, ptype, pstate, game_state)
            if unit:
                units.append(unit)

        # Second pass: detect status markers (Engaged, etc.) and propagate
        # them to units. Markers are separate pieces co-located on a hex
        # with the unit they reference. We match by hex position and (when
        # available) by ParentID linking back to the unit's pid.
        self._propagate_status_markers(game_state, units)

        return units

    def _propagate_status_markers(self, game_state, units):
        """Find Marker_* pieces and apply their state to co-located units.

        Recognizes:
          - Marker_Engaged.jpg → unit.engaged = True
        """
        # Build a quick lookup: pid -> Unit
        units_by_pid = {u.pid: u for u in units}
        # And by hex
        units_by_hex = defaultdict(list)
        for u in units:
            if u.hex_col is not None:
                units_by_hex[(u.hex_col, u.hex_row)].append(u)

        for pid, (ptype, pstate) in game_state.pieces.items():
            if 'Marker_Engaged' not in ptype:
                continue

            # Find ParentID linking back to a real unit
            parent_match = re.search(r'ParentID;(\d+)', pstate)
            if parent_match:
                parent_pid = parent_match.group(1)
                if parent_pid in units_by_pid:
                    units_by_pid[parent_pid].engaged = True

            # Also mark all units sharing the marker's hex as engaged.
            # In SPQR, an Engaged marker is dropped on each engaged unit's
            # hex, so co-location is the simpler heuristic.
            map_name, x, y = game_state.get_piece_position(pid)
            if map_name and x > 0 and y > 0:
                board = None
                if map_name in self.active_boards:
                    board = self.module_grid.get_board(map_name, self.active_boards[map_name])
                if board is None:
                    board = self.module_grid.find_board_for_pixel(map_name, x, y)
                if board:
                    h = board.pixel_to_hex(x, y)
                    if h:
                        for u in units_by_hex.get(h, []):
                            u.engaged = True

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
        def _is_unit_img(i):
            if 'Marker' in i or 'Highlight' in i:
                return False
            lo = i.lower()
            if 'finished' in lo or 'eliteused' in lo:
                return False
            if 'Routed' in i or 'Trumped' in i:
                return False
            if 'counter template' in lo:  # blank placeholder, not a real unit image
                return False
            # Skip small marker-like gifs (Screen, Missile, Rampage, etc.)
            if i in ('Highlight.gif',) or lo.startswith(('screen', 'missile', 'elrampage')):
                return False
            # Single-digit pngs used for numeric overlays
            if re.match(r'^\d+\.png$', i):
                return False
            return True

        unit_imgs = [i for i in imgs if _is_unit_img(i)]

        # Some pieces store the unit image only in pstate, not ptype:
        #   - BasicPiece image (e.g. "Syrian_EL_Indian1.jpg")
        #   - Layer/emb2 trait images (e.g. Macedonian phalanx with
        #     "Counter Template.png" BasicPiece + Layer showing
        #     "Macedon_PH_Macedon5.jpg,PH-Macedon-B.png")
        if unit.image and _is_unit_img(unit.image) and unit.image not in unit_imgs:
            unit_imgs.append(unit.image)

        if not unit_imgs:
            pstate_imgs = re.findall(r'([\w.-]+\.(?:png|gif|jpg))', pstate)
            for pi in pstate_imgs:
                if _is_unit_img(pi) and pi not in unit_imgs:
                    unit_imgs.append(pi)

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

        # Determine side via the game-specific classifier
        # For leaders, the classifier is called with the leader's piece image
        # (typically a .jpg like "RomanLeader_..." or "GermanLeader_...")
        if is_leader:
            # Find the leader image in the state (BasicPiece reference)
            leader_img_match = re.search(r'piece;[^;]*;[^;]*;([^;]+\.jpg)', pstate)
            classify_img = leader_img_match.group(1) if leader_img_match else ''
            unit.side = self.side_classifier(classify_img)
        else:
            # Combat units: prefer the coded image (e.g., XX-name.png) over descriptive
            coded_img = None
            for i in unit_imgs:
                if re.match(r'^[A-Z]{2,4}[-_]', i):  # Type prefix
                    coded_img = i
                    break
            classify_img = coded_img or (unit_imgs[0] if unit_imgs else '')
            unit.side = self.side_classifier(classify_img)
            # Set the coded image as the primary if found. Keep the
            # BasicPiece name when it's more specific (e.g. "PH Macedon 5")
            # than the derived-from-image name ("PH-Macedon").
            if coded_img:
                unit.image = coded_img
                derived_name = (coded_img.replace('-B.png', '')
                                        .replace('-F.png', '')
                                        .replace('.png', ''))
                bp_name = (unit.name or '').strip()
                # BasicPiece names like "Counter Template" are generic; skip those.
                if not bp_name or bp_name.lower() in ('counter template', ''):
                    unit.name = derived_name

        # Classify unit type via the game-specific callback if provided
        if unit.image and self.unit_type_classifier:
            unit.unit_type = self.unit_type_classifier(unit.image) or ''

        # Extract Command Range from AreaOfEffect trait (leaders only)
        if is_leader:
            aoe_match = re.search(r'AreaOfEffect;[^;]*;\d+;(\d+);', ptype)
            if aoe_match:
                unit.command_range = int(aoe_match.group(1))

        # Extract Cohesion Hits
        # The state segment immediately AFTER the BasicPiece (piece;...) segment
        # contains the COH Hits embellishment level as a small integer
        unit.cohesion_hits = self._extract_cohesion_hits(pstate)

        # Detect status flags. NOTE: slot_name from a placemark trait is the
        # placemark's TARGET, not the unit's own slot. Active combat units
        # often reference a "Routed" placemark target -- that doesn't mean
        # they're routed. Only treat as routed if the unit's own piece image
        # is a routed marker, or if its containing slot is literally a
        # routed pile (matched at the END of the slot name).
        if unit.image and ('Marker_Routed' in unit.image or 'Routed' in unit.image):
            unit.routed = True
        if unit.image and 'Marker_Engaged' in unit.image:
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

    def is_in_zoc(self, unit, is_skirmisher_check=None):
        """Check if a unit is in any enemy ZOC.

        Most wargames use full-hex ZOC for combat units, with exceptions
        for routed units, leaders, and (in some games) skirmishers.

        Args:
          unit: the unit to check
          is_skirmisher_check: optional callback (unit) -> bool that returns
            True if the unit is a skirmisher (doesn't exert ZOC). If None,
            all non-routed combat units are assumed to exert ZOC.
        """
        for enemy in self.adjacent_enemies(unit):
            if enemy.routed:
                continue
            if is_skirmisher_check and is_skirmisher_check(enemy):
                continue
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
    print("vassal_framework.units is a library module.")
    print("Use it via game-specific runners that supply a side_classifier:")
    print("  python3 -m games.<GameName>.<game>_lib.runner <save.vsav>")
    print()
    print("Or import in your own script:")
    print("  from vassal_framework import UnitScanner, Battlefield")
    sys.exit(0)

    print("\nLeaders:")
    for ldr in bf.leaders():
        cr = f"CR{ldr.command_range}" if ldr.command_range else "?"
        status = "FINISHED" if ldr.is_finished else "ACTIVE"
        print(f"  [{ldr.side[:1]}] {ldr.name:30s} {ldr.hex_id() or '?':5s} {cr:5s} {status}")

    print("\nDamaged combat units:")
    damaged = [u for u in units if u.cohesion_hits > 0 and not u.is_leader]
    for u in damaged[:30]:
        print(f"  [{u.side[:1]}] {u.name:25s} {u.hex_id() or '?':5s} hits={u.cohesion_hits}")
