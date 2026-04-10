#!/usr/bin/env python3
"""
VASSAL Move Generator
Reads a .vsav or .vlog, reconstructs the current game state,
applies AI moves, and writes a new .vsav loadable by VASSAL.
"""

import zipfile
import io
import re
import sys
import os
import random
import json
from collections import OrderedDict

# ---------------------------------------------------------------------------
# Obfuscation
# ---------------------------------------------------------------------------

def deobfuscate(raw_bytes):
    text = raw_bytes.decode('utf-8', errors='replace')
    if text.startswith('!VCSK'):
        key = int(text[5:7], 16)
        plain = []
        for i in range(7, len(text) - 1, 2):
            try:
                plain.append(chr(int(text[i:i+2], 16) ^ key))
            except ValueError:
                break
        return ''.join(plain)
    return text


def obfuscate(plaintext):
    key = random.randint(0, 255)
    result = f'!VCSK{key:02x}'
    for ch in plaintext:
        result += f'{(ord(ch) ^ key):02x}'
    return result.encode('utf-8')


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMMAND_SEP = '\x1b'  # ESC
PARAM_SEP = '/'


# ---------------------------------------------------------------------------
# Read save/log files
# ---------------------------------------------------------------------------

def read_save_raw(filepath):
    """Read and deobfuscate a .vsav or .vlog file."""
    with zipfile.ZipFile(filepath, 'r') as zf:
        raw = zf.read('savedGame')
    return deobfuscate(raw)


def read_metadata(filepath):
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            if 'moduledata' in zf.namelist():
                return zf.read('moduledata').decode('utf-8', errors='replace')
    except:
        pass
    return None


def read_all_zip_entries(filepath):
    """Read all non-savedGame entries from a save file (moduledata, savedata, etc.)."""
    entries = {}
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            for name in zf.namelist():
                if name != 'savedGame':
                    entries[name] = zf.read(name)
    except:
        pass
    return entries


def make_savedata(vassal_version="3.7.20"):
    """Generate a savedata XML entry."""
    import time
    timestamp = int(time.time() * 1000)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<data version="1">
  <version>2.9_alt</version>
  <extra1/>
  <extra2/>
  <VassalVersion>{vassal_version}</VassalVersion>
  <dateSaved>{timestamp}</dateSaved>
  <description/>
</data>
'''.encode('utf-8')


# ---------------------------------------------------------------------------
# Game State Reconstruction
# ---------------------------------------------------------------------------

class GameState:
    """Reconstructs and holds the full game state from a save or log file."""

    def __init__(self):
        self.pieces = OrderedDict()       # pieceId -> (type_string, state_string)
        self.other_commands = []           # non-piece commands (setup, restore, etc.)
        self.log_entries = []              # LOG commands from vlogs
        self.pre_commands = []             # commands before first AddPiece
        self.post_commands = []            # commands after last AddPiece (before logs)

    def load_from_file(self, filepath):
        """Load and reconstruct game state from a .vsav or .vlog."""
        cmd_str = read_save_raw(filepath)
        all_cmds = cmd_str.split(COMMAND_SEP)

        # Separate: initial state commands vs LOG entries
        state_cmds = []
        in_log = False
        for cmd in all_cmds:
            if cmd.startswith('LOG\t'):
                in_log = True
                self.log_entries.append(cmd)
            else:
                if in_log:
                    # Commands after log entries (rare, but handle)
                    self.log_entries.append(cmd)
                else:
                    state_cmds.append(cmd)

        # Parse initial state: extract AddPiece commands
        found_first_add = False
        found_last_add = False
        for cmd in state_cmds:
            if cmd.startswith('+/'):
                found_first_add = True
                # Parse AddPiece: +/id/type/state
                rest = cmd[2:]
                parts = rest.split('/', 2)
                if len(parts) >= 3:
                    pid, ptype, pstate = parts[0], parts[1], parts[2]
                    self.pieces[pid] = [ptype, pstate]
            else:
                if not found_first_add:
                    self.pre_commands.append(cmd)
                else:
                    self.post_commands.append(cmd)

        # Apply LOG entries to reconstruct current state
        for log_cmd in self.log_entries:
            if not log_cmd.startswith('LOG\t'):
                continue
            inner = log_cmd[4:]
            # Each log entry may contain multiple sub-commands separated by COMMAND_SEP
            # But since we already split on COMMAND_SEP, each log_cmd is a single LOG\t entry
            # The inner content is a single encoded command
            self._apply_command(inner)

    def _apply_command(self, cmd):
        """Apply a single command to the game state."""
        if cmd.startswith('+/'):
            # AddPiece
            rest = cmd[2:]
            parts = rest.split('/', 2)
            if len(parts) >= 3:
                self.pieces[parts[0]] = [parts[1], parts[2]]

        elif cmd.startswith('-/'):
            # RemovePiece
            pid = cmd[2:]
            if pid in self.pieces:
                del self.pieces[pid]

        elif cmd.startswith('D/'):
            # ChangePiece: D/id/newState/oldState
            rest = cmd[2:]
            parts = rest.split('/', 2)
            if len(parts) >= 2 and parts[0] in self.pieces:
                self.pieces[parts[0]][1] = parts[1]

        elif cmd.startswith('M/'):
            # MovePiece: M/id/newMapId/newX/newY/...
            rest = cmd[2:]
            parts = rest.split('/')
            if len(parts) >= 4 and parts[0] in self.pieces:
                pid = parts[0]
                new_map = parts[1] if parts[1] != 'null' else ''
                try:
                    new_x = int(parts[2])
                    new_y = int(parts[3])
                    self._update_piece_position(pid, new_map, new_x, new_y)
                except (ValueError, IndexError):
                    pass

    def _update_piece_position(self, pid, new_map, new_x, new_y):
        """Update a piece's position in its state string."""
        if pid not in self.pieces:
            return
        ptype, pstate = self.pieces[pid]

        # State is tab-separated, matching the type's decorator chain
        # The BasicPiece state (innermost) contains: mapName;x;y;gpId;...
        state_parts = pstate.split('\t')
        if not state_parts:
            return

        # Find the segment that contains coordinates
        # It's typically the last meaningful segment with map;x;y pattern
        for i in range(len(state_parts) - 1, -1, -1):
            fields = state_parts[i].split(';')
            if len(fields) >= 3:
                try:
                    old_x = int(fields[1])
                    old_y = int(fields[2])
                    # Found the position segment -- update it
                    if new_map:
                        fields[0] = new_map
                    fields[1] = str(new_x)
                    fields[2] = str(new_y)
                    state_parts[i] = ';'.join(fields)
                    self.pieces[pid][1] = '\t'.join(state_parts)
                    return
                except (ValueError, IndexError):
                    continue

    def get_piece_position(self, pid):
        """Get a piece's current map, x, y coordinates."""
        if pid not in self.pieces:
            return None, 0, 0
        ptype, pstate = self.pieces[pid]
        state_parts = pstate.split('\t')
        for i in range(len(state_parts) - 1, -1, -1):
            fields = state_parts[i].split(';')
            if len(fields) >= 3:
                try:
                    return fields[0], int(fields[1]), int(fields[2])
                except (ValueError, IndexError):
                    continue
        return None, 0, 0

    def move_piece(self, pid, new_hex_col, new_hex_row, grid):
        """Move a piece to a new hex position."""
        new_x, new_y = grid.hex_to_pixel(new_hex_col, new_hex_row)
        map_name, old_x, old_y = self.get_piece_position(pid)
        if map_name:
            self._update_piece_position(pid, map_name, new_x, new_y)
            return True
        return False

    def find_pieces_at_hex(self, hex_col, hex_row, grid):
        """Find all pieces at a given hex."""
        results = []
        for pid, (ptype, pstate) in self.pieces.items():
            map_name, x, y = self.get_piece_position(pid)
            if map_name and x > 0 and y > 0:
                pc, pr = grid.pixel_to_hex(x, y)
                if pc == hex_col and pr == hex_row:
                    results.append(pid)
        return results

    def find_pieces_by_image(self, image_pattern):
        """Find pieces whose type contains an image matching the pattern."""
        results = []
        for pid, (ptype, pstate) in self.pieces.items():
            if image_pattern in ptype:
                results.append(pid)
        return results

    def serialize(self):
        """Serialize the current game state to a command string."""
        parts = []
        # Pre-commands (begin_save, version checks, etc.)
        parts.extend(self.pre_commands)

        # All pieces as AddPiece commands
        for pid, (ptype, pstate) in self.pieces.items():
            parts.append(f'+/{pid}/{ptype}/{pstate}')

        # Post-commands (end_save, etc.)
        parts.extend(self.post_commands)

        return COMMAND_SEP.join(parts)

    def write_vsav(self, filepath, extra_entries=None):
        """Write the current state as a .vsav file.

        extra_entries: dict of {name: bytes} for moduledata, savedata, etc.
                       If None, generates minimal required entries.
        """
        cmd_str = self.serialize()
        encrypted = obfuscate(cmd_str)

        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('savedGame', encrypted)
            if extra_entries:
                for name, data in extra_entries.items():
                    if isinstance(data, str):
                        data = data.encode('utf-8')
                    zf.writestr(name, data)
            else:
                # Generate minimal required entries
                zf.writestr('savedata', make_savedata())

        return len(cmd_str)

    def write_vlog(self, filepath, move_log, player_name="Claude_AI", extra_entries=None):
        """
        Write the current state as a .vlog file with logged moves.

        move_log is a list of dicts, each with:
          - 'chat': a narration message (optional)
          - 'piece_id': piece to move
          - 'from_hex': source hex
          - 'to_hex': destination hex
          - 'name': unit description for the chat log
          - 'rule': rule reference
          - 'reasoning': why this move
        """
        # The .vlog structure:
        #   [initial state] + [LOG entries]
        # Initial state = the state BEFORE our moves (the state we loaded)
        # LOG entries = our moves as step-through commands

        # First, serialize the initial state (before any moves from this batch)
        initial_state = self.serialize()

        # Build LOG entries
        log_entries = []
        grid = HexGrid()

        for move in move_log:
            # Chat narration
            if 'chat' in move and move['chat']:
                msg = move['chat']
                log_entries.append(f"LOG\tCHAT<{player_name}> - {msg}")

            # Actual piece move
            if 'piece_id' in move and 'to_hex' in move:
                pid = move['piece_id']
                to_col, to_row = grid.parse_hex_id(move['to_hex'])
                new_x, new_y = grid.hex_to_pixel(to_col, to_row)

                map_name, old_x, old_y = self.get_piece_position(pid)
                if not map_name:
                    continue

                old_col, old_row = grid.pixel_to_hex(old_x, old_y)
                from_hex = grid.hex_id(old_col, old_row)
                to_hex = move['to_hex']

                unit_name = move.get('name', pid[:10])

                # Build the LOG entry with both the readable message and the command
                move_cmd = (
                    f"M/{pid}/{map_name}/{new_x}/{new_y}/null"
                    f"/{map_name}/{old_x}/{old_y}/null/{player_name}"
                )
                chat_text = f"CHAT* {player_name} moved {unit_name} from {from_hex} to {to_hex}"

                # Combine chat + move command in one LOG step
                log_entry = f"LOG\t{chat_text}{COMMAND_SEP}{move_cmd}"
                log_entries.append(log_entry)

                # Apply the move to our state so subsequent moves see updated positions
                self._update_piece_position(pid, map_name, new_x, new_y)

        # Assemble the full .vlog: initial state + log entries
        full_cmd = initial_state + COMMAND_SEP + COMMAND_SEP.join(log_entries)
        encrypted = obfuscate(full_cmd)

        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('savedGame', encrypted)
            if extra_entries:
                for name, data in extra_entries.items():
                    if isinstance(data, str):
                        data = data.encode('utf-8')
                    zf.writestr(name, data)
            else:
                zf.writestr('savedata', make_savedata())

        return len(log_entries)


# ---------------------------------------------------------------------------
# Grid System
# ---------------------------------------------------------------------------

class HexGrid:
    """Hex grid coordinate conversion for SPQR-style maps."""

    def __init__(self, dx=110.5, dy=96.0, x0=56, y0=18):
        self.dx = dx
        self.dy = dy
        self.x0 = x0
        self.y0 = y0

    def pixel_to_hex(self, px, py):
        col = round((px - self.x0) / self.dx)
        row = round((py - self.y0) / self.dy)
        return col, row

    def hex_to_pixel(self, col, row):
        x = round(self.x0 + col * self.dx)
        y = round(self.y0 + row * self.dy)
        return x, y

    def hex_id(self, col, row):
        return f'{col:02d}{row:02d}'

    def parse_hex_id(self, hex_str):
        col = int(hex_str[:2])
        row = int(hex_str[2:])
        return col, row


# ---------------------------------------------------------------------------
# Move list
# ---------------------------------------------------------------------------

def apply_moves(state, grid, moves):
    """
    Apply a list of moves to the game state.
    Each move is a dict: {piece_id: str, to_hex: str} or {from_hex: str, to_hex: str, image_pattern: str}
    """
    results = []
    for move in moves:
        if 'piece_id' in move:
            pid = move['piece_id']
            to_col, to_row = grid.parse_hex_id(move['to_hex'])
            old_map, old_x, old_y = state.get_piece_position(pid)
            old_col, old_row = grid.pixel_to_hex(old_x, old_y)
            success = state.move_piece(pid, to_col, to_row, grid)
            results.append({
                'piece_id': pid,
                'from_hex': grid.hex_id(old_col, old_row),
                'to_hex': move['to_hex'],
                'success': success,
            })
        elif 'from_hex' in move and 'image_pattern' in move:
            # Find piece by hex and image
            from_col, from_row = grid.parse_hex_id(move['from_hex'])
            pids = state.find_pieces_at_hex(from_col, from_row, grid)
            matched = None
            for pid in pids:
                ptype = state.pieces[pid][0]
                if move['image_pattern'] in ptype:
                    matched = pid
                    break
            if matched:
                to_col, to_row = grid.parse_hex_id(move['to_hex'])
                success = state.move_piece(matched, to_col, to_row, grid)
                results.append({
                    'piece_id': matched,
                    'unit': move.get('name', move['image_pattern']),
                    'from_hex': move['from_hex'],
                    'to_hex': move['to_hex'],
                    'success': success,
                })
            else:
                results.append({
                    'unit': move.get('name', move['image_pattern']),
                    'from_hex': move['from_hex'],
                    'to_hex': move['to_hex'],
                    'success': False,
                    'error': f"No piece matching '{move['image_pattern']}' found at hex {move['from_hex']}"
                })
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 vassal_move.py <input.vsav|vlog> <output.vsav> [moves.json]")
        print()
        print("If moves.json is not provided, just reconstructs and re-saves the state.")
        print()
        print("moves.json format:")
        print('  [')
        print('    {"from_hex": "2916", "to_hex": "2817", "image_pattern": "LG-Has-V", "name": "V Hastati"},')
        print('    {"piece_id": "1234567890", "to_hex": "3015"},')
        print('  ]')
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    moves_path = sys.argv[3] if len(sys.argv) > 3 else None

    # Load game state
    print(f"Loading: {input_path}")
    state = GameState()
    state.load_from_file(input_path)
    metadata = read_metadata(input_path)

    print(f"  Pieces: {len(state.pieces)}")
    print(f"  Pre-commands: {len(state.pre_commands)}")
    print(f"  Post-commands: {len(state.post_commands)}")
    print(f"  Log entries applied: {len(state.log_entries)}")

    grid = HexGrid()

    # Apply moves if provided
    if moves_path:
        with open(moves_path) as f:
            moves = json.load(f)
        print(f"\nApplying {len(moves)} moves...")
        results = apply_moves(state, grid, moves)
        for r in results:
            status = "OK" if r['success'] else f"FAILED: {r.get('error', 'unknown')}"
            name = r.get('unit', r.get('piece_id', '?'))
            print(f"  {name}: {r['from_hex']} -> {r['to_hex']} [{status}]")

    # Write output
    print(f"\nWriting: {output_path}")
    size = state.write_vsav(output_path, metadata)
    print(f"  Command string: {size:,} chars")
    print("Done. Load this file in VASSAL to see the result.")


if __name__ == '__main__':
    main()
