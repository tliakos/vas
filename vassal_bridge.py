#!/usr/bin/env python3
"""
VASSAL Server Bridge
Connects to a VASSAL game server as a player, receives/sends game commands,
and acts as the interface between the VASSAL server and the AI agent.

Usage:
  python3 vassal_bridge.py --module "MyGame" --player "Claude_AI" --room "AI Game"
  python3 vassal_bridge.py --module "MyGame" --player "Claude_AI" --host localhost --port 5050
"""

import socket
import threading
import time
import sys
import os
import re
import zlib
import base64
import argparse
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# SequenceEncoder (Python port of VASSAL.tools.SequenceEncoder)
# ---------------------------------------------------------------------------

class SequenceEncoder:
    """Encode multiple fields into a single string with a delimiter, escaping as needed."""

    def __init__(self, delim, initial=None):
        self.delim = delim
        self.parts = []
        if initial is not None:
            self.parts.append(self._escape(str(initial)))

    def append(self, val):
        self.parts.append(self._escape(str(val)))
        return self

    def _escape(self, s):
        s = s.replace('\\', '\\\\')
        s = s.replace(self.delim, '\\' + self.delim)
        return s

    def value(self):
        return self.delim.join(self.parts)


class SequenceDecoder:
    """Decode a SequenceEncoder-encoded string."""

    def __init__(self, s, delim):
        self.delim = delim
        self.tokens = self._split(s)
        self.pos = 0

    def _split(self, s):
        parts = []
        current = []
        i = 0
        while i < len(s):
            if s[i] == '\\' and i + 1 < len(s):
                current.append(s[i + 1])
                i += 2
            elif s[i] == self.delim:
                parts.append(''.join(current))
                current = []
                i += 1
            else:
                current.append(s[i])
                i += 1
        parts.append(''.join(current))
        return parts

    def has_more(self):
        return self.pos < len(self.tokens)

    def next_token(self, default=""):
        if self.pos < len(self.tokens):
            val = self.tokens[self.pos]
            self.pos += 1
            return val
        return default


# ---------------------------------------------------------------------------
# Protocol (Python port of VASSAL.chat.node.Protocol)
# ---------------------------------------------------------------------------

REGISTER = "REG\t"
REG_REQUEST = "REG_REQUEST\t"
JOIN = "JOIN\t"
FORWARD = "FWD\t"
STATS = "STATS\t"
LIST = "LIST\t"
NODE_INFO = "NODE_INFO\t"
ROOM_INFO = "ROOM_INFO\t"
LOGIN = "LOGIN\t"
KICK = "KICK\t"
SIGN_OFF = "!BYE"
ZIP_HEADER = "!ZIP!"
COMPRESSION_LIMIT = 1000


def encode_register(player_id, path, info):
    se = SequenceEncoder('\t', player_id)
    se.append(path)
    se.append(info)
    return REGISTER + se.value()


def encode_login(username):
    return LOGIN + username


def encode_join(room_path, password=None):
    if password:
        return JOIN + room_path + "\t" + password
    return JOIN + room_path


def encode_forward(recipient_path, message):
    se = SequenceEncoder('\t', recipient_path)
    se.append(message)
    return FORWARD + se.value()


def decode_forward(cmd):
    """Decode a FWD message -> (recipient_path, message)"""
    if cmd.startswith(FORWARD):
        sd = SequenceDecoder(cmd[len(FORWARD):], '\t')
        path = sd.next_token()
        msg = sd.next_token()
        return path, msg
    return None, None


def compress_message(msg):
    """Compress a message if it exceeds the compression limit."""
    if len(msg) > COMPRESSION_LIMIT:
        compressed = zlib.compress(msg.encode('utf-8'))
        return ZIP_HEADER + base64.b64encode(compressed).decode('ascii')
    return msg


def decompress_message(msg):
    """Decompress a message if it has the ZIP header."""
    if msg.startswith(ZIP_HEADER):
        compressed = base64.b64decode(msg[len(ZIP_HEADER):])
        return zlib.decompress(compressed).decode('utf-8')
    return msg


# ---------------------------------------------------------------------------
# Player Info Encoding
# ---------------------------------------------------------------------------

def encode_player_info(name, module_version="", looking=True, away=False, profile=""):
    """Encode player properties in the format VASSAL expects."""
    # VASSAL uses java.util.Properties encoding
    lines = []
    lines.append(f"name={name}")
    lines.append(f"looking={'true' if looking else 'false'}")
    lines.append(f"away={'true' if away else 'false'}")
    if profile:
        lines.append(f"profile={profile}")
    if module_version:
        lines.append(f"moduleVersion={module_version}")
    return "\\n".join(lines)


# ---------------------------------------------------------------------------
# VASSAL Bridge Client
# ---------------------------------------------------------------------------

class VassalBridge:
    """
    Connects to a VASSAL server and acts as a game player.
    Receives game commands from the opponent and forwards them to a callback.
    Sends game commands from the AI back to the server.
    """

    def __init__(self, host, port, module_name, player_name, room_name,
                 on_game_command=None, on_chat=None, on_status=None):
        self.host = host
        self.port = port
        self.module_name = module_name
        self.player_name = player_name
        self.room_name = room_name
        self.player_id = f"{player_name}.{int(time.time() * 1000)}"

        # Callbacks
        self.on_game_command = on_game_command or (lambda cmd: None)
        self.on_chat = on_chat or (lambda msg: None)
        self.on_status = on_status or (lambda msg: None)

        self.sock = None
        self.reader_thread = None
        self.running = False
        self.connected = False

        # Logging
        self.log_file = None
        self.command_buffer = []

    def connect(self):
        """Connect to the VASSAL server."""
        self.on_status(f"Connecting to {self.host}:{self.port}...")
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(1.0)  # For clean shutdown
            self.running = True
            self.connected = True

            # Start reader thread
            self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.reader_thread.start()

            # Register with server
            module_path = f"{self.module_name}/{self.room_name}"
            player_info = encode_player_info(self.player_name)
            self._send(encode_register(self.player_id, module_path, player_info))
            self._send(encode_login(self.player_name))

            self.on_status(f"Connected as '{self.player_name}' in room '{self.room_name}'")
            return True

        except (socket.error, OSError) as e:
            self.on_status(f"Connection failed: {e}")
            self.connected = False
            return False

    def join_room(self, room_name, password=None):
        """Join a specific room."""
        self.room_name = room_name
        path = f"{self.module_name}/{room_name}"
        self._send(encode_join(path, password))
        self.on_status(f"Joined room: {room_name}")

    def send_game_command(self, command_string):
        """Send a game command to other players in the room."""
        msg = compress_message(command_string)
        path = SequenceEncoder('/', self.module_name) \
            .append(self.room_name) \
            .append(f"~{self.player_id}") \
            .value()
        self._send(encode_forward(path, msg))
        self.command_buffer.append({
            "direction": "sent",
            "timestamp": datetime.now().isoformat(),
            "command": command_string[:200] + ("..." if len(command_string) > 200 else ""),
        })

    def send_chat(self, message):
        """Send a chat message (appears in the VASSAL chat window)."""
        # Chat messages are sent as encoded Commands through the same channel
        # The Chatter component handles them
        chat_cmd = f"CHAT{message}"
        self.send_game_command(chat_cmd)

    def disconnect(self):
        """Disconnect from the server."""
        self.running = False
        if self.sock:
            try:
                self._send(SIGN_OFF)
                self.sock.close()
            except (socket.error, OSError):
                pass
        self.connected = False
        self.on_status("Disconnected")

    def _send(self, line):
        """Send a line to the server."""
        if self.sock and self.connected:
            try:
                self.sock.sendall((line + "\n").encode('utf-8'))
            except (socket.error, OSError) as e:
                self.on_status(f"Send error: {e}")
                self.connected = False

    def _read_loop(self):
        """Background thread: read lines from the server."""
        buffer = ""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    self.on_status("Server closed connection")
                    self.connected = False
                    break
                buffer += data.decode('utf-8', errors='replace')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self._handle_message(line)
            except socket.timeout:
                continue
            except (socket.error, OSError) as e:
                if self.running:
                    self.on_status(f"Read error: {e}")
                    self.connected = False
                break

    def _handle_message(self, line):
        """Process an incoming server message."""
        if line.startswith(FORWARD):
            path, msg = decode_forward(line)
            if msg:
                msg = decompress_message(msg)
                self.command_buffer.append({
                    "direction": "received",
                    "timestamp": datetime.now().isoformat(),
                    "command": msg[:200] + ("..." if len(msg) > 200 else ""),
                })
                self.on_game_command(msg)

        elif line.startswith(LIST):
            self.on_status(f"Player list updated")

        elif line.startswith(NODE_INFO):
            pass  # Node updates

        elif line.startswith(ROOM_INFO):
            self.on_status(f"Room info updated")

        elif line.startswith(REG_REQUEST):
            # Server wants us to re-register
            module_path = f"{self.module_name}/{self.room_name}"
            player_info = encode_player_info(self.player_name)
            self._send(encode_register(self.player_id, module_path, player_info))

    def get_command_log(self):
        """Return the buffered command log."""
        return list(self.command_buffer)

    def clear_command_log(self):
        """Clear the command buffer."""
        self.command_buffer.clear()


# ---------------------------------------------------------------------------
# Standalone mode: interactive bridge
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VASSAL Server Bridge for AI Play")
    parser.add_argument("--host", default="game.vassalengine.org",
                        help="VASSAL server host (default: game.vassalengine.org)")
    parser.add_argument("--port", type=int, default=5050,
                        help="VASSAL server port (default: 5050)")
    parser.add_argument("--module", required=True,
                        help="Module name (must match the VASSAL module)")
    parser.add_argument("--player", default="Claude_AI",
                        help="Player name (default: Claude_AI)")
    parser.add_argument("--room", default="Main Room",
                        help="Room to join (default: 'Main Room')")
    parser.add_argument("--log", default=None,
                        help="Log file for commands (optional)")
    parser.add_argument("--listen-only", action="store_true",
                        help="Listen mode: only receive and log commands, don't send")
    args = parser.parse_args()

    received_commands = []

    def on_game_command(cmd):
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Truncate for display
        display = cmd[:120] + ("..." if len(cmd) > 120 else "")
        print(f"  [{timestamp}] GAME CMD: {display}")
        received_commands.append(cmd)
        if args.log:
            with open(args.log, 'a') as f:
                f.write(json.dumps({"time": timestamp, "cmd": cmd}) + "\n")

    def on_status(msg):
        print(f"  [STATUS] {msg}")

    bridge = VassalBridge(
        host=args.host,
        port=args.port,
        module_name=args.module,
        player_name=args.player,
        room_name=args.room,
        on_game_command=on_game_command,
        on_status=on_status,
    )

    print(f"VASSAL Bridge v1.0")
    print(f"  Module: {args.module}")
    print(f"  Player: {args.player}")
    print(f"  Server: {args.host}:{args.port}")
    print(f"  Room:   {args.room}")
    print()

    if not bridge.connect():
        print("Failed to connect. Exiting.")
        sys.exit(1)

    print()
    print("Bridge is running. Commands:")
    print("  /join <room>     -- Join a room")
    print("  /chat <message>  -- Send a chat message")
    print("  /log             -- Show received command count")
    print("  /dump            -- Dump last received command")
    print("  /quit            -- Disconnect and exit")
    print()

    try:
        while bridge.connected:
            try:
                line = input("> ").strip()
            except EOFError:
                break

            if not line:
                continue

            if line.startswith("/quit"):
                break
            elif line.startswith("/join "):
                room = line[6:].strip()
                bridge.join_room(room)
            elif line.startswith("/chat "):
                msg = line[6:].strip()
                bridge.send_chat(msg)
            elif line == "/log":
                print(f"  Received {len(received_commands)} commands")
            elif line == "/dump":
                if received_commands:
                    print(f"  Last command ({len(received_commands[-1])} chars):")
                    print(f"  {received_commands[-1][:500]}")
                else:
                    print("  No commands received yet")
            else:
                print(f"  Unknown command: {line}")

    except KeyboardInterrupt:
        print("\nInterrupted")

    bridge.disconnect()
    print("Bridge stopped.")


if __name__ == "__main__":
    main()
