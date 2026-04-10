#!/usr/bin/env python3
"""
VASSAL Play-By-Email / Hot-Seat Turn Manager

Manages turn-based play via save files. Three modes:
  1. PBEM: Human saves .vsav → AI processes → AI saves .vsav → email/share to human
  2. Hot-seat: Both sides play on the same machine, alternating turns via save files
  3. Watch folder: Monitor a directory for new .vsav files and auto-process AI turns

Usage:
  # Process a single turn (one-shot)
  python3 vassal_pbem.py turn --input game.vsav --output ai_response.vsav --side "Carthaginian"

  # Watch a folder for new saves (auto-process mode)
  python3 vassal_pbem.py watch --dir games/SPQR/ --side "Carthaginian" --pattern "*.vsav"

  # Generate a .vlog with logged moves (for full replay in VASSAL)
  python3 vassal_pbem.py turn --input game.vsav --output ai_turn.vlog --format vlog --side "Carthaginian"
"""

import zipfile
import io
import os
import sys
import json
import time
import random
import argparse
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Save file read/write (from vmod_analyzer.py)
# ---------------------------------------------------------------------------

def deobfuscate(raw_bytes):
    """Deobfuscate a VASSAL savedGame entry."""
    text = raw_bytes.decode('utf-8', errors='replace')
    if text.startswith('!VCSK'):
        key = int(text[5:7], 16)
        plain = []
        for i in range(7, len(text) - 1, 2):
            try:
                byte_val = int(text[i:i + 2], 16) ^ key
                plain.append(chr(byte_val))
            except ValueError:
                break
        return ''.join(plain)
    return text


def obfuscate(plaintext):
    """Obfuscate plaintext for a VASSAL savedGame entry."""
    key = random.randint(0, 255)
    result = f'!VCSK{key:02x}'
    for ch in plaintext:
        result += f'{(ord(ch) ^ key):02x}'
    return result.encode('utf-8')


def read_save(filepath):
    """Read and deobfuscate a .vsav or .vlog file. Returns the command string."""
    with zipfile.ZipFile(filepath, 'r') as zf:
        raw = zf.read('savedGame')
    return deobfuscate(raw)


def write_save(filepath, command_string, metadata=None):
    """Write an obfuscated .vsav file."""
    encrypted = obfuscate(command_string)
    with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('savedGame', encrypted)
        if metadata:
            zf.writestr('moduledata', metadata)


def read_metadata(filepath):
    """Read moduledata from a save file."""
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            if 'moduledata' in zf.namelist():
                return zf.read('moduledata').decode('utf-8', errors='replace')
    except (zipfile.BadZipFile, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

COMMAND_SEP = '\x1b'  # ESC character


def parse_commands(command_string):
    """Split a command string into individual commands."""
    return command_string.split(COMMAND_SEP)


def join_commands(commands):
    """Join individual commands back into a command string."""
    return COMMAND_SEP.join(commands)


def extract_pieces(command_string):
    """Extract all AddPiece commands from a save. Returns list of piece dicts."""
    commands = parse_commands(command_string)
    pieces = []
    for cmd in commands:
        if cmd.startswith('+/'):
            parts = cmd[2:].split('/', 2)
            if len(parts) >= 3:
                piece_id, piece_type, piece_state = parts
                # Parse BasicPiece state for position (innermost tab-separated segment)
                state_parts = piece_state.split('\t')
                bp_state = state_parts[-1] if state_parts else ""
                bp_fields = bp_state.split(';')
                pieces.append({
                    'id': piece_id,
                    'type': piece_type,
                    'state': piece_state,
                    'map': bp_fields[0] if len(bp_fields) > 0 else '',
                    'x': bp_fields[1] if len(bp_fields) > 1 else '',
                    'y': bp_fields[2] if len(bp_fields) > 2 else '',
                })
    return pieces


def get_game_state_summary(command_string):
    """Generate a human-readable summary of the game state."""
    pieces = extract_pieces(command_string)
    commands = parse_commands(command_string)

    summary = {
        'total_commands': len(commands),
        'total_pieces': len(pieces),
        'pieces_by_map': {},
        'has_log_entries': any(c.startswith('LOG\t') for c in commands),
        'log_entry_count': sum(1 for c in commands if c.startswith('LOG\t')),
    }

    for p in pieces:
        map_name = p['map'] or '(no map)'
        if map_name not in summary['pieces_by_map']:
            summary['pieces_by_map'][map_name] = 0
        summary['pieces_by_map'][map_name] += 1

    return summary


# ---------------------------------------------------------------------------
# Turn processing
# ---------------------------------------------------------------------------

def process_turn(input_path, output_path, side, output_format='vsav'):
    """
    Process a single AI turn.

    Reads the input save, extracts game state, and writes a placeholder output.
    In production, this is where Claude would analyze and generate moves.
    """
    print(f"Reading: {input_path}")
    command_string = read_save(input_path)
    metadata = read_metadata(input_path)

    summary = get_game_state_summary(command_string)
    print(f"  Commands: {summary['total_commands']}")
    print(f"  Pieces: {summary['total_pieces']}")
    for map_name, count in summary['pieces_by_map'].items():
        print(f"    {map_name}: {count} pieces")
    if summary['has_log_entries']:
        print(f"  Log entries: {summary['log_entry_count']} (this is a .vlog with replay steps)")

    # Extract pieces for analysis
    pieces = extract_pieces(command_string)

    # Write analysis output for Claude to process
    analysis_path = str(output_path) + '.analysis.json'
    analysis = {
        'input_file': str(input_path),
        'timestamp': datetime.now().isoformat(),
        'side': side,
        'summary': summary,
        'pieces': pieces[:50],  # Cap for readability; full list available
        'piece_count': len(pieces),
        'command_string_length': len(command_string),
    }

    with open(analysis_path, 'w') as f:
        json.dump(analysis, f, indent=2)
    print(f"\n  Analysis written to: {analysis_path}")
    print(f"  Pass this file to Claude for AI turn processing.")
    print(f"  Claude will generate the response commands and save to: {output_path}")

    # Also write the raw deobfuscated command string for Claude to read directly
    raw_path = str(output_path) + '.raw.txt'
    with open(raw_path, 'w') as f:
        f.write(command_string)
    print(f"  Raw commands written to: {raw_path}")

    return analysis


def watch_folder(watch_dir, side, pattern="*.vsav", poll_interval=5):
    """Watch a directory for new save files and auto-process them."""
    watch_path = Path(watch_dir)
    seen = set()

    # Initialize with existing files
    for f in watch_path.glob(pattern):
        seen.add(str(f))

    print(f"Watching {watch_dir} for new {pattern} files...")
    print(f"Playing as: {side}")
    print(f"Press Ctrl+C to stop.\n")

    try:
        while True:
            for f in watch_path.glob(pattern):
                fstr = str(f)
                if fstr not in seen:
                    seen.add(fstr)
                    print(f"\n{'='*60}")
                    print(f"New file detected: {f.name}")
                    print(f"{'='*60}")

                    # Generate output filename
                    stem = f.stem
                    output = watch_path / f"{stem}_ai_response.vsav"
                    process_turn(fstr, str(output), side)

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\nWatch stopped.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VASSAL PBEM / Hot-Seat Turn Manager")
    subparsers = parser.add_subparsers(dest='mode', help='Operating mode')

    # Turn mode: process a single turn
    turn_parser = subparsers.add_parser('turn', help='Process a single AI turn')
    turn_parser.add_argument('--input', required=True, help='Input .vsav or .vlog file')
    turn_parser.add_argument('--output', required=True, help='Output file path')
    turn_parser.add_argument('--side', required=True, help='Side the AI is playing')
    turn_parser.add_argument('--format', choices=['vsav', 'vlog'], default='vsav',
                             help='Output format (default: vsav)')

    # Watch mode: monitor folder for new saves
    watch_parser = subparsers.add_parser('watch', help='Watch folder for new save files')
    watch_parser.add_argument('--dir', required=True, help='Directory to watch')
    watch_parser.add_argument('--side', required=True, help='Side the AI is playing')
    watch_parser.add_argument('--pattern', default='*.vsav', help='File pattern (default: *.vsav)')
    watch_parser.add_argument('--interval', type=int, default=5, help='Poll interval in seconds')

    # Info mode: just analyze a save file
    info_parser = subparsers.add_parser('info', help='Analyze a save file without processing')
    info_parser.add_argument('file', help='Save file to analyze')

    args = parser.parse_args()

    if args.mode == 'turn':
        process_turn(args.input, args.output, args.side, args.format)
    elif args.mode == 'watch':
        watch_folder(args.dir, args.side, args.pattern, args.interval)
    elif args.mode == 'info':
        cmd_string = read_save(args.file)
        summary = get_game_state_summary(cmd_string)
        print(json.dumps(summary, indent=2))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
