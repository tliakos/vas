#!/usr/bin/env python3
"""
VASSAL .vmod Module Analyzer
Unpacks and analyzes any VASSAL module file, producing a structured report
of all game components: pieces, maps, grids, prototypes, scenarios, dice,
global properties, turn structure, and player sides.
"""

import zipfile
import xml.etree.ElementTree as ET
import json
import sys
import os
import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Trait ID prefix -> human-readable name
# ---------------------------------------------------------------------------
TRAIT_IDS = {
    "piece;":        "BasicPiece",
    "basicName;":    "BasicName",
    "emb2;":         "Embellishment",
    "emb;":          "Embellishment(old)",
    "obs;":          "Mask/Obscurable",
    "hide;":         "Invisible/Hideable",
    "label;":        "TextLabel",
    "rotate;":       "FreeRotator",
    "pivot;":        "Pivot",
    "mark;":         "Marker",
    "PROP;":         "DynamicProperty",
    "calcProp;":     "CalculatedProperty",
    "prototype;":    "UsePrototype",
    "immob;":        "Immobilized",
    "delete;":       "Delete",
    "clone;":        "Clone",
    "replace;":      "Replace",
    "placemark;":    "PlaceMarker",
    "sendto;":       "SendToLocation",
    "return;":       "ReturnToDeck",
    "globalkey;":    "GlobalKeyCommand",
    "macro;":        "TriggerAction",
    "report;":       "ReportState",
    "markmoved;":    "MovementMarkable",
    "footprint;":    "Footprint",
    "restrict;":     "Restricted",
    "hideCmd;":      "RestrictCommands",
    "setprop;":      "SetGlobalProperty",
    "setpieceprop;": "SetPieceProperty",
    "playSound;":    "PlaySound",
    "button;":       "ActionButton",
    "globalhotkey;": "GlobalHotKey",
    "submenu;":      "SubMenu",
    "menuSeparator;":"MenuSeparator",
    "translate;":    "Translate",
    "AreaOfEffect;": "AreaOfEffect",
    "nonRect2;":     "NonRectangular",
    "nonRect;":      "NonRectangular(old)",
    "table;":        "TableInfo",
    "propertysheet;":"PropertySheet",
    "mat;":          "Mat",
    "matPiece;":     "MatCargo",
    "border;":       "BorderOutline",
    "attach;":       "Attachment",
    "locCommand;":   "MultiLocationCommand",
    "locmsg;":       "TranslatableMessage",
    "deselect;":     "Deselect",
    "cmt;":          "Comment",
}


def tag_short(tag):
    """Strip the full Java class path to just the class name."""
    return tag.rsplit(".", 1)[-1] if "." in tag else tag


def parse_trait_string(trait_str):
    """Parse a single trait definition string into (trait_id, fields)."""
    idx = trait_str.find(";")
    if idx < 0:
        return trait_str, {}
    prefix = trait_str[:idx + 1]
    name = TRAIT_IDS.get(prefix, prefix)
    rest = trait_str[idx + 1:]
    return name, rest


def parse_piece_type(type_string):
    """
    Parse a full piece type definition string (tab-separated decorator chain).
    Returns list of parsed traits from outermost to innermost.
    """
    if not type_string or not type_string.strip():
        return []
    layers = type_string.strip().split("\t")
    traits = []
    for layer in layers:
        layer = layer.strip()
        if not layer:
            continue
        name, fields = parse_trait_string(layer)
        traits.append({"trait": name, "raw": layer, "fields": fields})
    return traits


def extract_markers(traits):
    """Pull out Marker property keys from a parsed trait list.

    Marker type format: mark;key1,key2,...
    The values are in the state string (not the type string), so from
    a buildFile.xml type definition we can only extract the property names.
    Values become visible when parsing a save file's state strings.
    """
    markers = {}
    for t in traits:
        if t["trait"] == "Marker" and t["fields"]:
            # Fields after 'mark;' are comma-separated key names
            # Use SequenceEncoder-aware splitting (backslash escapes commas)
            keys = _se_split(t["fields"], ",")
            for key in keys:
                if key:
                    markers[key] = "(defined)"
    return markers


def _se_split(s, sep):
    """Split a string respecting SequenceEncoder escaping (backslash + sep)."""
    parts = []
    current = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            current.append(s[i + 1])
            i += 2
        elif s[i] == sep:
            parts.append(''.join(current))
            current = []
            i += 1
        else:
            current.append(s[i])
            i += 1
    parts.append(''.join(current))
    return parts


def extract_prototypes(traits):
    """Pull out UsePrototype references."""
    protos = []
    for t in traits:
        if t["trait"] == "UsePrototype" and t["fields"]:
            name = t["fields"].split(";")[0]
            if name:
                protos.append(name)
    return protos


def extract_dynamic_props(traits):
    """Pull out DynamicProperty names.

    DynamicProperty type format after PROP; prefix:
    key;constraints;keyCommandList;description
    (semicolon-separated via SequenceEncoder)
    """
    props = []
    for t in traits:
        if t["trait"] == "DynamicProperty" and t["fields"]:
            # First field after 'PROP;' is the property key name
            parts = t["fields"].split(";")
            if parts and parts[0]:
                props.append(parts[0])
    return props


def extract_basic_piece_info(traits):
    """Extract the BasicPiece image and name.

    BasicPiece type format: piece;cloneKey;deleteKey;imageName;commonName
    (semicolon-separated via SequenceEncoder)
    cloneKey and deleteKey are single chars (often \\0).
    """
    for t in traits:
        if t["trait"] == "BasicPiece" and t["fields"]:
            parts = t["fields"].split(";")
            info = {}
            # Standard format: cloneKey;deleteKey;imageName;commonName
            if len(parts) >= 4:
                info["image"] = parts[2] if parts[2] else None
                info["name"] = parts[3] if parts[3] else None
            elif len(parts) >= 3:
                info["image"] = parts[1] if parts[1] else None
                info["name"] = parts[2] if parts[2] else None
            return info
    return {}


def extract_basic_name(traits):
    """Extract BasicName trait value."""
    for t in traits:
        if t["trait"] == "BasicName" and t["fields"]:
            parts = t["fields"].split(";")
            if parts:
                return parts[0]
    return None


# ---------------------------------------------------------------------------
# XML analysis
# ---------------------------------------------------------------------------

def analyze_module_metadata(zf):
    """Parse the moduledata file."""
    meta = {}
    for name in ["moduledata"]:
        if name in zf.namelist():
            data = zf.read(name).decode("utf-8", errors="replace")
            try:
                root = ET.fromstring(data)
                for child in root:
                    meta[child.tag] = child.text
            except ET.ParseError:
                meta["_raw"] = data[:500]
    return meta


def analyze_buildfile(zf):
    """Parse buildFile.xml and extract all components."""
    bf_name = None
    for candidate in ["buildFile.xml", "buildFile"]:
        if candidate in zf.namelist():
            bf_name = candidate
            break
    if not bf_name:
        return None

    data = zf.read(bf_name).decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        return {"error": f"Failed to parse buildFile: {e}"}

    result = {
        "module_attrs": dict(root.attrib),
        "player_sides": [],
        "maps": [],
        "prototypes": [],
        "piece_palettes": [],
        "predefined_setups": [],
        "dice": [],
        "global_properties": [],
        "turn_tracker": [],
        "global_key_commands": [],
        "startup_key_commands": [],
        "other_components": [],
    }

    _walk_buildfile(root, result, depth=0)
    return result


def _walk_buildfile(element, result, depth):
    """Recursively walk the buildFile XML tree and extract components."""
    tag = tag_short(element.tag)

    # --- Player Roster ---
    if tag == "PlayerRoster":
        for entry in element:
            side_tag = tag_short(entry.tag)
            if side_tag == "entry":
                side_el = entry.find("side")
                if side_el is not None and side_el.text:
                    result["player_sides"].append(side_el.text)
            # Some modules use direct side attributes
            if "side" in entry.attrib:
                result["player_sides"].append(entry.attrib["side"])

    # --- Maps ---
    elif tag in ("Map", "PrivateMap", "PlayerHand"):
        map_info = {
            "type": tag,
            "name": element.attrib.get("mapName", element.attrib.get("name", "unnamed")),
            "attributes": dict(element.attrib),
            "boards": [],
            "grids": [],
            "zones": [],
            "setup_stacks": [],
        }
        _extract_map_contents(element, map_info)
        result["maps"].append(map_info)

    # --- Prototypes ---
    elif tag == "PrototypeDefinition":
        proto_name = element.attrib.get("name", "unnamed")
        description = element.attrib.get("description", "")
        type_str = (element.text or "").strip()
        traits = parse_piece_type(type_str)
        result["prototypes"].append({
            "name": proto_name,
            "description": description,
            "trait_count": len(traits),
            "traits": [t["trait"] for t in traits],
            "markers": extract_markers(traits),
            "uses_prototypes": extract_prototypes(traits),
            "dynamic_properties": extract_dynamic_props(traits),
        })

    # --- Piece Palettes ---
    elif tag == "PieceWindow":
        palette = {
            "name": element.attrib.get("name", element.attrib.get("entryName", "Pieces")),
            "pieces": [],
        }
        _extract_piece_slots(element, palette["pieces"])
        result["piece_palettes"].append(palette)

    # --- Predefined Setups ---
    elif tag == "PredefinedSetup":
        result["predefined_setups"].append({
            "name": element.attrib.get("name", "unnamed"),
            "file": element.attrib.get("file", ""),
            "useFile": element.attrib.get("useFile", "true"),
            "isMenu": element.attrib.get("isMenu", "false"),
            "description": element.attrib.get("description", ""),
        })

    # --- Dice ---
    elif tag == "DiceButton":
        result["dice"].append({
            "type": "DiceButton",
            "name": element.attrib.get("name", ""),
            "nDice": element.attrib.get("nDice", "1"),
            "nSides": element.attrib.get("nSides", "6"),
            "plus": element.attrib.get("plus", "0"),
            "reportTotal": element.attrib.get("reportTotal", "false"),
            "attributes": dict(element.attrib),
        })
    elif tag == "SpecialDiceButton":
        dice_info = {
            "type": "SpecialDiceButton",
            "name": element.attrib.get("name", ""),
            "faces": [],
            "attributes": dict(element.attrib),
        }
        for child in element:
            child_tag = tag_short(child.tag)
            if child_tag == "SpecialDie":
                for face in child:
                    if tag_short(face.tag) == "SpecialDieFace":
                        dice_info["faces"].append(dict(face.attrib))
        result["dice"].append(dice_info)

    # --- Global Properties ---
    elif tag == "GlobalProperty":
        result["global_properties"].append({
            "name": element.attrib.get("name", ""),
            "initialValue": element.attrib.get("initialValue", ""),
            "description": element.attrib.get("description", ""),
            "numeric": element.attrib.get("isNumeric", "false"),
            "min": element.attrib.get("min", ""),
            "max": element.attrib.get("max", ""),
            "wrap": element.attrib.get("wrap", "false"),
        })

    # --- Turn Tracker ---
    elif tag == "TurnTracker":
        tracker = {"name": "TurnTracker", "levels": []}
        _extract_turn_levels(element, tracker["levels"])
        result["turn_tracker"].append(tracker)

    # --- Global Key Commands ---
    elif tag == "GlobalKeyCommand":
        result["global_key_commands"].append({
            "name": element.attrib.get("name", ""),
            "description": element.attrib.get("description", ""),
            "attributes": dict(element.attrib),
        })
    elif tag == "StartupGlobalKeyCommand":
        result["startup_key_commands"].append({
            "name": element.attrib.get("name", ""),
            "description": element.attrib.get("description", ""),
            "attributes": dict(element.attrib),
        })

    # --- Recurse into children ---
    for child in element:
        _walk_buildfile(child, result, depth + 1)


def _extract_map_contents(map_element, map_info):
    """Recursively extract boards, grids, zones, and setup stacks from a map."""
    for child in map_element:
        child_tag = tag_short(child.tag)

        if child_tag == "Board":
            map_info["boards"].append({
                "name": child.attrib.get("name", ""),
                "image": child.attrib.get("image", ""),
                "width": child.attrib.get("width", ""),
                "height": child.attrib.get("height", ""),
                "attributes": dict(child.attrib),
            })

        elif child_tag == "HexGrid":
            grid = {
                "type": "HexGrid",
                "dx": child.attrib.get("dx", ""),
                "dy": child.attrib.get("dy", ""),
                "x0": child.attrib.get("x0", "0"),
                "y0": child.attrib.get("y0", "0"),
                "sideways": child.attrib.get("sideways", "false"),
                "color": child.attrib.get("color", ""),
                "visible": child.attrib.get("visible", "false"),
                "cornersLegal": child.attrib.get("cornersLegal", "false"),
                "edgesLegal": child.attrib.get("edgesLegal", "false"),
                "numbering": None,
            }
            for gc in child:
                gc_tag = tag_short(gc.tag)
                if "Numbering" in gc_tag:
                    grid["numbering"] = dict(gc.attrib)
            map_info["grids"].append(grid)

        elif child_tag == "SquareGrid":
            grid = {
                "type": "SquareGrid",
                "dx": child.attrib.get("dx", ""),
                "dy": child.attrib.get("dy", ""),
                "x0": child.attrib.get("x0", "0"),
                "y0": child.attrib.get("y0", "0"),
                "color": child.attrib.get("color", ""),
                "visible": child.attrib.get("visible", "false"),
                "numbering": None,
            }
            for gc in child:
                gc_tag = tag_short(gc.tag)
                if "Numbering" in gc_tag:
                    grid["numbering"] = dict(gc.attrib)
            map_info["grids"].append(grid)

        elif child_tag == "RegionGrid":
            regions = []
            for gc in child:
                if tag_short(gc.tag) == "Region":
                    regions.append({
                        "name": gc.attrib.get("name", ""),
                        "originx": gc.attrib.get("originx", ""),
                        "originy": gc.attrib.get("originy", ""),
                    })
            map_info["grids"].append({
                "type": "RegionGrid",
                "region_count": len(regions),
                "regions": regions[:50],  # cap for large modules
            })

        elif child_tag == "ZonedGrid":
            zones = []
            for gc in child:
                if tag_short(gc.tag) == "Zone":
                    zone_info = {
                        "name": gc.attrib.get("name", ""),
                        "path": gc.attrib.get("path", ""),
                        "grids": [],
                    }
                    _extract_map_contents(gc, {"boards": [], "grids": zone_info["grids"], "zones": [], "setup_stacks": []})
                    zones.append(zone_info)
            map_info["zones"].extend(zones)
            map_info["grids"].append({"type": "ZonedGrid", "zone_count": len(zones)})

        elif child_tag == "SetupStack":
            stack_info = {
                "name": child.attrib.get("name", ""),
                "owningBoard": child.attrib.get("owningBoard", ""),
                "useGridLocation": child.attrib.get("useGridLocation", "false"),
                "location": child.attrib.get("location", ""),
                "x": child.attrib.get("x", ""),
                "y": child.attrib.get("y", ""),
                "pieces": [],
            }
            for slot in child:
                if tag_short(slot.tag) == "PieceSlot":
                    type_str = (slot.text or "").strip()
                    traits = parse_piece_type(type_str)
                    bp = extract_basic_piece_info(traits)
                    bn = extract_basic_name(traits)
                    stack_info["pieces"].append({
                        "gpId": slot.attrib.get("gpId", ""),
                        "entryName": slot.attrib.get("entryName", bn or bp.get("name", "")),
                        "image": bp.get("image", ""),
                        "trait_count": len(traits),
                        "markers": extract_markers(traits),
                        "prototypes": extract_prototypes(traits),
                    })
            map_info["setup_stacks"].append(stack_info)

        else:
            # Recurse for containers like BoardPicker
            _extract_map_contents(child, map_info)


def _extract_piece_slots(element, pieces_list):
    """Recursively find all PieceSlot elements under a palette."""
    tag = tag_short(element.tag)

    if tag == "PieceSlot":
        type_str = (element.text or "").strip()
        traits = parse_piece_type(type_str)
        bp = extract_basic_piece_info(traits)
        bn = extract_basic_name(traits)
        pieces_list.append({
            "gpId": element.attrib.get("gpId", ""),
            "entryName": element.attrib.get("entryName", bn or bp.get("name", "")),
            "image": bp.get("image", ""),
            "width": element.attrib.get("width", ""),
            "height": element.attrib.get("height", ""),
            "trait_count": len(traits),
            "traits": [t["trait"] for t in traits],
            "markers": extract_markers(traits),
            "uses_prototypes": extract_prototypes(traits),
            "dynamic_properties": extract_dynamic_props(traits),
        })

    for child in element:
        _extract_piece_slots(child, pieces_list)


def _extract_turn_levels(element, levels):
    """Recursively extract turn tracker levels."""
    for child in element:
        child_tag = tag_short(child.tag)
        if "TurnLevel" in child_tag or "Counter" in child_tag:
            level = {
                "type": child_tag,
                "name": child.attrib.get("name", child.attrib.get("value", "")),
                "attributes": dict(child.attrib),
                "sub_levels": [],
            }
            _extract_turn_levels(child, level["sub_levels"])
            levels.append(level)


# ---------------------------------------------------------------------------
# Save file analysis
# ---------------------------------------------------------------------------

def deobfuscate(data_bytes):
    """Deobfuscate a VASSAL savedGame entry."""
    text = data_bytes.decode("utf-8", errors="replace")
    if text.startswith("!VCSK"):
        key = int(text[5:7], 16)
        plain = []
        for i in range(7, len(text) - 1, 2):
            try:
                byte_val = int(text[i:i+2], 16) ^ key
                plain.append(chr(byte_val))
            except ValueError:
                break
        return "".join(plain)
    return text


def analyze_embedded_save(zf, save_path):
    """Analyze a .vsav file embedded inside the .vmod."""
    save_data = zf.read(save_path)
    # The embedded save is itself a ZIP
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(save_data)) as save_zf:
            if "savedGame" in save_zf.namelist():
                raw = save_zf.read("savedGame")
                plain = deobfuscate(raw)
                # Count commands (separated by ESC char \x1b)
                commands = plain.split("\x1b")
                # Count AddPiece commands
                add_count = sum(1 for c in commands if c.startswith("+/"))
                return {
                    "total_commands": len(commands),
                    "add_piece_commands": add_count,
                    "has_begin_save": "begin_save" in plain,
                    "has_end_save": "end_save" in plain,
                    "size_bytes": len(plain),
                }
    except (zipfile.BadZipFile, Exception) as e:
        return {"error": str(e)}
    return {"error": "no savedGame entry"}


# ---------------------------------------------------------------------------
# Top-level analysis
# ---------------------------------------------------------------------------

def analyze_vmod(vmod_path):
    """Full analysis of a .vmod file."""
    report = {
        "file": os.path.basename(vmod_path),
        "file_size": os.path.getsize(vmod_path),
    }

    with zipfile.ZipFile(vmod_path, "r") as zf:
        all_entries = zf.namelist()
        report["zip_entry_count"] = len(all_entries)

        # Categorize entries
        images = [e for e in all_entries if e.startswith("images/")]
        sounds = [e for e in all_entries if e.startswith("sounds/")]
        saves = [e for e in all_entries if e.endswith(".vsav")]
        report["image_count"] = len(images)
        report["sound_count"] = len(sounds)
        report["embedded_save_count"] = len(saves)
        report["image_files"] = images[:100]  # cap for huge modules
        report["sound_files"] = sounds[:50]

        # Module metadata
        report["metadata"] = analyze_module_metadata(zf)

        # buildFile analysis
        bf = analyze_buildfile(zf)
        if bf:
            report["module"] = bf
        else:
            report["module"] = {"error": "No buildFile found"}

        # Analyze embedded saves (scenarios)
        report["embedded_saves"] = {}
        for save_path in saves:
            report["embedded_saves"][save_path] = analyze_embedded_save(zf, save_path)

    return report


def print_summary(report):
    """Print a human-readable summary of the analysis."""
    print("=" * 70)
    print(f"VASSAL MODULE ANALYSIS: {report['file']}")
    print(f"File size: {report['file_size']:,} bytes")
    print(f"ZIP entries: {report['zip_entry_count']}")
    print(f"Images: {report['image_count']}  |  Sounds: {report['sound_count']}  |  Embedded saves: {report['embedded_save_count']}")
    print("=" * 70)

    meta = report.get("metadata", {})
    if meta:
        print(f"\nGame: {meta.get('name', 'Unknown')}")
        print(f"Module Version: {meta.get('version', '?')}")
        print(f"Vassal Version: {meta.get('VassalVersion', '?')}")

    mod = report.get("module", {})
    if "error" in mod:
        print(f"\nModule Error: {mod['error']}")
        return

    # Player sides
    sides = mod.get("player_sides", [])
    if sides:
        print(f"\nPlayer Sides ({len(sides)}): {', '.join(sides)}")

    # Maps
    maps = mod.get("maps", [])
    print(f"\nMaps ({len(maps)}):")
    for m in maps:
        board_names = [b["name"] for b in m.get("boards", [])]
        grid_types = [g["type"] for g in m.get("grids", [])]
        zone_names = [z["name"] for z in m.get("zones", [])]
        setup_count = sum(len(s["pieces"]) for s in m.get("setup_stacks", []))
        print(f"  [{m['type']}] {m['name']}")
        if board_names:
            print(f"    Boards: {', '.join(board_names)}")
        if grid_types:
            print(f"    Grids: {', '.join(grid_types)}")
            for g in m.get("grids", []):
                if g["type"] in ("HexGrid", "SquareGrid"):
                    print(f"      {g['type']}: dx={g['dx']} dy={g['dy']} origin=({g['x0']},{g['y0']})"
                          + (f" sideways={g['sideways']}" if g.get("sideways") else ""))
                    if g.get("numbering"):
                        n = g["numbering"]
                        print(f"      Numbering: sep={n.get('sep','')} hType={n.get('hType','')} vType={n.get('vType','')}"
                              f" hOff={n.get('hOff','')} vOff={n.get('vOff','')}")
        if zone_names:
            print(f"    Zones ({len(zone_names)}): {', '.join(zone_names[:20])}")
        if setup_count:
            print(f"    At-Start pieces: {setup_count} (in {len(m.get('setup_stacks',[]))} stacks)")

    # Prototypes
    protos = mod.get("prototypes", [])
    print(f"\nPrototypes ({len(protos)}):")
    for p in protos:
        marker_str = ", ".join(f"{k}={v}" for k, v in p["markers"].items()) if p["markers"] else ""
        proto_refs = ", ".join(p["uses_prototypes"]) if p["uses_prototypes"] else ""
        line = f"  {p['name']} ({p['trait_count']} traits)"
        if p.get("description"):
            line += f" -- {p['description']}"
        print(line)
        if marker_str:
            print(f"    Markers: {marker_str}")
        if proto_refs:
            print(f"    Uses: {proto_refs}")
        if p["dynamic_properties"]:
            print(f"    DynProps: {', '.join(p['dynamic_properties'])}")

    # Piece palettes
    palettes = mod.get("piece_palettes", [])
    total_pieces = sum(len(p["pieces"]) for p in palettes)
    print(f"\nPiece Palettes ({len(palettes)}, {total_pieces} total pieces):")
    for pal in palettes:
        print(f"  {pal['name']} ({len(pal['pieces'])} pieces)")
        for pc in pal["pieces"][:30]:  # cap display
            marker_str = ", ".join(f"{k}={v}" for k, v in pc["markers"].items()) if pc["markers"] else ""
            proto_str = ", ".join(pc["uses_prototypes"]) if pc["uses_prototypes"] else ""
            line = f"    [{pc.get('gpId','')}] {pc['entryName']}"
            if pc.get("image"):
                line += f"  img={pc['image']}"
            print(line)
            if marker_str:
                print(f"      Markers: {marker_str}")
            if proto_str:
                print(f"      Prototypes: {proto_str}")
        if len(pal["pieces"]) > 30:
            print(f"    ... and {len(pal['pieces']) - 30} more pieces")

    # Predefined setups
    setups = mod.get("predefined_setups", [])
    if setups:
        print(f"\nPredefined Setups / Scenarios ({len(setups)}):")
        for s in setups:
            desc = f" -- {s['description']}" if s.get("description") else ""
            print(f"  {s['name']}{desc}")
            if s.get("file"):
                print(f"    File: {s['file']}")

    # Dice
    dice = mod.get("dice", [])
    if dice:
        print(f"\nDice ({len(dice)}):")
        for d in dice:
            if d["type"] == "DiceButton":
                print(f"  {d['name']}: {d['nDice']}d{d['nSides']}+{d['plus']}"
                      f" (reportTotal={d['reportTotal']})")
            else:
                print(f"  {d['name']}: Special ({len(d.get('faces',[]))} faces)")

    # Global properties
    gprops = mod.get("global_properties", [])
    if gprops:
        print(f"\nGlobal Properties ({len(gprops)}):")
        for gp in gprops:
            print(f"  {gp['name']} = {gp['initialValue']}"
                  + (f" (numeric, {gp['min']}-{gp['max']})" if gp["numeric"] == "true" else ""))

    # Turn tracker
    trackers = mod.get("turn_tracker", [])
    if trackers:
        print(f"\nTurn Tracker:")
        for t in trackers:
            _print_turn_levels(t["levels"], indent=2)

    # Global key commands
    gkcs = mod.get("global_key_commands", [])
    if gkcs:
        print(f"\nGlobal Key Commands ({len(gkcs)}):")
        for g in gkcs:
            print(f"  {g['name']}: {g.get('description', '')}")

    # Embedded saves
    esaves = report.get("embedded_saves", {})
    if esaves:
        print(f"\nEmbedded Save Analysis:")
        for path, info in esaves.items():
            if "error" in info:
                print(f"  {path}: ERROR - {info['error']}")
            else:
                print(f"  {path}: {info['add_piece_commands']} pieces, "
                      f"{info['total_commands']} commands, {info['size_bytes']:,} bytes")

    print("\n" + "=" * 70)


def _print_turn_levels(levels, indent):
    """Recursively print turn tracker levels."""
    for level in levels:
        attrs = level.get("attributes", {})
        start = attrs.get("start", "")
        current = attrs.get("current", "")
        print(f"{' ' * indent}{level['type']}: {level['name']}"
              + (f" (start={start})" if start else "")
              + (f" [current={current}]" if current else ""))
        if level.get("sub_levels"):
            _print_turn_levels(level["sub_levels"], indent + 2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vmod_analyzer.py <path_to.vmod> [--json]")
        sys.exit(1)

    vmod_path = sys.argv[1]
    use_json = "--json" in sys.argv

    if not os.path.isfile(vmod_path):
        print(f"Error: File not found: {vmod_path}")
        sys.exit(1)

    report = analyze_vmod(vmod_path)

    if use_json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_summary(report)
