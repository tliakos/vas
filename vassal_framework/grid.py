#!/usr/bin/env python3
"""
VASSAL Grid Framework -- Generic hex/square grid handling for any VASSAL module.

Parses buildFile.xml from any .vmod, extracts per-board grid parameters,
implements the EXACT VASSAL pixel<->hex conversion formula (matching
HexGrid.java and HexGridNumbering.java in the VASSAL source), and handles
multi-board maps with board offsets.

This is the foundation for any AI play in any hex-and-counter game.
"""

import zipfile
import xml.etree.ElementTree as ET
import re
from typing import Optional


def tag_short(tag):
    """Strip Java class path from XML element tag."""
    return tag.rsplit(".", 1)[-1] if "." in tag else tag


# ---------------------------------------------------------------------------
# Grid configurations
# ---------------------------------------------------------------------------

class HexGridConfig:
    """A VASSAL HexGrid configuration parsed from buildFile.xml.

    Implements the same formula as VASSAL.build.module.map.boardPicker.board.HexGrid
    and HexGridNumbering.

    Key attributes from VASSAL XML:
      dx       -- hex width
      dy       -- hex size (full height)
      x0, y0   -- grid origin offset
      sideways -- if true, hex grid is rotated 90 (flat-top)
      stagger  -- staggered offset for odd columns
      hOff     -- column number offset
      vOff     -- row number offset
      hDescend -- horizontal numbering descends
      vDescend -- vertical numbering descends
      first    -- "H" (column-first) or "V" (row-first)
      sep      -- separator string between col/row in display
      max_cols / max_rows -- board hex dimensions (for descend math)
    """

    def __init__(self, **kwargs):
        # Grid geometry
        self.dx = float(kwargs.get('dx', 96))
        self.dy = float(kwargs.get('dy', 110))
        self.x0 = int(round(float(kwargs.get('x0', 0))))
        self.y0 = int(round(float(kwargs.get('y0', 0))))
        self.sideways = kwargs.get('sideways', False)

        # Numbering
        self.h_off = int(kwargs.get('hOff', 0))
        self.v_off = int(kwargs.get('vOff', 0))
        self.h_descend = kwargs.get('hDescend', False)
        self.v_descend = kwargs.get('vDescend', False)
        self.stagger = kwargs.get('stagger', True)
        self.first = kwargs.get('first', 'H')  # H = column-first, V = row-first
        self.sep = kwargs.get('sep', '')
        self.h_leading = int(kwargs.get('hLeading', 0))
        self.v_leading = int(kwargs.get('vLeading', 0))
        self.h_type = kwargs.get('hType', 'N')  # N = numeric, A = alpha
        self.v_type = kwargs.get('vType', 'N')

        # Board dimensions (for descend math) -- usually inferred from board image
        # Default values; will be overridden by Board parser
        self.max_cols = int(kwargs.get('max_cols', 50))
        self.max_rows = int(kwargs.get('max_rows', 50))

    @classmethod
    def from_xml(cls, element):
        """Build HexGridConfig from a parsed VASSAL HexGrid XML element."""
        attrs = dict(element.attrib)
        kwargs = {
            'dx': attrs.get('dx', '96'),
            'dy': attrs.get('dy', '110'),
            'x0': attrs.get('x0', '0'),
            'y0': attrs.get('y0', '0'),
            'sideways': attrs.get('sideways', 'false') == 'true',
        }

        # Find HexGridNumbering child
        for child in element:
            tag = tag_short(child.tag)
            if 'Numbering' in tag:
                n_attrs = dict(child.attrib)
                kwargs['hOff'] = int(n_attrs.get('hOff', 0))
                kwargs['vOff'] = int(n_attrs.get('vOff', 0))
                kwargs['hDescend'] = n_attrs.get('hDescend', 'false') == 'true'
                kwargs['vDescend'] = n_attrs.get('vDescend', 'false') == 'true'
                kwargs['stagger'] = n_attrs.get('stagger', 'true') == 'true'
                kwargs['first'] = n_attrs.get('first', 'H')
                kwargs['sep'] = n_attrs.get('sep', '')
                kwargs['hLeading'] = int(n_attrs.get('hLeading', 0))
                kwargs['vLeading'] = int(n_attrs.get('vLeading', 0))
                kwargs['hType'] = n_attrs.get('hType', 'N')
                kwargs['vType'] = n_attrs.get('vType', 'N')
                break

        return cls(**kwargs)

    def pixel_to_hex(self, px, py):
        """Convert pixel coordinates to (col, row) hex IDs.

        This implements the exact VASSAL formula:
          1. rotateIfSideways: swap x,y if sideways
          2. raw_col = round((x - origin.x) / dx)  (using floor + 0.5)
          3. raw_row depends on raw_col parity (stagger)
          4. Apply numbering offsets and descend
        """
        x, y = px, py
        if self.sideways:
            x, y = y, x  # rotateIfSideways

        # Raw column (VASSAL uses floor(x/dx + 0.5) which equals round)
        raw_col = int((x - self.x0) / self.dx + 0.5)
        if (x - self.x0) < 0 and ((x - self.x0) / self.dx + 0.5) < 0:
            raw_col = int((x - self.x0) / self.dx + 0.5) - (1 if (x - self.x0) % self.dx != 0 else 0)

        # Raw row (with stagger offset for odd columns)
        if raw_col % 2 == 0:
            raw_row = round((y - self.y0) / self.dy)
        else:
            raw_row = round((y - self.y0 - self.dy / 2) / self.dy)

        return self._apply_numbering(raw_col, raw_row)

    def _apply_numbering(self, raw_col, raw_row):
        """Apply hOff/vOff/hDescend/vDescend/stagger to raw col/row."""
        # Column transformation (per HexGridNumbering.getColumn)
        col = raw_col
        if self.v_descend and self.sideways:
            col = self.max_rows - col
        if self.h_descend and not self.sideways:
            col = self.max_cols - col

        # Row transformation (per HexGridNumbering.getRow)
        row = raw_row
        if self.v_descend and not self.sideways:
            row = self.max_rows - row
        if self.h_descend and self.sideways:
            row = self.max_cols - row

        # Stagger adjustment (per HexGridNumbering.getRow)
        if self.stagger:
            if self.sideways:
                if raw_col % 2 != 0:
                    if self.h_descend:
                        row -= 1
                    else:
                        row += 1
            else:
                if raw_col % 2 != 0:
                    if self.v_descend:
                        row -= 1
                    else:
                        row += 1

        # Apply numbering offsets
        col += self.h_off
        row += self.v_off

        return col, row

    def hex_to_pixel(self, col, row):
        """Convert (col, row) hex ID back to pixel coordinates."""
        # Reverse numbering offsets
        col_internal = col - self.h_off
        row_internal = row - self.v_off

        # Reverse stagger
        raw_col = col_internal
        if self.v_descend and self.sideways:
            raw_col = self.max_rows - col_internal
        if self.h_descend and not self.sideways:
            raw_col = self.max_cols - col_internal

        if self.stagger:
            if self.sideways:
                if raw_col % 2 != 0:
                    if self.h_descend:
                        row_internal += 1
                    else:
                        row_internal -= 1
            else:
                if raw_col % 2 != 0:
                    if self.v_descend:
                        row_internal += 1
                    else:
                        row_internal -= 1

        if self.v_descend and not self.sideways:
            raw_row = self.max_rows - row_internal
        elif self.h_descend and self.sideways:
            raw_row = self.max_cols - row_internal
        else:
            raw_row = row_internal

        # Compute rotated pixel coordinates
        x = self.x0 + raw_col * self.dx
        if raw_col % 2 == 0:
            y = self.y0 + raw_row * self.dy
        else:
            y = self.y0 + raw_row * self.dy + self.dy / 2

        # Un-rotate
        if self.sideways:
            return int(round(y)), int(round(x))
        return int(round(x)), int(round(y))

    def hex_distance(self, c1, r1, c2, r2):
        """Calculate hex distance using cube coordinates (handles all hex types)."""
        # Convert offset (col, row) to cube coordinates
        # For odd-q vertical layout (sideways flat-top):
        x1 = c1
        z1 = r1 - (c1 - (c1 & 1)) // 2
        y1 = -x1 - z1

        x2 = c2
        z2 = r2 - (c2 - (c2 & 1)) // 2
        y2 = -x2 - z2

        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))

    def hex_id(self, col, row):
        """Format as a hex ID string (e.g., '2607')."""
        return f"{col:02d}{row:02d}"

    def parse_hex_id(self, hex_str):
        """Parse a hex ID string back to (col, row)."""
        return int(hex_str[:2]), int(hex_str[2:])


# ---------------------------------------------------------------------------
# Board: a single playable area with a grid
# ---------------------------------------------------------------------------

class Board:
    """A board within a multi-board map, with its own grid and pixel offset."""

    def __init__(self, name, image=None, grid=None, offset_x=0, offset_y=0,
                 width=None, height=None):
        self.name = name
        self.image = image
        self.grid = grid
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.width = width
        self.height = height

    def pixel_to_hex(self, px, py):
        """Convert pixel coordinates (relative to parent map) to hex on this board."""
        if not self.grid:
            return None
        local_x = px - self.offset_x
        local_y = py - self.offset_y
        return self.grid.pixel_to_hex(local_x, local_y)

    def hex_to_pixel(self, col, row):
        """Convert hex ID to pixel coordinates relative to parent map."""
        if not self.grid:
            return None
        local_x, local_y = self.grid.hex_to_pixel(col, row)
        return local_x + self.offset_x, local_y + self.offset_y

    def contains_pixel(self, px, py):
        """Check if a pixel position is within this board."""
        if self.width is None or self.height is None:
            return True  # Can't check without dimensions
        return (self.offset_x <= px < self.offset_x + self.width and
                self.offset_y <= py < self.offset_y + self.height)

    def __repr__(self):
        return f"Board('{self.name}', offset=({self.offset_x},{self.offset_y}))"


# ---------------------------------------------------------------------------
# Module parser: extracts grid info from any vmod
# ---------------------------------------------------------------------------

class ModuleGrid:
    """Top-level grid information for a vmod, organized by map name -> board name."""

    def __init__(self):
        self.maps = {}  # map_name -> {board_name: Board}

    @classmethod
    def from_vmod(cls, vmod_path):
        """Parse a .vmod file and extract all board grids."""
        with zipfile.ZipFile(vmod_path) as zf:
            bf_name = 'buildFile.xml' if 'buildFile.xml' in zf.namelist() else 'buildFile'
            bf_data = zf.read(bf_name).decode('utf-8', errors='replace')

        root = ET.fromstring(bf_data)
        instance = cls()
        instance._walk(root, current_map=None)
        return instance

    def _walk(self, element, current_map):
        """Recursively walk the XML tree extracting maps, boards, and grids."""
        tag = tag_short(element.tag)

        if tag in ('Map', 'PrivateMap', 'PlayerHand'):
            map_name = element.attrib.get('mapName', element.attrib.get('name', 'unnamed'))
            current_map = map_name
            if map_name not in self.maps:
                self.maps[map_name] = {}

        elif tag == 'Board':
            if current_map is None:
                return  # Skip orphan boards
            board_name = element.attrib.get('name', 'unnamed')
            image = element.attrib.get('image', '')
            width = element.attrib.get('width')
            height = element.attrib.get('height')

            # Find HexGrid or SquareGrid child
            grid = None
            for child in element:
                child_tag = tag_short(child.tag)
                if child_tag == 'HexGrid':
                    grid = HexGridConfig.from_xml(child)
                # ZonedGrid contains nested grids; for now extract first hex grid found
                elif child_tag == 'ZonedGrid':
                    for zc in child:
                        if tag_short(zc.tag) == 'HexGrid':
                            grid = HexGridConfig.from_xml(zc)
                            break

            board = Board(board_name, image=image, grid=grid)
            if width:
                try: board.width = int(width)
                except ValueError: pass
            if height:
                try: board.height = int(height)
                except ValueError: pass

            self.maps[current_map][board_name] = board

        for child in element:
            self._walk(child, current_map)

    def get_board(self, map_name, board_name):
        """Get a specific board by map and name."""
        return self.maps.get(map_name, {}).get(board_name)

    def get_first_board(self, map_name):
        """Get the first board in a map (for single-board maps)."""
        boards = self.maps.get(map_name, {})
        if boards:
            return next(iter(boards.values()))
        return None

    def find_board_for_pixel(self, map_name, px, py):
        """Find which board on a map contains a given pixel position."""
        for board in self.maps.get(map_name, {}).values():
            if board.contains_pixel(px, py):
                return board
        return self.get_first_board(map_name)

    def pixel_to_hex(self, map_name, px, py, board_name=None):
        """Convert a pixel on a map to a hex ID. Auto-detects board if not specified."""
        if board_name:
            board = self.get_board(map_name, board_name)
        else:
            board = self.find_board_for_pixel(map_name, px, py)
        if not board:
            return None, None
        return board.pixel_to_hex(px, py)

    def hex_to_pixel(self, map_name, board_name, col, row):
        """Convert a hex ID to pixel coordinates."""
        board = self.get_board(map_name, board_name)
        if not board:
            return None, None
        return board.hex_to_pixel(col, row)

    def set_board_dimensions(self, map_name, board_name, max_cols, max_rows):
        """Override max_cols/max_rows for a board's grid (for descend calculations)."""
        board = self.get_board(map_name, board_name)
        if board and board.grid:
            board.grid.max_cols = max_cols
            board.grid.max_rows = max_rows


# ---------------------------------------------------------------------------
# Calibration utility
# ---------------------------------------------------------------------------

def calibrate_max_columns(grid, known_points, target_max=50):
    """Given known (hex_col, hex_row, pixel_x, pixel_y) calibration points,
    find the max_cols value that makes the formula match.
    """
    best_max = grid.max_cols
    best_errors = float('inf')

    for test_max in range(20, target_max + 1):
        grid.max_cols = test_max
        grid.max_rows = test_max
        errors = 0
        for c, r, px, py in known_points:
            cc, cr = grid.pixel_to_hex(px, py)
            if cc != c or cr != r:
                errors += 1
        if errors < best_errors:
            best_errors = errors
            best_max = test_max

    grid.max_cols = best_max
    grid.max_rows = best_max
    return best_max, best_errors


# ---------------------------------------------------------------------------
# CLI / test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 vassal_grid.py <module.vmod> [map_name] [board_name]")
        sys.exit(1)

    mg = ModuleGrid.from_vmod(sys.argv[1])
    print(f"Maps in module: {list(mg.maps.keys())}")
    for map_name, boards in mg.maps.items():
        print(f"\nMap: {map_name}")
        for board_name, board in boards.items():
            print(f"  Board: {board_name}")
            if board.grid:
                g = board.grid
                print(f"    dx={g.dx} dy={g.dy} origin=({g.x0},{g.y0})")
                print(f"    sideways={g.sideways} stagger={g.stagger}")
                print(f"    hOff={g.h_off} vOff={g.v_off} hDescend={g.h_descend}")
