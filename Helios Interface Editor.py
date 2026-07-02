import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import copy
import os
import re
import sys

#Parser development commented out line 1905, 1922, 3034
# Name of the window/taskbar icon inside the app assets folder.
APP_ICON_FILE = os.path.join("assets", "Helios Interface Editor.ico")


def resource_path(filename):
    """Absolute path to a bundled resource. Works for a normal run (file next to
    the script) and for a PyInstaller one-file build (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = os.getcwd()
    return os.path.join(base, filename)


def strip_private_fields(value):
    if isinstance(value, dict):
        return {
            key: strip_private_fields(item)
            for key, item in value.items()
            if not key.startswith("_")
        }
    if isinstance(value, list):
        return [strip_private_fields(item) for item in value]
    return value

# The device/name "prettifier" lives in the Lua compiler module. Import it once
# (lazily-safe) so the editor still runs even when that file isn't present.
try:
    from parser_engine import _prettify_device as _core_prettify_device
except Exception:
    _core_prettify_device = None


def prettify_label(text):
    """Clean up a raw device/name string for display while preserving the
    user's original capitalization: take the trailing dotted leaf, turn
    underscores into spaces, and leave letter case untouched (e.g.
    'MAIN.gear_handle' -> 'gear handle', 'MY_DEVICE' -> 'MY DEVICE')."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    leaf = raw.split(".")[-1]
    return leaf.replace("_", " ")


# ── Constants ──────────────────────────────────────────────────────────────────
DCS_LEADER = "DCS.Common."

HELIOS_TYPES = [
    DCS_LEADER + "PushButton",
    DCS_LEADER + "Switch",
    DCS_LEADER + "Axis",
    DCS_LEADER + "ScaledNetworkValue",
    DCS_LEADER + "NetworkValue",
    DCS_LEADER + "RotaryEncoder",
    DCS_LEADER + "FlagValue",
    DCS_LEADER + "Text"
]

# Generates the tab labels in order
TAB_LABELS = {helios_type: re.sub(r"(\w)([A-Z])", r"\1 \2", helios_type.split(".")[-1])
              for helios_type in HELIOS_TYPES}

# Default export "format" strings for the value-style helios types. These are
# the values the Add/Edit dialog pre-fills (and the user can change).
DEFAULT_SCALED_FORMAT = "%.3f"
DEFAULT_NETWORK_FORMAT = "%.3f"

UNIT_GROUPS = [
    ("Generic Units", ["NoValue", "Numeric", "Text", "Boolean"]),
    ("Angle Units", ["Radians", "Degrees"]),
    ("Temperature Units", ["Celsius"]),
    ("Distance Units", ["Meters", "Kilometers", "Feet", "Miles", "NauticalMiles"]),
    ("Revolution Units", ["RPMPercent"]),
    ("Time Units", ["Seconds", "Minutes", "Hours"]),
    ("Mass Units", ["Pounds", "Kilograms"]),
    ("Area Units", ["SquareInch", "SquareFoot", "SquareCentimeter"]),
    ("Speed Units", ["MetersPerSecond", "FeetPerSecond", "FeetPerMinute", "MilesPerHour", "Knots", "KilometersPerHour"]),
    ("Mass Flow Units", ["PoundsPerHour"]),
    ("Pressure Units", ["PoundsPerSquareInch", "PoundsPerSquareFoot", "InchesOfMercury", "MilimetersOfMercury", "Millibar", "Bar", "KilgramsForcePerSquareCentimeter"]),
    ("Volume Units", ["Liters"]),
    ("Electrical Units", ["Volts"]),
]

# Standard description text applied per helios type by the "Set Descriptions"
# button. ScaledNetworkValue maps to None, meaning "leave the description
# exactly as it is" (it is intentionally left blank).
DESCRIPTION_BY_TYPE = {
    DCS_LEADER + "PushButton":         "Current State of This Button",
    DCS_LEADER + "Switch":             "Current Position of This Switch",
    DCS_LEADER + "FlagValue":          "Current State of This Indicator",
    DCS_LEADER + "Axis":               "Current Value of This Potentiometer",
    DCS_LEADER + "RotaryEncoder":      "Current Position of This Rotary Encoder",
    DCS_LEADER + "NetworkValue":       "Numeric Value Between 0 and 1",
    DCS_LEADER + "ScaledNetworkValue": "Mapped Output from lua min/max to desired range",   # leave blank, as it is now
    DCS_LEADER + "Text":               "Text Value",
}

# Columns that hold DCS IDs. They are validated as positive integers and sorted
# numerically (not as strings) when the user clicks a column header.
ID_COLUMNS = {
    "id",
    "btn_deviceId", "pushId", "releaseId",
    "set_deviceId", "set_actionId",
    "inc_deviceId", "inc_actionId", "dec_deviceId", "dec_actionId",
    "deviceId", "actionId",
}

# Grid columns whose cell values are centred within their column. Covers every
# ID-type column plus the axis bounds, switch positions and calibration-point
# counts. Text columns (device, name, description) stay left-aligned.
CENTERED_COLUMNS = set(ID_COLUMNS) | {"argumentMin", "argumentMax", "positions", "points"}

# Optional (key, label) id fields validated per helios type by the entry dialog,
# in addition to the always-required Export ID(Arg).
_OPTIONAL_ID_CHECKS_BY_TYPE = {
    DCS_LEADER + "PushButton": [
        ("btn_deviceId", "Device ID"), ("pushId", "Push ID"), ("releaseId", "Release ID")],
    DCS_LEADER + "Axis": [
        ("set_deviceId", "Set Device ID"), ("set_actionId", "Set Action ID")],
    DCS_LEADER + "RotaryEncoder": [
        ("inc_deviceId", "Increment Device ID"), ("inc_actionId", "Increment Action ID"),
        ("dec_deviceId", "Decrement Device ID"), ("dec_actionId", "Decrement Action ID")],
    DCS_LEADER + "Switch": [
        ("deviceId", "Device ID"), ("switch_actionId", "Action ID")],
}

# ── Theming ─────────────────────────────────────────────────────────────────────
# Two full colour palettes. apply_theme() copies a palette into the module-level
# colour names below; every widget reads those names at build time, so switching
# themes is a matter of re-applying a palette and rebuilding the UI.
DARK_THEME = {
    "bg": "#1a1f2e", "mid": "#252b3b", "panel": "#1e2436",
    "row_odd": "#252b3b", "row_even": "#2c3348", "row_sel": "#3a5a8c",
    "accent": "#4a9eff", "accent2": "#ff7c4a",
    "text_pri": "#e8eaf0", "text_sec": "#8b92a8", "text_head": "#b8c0d4",
    "border": "#363d52", "success": "#4aff8c", "warn": "#ffd24a",
    "error": "#ff4a6a", "danger_bg": "#4a1a2a", "danger_fg": "#ff4a6a",
}

LIGHT_THEME = {
    "bg": "#f4f6fb", "mid": "#ffffff", "panel": "#e9edf5",
    "row_odd": "#ffffff", "row_even": "#eef2f9", "row_sel": "#bcd4f5",
    "accent": "#2563eb", "accent2": "#c2560c",
    "text_pri": "#1a1f2e", "text_sec": "#5b6478", "text_head": "#33405c",
    "border": "#cdd6e6", "success": "#15803d", "warn": "#b45309",
    "error": "#dc2626", "danger_bg": "#fde2e2", "danger_fg": "#dc2626",
}

# Colour names used throughout the UI (populated by apply_theme below).
DARK_BG = MID_BG = PANEL_BG = ROW_ODD = ROW_EVEN = ROW_SEL = ""
ACCENT = ACCENT2 = TEXT_PRI = TEXT_SEC = TEXT_HEAD = BORDER = ""
SUCCESS = WARN = ERROR = DANGER_BG = DANGER_FG = ""


def apply_theme(palette):
    """Copy `palette` into the module-level colour names so the whole UI can
    read them. Call this before (re)building the window."""
    global DARK_BG, MID_BG, PANEL_BG, ROW_ODD, ROW_EVEN, ROW_SEL
    global ACCENT, ACCENT2, TEXT_PRI, TEXT_SEC, TEXT_HEAD, BORDER
    global SUCCESS, WARN, ERROR, DANGER_BG, DANGER_FG
    DARK_BG   = palette["bg"]
    MID_BG    = palette["mid"]
    PANEL_BG  = palette["panel"]
    ROW_ODD   = palette["row_odd"]
    ROW_EVEN  = palette["row_even"]
    ROW_SEL   = palette["row_sel"]
    ACCENT    = palette["accent"]
    ACCENT2   = palette["accent2"]
    TEXT_PRI  = palette["text_pri"]
    TEXT_SEC  = palette["text_sec"]
    TEXT_HEAD = palette["text_head"]
    BORDER    = palette["border"]
    SUCCESS   = palette["success"]
    WARN      = palette["warn"]
    ERROR     = palette["error"]
    DANGER_BG = palette["danger_bg"]
    DANGER_FG = palette["danger_fg"]


apply_theme(DARK_THEME)  # start in dark mode

FONT_MONO = ("Consolas", 9)
FONT_UI   = ("Segoe UI", 9)
FONT_HEAD = ("Segoe UI", 9, "bold")
FONT_TITLE= ("Segoe UI", 11, "bold")


def make_blank_entry(helios_type):
    base = {
        "heliosType": helios_type,
        "device": "",
        "name": "",
        "description": DESCRIPTION_BY_TYPE.get(helios_type) or "",
    }
    if helios_type == DCS_LEADER + "FlagValue":
        base["exports"] = [{"format": "%0.3f", "id": ""}]
    elif helios_type == DCS_LEADER + "Text":
        base["exports"] = [{"isExportedEveryFrame": True, "id": ""}]
    elif helios_type == DCS_LEADER + "PushButton":
        base["exports"] = [{"format": "%1d", "isExportedEveryFrame": False, "id": ""}]
        base["buttons"] = [{"deviceId": "", "pushId": "", "pushValue": 1.0,
                             "releaseId": "", "releaseValue": 0.0}]
    elif helios_type == DCS_LEADER + "Axis":
        base["exports"] = [{"format": "%.3f", "id": ""}]
        base["loop"] = False
        base["argumentValue"] = "0.025"
        base["argumentMin"] = "0.0"
        base["argumentMax"] = "1.0"
        base["actions"] = {"set": {"deviceId": "", "actionId": ""}}
    elif helios_type == DCS_LEADER + "NetworkValue":
        base["exports"] = [{"format": DEFAULT_NETWORK_FORMAT, "id": ""}]
        base["unit"] = "Numeric"
    elif helios_type == DCS_LEADER + "ScaledNetworkValue":
        base["exports"] = [{"format": DEFAULT_SCALED_FORMAT, "id": ""}]
        base["unit"] = "Numeric"
        base["exposeunscaledvalue"] = True
        base["calibration"] = {
            "points": [{"value": "0.0", "mappedValue": "0.0"}, {"value": "1.0", "mappedValue": "1.0"}],
            "precision": 5
        }
    elif helios_type == DCS_LEADER + "RotaryEncoder":
        base["exports"] = [{"format": "%.3f", "id": ""}]
        base["unit"] = "Numeric"
        base["argumentValue"] = 0.025
        base["actions"] = {
            "increment": {"deviceId": "", "actionId": ""},
            "decrement":  {"deviceId": "", "actionId": ""}
        }
    elif helios_type == DCS_LEADER + "Switch":
        base["exports"] = [{"format": "%0.1f", "id": ""}]
        base["deviceId"] = ""
        base["positions"] = [
            {"argumentValue": "0.0", "name": "", "actionId": ""},
            {"argumentValue": "1.0", "name": "", "actionId": ""}
        ]
    return base


# ── Utility ────────────────────────────────────────────────────────────────────
def first_export(entry):
    """Return the entry's first export dict, or {} when it has none.

    Real Helios profiles sometimes carry an empty ``exports`` list (some
    RotaryEncoders in the stock A-10C profile do), so callers must never assume
    ``exports[0]`` exists."""
    exports = entry.get("exports")
    if isinstance(exports, list) and exports:
        first = exports[0]
        return first if isinstance(first, dict) else {}
    return {}


def get_all_ids(functions):
    ids = set()
    for function in functions:
        for export in function.get("exports", []):
            export_id = str(export.get("id", "")).strip()
            if export_id:
                try:
                    ids.add(int(export_id))
                except ValueError:
                    pass
    return ids


def max_id(functions):
    ids = get_all_ids(functions)
    return max(ids) if ids else 0


def to_int(value):
    """Coerce id-like fields to int for JSON output.
    - Whole numbers ("3001", "3001.0", 3001) -> int 3001
    - Blank/None -> "" (preserves the original blank-field behavior)
    - Non-numeric text -> returned unchanged so nothing is lost
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text == "":
        return ""
    try:
        if text.lstrip("+-").isdigit():
            return int(text)
        as_float = float(text)
        if as_float.is_integer():
            return int(as_float)
    except (ValueError, TypeError):
        pass
    return value


def positive_int_or_none(value):
    """Interpret an ID-field value.
    Returns:
      None        -> the field was blank
      int (> 0)   -> a valid positive integer ID
      False       -> the field held something that is not a positive integer
    """
    text = str(value).strip()
    if text == "":
        return None
    try:
        if text.lstrip("+").isdigit():
            number = int(text)
            return number if number > 0 else False
        as_float = float(text)
        if as_float.is_integer() and as_float > 0:
            return int(as_float)
    except (ValueError, TypeError):
        pass
    return False


def int_sort_value(value, missing=float("inf")):
    """Return an integer suitable for numeric sorting, or `missing` when the
    value isn't a (signed) integer so blanks/non-numerics sort consistently."""
    text = str(value).strip()
    if text.lstrip("+-").isdigit():
        return int(text)
    return missing


# ── Helios type conversion ──────────────────────────────────────────────────────
# Several helios types store a "primary" DCS device id, but in different places.
# When the user changes a function's type we keep that device id (along with the
# common device/name/description/export-id fields) and reset everything else to
# the new type's defaults, since the type-specific wiring doesn't map cleanly.
def _push_device_id(entry):
    return entry.get("buttons", [{}])[0].get("deviceId", "")


def _switch_device_id(entry):
    return entry.get("deviceId", "")


def _axis_device_id(entry):
    return entry.get("actions", {}).get("set", {}).get("deviceId", "")


def _rotary_device_id(entry):
    actions = entry.get("actions", {})
    return (actions.get("increment", {}).get("deviceId", "")
            or actions.get("decrement", {}).get("deviceId", ""))


_DEVICE_ID_GETTERS = {
    DCS_LEADER + "PushButton":    _push_device_id,
    DCS_LEADER + "Switch":        _switch_device_id,
    DCS_LEADER + "Axis":          _axis_device_id,
    DCS_LEADER + "RotaryEncoder": _rotary_device_id,
}


def get_primary_device_id(entry):
    """Best-effort: pull the main DCS device id out of a function entry,
    wherever the entry's helios type happens to keep it. Returns "" if none."""
    getter = _DEVICE_ID_GETTERS.get(entry.get("heliosType", ""))
    return getter(entry) if getter else ""


def _push_action_id(entry):
    button = entry.get("buttons", [{}])[0]
    return button.get("pushId", "") or button.get("releaseId", "")


def _first_switch_action_id(entry):
    for position in entry.get("positions", []):
        action_id = str(position.get("actionId", "")).strip()
        if action_id:
            return action_id
    return ""


def _axis_action_id(entry):
    return entry.get("actions", {}).get("set", {}).get("actionId", "")


def _rotary_action_id(entry):
    actions = entry.get("actions", {})
    return (actions.get("increment", {}).get("actionId", "")
            or actions.get("decrement", {}).get("actionId", ""))


_ACTION_ID_GETTERS = {
    DCS_LEADER + "PushButton":    _push_action_id,
    DCS_LEADER + "Switch":        _first_switch_action_id,
    DCS_LEADER + "Axis":          _axis_action_id,
    DCS_LEADER + "RotaryEncoder": _rotary_action_id,
}


def get_primary_action_id(entry):
    """Best-effort: pull the main DCS action id out of a function entry.
    Returns "" when the type has no single action id (network/text values)."""
    getter = _ACTION_ID_GETTERS.get(entry.get("heliosType", ""))
    return getter(entry) if getter else ""


def _as_id_str(value):
    """Stringify an id-ish value, mapping None / "" to ""."""
    return str(value) if value not in (None, "") else ""


def _scan_actions_for_ids(entry):
    """Return (device_id, action_id) gleaned from any of the entry's `actions`
    sub-objects (set / increment / decrement / ...)."""
    device_id = ""
    action_id = ""
    actions = entry.get("actions", {})
    if isinstance(actions, dict):
        for sub in actions.values():
            if isinstance(sub, dict):
                device_id = device_id or _as_id_str(sub.get("deviceId"))
                action_id = action_id or _as_id_str(sub.get("actionId"))
    return device_id, action_id


def _first_button_device_id(entry):
    """Device id of the entry's first button, or "" when there is none."""
    buttons = entry.get("buttons", [])
    if isinstance(buttons, list) and buttons and isinstance(buttons[0], dict):
        return _as_id_str(buttons[0].get("deviceId"))
    return ""


def best_effort_ids(entry):
    """Return (device_id, action_id) as strings for *any* function, including
    types this editor doesn't model (AbsoluteEncoder, the VHF encoders, etc.).
    Tries the type-aware getters first, then falls back to scanning the entry's
    `actions` sub-objects, a top-level deviceId, or the first button."""
    device_id = _as_id_str(get_primary_device_id(entry))
    action_id = _as_id_str(get_primary_action_id(entry))
    scanned_device, scanned_action = _scan_actions_for_ids(entry)
    device_id = device_id or scanned_device or _as_id_str(entry.get("deviceId"))
    action_id = action_id or scanned_action
    if not device_id:
        device_id = _first_button_device_id(entry)
    return device_id, action_id


def set_primary_device_id(entry, device_id):
    """Write a device id into the place the entry's helios type expects it.
    No-op for types that have no single primary device id (network/text values)."""
    if device_id in ("", None):
        return
    helios_type = entry.get("heliosType", "")
    if helios_type == DCS_LEADER + "PushButton":
        entry["buttons"][0]["deviceId"] = to_int(device_id)
    elif helios_type == DCS_LEADER + "Switch":
        entry["deviceId"] = to_int(device_id)
    elif helios_type == DCS_LEADER + "Axis":
        entry["actions"]["set"]["deviceId"] = to_int(device_id)
    elif helios_type == DCS_LEADER + "RotaryEncoder":
        entry["actions"]["increment"]["deviceId"] = to_int(device_id)
        entry["actions"]["decrement"]["deviceId"] = to_int(device_id)


def set_primary_action_id(entry, action_id):
    """Write an action id into the place the entry's helios type expects it.
    For a PushButton the action id maps to *both* pushId and releaseId; for a
    Switch it is written to every position. No-op for types that have no single
    primary action id (network/text values)."""
    if action_id in ("", None):
        return
    value = to_int(action_id)
    helios_type = entry.get("heliosType", "")
    if helios_type == DCS_LEADER + "PushButton":
        entry["buttons"][0]["pushId"] = value
        entry["buttons"][0]["releaseId"] = value
    elif helios_type == DCS_LEADER + "Switch":
        for position in entry.get("positions", []):
            position["actionId"] = value
    elif helios_type == DCS_LEADER + "Axis":
        entry["actions"]["set"]["actionId"] = value
    elif helios_type == DCS_LEADER + "RotaryEncoder":
        entry["actions"]["increment"]["actionId"] = value
        entry["actions"]["decrement"]["actionId"] = value


def convert_entry_type(entry, new_type):
    """Build a fresh entry of `new_type` that preserves the common fields and the
    export id from `entry`, carrying the primary device id where it maps cleanly.
    All other type-specific fields are reset to the new type's defaults."""
    new_entry = make_blank_entry(new_type)
    new_entry["device"]      = entry.get("device", "")
    new_entry["name"]        = entry.get("name", "")
    # Keep an existing description; otherwise fall back to the new type's default.
    new_entry["description"] = entry.get("description") or DESCRIPTION_BY_TYPE.get(new_type) or ""
    # Preserve the export id (first export) so existing wiring/links stay intact.
    old_exports = entry.get("exports", [{}])
    old_id = old_exports[0].get("id", "") if old_exports else ""
    if new_entry.get("exports"):
        new_entry["exports"][0]["id"] = to_int(old_id)
    # Best-effort device-id and action-id carryover between the two types.
    set_primary_device_id(new_entry, get_primary_device_id(entry))
    set_primary_action_id(new_entry, get_primary_action_id(entry))
    return new_entry


def device_action_sort_key(entry):
    """Sort key used for saving, the Full View, and the in-memory order after
    every add / load / import.

    Entries that have *neither* a device id nor an action id — the display
    values such as NetworkValue / FlagValue / ScaledNetworkValue / Text — are
    ordered first, alphabetically by device name and then by name.

    Entries that have a device id and/or action id are ordered after those
    display-only entries, by primary device id and then by primary action id
    (ids compare as integers; a missing id sorts last within its group via
    int_sort_value's +inf)."""
    device_value = int_sort_value(get_primary_device_id(entry))
    action_value = int_sort_value(get_primary_action_id(entry))
    if device_value == float("inf") and action_value == float("inf"):
        return (0,
                str(entry.get("device", "")).lower(),
                str(entry.get("name", "")).lower(),
                0.0, 0.0)
    return (1, device_value, action_value, "", "")


def device_name_sort_key(entry):
    """Sort key: alphabetical by device name, then by name (both
    case-insensitive). Used as the alternative save / Full View ordering."""
    return (str(entry.get("device", "")).lower(), str(entry.get("name", "")).lower())


# The two save / Full View ordering options the user can pick between.
# key -> (menu label, sort-key function)
SORT_METHODS = {
    "deviceaction": ("Device ID, then Action ID", device_action_sort_key),
    "devicename":   ("Device Name, then Name (alphabetical)", device_name_sort_key),
}


def find_last_added_function(editor, helios_type):
    best = None
    best_index = -1
    for function in editor._data.get("functions", []):
        if function.get("heliosType") != helios_type:
            continue
        created_index = function.get("_created_session_index", -1)
        if created_index > best_index:
            best = function
            best_index = created_index

    if best is not None:
        return best

    last_added = getattr(editor, "_last_added_function", None)
    if last_added is not None and last_added.get("heliosType") == helios_type:
        return last_added
    return None


def find_last_saved_function(editor, helios_type):
    best = None
    best_index = -1
    for function in editor._data.get("functions", []):
        if function.get("heliosType") != helios_type:
            continue
        saved_index = function.get("_saved_session_index", -1)
        if saved_index > best_index:
            best = function
            best_index = saved_index

    if best is not None:
        return best

    last_saved = getattr(editor, "_last_saved_function", None)
    if last_saved is not None and last_saved.get("heliosType") == helios_type:
        return last_saved
    return None


def duplicate_last(editor, helios_type):
    """Duplicate the most recently saved device of `helios_type` within
    the given `editor` instance. Clears export ids and refreshes the UI.
    """
    last_saved = find_last_saved_function(editor, helios_type)
    if last_saved is None:
        messagebox.showinfo("No Entry", "No previous saved entry to duplicate for this tab.")
        return

    entry = copy.deepcopy(last_saved)
    for exp in entry.get("exports", []):
        exp["id"] = ""
    entry["name"] = (entry.get("name", "") or "") + " (copy)"
    editor._data["functions"].append(entry)
    editor._last_added_device = entry.get("device", "")
    editor._last_added_device_id = get_primary_device_id(entry)
    editor._last_added_function = entry
    editor._sort_functions()
    editor._refresh_all()
    editor._update_max_id()

    # Select the duplicated entry and immediately open it for editing.
    for index, function in enumerate(editor._data["functions"]):
        if function is entry:
            editor._select_tab(helios_type)
            editor._select_function(helios_type, index)
            editor._edit_entry(helios_type)
            break

def duplicate_selected(editor, helios_type):
    """Duplicate the currently selected row in the given `editor` tab.
    Clears export ids and opens the duplicate for editing."""
    tree = editor._trees.get(helios_type)
    if tree is None:
        return
    selection = tree.selection()
    if not selection:
        messagebox.showinfo("No Selection", "Select a row to duplicate.", parent=editor)
        return
    if len(selection) > 1:
        messagebox.showinfo("Select One",
                            "Duplicate Selected works on a single row — select just one.",
                            parent=editor)
        return
    item_id = selection[0]
    tags = tree.item(item_id, "tags")
    function_index = int(tags[0]) if tags else -1
    if function_index < 0:
        return

    original = editor._data["functions"][function_index]
    entry = copy.deepcopy(original)
    entry["_created_session_index"] = editor._next_created_session_index
    editor._next_created_session_index += 1
    for exp in entry.get("exports", []):
        exp["id"] = ""
    entry["name"] = (entry.get("name", "") or "") + " (copy)"
    editor._data["functions"].append(entry)
    editor._last_added_device = entry.get("device", "")
    editor._last_added_device_id = get_primary_device_id(entry)
    editor._last_added_function = entry
    editor._sort_functions()
    editor._refresh_all()
    editor._update_max_id()

    for index, function in enumerate(editor._data["functions"]):
        if function is entry:
            editor._select_tab(helios_type)
            editor._select_function(helios_type, index)
            editor._edit_entry(helios_type)
            break


# The canonical "axis" values that must keep a one-decimal form when saved or
# shown. Every other float is rounded to at most three decimal places.
SPECIAL_FLOAT_STRINGS = {
    -1.0: "-1.0",
    -0.5: "-0.5",
    0.0:  "0.0",
    0.5:  "0.5",
    1.0:  "1.0",
}


def format_float(value):
    """Format a float for saving / display.

    The canonical values -1.0, -0.5, 0.0, 0.5 and 1.0 are written exactly in
    that one-decimal form. Every other value is rounded to at most three
    decimal places, with any trailing zeros trimmed (e.g. 0.025 -> "0.025",
    0.100 -> "0.1", 3.14159 -> "3.142")."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    # Round first so values that drift onto a canonical value (e.g. 0.49996 or
    # a tiny 0.0001) still take the canonical one-decimal form. Adding 0.0
    # normalises a possible -0.0 before the lookup.
    rounded = round(number, 3) + 0.0
    if rounded in SPECIAL_FLOAT_STRINGS:
        return SPECIAL_FLOAT_STRINGS[rounded]
    text = f"{rounded:.3f}".rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        return "0.0"
    return text


def _coerce_to_float(value):
    """Turn an int or numeric string into a float; leave bools, blanks and
    non-numeric text untouched. Used to funnel a value into format_float so the
    canonical SPECIAL_FLOAT_STRINGS form is applied even when the source stored
    it as a bare integer (e.g. a switch position of "1" or a pushValue of 0)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return value
        try:
            return float(text)
        except (ValueError, TypeError):
            return value
    return value


def _coerce_keys(mapping, keys):
    """Coerce the given keys of a dict in place to floats, when the dict has
    them. A no-op for non-dicts."""
    if not isinstance(mapping, dict):
        return
    for key in keys:
        if key in mapping:
            mapping[key] = _coerce_to_float(mapping[key])


def _coerce_keys_in_list(items, keys):
    """Coerce the given keys to floats in every dict found in `items`."""
    for item in items or []:
        _coerce_keys(item, keys)


def normalize_special_floats(entry):
    """Coerce the specific value fields that should use the canonical
    SPECIAL_FLOAT_STRINGS formatting to floats, so they are written and shown in
    that form even when stored as bare integers. Scoped to exactly:

      * ScaledNetworkValue : calibration.points[].value, .mappedValue
      * PushButton         : buttons[].pushValue, .releaseValue
      * Switch             : positions[].argumentValue
      * Axis               : argumentMin, argumentMax

    ID fields and everything else are left untouched. Mutates and returns
    `entry`."""
    _coerce_keys(entry, ("argumentMin", "argumentMax"))
    _coerce_keys_in_list(entry.get("buttons"), ("pushValue", "releaseValue"))
    _coerce_keys_in_list(entry.get("positions"), ("argumentValue",))
    calibration = entry.get("calibration")
    if isinstance(calibration, dict):
        _coerce_keys_in_list(calibration.get("points"), ("value", "mappedValue"))
    return entry


def _equal_values(first, second):
    """Compare two raw field values for equality: numerically when both are
    numeric (so 1 and "1.0" count as equal), otherwise by trimmed string."""
    coerced_first = _coerce_to_float(first)
    coerced_second = _coerce_to_float(second)
    if isinstance(coerced_first, float) and isinstance(coerced_second, float):
        return abs(coerced_first - coerced_second) < 1e-9
    return str(first).strip() == str(second).strip()


def arg_min_max_match(entry):
    """True when an entry defines both argumentMin and argumentMax and the two
    hold the same value — meaning no range of travel. Checked for every function
    regardless of helios type (Axis, AbsoluteEncoder, the VHF encoders, ...),
    since argumentMin/argumentMax are the schema's universal range bounds."""
    if "argumentMin" not in entry or "argumentMax" not in entry:
        return False
    return _equal_values(entry.get("argumentMin"), entry.get("argumentMax"))


def _duplicate_position_value(entry):
    """Return the argumentValue shared by two or more of a switch's positions, or
    None if every position value is distinct."""
    seen = []
    for position in entry.get("positions", []) or []:
        if not isinstance(position, dict) or "argumentValue" not in position:
            continue
        value = position.get("argumentValue")
        if any(_equal_values(value, prior) for prior in seen):
            return value
        seen.append(value)
    return None


def _points_conflict(point_a, point_b):
    """True when two calibration points share a `value` but map it to different
    `mappedValue`s."""
    if "value" not in point_a or "value" not in point_b:
        return False
    return (_equal_values(point_a.get("value"), point_b.get("value"))
            and not _equal_values(point_a.get("mappedValue"), point_b.get("mappedValue")))


def _calibration_conflict(entry):
    """Return (value, mappedA, mappedB) for the first pair of ScaledNetworkValue
    calibration points that share a `value` but map to different `mappedValue`s,
    or None if there is no such conflict."""
    calibration = entry.get("calibration", {})
    points = calibration.get("points", []) if isinstance(calibration, dict) else []
    cleaned = [point for point in points if isinstance(point, dict)]
    for i, point_a in enumerate(cleaned):
        for point_b in cleaned[i + 1:]:
            if _points_conflict(point_a, point_b):
                return (point_a.get("value"), point_a.get("mappedValue"),
                        point_b.get("mappedValue"))
    return None


def _arg_min_max_issue(entry):
    if "argumentMin" in entry and "argumentMax" in entry \
            and _equal_values(entry.get("argumentMin"), entry.get("argumentMax")):
        return f"Argument Min equals Argument Max ({format_float(entry.get('argumentMin', ''))})"
    return None


def _switch_issue(entry):
    duplicate = _duplicate_position_value(entry)
    if duplicate is not None:
        return f"Two or more positions share argumentValue {format_float(duplicate)}"
    return None


def _scaled_issue(entry):
    conflict = _calibration_conflict(entry)
    if conflict is None:
        return None
    value, mapped_a, mapped_b = conflict
    return (f"Calibration value {format_float(value)} maps to both "
            f"{format_float(mapped_a)} and {format_float(mapped_b)}")


def _button_value_clash(button):
    return (isinstance(button, dict) and "pushValue" in button and "releaseValue" in button
            and _equal_values(button.get("pushValue"), button.get("releaseValue")))


def _pushbutton_issue(entry):
    for button in entry.get("buttons", []) or []:
        if _button_value_clash(button):
            return f"Push value equals Release value ({format_float(button.get('pushValue', ''))})"
    return None


# Per-type validation rules, dispatched by helios type in validation_issue.
_TYPE_VALIDATORS = {
    DCS_LEADER + "Switch": _switch_issue,
    DCS_LEADER + "ScaledNetworkValue": _scaled_issue,
    DCS_LEADER + "PushButton": _pushbutton_issue,
}


def validation_issue(entry):
    """Return a short description of a validation problem with this function, or
    None when it passes. Rules:

      * Any type        : argumentMin equals argumentMax (no range of travel).
      * Switch          : two or more positions share an argumentValue
                          (this also covers "min equals max", since a set whose
                          min equals its max is all-equal).
      * ScaledNetworkValue : two calibration points share a `value` but map to
                          different `mappedValue`s.
      * PushButton      : a button's pushValue equals its releaseValue.

    The generic min/max rule wins first; otherwise the type-specific rule runs."""
    generic = _arg_min_max_issue(entry)
    if generic is not None:
        return generic
    validator = _TYPE_VALIDATORS.get(entry.get("heliosType", ""))
    return validator(entry) if validator else None


def cast_numbers_to_strings(value):
    """Recursively convert every numeric value (int/float) to its string form,
    walking dicts and lists. Booleans and None are left untouched so flags such
    as isExportedEveryFrame keep their type. Used on save so the written file
    stores all numbers as strings. Floats are formatted by format_float so the
    canonical axis values keep their one-decimal form and all other floats are
    limited to three decimal places."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format_float(value)
    if isinstance(value, dict):
        return {key: cast_numbers_to_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [cast_numbers_to_strings(item) for item in value]
    return value


def _string_to_number(text):
    """Turn a numeric-looking string into an int or float; leave anything else
    (e.g. '%.3f', 'Initial', '') unchanged."""
    stripped = text.strip()
    if stripped == "":
        return text
    if re.fullmatch(r"[+-]?\d+", stripped):
        try:
            return int(stripped)
        except ValueError:
            return text
    if stripped.lower().lstrip("+-") in ("inf", "infinity", "nan"):
        return text  # don't let float() turn these into inf/nan
    try:
        return float(stripped)
    except (ValueError, TypeError):
        return text


def cast_strings_to_numbers(value):
    """Recursively convert every numeric-looking string into an int or float,
    walking dicts and lists. Non-numeric strings and all other types are left
    untouched. Used on open so numbers come back in as numbers."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _string_to_number(value)
    if isinstance(value, dict):
        return {key: cast_strings_to_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [cast_strings_to_numbers(item) for item in value]
    return value


# ── Dialog base ────────────────────────────────────────────────────────────────
class EntryDialog(tk.Toplevel):
    def __init__(self, parent, title, helios_type, existing=None, functions=None, edit_index=None):
        super().__init__(parent)
        self.title(title)
        self.helios_type = helios_type
        self.functions = functions or []
        self.edit_index = edit_index
        self.result = None

        self.configure(bg=DARK_BG)
        self.resizable(True, True)
        self.grab_set()

        self._vars = {}
        self._pos_vars = []
        self._pos_count_var = tk.IntVar(value=2)
        self._min_var = tk.DoubleVar(value=0.0)
        self._max_var = tk.DoubleVar(value=1.0)
        # When True the auto-generated switch position values are assigned in
        # reverse order (toggled by the "Swap Position Values" button); names
        # stay anchored to their rows.
        self._pos_reversed = False
        # ScaledNetworkValue calibration points (dynamic, like switch positions)
        self._pt_vars = []
        self._pt_count_var = tk.IntVar(value=2)
        # Debounce timers: rebuild the position / point rows only once the user
        # has paused typing, so a multi-digit count (e.g. "12") doesn't rebuild
        # at "1" first and throw away rows in between.
        self._pos_rebuild_after = None
        self._pt_rebuild_after = None

        self._build_ui(existing)
        self.update_idletasks()
        req_w, req_h = self.winfo_reqwidth(), self.winfo_reqheight()
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        win_w, win_h = min(req_w + 40, 900), min(req_h + 40, 700)
        self.geometry(f"{win_w}x{win_h}+{(screen_w - win_w) // 2}+{(screen_h - win_h) // 2}")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _frame(self, parent, **kwargs):
        return tk.Frame(parent, bg=DARK_BG, **kwargs)

    def _label(self, parent, text, sub=False):
        colour = TEXT_SEC if sub else TEXT_HEAD
        return tk.Label(parent, text=text, bg=DARK_BG, fg=colour, font=FONT_UI)

    def _entry(self, parent, width=28):
        return tk.Entry(parent, width=width, bg=MID_BG, fg=TEXT_PRI, insertbackground=TEXT_PRI,
                        relief="flat", font=FONT_MONO,
                        highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)

    def _row(self, parent, label, key, default="", sub=False, row=None):
        row_index = row if row is not None else len(self._vars)
        self._label(parent, label, sub).grid(row=row_index, column=0, sticky="w", padx=(8, 4), pady=3)
        var = tk.StringVar(value=str(default))
        entry_widget = self._entry(parent)
        entry_widget.configure(textvariable=var)
        entry_widget.grid(row=row_index, column=1, sticky="ew", padx=(0, 8), pady=3)
        self._vars[key] = var
        return row_index + 1

    # ── build ─────────────────────────────────────────────────────────────────
    def _section(self, parent, text, row):
        """Render a section header + divider; returns the next free grid row."""
        tk.Label(parent, text=text, bg=DARK_BG, fg=ACCENT, font=FONT_HEAD
                 ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 2))
        tk.Frame(parent, bg=BORDER, height=1).grid(
            row=row + 1, column=0, columnspan=2, sticky="ew", padx=8)
        return row + 2

    def _build_pushbutton_fields(self, inner, entry, export, existing, row):
        row = self._section(inner, "Button Mapping", row)
        button = entry.get("buttons", [{}])[0]
        row = self._row(inner, "Device ID",     "btn_deviceId",  button.get("deviceId", ""), row=row)
        row = self._row(inner, "Push ID (actionId)",    "pushId",    button.get("pushId", ""), row=row)
        row = self._row(inner, "Release ID (actionId)", "releaseId", button.get("releaseId", ""), row=row)
        return row

    def _build_axis_fields(self, inner, entry, export, existing, row):
        row = self._section(inner, "Axis Config", row)
        row = self._row(inner, "Argument Min",   "argumentMin",   entry.get("argumentMin", "0.0"), row=row)
        row = self._row(inner, "Argument Max",   "argumentMax",   entry.get("argumentMax", "1.0"), row=row)
        row = self._section(inner, "Set Action", row)
        set_action = entry.get("actions", {}).get("set", {})
        row = self._row(inner, "Device ID",  "set_deviceId",  set_action.get("deviceId", ""), row=row)
        row = self._row(inner, "Action ID",  "set_actionId",  set_action.get("actionId", ""), row=row)
        return row

    def _build_network_fields(self, inner, entry, export, existing, row):
        row = self._section(inner, "Export Format", row)
        return self._row(inner, "Format", "format",
                         export.get("format") or DEFAULT_NETWORK_FORMAT, row=row)

    def _debounce_cal_points(self):
        if self._pt_rebuild_after is not None:
            try:
                self.after_cancel(self._pt_rebuild_after)
            except Exception:  # noqa
                pass
        self._pt_rebuild_after = self.after(500, lambda: self._build_cal_points(None))

    @staticmethod
    def _coerce_bool_value(value, default=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off", ""}:
                return False
        if value in (None, ""):
            return default
        return bool(value)

    def _build_scaled_fields(self, inner, entry, export, existing, row):
        row = self._section(inner, "Export Format", row)
        row = self._row(inner, "Format", "format",
                        export.get("format") or DEFAULT_SCALED_FORMAT, row=row)

        self._label(inner, "Unit").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        initial_unit = (existing or {}).get("unit") or "Numeric"
        if initial_unit not in {unit for _, units in UNIT_GROUPS for unit in units}:
            initial_unit = "Numeric"
        self._unit_var = tk.StringVar(value=initial_unit)
        unit_button = tk.Frame(inner, bg=MID_BG, bd=0, highlightthickness=1,
                               highlightcolor=ACCENT, highlightbackground=BORDER)
        unit_button.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=3)
        unit_button.columnconfigure(0, weight=1)

        unit_text = tk.Label(unit_button, text=initial_unit, bg=MID_BG, fg=TEXT_PRI,
                             font=FONT_MONO, anchor="w")
        unit_text.grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=2)

        unit_arrow = tk.Label(unit_button, text="▼", bg=MID_BG, fg=TEXT_HEAD,
                              font=FONT_UI, anchor="e")
        unit_arrow.grid(row=0, column=1, sticky="e", padx=(0, 4), pady=2)

        unit_menu = tk.Menu(unit_button, tearoff=False, bg=MID_BG, fg=TEXT_PRI)

        def open_unit_menu(event=None):
            unit_menu.tk_popup(unit_button.winfo_rootx(), unit_button.winfo_rooty() + unit_button.winfo_height())

        def set_unit(value):
            self._unit_var.set(value)
            unit_text.configure(text=value)

        for widget in (unit_button, unit_text, unit_arrow):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", open_unit_menu)

        for group_name, units in UNIT_GROUPS:
            unit_menu.add_separator()
            unit_menu.add_command(
                label=group_name,
                command=lambda: None,
                font=(FONT_UI[0], FONT_UI[1] + 1, "bold"),
                foreground=TEXT_SEC,
                background=MID_BG,
                activebackground=MID_BG,
                activeforeground=TEXT_SEC,
            )
            for unit_name in units:
                unit_menu.add_command(
                    label=unit_name,
                    command=lambda value=unit_name: set_unit(value),
                )
        row += 1

        self._expose_unscaled_var = tk.BooleanVar(
            value=self._coerce_bool_value((existing or {}).get("exposeunscaledvalue", True), True)
        )
        expose_text_var = tk.StringVar(value="true" if self._expose_unscaled_var.get() else "false")
        self._expose_unscaled_var.trace_add(
            "write",
            lambda *_: expose_text_var.set("true" if self._expose_unscaled_var.get() else "false")
        )
        self._label(inner, "Expose Unscaled Value").grid(
            row=row, column=0, sticky="w", padx=(8, 4), pady=3
        )
        tk.Checkbutton(
            inner,
            variable=self._expose_unscaled_var,
            textvariable=expose_text_var,
            bg=DARK_BG,
            fg=TEXT_PRI,
            selectcolor=MID_BG,
            activebackground=DARK_BG,
            activeforeground=TEXT_PRI,
            highlightthickness=0,
            relief="flat",
        ).grid(row=row, column=1, sticky="w", padx=(0, 8), pady=3)
        row += 1

        row = self._section(inner, "Calibration Points", row)
        self._label(inner, "Point Count (≥2)").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        point_count_entry = self._entry(inner, width=8)
        point_count_entry.configure(textvariable=self._pt_count_var)
        point_count_entry.grid(row=row, column=1, sticky="w", padx=(0, 8), pady=3)
        row += 1

        # Load existing point count if editing.
        if existing:
            existing_points = existing.get("calibration", {}).get("points", [])
            if existing_points:
                self._pt_count_var.set(len(existing_points))

        tk.Button(inner, text="⇅  Swap Point Values", bg=ACCENT2, fg=DARK_BG,
                  font=FONT_UI, relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._swap_cal_points).grid(
                      row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 4))
        row += 1

        self._pt_frame = tk.Frame(inner, bg=DARK_BG)
        self._pt_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8)
        row += 1
        self._pt_frame.columnconfigure(1, weight=1)
        self._pt_frame.columnconfigure(2, weight=1)
        self._build_cal_points(existing)
        self._pt_count_var.trace_add("write", lambda *_: self._debounce_cal_points())
        return row

    def _build_rotary_fields(self, inner, entry, export, existing, row):
        row = self._section(inner, "Actions", row)
        increment = entry.get("actions", {}).get("increment", {})
        decrement = entry.get("actions", {}).get("decrement", {})
        row = self._row(inner, "Increment Device ID", "inc_deviceId", increment.get("deviceId", ""), row=row)
        row = self._row(inner, "Increment Action ID", "inc_actionId", increment.get("actionId", ""), row=row)
        row = self._row(inner, "Decrement Device ID", "dec_deviceId", decrement.get("deviceId", ""), row=row)
        row = self._row(inner, "Decrement Action ID", "dec_actionId", decrement.get("actionId", ""), row=row)
        return row

    def _build_switch_config(self, inner, entry, existing, row):
        row = self._section(inner, "Switch Config", row)
        self._label(inner, "Device ID *").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        device_id_var = tk.StringVar(value=entry.get("deviceId", ""))
        device_id_entry = self._entry(inner)
        device_id_entry.configure(textvariable=device_id_var)
        device_id_entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=3)
        self._vars["deviceId"] = device_id_var
        row += 1

        # Single shared Action ID for all positions.
        self._label(inner, "Action ID").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        action_id_var = tk.StringVar(value="")
        action_id_entry = self._entry(inner)
        action_id_entry.configure(textvariable=action_id_var)
        action_id_entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=3)
        self._vars["switch_actionId"] = action_id_var
        row += 1

        # Prefill the shared Action ID from the first position that has one.
        if existing:
            found = _first_switch_action_id(existing)
            if found:
                action_id_var.set(found)

        self._label(inner, "Min Value").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        min_entry = self._entry(inner, width=14)
        min_entry.configure(textvariable=self._min_var)
        min_entry.grid(row=row, column=1, sticky="w", padx=(0, 8), pady=3)
        row += 1

        self._label(inner, "Max Value").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        max_entry = self._entry(inner, width=14)
        max_entry.configure(textvariable=self._max_var)
        max_entry.grid(row=row, column=1, sticky="w", padx=(0, 8), pady=3)
        row += 1

        self._label(inner, "Position Count (≥2)").grid(row=row, column=0, sticky="w", padx=(8, 4), pady=3)
        count_entry = self._entry(inner, width=8)
        count_entry.configure(textvariable=self._pos_count_var)
        count_entry.grid(row=row, column=1, sticky="w", padx=(0, 8), pady=3)
        row += 1
        return row

    def _load_switch_bounds(self, existing):
        """Seed Min/Max/Count and the reversed flag from an existing switch's
        stored position values."""
        position_list = existing.get("positions", [])
        if not position_list:
            return
        try:
            first_value = float(position_list[0].get("argumentValue", 0.0))
            last_value = float(position_list[-1].get("argumentValue", 1.0))
        except (ValueError, TypeError):
            first_value, last_value = 0.0, 1.0
        # Keep the Min/Max bounds ascending and record whether the stored values
        # run high→low (a previously swapped switch).
        self._pos_reversed = first_value > last_value
        self._min_var.set(min(first_value, last_value))
        self._max_var.set(max(first_value, last_value))
        self._pos_count_var.set(len(position_list))

    def _debounce_positions(self):
        if self._pos_rebuild_after is not None:
            try:
                self.after_cancel(self._pos_rebuild_after)
            except Exception:  # noqa
                pass
        self._pos_rebuild_after = self.after(500, lambda: self._build_positions(None))

    def _build_switch_positions(self, inner, existing, row):
        row = self._section(inner, "Positions", row)
        tk.Button(inner, text="⇅  Swap Position Values", bg=ACCENT2, fg=DARK_BG,
                  font=FONT_UI, relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._swap_positions).grid(
                      row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 4))
        row += 1
        self._pos_frame = tk.Frame(inner, bg=DARK_BG)
        self._pos_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8)
        row += 1
        self._pos_frame.columnconfigure(1, weight=1)
        self._build_positions(existing)
        for var in (self._min_var, self._max_var, self._pos_count_var):
            var.trace_add("write", lambda *_: self._debounce_positions())
        return row

    def _build_switch_fields(self, inner, entry, export, existing, row):
        row = self._build_switch_config(inner, entry, existing, row)
        if existing:
            self._load_switch_bounds(existing)
        return self._build_switch_positions(inner, existing, row)

    def _build_dialog_buttons(self):
        button_row = tk.Frame(self, bg=DARK_BG)
        button_row.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(button_row, text="✓  Save Entry", bg=ACCENT, fg=DARK_BG, font=FONT_HEAD,
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  command=self._save).pack(side="right", padx=(4, 0))
        tk.Button(button_row, text="✕  Cancel", bg=MID_BG, fg=TEXT_SEC, font=FONT_UI,
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  command=self.destroy).pack(side="right")

    def _build_ui(self, existing):
        outer = tk.Frame(self, bg=DARK_BG)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        canvas = tk.Canvas(outer, bg=DARK_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=DARK_BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfig(window_id, width=event.width))
        canvas.bind_all("<MouseWheel>",
                        lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        inner.columnconfigure(1, weight=1)

        entry = existing or {}
        export = first_export(entry)

        row = self._section(inner, "Core", 0)
        row = self._row(inner, "Export ID(Arg) *", "id", export.get("id", ""), row=row)
        row = self._row(inner, "Device *",    "device", entry.get("device", ""), row=row)
        row = self._row(inner, "Name *",      "name",   entry.get("name", ""), row=row)
        # Default the description to the per-type text when none is set yet.
        default_description = entry.get("description") or DESCRIPTION_BY_TYPE.get(self.helios_type) or ""
        row = self._row(inner, "Description", "description", default_description, row=row)

        # Per-type fields, dispatched by helios type.
        builders = {
            DCS_LEADER + "PushButton":         self._build_pushbutton_fields,
            DCS_LEADER + "Axis":               self._build_axis_fields,
            DCS_LEADER + "NetworkValue":       self._build_network_fields,
            DCS_LEADER + "ScaledNetworkValue": self._build_scaled_fields,
            DCS_LEADER + "RotaryEncoder":      self._build_rotary_fields,
            DCS_LEADER + "Switch":             self._build_switch_fields,
        }
        builder = builders.get(self.helios_type)
        if builder:
            builder(inner, entry, export, existing, row)

        self._build_dialog_buttons()

    def _read_position_params(self):
        """Parse (count, minimum, maximum) from the position controls, clamping
        the count to at least 2. Returns None if any field doesn't parse."""
        try:
            count = int(self._pos_count_var.get())
            minimum = float(self._min_var.get())
            maximum = float(self._max_var.get())
        except (ValueError, tk.TclError):
            return None
        return max(2, count), minimum, maximum

    @staticmethod
    def _position_values(count, minimum, maximum, reverse):
        """Ascending argument values spanning minimum..maximum (the last pinned
        exactly to maximum so float drift can't push it off the bound), reversed
        when the switch has been swapped."""
        delta = ((maximum - minimum) / (count - 1)) if count > 1 else 0
        values = [round(maximum if i == count - 1 else minimum + i * delta, 3)
                  for i in range(count)]
        return values[::-1] if reverse else values

    @staticmethod
    def _position_names(existing, prior_names):
        """Names come from the existing entry on first build, otherwise from
        whatever the user has already typed (captured before the rebuild)."""
        if existing:
            return [position.get("name", "") for position in existing.get("positions", [])]
        return prior_names

    def _render_position_row(self, index, arg_value, name0):
        arg_label = tk.Label(self._pos_frame, text=format_float(arg_value), bg=MID_BG, fg=WARN,
                             font=FONT_MONO, width=16, anchor="w", relief="flat", padx=4)
        arg_label.grid(row=index + 1, column=1, padx=4, pady=2, sticky="w")

        name_var = tk.StringVar(value=name0)
        name_entry = self._entry(self._pos_frame, width=20)
        name_entry.configure(textvariable=name_var)
        name_entry.grid(row=index + 1, column=2, padx=4, pady=2, sticky="ew")

        index_label = tk.Label(self._pos_frame, text=str(index + 1), bg=DARK_BG, fg=TEXT_SEC,
                               font=FONT_UI)
        index_label.grid(row=index + 1, column=0, padx=4)
        self._pos_vars.append((arg_value, name_var))

    def _render_position_rows(self, count, values, names):
        headers = ["Pos", "Argument Value (auto)", "Position Name"]
        for col_index, header in enumerate(headers):
            tk.Label(self._pos_frame, text=header, bg=DARK_BG, fg=ACCENT, font=FONT_HEAD,
                     ).grid(row=0, column=col_index, sticky="w", padx=4, pady=(0, 4))
        for index in range(count):
            name0 = names[index] if index < len(names) else ""
            self._render_position_row(index, values[index], name0)

    def _build_positions(self, existing=None):
        self._pos_rebuild_after = None
        # A debounced rebuild can fire after the dialog has closed; bail out if
        # the frame is gone.
        if not self._pos_frame.winfo_exists():
            return
        # Preserve names already typed so a rebuild (count/min/max change, or a
        # value swap) keeps each name anchored to its row.
        prior_names = [name_var.get() for (_v, name_var) in self._pos_vars]
        for child in self._pos_frame.winfo_children():
            child.destroy()
        self._pos_vars = []

        params = self._read_position_params()
        if params is None:
            return
        count, minimum, maximum = params

        # Generate the (ascending) argument values, assigned in reverse when the
        # switch has been swapped; names stay put.
        values = self._position_values(count, minimum, maximum, self._pos_reversed)
        names = self._position_names(existing, prior_names)
        self._render_position_rows(count, values, names)

    def _swap_positions(self):
        """Reverse the switch's position values while keeping each entered name
        on its row. The reversal is sticky, so it survives later count or
        min/max edits until swapped back."""
        self._pos_reversed = not self._pos_reversed
        self._build_positions(None)

    def _swap_cal_points(self):
        """Reverse the Value column of the calibration points while leaving each
        entered Mapped Value in place."""
        reversed_values = [value_var.get() for (value_var, _m) in self._pt_vars][::-1]
        for (value_var, _mapped_var), new_value in zip(self._pt_vars, reversed_values):
            value_var.set(new_value)

    def _build_cal_points(self, existing=None):
        """Build N calibration-point rows (Value / Mapped Value), mirroring the
        dynamic switch positions table. Typed values survive a count change."""
        self._pt_rebuild_after = None
        # A debounced rebuild can fire after the dialog has closed; bail out if
        # the frame is gone.
        if not self._pt_frame.winfo_exists():
            return
        try:
            count = int(self._pt_count_var.get())
        except (ValueError, tk.TclError):
            return
        count = max(2, count)

        # Capture currently-typed values so they aren't lost when the count changes
        current = [(value_var.get(), mapped_var.get()) for (value_var, mapped_var) in self._pt_vars]

        for child in self._pt_frame.winfo_children():
            child.destroy()
        self._pt_vars = []

        points = existing.get("calibration", {}).get("points", []) if existing else []

        headers = ["Pt", "Value", "Mapped Value"]
        for col_index, header in enumerate(headers):
            tk.Label(self._pt_frame, text=header, bg=DARK_BG, fg=ACCENT, font=FONT_HEAD,
                     ).grid(row=0, column=col_index, sticky="w", padx=4, pady=(0, 4))

        for index in range(count):
            if index < len(points):
                value0 = points[index].get("value", "")
                mapped0 = points[index].get("mappedValue", "")
            elif index < len(current):
                value0, mapped0 = current[index]
            else:
                value0, mapped0 = "", ""

            index_label = tk.Label(self._pt_frame, text=str(index + 1), bg=DARK_BG, fg=TEXT_SEC, font=FONT_UI)
            index_label.grid(row=index + 1, column=0, padx=4)

            value_var = tk.StringVar(value=value0)
            value_entry = self._entry(self._pt_frame, width=20)
            value_entry.configure(textvariable=value_var)
            value_entry.grid(row=index + 1, column=1, padx=4, pady=2, sticky="ew")

            mapped_var = tk.StringVar(value=mapped0)
            mapped_entry = self._entry(self._pt_frame, width=20)
            mapped_entry.configure(textvariable=mapped_var)
            mapped_entry.grid(row=index + 1, column=2, padx=4, pady=2, sticky="ew")

            self._pt_vars.append((value_var, mapped_var))

    @staticmethod
    def _check_id_value(value, label, required):
        """Return an error string for one id field, or None when it's valid.
        Blank is allowed unless the field is required; a non-blank value must be
        a positive integer."""
        parsed = positive_int_or_none(value)
        if parsed is None:
            return f"{label} is required and must be a positive integer." if required else None
        if parsed is False:
            return f"{label} must be a positive integer."
        return None

    def _validate_id_fields(self, values):
        """Ensure every ID field is a positive integer. The Export ID(Arg) is
        required; the rest are optional but must be positive integers when
        filled in. Returns an error string, or None when everything is valid."""
        checks = [("id", "Export ID(Arg)", True)]
        checks += [(key, label, False)
                   for key, label in _OPTIONAL_ID_CHECKS_BY_TYPE.get(self.helios_type, [])]
        for key, label, required in checks:
            error = self._check_id_value(values.get(key, ""), label, required)
            if error:
                return error
        return None

    def _validate_required(self, values):
        """Return an error message for the first missing required text field, or
        None when Export ID(Arg), Device and Name are all present."""
        for key, label in (("id", "Export ID(Arg)"), ("device", "Device"), ("name", "Name")):
            if not values.get(key, ""):
                return f"{label} is required."
        return None

    def _is_edit_index(self, index):
        """True when `index` is the function currently being edited (so it is
        skipped by the duplicate scans)."""
        return self.edit_index is not None and index == self.edit_index

    @staticmethod
    def _function_uses_id(function, export_id):
        for export in function.get("exports", []):
            if str(export.get("id", "")).strip() == export_id:
                return True
        return False

    def _find_entry_collisions(self, entry):
        """Every existing function the entry-to-be-saved would collide with, and
        why — matching the Collisions tab rules: a shared Export ID(Arg), a shared
        Device ID + Action ID, or a shared Device + Name (both must match).
        Returns a list of (other_function, [reason, ...])."""
        new_export = str(first_export(entry).get("id", "")).strip()
        new_device_id = str(get_primary_device_id(entry)).strip()
        new_action_id = str(get_primary_action_id(entry)).strip()
        new_device = str(entry.get("device", "")).strip()
        new_name = str(entry.get("name", "")).strip()
        collisions = []
        for index, other in enumerate(self.functions):
            if self._is_edit_index(index):
                continue
            reasons = []
            if new_export and self._function_uses_id(other, new_export):
                reasons.append(f"Export ID(Arg) {new_export}")
            if new_device_id and new_action_id \
                    and str(get_primary_device_id(other)).strip() == new_device_id \
                    and str(get_primary_action_id(other)).strip() == new_action_id:
                reasons.append(
                    f"Device ID {new_device_id} + Action ID {new_action_id}")
            if new_name \
                    and str(other.get("device", "")).strip() == new_device \
                    and str(other.get("name", "")).strip() == new_name:
                reasons.append(f"Device + Name '{new_device} · {new_name}'")
            if reasons:
                collisions.append((other, reasons))
        return collisions

    def _confirm_collisions(self, collisions):
        """Tell the user exactly what this entry collides with (and why) before it
        lands on the Collisions tab; return True to add it anyway."""
        lines = ["Heads up — this entry will be listed on the Collisions tab.",
                 "", "It collides with:"]
        for other, reasons in collisions[:12]:
            other_type = TAB_LABELS.get(other.get("heliosType", ""),
                                        other.get("heliosType", "").split(".")[-1])
            label = " · ".join(part for part in
                               (str(other.get("device", "")).strip(),
                                str(other.get("name", "")).strip()) if part) or "(unnamed)"
            lines.append(f"  • {label} ({other_type}) — shares {'; '.join(reasons)}")
        if len(collisions) > 12:
            lines.append(f"  …and {len(collisions) - 12} more.")
        lines += ["", "Collisions are allowed but flagged for review.",
                  "", "Add this entry anyway?"]
        return messagebox.askyesno("Collision Detected", "\n".join(lines), parent=self)

    def _save_pushbutton(self, entry, values):
        entry["buttons"][0]["deviceId"]  = to_int(values.get("btn_deviceId", ""))
        entry["buttons"][0]["pushId"]    = to_int(values.get("pushId", ""))
        entry["buttons"][0]["releaseId"] = to_int(values.get("releaseId", ""))

    def _save_axis(self, entry, values):
        entry["argumentMin"] = values.get("argumentMin", "")
        entry["argumentMax"] = values.get("argumentMax", "")
        entry["actions"]["set"]["deviceId"] = to_int(values.get("set_deviceId", ""))
        entry["actions"]["set"]["actionId"] = to_int(values.get("set_actionId", ""))

    def _save_network(self, entry, values):
        export_format = values.get("format", "").strip()
        if export_format:
            entry["exports"][0]["format"] = export_format

    def _save_scaled(self, entry, values):
        self._save_network(entry, values)  # identical export-format handling
        entry["unit"] = self._unit_var.get().strip() or "Numeric"
        entry["exposeunscaledvalue"] = bool(self._expose_unscaled_var.get())
        entry["calibration"]["points"] = [
            {"value": value_var.get().strip(), "mappedValue": mapped_var.get().strip()}
            for (value_var, mapped_var) in self._pt_vars
        ]

    def _save_rotary(self, entry, values):
        entry["actions"]["increment"]["deviceId"] = to_int(values.get("inc_deviceId", ""))
        entry["actions"]["increment"]["actionId"] = to_int(values.get("inc_actionId", ""))
        entry["actions"]["decrement"]["deviceId"] = to_int(values.get("dec_deviceId", ""))
        entry["actions"]["decrement"]["actionId"] = to_int(values.get("dec_actionId", ""))

    def _save_switch(self, entry, values):
        entry["deviceId"] = to_int(values.get("deviceId", ""))
        shared_action = to_int(values.get("switch_actionId", ""))
        entry["positions"] = [
            {"argumentValue": format_float(arg_value),
             "name": name_var.get().strip(),
             "actionId": shared_action}
            for (arg_value, name_var) in self._pos_vars
        ]

    def _populate_entry_fields(self, helios_type, entry, values):
        """Fill the type-specific fields of a freshly built entry from the form
        values, dispatched by helios type."""
        savers = {
            DCS_LEADER + "PushButton":         self._save_pushbutton,
            DCS_LEADER + "Axis":               self._save_axis,
            DCS_LEADER + "NetworkValue":       self._save_network,
            DCS_LEADER + "ScaledNetworkValue": self._save_scaled,
            DCS_LEADER + "RotaryEncoder":      self._save_rotary,
            DCS_LEADER + "Switch":             self._save_switch,
        }
        saver = savers.get(helios_type)
        if saver:
            saver(entry, values)

    def _save(self):
        values = {key: var.get().strip() for key, var in self._vars.items()}

        # Validate required text fields, then that every ID field is a positive int.
        error = self._validate_required(values)
        if error:
            messagebox.showerror("Missing Field", error, parent=self)
            return
        id_error = self._validate_id_fields(values)
        if id_error:
            messagebox.showerror("Invalid ID", id_error, parent=self)
            return

        export_id = values.get("id", "")
        device = values.get("device", "")
        name = values.get("name", "")

        helios_type = self.helios_type
        entry = make_blank_entry(helios_type)
        entry["device"] = device
        entry["name"] = name
        entry["description"] = values.get("description", "")
        entry["exports"][0]["id"] = to_int(export_id)
        self._populate_entry_fields(helios_type, entry, values)

        # Alert on anything that would put this entry on the Collisions tab —
        # a shared Export ID(Arg), Device ID + Action ID, or Name — naming each
        # colliding function and the cause. Collisions are allowed, so the user
        # can proceed or cancel.
        collisions = self._find_entry_collisions(entry)
        if collisions and not self._confirm_collisions(collisions):
            return

        self.result = entry
        self.destroy()


# ── Change-type dialog ──────────────────────────────────────────────────────────
class ChangeTypeDialog(tk.Toplevel):
    """Small dialog to pick a new helios type for an existing function.
    Sets self.result to the chosen full helios type string (e.g.
    'DCS.Common.Switch'), or leaves it None on cancel / no change."""
    # Map friendly tab labels back to their full helios type strings.
    LABEL_TO_TYPE = {label: helios_type for helios_type, label in TAB_LABELS.items()}

    def __init__(self, parent, entry, count=1):
        super().__init__(parent)
        self.title("Change Helios Type")
        self.configure(bg=DARK_BG)
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._entry = entry
        self._count = count

        current_type = entry.get("heliosType", "")
        self._label_var = tk.StringVar(value=TAB_LABELS.get(current_type, current_type))

        outer = tk.Frame(self, bg=DARK_BG)
        outer.pack(fill="both", expand=True, padx=18, pady=16)
        outer.columnconfigure(1, weight=1)

        tk.Label(outer, text="Change Helios Type", bg=DARK_BG, fg=ACCENT,
                 font=FONT_TITLE).grid(row=0, column=0, columnspan=2,
                                       sticky="w", pady=(0, 12))

        name = entry.get("name", "") or "(unnamed)"
        device = entry.get("device", "") or "(no device)"
        export_id = first_export(entry).get("id", "")
        if self._count > 1:
            function_text = f"Functions:  {self._count} selected (showing '{name}')"
        else:
            function_text = f"Function:   {name}"
        tk.Label(outer, text=function_text, bg=DARK_BG, fg=TEXT_PRI,
                 font=FONT_UI).grid(row=1, column=0, columnspan=2, sticky="w")
        tk.Label(outer, text=f"Device:     {device}", bg=DARK_BG, fg=TEXT_SEC,
                 font=FONT_UI).grid(row=2, column=0, columnspan=2, sticky="w")
        tk.Label(outer, text=f"Export ID(Arg):  {export_id}", bg=DARK_BG, fg=TEXT_SEC,
                 font=FONT_UI).grid(row=3, column=0, columnspan=2, sticky="w",
                                    pady=(0, 12))

        tk.Label(outer, text="Current type", bg=DARK_BG, fg=TEXT_SEC,
                 font=FONT_UI).grid(row=4, column=0, sticky="w", pady=3)
        tk.Label(outer, text=TAB_LABELS.get(current_type, current_type), bg=DARK_BG, fg=WARN,
                 font=FONT_MONO).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=3)

        tk.Label(outer, text="New type", bg=DARK_BG, fg=TEXT_SEC,
                 font=FONT_UI).grid(row=5, column=0, sticky="w", pady=3)
        combo = ttk.Combobox(outer, textvariable=self._label_var,
                             values=[TAB_LABELS[helios_type] for helios_type in HELIOS_TYPES],
                             state="readonly", width=26, font=FONT_UI)
        combo.grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=3)

        note = ("Keeps device, name, description and Export ID(Arg) (plus the device "
                "ID where it maps).\nAll other type-specific fields reset to the "
                "new type's defaults — open\nthe entry with Edit afterwards to "
                "fill them in.")
        tk.Label(outer, text=note, bg=DARK_BG, fg=TEXT_SEC, font=FONT_UI,
                 justify="left").grid(row=6, column=0, columnspan=2,
                                      sticky="w", pady=(12, 0))

        button_row = tk.Frame(self, bg=DARK_BG)
        button_row.pack(fill="x", padx=18, pady=(0, 14))
        tk.Button(button_row, text="✓  Change Type", bg=ACCENT, fg=DARK_BG,
                  font=FONT_HEAD, relief="flat", padx=16, pady=6, cursor="hand2",
                  command=self._confirm).pack(side="right", padx=(4, 0))
        tk.Button(button_row, text="✕  Cancel", bg=MID_BG, fg=TEXT_SEC, font=FONT_UI,
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  command=self.destroy).pack(side="right")

        self.update_idletasks()
        win_w, win_h = self.winfo_reqwidth(), self.winfo_reqheight()
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{win_w}x{win_h}+{(screen_w - win_w) // 2}+{(screen_h - win_h) // 2}")

    def _confirm(self):
        new_type = self.LABEL_TO_TYPE.get(self._label_var.get())
        if not new_type:
            self.destroy()
            return
        if new_type == self._entry.get("heliosType", ""):
            messagebox.showinfo("No Change",
                                "That's already this function's type.",
                                parent=self)
            return
        self.result = new_type
        self.destroy()


# ── Column definitions per type ────────────────────────────────────────────────
def get_columns(helios_type):
    base = [("id", "Export ID(Arg)", 60), ("device", "Device", 100),
            ("name", "Name", 120), ("description", "Description", 180)]
    if helios_type == DCS_LEADER + "PushButton":
        return base + [("btn_deviceId", "Btn DeviceID", 90), ("pushId", "Push ID", 80),
                       ("releaseId", "Release ID", 80)]
    if helios_type == DCS_LEADER + "Axis":
        return base + [("argumentMin", "Arg Min", 70), ("argumentMax", "Arg Max", 70),
                       ("set_deviceId", "Set DevID", 80), ("set_actionId", "Set ActID", 80)]
    if helios_type == DCS_LEADER + "ScaledNetworkValue":
        return base + [("points", "Calibration Points", 130)]
    if helios_type == DCS_LEADER + "RotaryEncoder":
        return base + [("inc_deviceId", "Inc DevID", 80), ("inc_actionId", "Inc ActID", 80),
                       ("dec_deviceId", "Dec DevID", 80), ("dec_actionId", "Dec ActID", 80)]
    if helios_type == DCS_LEADER + "Switch":
        return base + [("deviceId", "DeviceID", 80), ("actionId", "Action ID", 80),
                       ("positions", "Positions", 120)]
    return base


def flatten_entry(entry):
    """Flatten a functions entry to a dict for display."""
    helios_type = entry.get("heliosType", "")
    export = first_export(entry)
    flat = {
        "id":          str(export.get("id", "")),
        "device":      entry.get("device", ""),
        "name":        entry.get("name", ""),
        "description": entry.get("description", ""),
    }
    if helios_type == DCS_LEADER + "PushButton":
        button = entry.get("buttons", [{}])[0]
        flat["btn_deviceId"] = str(button.get("deviceId", ""))
        flat["pushId"]       = str(button.get("pushId", ""))
        flat["releaseId"]    = str(button.get("releaseId", ""))
    elif helios_type == DCS_LEADER + "Axis":
        # Real DCS/Helios files use the correctly spelled "argument*" keys,
        # while this editor historically wrote "argument*". Read either so
        # both imported and externally-authored profiles display correctly.
        flat["argumentMin"]  = format_float(entry.get("argumentMin", ""))
        flat["argumentMax"]  = format_float(entry.get("argumentMax", ""))
        set_action = entry.get("actions", {}).get("set", {})
        flat["set_deviceId"]  = str(set_action.get("deviceId", ""))
        flat["set_actionId"]  = str(set_action.get("actionId", ""))
    elif helios_type == DCS_LEADER + "ScaledNetworkValue":
        points = entry.get("calibration", {}).get("points", [])
        flat["points"] = f"{len(points)} points"
    elif helios_type == DCS_LEADER + "RotaryEncoder":
        increment = entry.get("actions", {}).get("increment", {})
        decrement = entry.get("actions", {}).get("decrement", {})
        flat["inc_deviceId"] = str(increment.get("deviceId", ""))
        flat["inc_actionId"] = str(increment.get("actionId", ""))
        flat["dec_deviceId"] = str(decrement.get("deviceId", ""))
        flat["dec_actionId"] = str(decrement.get("actionId", ""))
    elif helios_type == DCS_LEADER + "Switch":
        flat["deviceId"]  = str(entry.get("deviceId", ""))
        positions = entry.get("positions", [])
        flat["positions"] = f"{len(positions)} positions"
        # All positions share one action id now; surface the first non-empty one
        action_id = ""
        for position in positions:
            candidate = str(position.get("actionId", "")).strip()
            if candidate:
                action_id = candidate
                break
        flat["actionId"] = action_id
    return flat


# ── Main App ───────────────────────────────────────────────────────────────────
class HeliosEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Helios Interface Editor")
        self._set_window_icon()
        self.configure(bg=DARK_BG)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = max(900, (screen_w * 33) // 80)
        win_h = max(700, (screen_h * 3) // 4)
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2)
        self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.state("normal")

        self._data = {
            "source": "User", "version": "Initial", "commit": "", "type": "DCS",
            "name": "", "module": "", "vehicles": [], "functions": []
        }
        self._current_file = None
        # Active save / Full View ordering: "deviceaction" or "devicename".
        self._sort_method = "deviceaction"
        # Remember the device of the most recently added entry so the next Add
        # dialog can pre-fill the same device name + id.
        self._last_added_device = ""
        self._last_added_device_id = ""
        self._last_added_function = None
        self._last_saved_function = None
        self._next_saved_session_index = 1
        self._next_created_session_index = 1
        self._trees = {}        # heliosType -> Treeview
        self._tab_count_lbls = {}   # heliosType -> per-tab count Label
        self._sort_col = {}     # heliosType -> (col, reverse)
        self._theme_name = "dark"
        self._header_frame = None
        # Baseline used to detect unsaved changes (set after the UI is built).
        self._clean_signature = None

        # Header search state (persists across theme rebuilds)
        self._search_matches = []     # function indices matching the last query
        self._search_pos = -1         # which match we're currently parked on
        self._search_last_query = None

        self._setup_styles()
        self._build_menu()
        self._build_header()
        self._build_tabs()
        self._refresh_all()

        # Closing the window (the X button) goes through the same unsaved-change
        # prompt as File ▸ Exit.
        self.protocol("WM_DELETE_WINDOW", self._on_exit)
        # The freshly-opened, empty profile is the initial clean baseline.
        self._mark_clean()

    # ── window icon ──────────────────────────────────────────────────────────────
    def _set_window_icon(self):
        """Use Helios.ico for the title bar / taskbar instead of the default Tk
        feather. `default=` applies it to this window and every dialog opened
        afterwards. Silently keeps the default icon if the file isn't found
        (e.g. Helios.ico wasn't kept next to the script)."""
        icon_path = resource_path(APP_ICON_FILE)
        if not os.path.exists(icon_path):
            return
        try:
            self.iconbitmap(default=icon_path)
        except Exception:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    # ── styles ─────────────────────────────────────────────────────────────────
    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",        background=DARK_BG, borderwidth=0)
        style.configure("TNotebook.Tab",    background=MID_BG,  foreground=TEXT_SEC,
                        font=FONT_UI, padding=[14, 6], borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", PANEL_BG)],
                  foreground=[("selected", ACCENT)])
        style.configure("Treeview",         background=ROW_ODD, fieldbackground=ROW_ODD,
                        foreground=TEXT_PRI, font=FONT_MONO, rowheight=24, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_BG, foreground=TEXT_HEAD,
                        font=FONT_HEAD, relief="flat")
        style.map("Treeview",
                  background=[("selected", ROW_SEL)],
                  foreground=[("selected", TEXT_PRI)])
        style.configure("Vertical.TScrollbar", background=MID_BG, troughcolor=DARK_BG,
                        arrowcolor=TEXT_SEC, borderwidth=0)

    # ── menu ───────────────────────────────────────────────────────────────────
    def _build_menu(self):
        menu_bar = tk.Menu(self, bg=MID_BG, fg=TEXT_PRI, activebackground=ACCENT,
                           activeforeground=DARK_BG, relief="flat", font=FONT_UI)
        self.configure(menu=menu_bar)
        file_menu = tk.Menu(menu_bar, tearoff=0, bg=MID_BG, fg=TEXT_PRI,
                            activebackground=ACCENT, activeforeground=DARK_BG, font=FONT_UI)
        menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New",        command=self._new,    accelerator="Ctrl+N")
        file_menu.add_command(label="Open…",      command=self._open,   accelerator="Ctrl+O")
        file_menu.add_command(label="Save",       command=self._save,   accelerator="Ctrl+S")
        file_menu.add_command(label="Save As…",   command=self._save_as)
        # file_menu.add_separator()
        # # Import moved into the File menu and renamed; it now searches the chosen
        # # cockpit folder and all of its subfolders for the clickabledata file.
        # file_menu.add_command(label="Import DCS Cockpit folder…",
        #                       command=self._import_dcs_folder,
        #                       accelerator="Ctrl+I")
        file_menu.add_separator()
        toggle_label = ("Switch to Light Mode" if self._theme_name == "dark"
                        else "Switch to Dark Mode")
        file_menu.add_command(label=toggle_label, command=self._toggle_theme)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",       command=self._on_exit)

        self.bind_all("<Control-n>", lambda event: self._new())
        self.bind_all("<Control-o>", lambda event: self._open())
        self.bind_all("<Control-s>", lambda event: self._save())
        # self.bind_all("<Control-i>", lambda event: self._import_dcs_folder())

    # ── theme switching ─────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self._set_theme("light" if self._theme_name == "dark" else "dark")

    def _set_theme(self, name):
        """Switch the colour scheme and rebuild the chrome so every widget picks
        up the new palette. Field values and the active tab are preserved."""
        if name == self._theme_name:
            return
        self._sync_header_to_data()
        try:
            current_tab = self._nb.index(self._nb.select())
        except Exception:
            current_tab = 0

        self._theme_name = name
        apply_theme(LIGHT_THEME if name == "light" else DARK_THEME)

        self.configure(bg=DARK_BG)
        self._setup_styles()
        self._build_menu()

        # Rebuild header + tabs against the new palette.
        if self._header_frame is not None:
            self._header_frame.destroy()
        self._nb.destroy()
        self._build_header()
        self._build_tabs()
        self._sync_data_to_header()
        self._refresh_all()

        try:
            self._nb.select(current_tab)
        except Exception:
            pass

    # ── header ─────────────────────────────────────────────────────────────────
    def _build_header(self):
        header = tk.Frame(self, bg=PANEL_BG, pady=10)
        header.pack(fill="x", padx=0, pady=0)
        self._header_frame = header

        tk.Label(header, text="HELIOS INTERFACE EDITOR", bg=PANEL_BG, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=14,
                                                     sticky="w", padx=16, pady=(0, 8))

        self._hdr_vars = {}

        fields = [
            ("Source",  "source",  12),
            ("Version", "version", 10),
            ("Commit",  "commit",  12),
            ("Type",    "type",    12),
            ("Module",  "module",  14),
            ("Vehicles (comma-sep)", "vehicles_str", 20),
        ]
        col = 0
        for label, key, width in fields:
            tk.Label(header, text=label, bg=PANEL_BG, fg=TEXT_SEC, font=FONT_UI
                     ).grid(row=1, column=col, sticky="w", padx=(12, 2))
            var = tk.StringVar()
            entry = tk.Entry(header, textvariable=var, width=width, bg=MID_BG, fg=TEXT_PRI,
                             insertbackground=TEXT_PRI, relief="flat", font=FONT_MONO,
                             highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER)
            entry.grid(row=2, column=col, sticky="ew", padx=(12, 2), pady=2)
            self._hdr_vars[key] = var
            col += 1

        # Name (read-only derived)
        tk.Label(header, text="Name (auto)", bg=PANEL_BG, fg=TEXT_SEC, font=FONT_UI
                 ).grid(row=1, column=col, sticky="w", padx=(12, 2))
        self._name_lbl = tk.Label(header, text="", bg=MID_BG, fg=WARN, font=FONT_MONO,
                                  width=22, anchor="w", relief="flat", padx=4)
        self._name_lbl.grid(row=2, column=col, sticky="ew", padx=(12, 2), pady=2)
        col += 1

        # Max ID
        tk.Label(header, text="Max id used", bg=PANEL_BG, fg=TEXT_SEC, font=FONT_UI
                 ).grid(row=1, column=col, sticky="w", padx=(16, 2))
        self._max_id_lbl = tk.Label(header, text="0", bg=MID_BG, fg=SUCCESS, font=("Consolas", 13, "bold"),
                                    width=8, anchor="center", relief="flat", padx=4)
        self._max_id_lbl.grid(row=2, column=col, padx=(16, 12), pady=2)
        col += 1

        # Total devices (all types combined)
        tk.Label(header, text="Total devices", bg=PANEL_BG, fg=TEXT_SEC, font=FONT_UI
                 ).grid(row=1, column=col, sticky="w", padx=(16, 2))
        self._total_count_lbl = tk.Label(header, text="0", bg=MID_BG, fg=ACCENT,
                                         font=("Consolas", 13, "bold"),
                                         width=8, anchor="center", relief="flat", padx=4)
        self._total_count_lbl.grid(row=2, column=col, padx=(16, 12), pady=2)

        # Traces
        for key in ("type", "module"):
            self._hdr_vars[key].trace_add("write", self._update_name)

        # Search strip — find a function by name/device/id and jump to its tab.
        search_frame = tk.Frame(header, bg=PANEL_BG)
        search_frame.grid(row=3, column=0, columnspan=15, sticky="w", padx=12, pady=(8, 0))

        tk.Label(search_frame, text="🔍  Search", bg=PANEL_BG, fg=TEXT_SEC,
                 font=FONT_UI).pack(side="left", padx=(0, 6))

        self._search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self._search_var, width=36,
                                bg=MID_BG, fg=TEXT_PRI, insertbackground=TEXT_PRI,
                                relief="flat", font=FONT_MONO, highlightthickness=1,
                                highlightcolor=ACCENT, highlightbackground=BORDER)
        search_entry.pack(side="left")
        search_entry.bind("<Return>", lambda event: self._do_search())

        tk.Button(search_frame, text="Find", bg=ACCENT, fg=DARK_BG, font=FONT_HEAD,
                  relief="flat", padx=14, pady=3, cursor="hand2",
                  command=self._do_search).pack(side="left", padx=(6, 0))

        self._search_status = tk.Label(search_frame, text="", bg=PANEL_BG, fg=TEXT_SEC,
                                       font=FONT_UI)
        self._search_status.pack(side="left", padx=(10, 0))

        tk.Label(search_frame, text="(Enter cycles through matches)", bg=PANEL_BG,
                 fg=TEXT_SEC, font=FONT_UI).pack(side="left", padx=(10, 0))

        # Global action: stamp a standard description onto every function based
        # on its helios type (ScaledNetworkValue is intentionally left blank).
        tk.Button(search_frame, text="🏷  Set Descriptions", bg=ACCENT2, fg=DARK_BG,
                  font=FONT_HEAD, relief="flat", padx=14, pady=3, cursor="hand2",
                  command=self._apply_descriptions).pack(side="left", padx=(24, 0))

        # Global action: give every device that has no Export ID(Arg) the next free id,
        # counting up from the highest id currently in use.
        tk.Button(search_frame, text="🔢  Auto-fill Id's", bg=ACCENT, fg=DARK_BG,
                  font=FONT_HEAD, relief="flat", padx=14, pady=3, cursor="hand2",
                  command=self._auto_fill_ids).pack(side="left", padx=(10, 0))

        # Populate
        self._hdr_vars["source"].set(self._data.get("source", "User"))

    # ── search ─────────────────────────────────────────────────────────────────
    def _function_matches_query(self, function, query):
        """True when `query` (already lowercased) appears in any searchable
        field of `function`: name, device, description, export id, the
        prettified name/device, or the primary device/action ids."""
        haystack = [
            str(function.get("name", "")),
            str(function.get("device", "")),
            str(function.get("description", "")),
            prettify_label(function.get("name", "")),
            prettify_label(function.get("device", "")),
            str(get_primary_device_id(function)),
            str(get_primary_action_id(function)),
        ]
        for export in function.get("exports", []):
            haystack.append(str(export.get("id", "")))
            ### Edit here 
        return any(query in field.lower() for field in haystack)

    def _do_search(self):
        """Find functions matching the search box and jump to the first match's
        tab/row. Pressing Find/Enter again with the same query cycles to the
        next match (wrapping around)."""
        query = self._search_var.get().strip().lower()
        if not query:
            self._search_matches = []
            self._search_pos = -1
            self._search_last_query = None
            self._search_status.configure(text="", fg=TEXT_SEC)
            return

        matches = [index for index, function in enumerate(self._data["functions"])
                   if self._function_matches_query(function, query)]

        if not matches:
            self._search_matches = []
            self._search_pos = -1
            self._search_last_query = query
            self._search_status.configure(text="No matches", fg=ERROR)
            return

        # Same query as last time → advance to the next match; otherwise restart.
        if query == self._search_last_query and matches == self._search_matches:
            self._search_pos = (self._search_pos + 1) % len(matches)
        else:
            self._search_pos = 0

        self._search_last_query = query
        self._search_matches = matches

        function_index = matches[self._search_pos]
        helios_type = self._data["functions"][function_index].get("heliosType", "")
        self._select_tab(helios_type)
        self._select_function(helios_type, function_index)
        self._search_status.configure(
            text=f"{self._search_pos + 1} / {len(matches)}", fg=SUCCESS)

    def _update_name(self, *_):
        profile_type = self._hdr_vars["type"].get().strip()
        module = self._hdr_vars["module"].get().strip()
        name = f"{profile_type} {module}".strip()
        self._name_lbl.configure(text=name)
        self._data["name"] = name

    def _sync_header_to_data(self):
        for key in ("source", "version", "commit", "type", "module"):
            self._data[key] = self._hdr_vars[key].get().strip()
        vehicles_str = self._hdr_vars["vehicles_str"].get().strip()
        self._data["vehicles"] = [vehicle.strip() for vehicle in vehicles_str.split(",") if vehicle.strip()]
        self._update_name(None)
        self._update_max_id()

    def _sync_data_to_header(self):
        for key in ("source", "version", "commit", "type", "module"):
            self._hdr_vars[key].set(self._data.get(key, ""))
        self._hdr_vars["vehicles_str"].set(", ".join(self._data.get("vehicles", [])))
        self._update_name()
        self._update_max_id()

    def _update_max_id(self):
        highest = max_id(self._data.get("functions", []))
        self._max_id_lbl.configure(text=str(highest))

    # ── tabs ───────────────────────────────────────────────────────────────────
    def _build_tabs(self):
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=0, pady=0)
        self._trees = {}
        self._tab_count_lbls = {}

        for helios_type in HELIOS_TYPES:
            frame = tk.Frame(self._nb, bg=PANEL_BG)
            self._nb.add(frame, text=TAB_LABELS[helios_type])
            self._build_tab(frame, helios_type)

        # A read-only "Full View" tab that shows every function exactly as it
        # would be written to the save file (prettified labels, device-then-
        # action order, all numbers as strings).
        full_frame = tk.Frame(self._nb, bg=PANEL_BG)
        self._nb.add(full_frame, text="Full View")
        self._build_full_view_tab(full_frame)

        # A "Collisions" tab that flags functions sharing an Export ID(Arg), or a
        # Device ID + Action ID, and highlights the shared value.
        collisions_frame = tk.Frame(self._nb, bg=PANEL_BG)
        self._nb.add(collisions_frame, text="Collisions")
        self._build_collisions_tab(collisions_frame)

        # A "Validation" tab that lists functions whose Argument Min equals their
        # Argument Max (a degenerate axis range).
        validation_frame = tk.Frame(self._nb, bg=PANEL_BG)
        self._nb.add(validation_frame, text="Value Check")
        self._build_validation_tab(validation_frame)

        # Auto-refresh the Collisions / Full View / Validation tabs whenever they
        # are opened.
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_validation_tab(self, frame):
        toolbar = tk.Frame(frame, bg=PANEL_BG, pady=6)
        toolbar.pack(fill="x", padx=8)
        tk.Label(toolbar,
                 text="Functions with a configuration problem "
                      "(see the Issue column for the reason)",
                 bg=PANEL_BG, fg=TEXT_HEAD, font=FONT_HEAD).pack(side="left")
        tk.Button(toolbar, text="⟳  Refresh", bg=ACCENT, fg=DARK_BG, font=FONT_UI,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._refresh_validation).pack(side="left", padx=(12, 0))
        self._validation_count_lbl = tk.Label(toolbar, text="", bg=PANEL_BG,
                                               fg=ACCENT2, font=FONT_HEAD)
        self._validation_count_lbl.pack(side="right", padx=(8, 8))

        container = tk.Frame(frame, bg=PANEL_BG)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        vertical_sb = ttk.Scrollbar(container, orient="vertical")
        horizontal_sb = ttk.Scrollbar(container, orient="horizontal")

        columns = [("id", "Export ID(Arg)", 70), ("type", "Type", 130),
                   ("device", "Device", 140), ("name", "Name", 160),
                   ("deviceId", "Device ID", 90), ("actionId", "Action ID", 90),
                   ("issue", "Issue", 340)]
        column_ids = [column[0] for column in columns]

        tree = ttk.Treeview(container, columns=column_ids, show="headings",
                            yscrollcommand=vertical_sb.set, xscrollcommand=horizontal_sb.set,
                            selectmode="extended")
        vertical_sb.configure(command=tree.yview)
        horizontal_sb.configure(command=tree.xview)
        for column_id, column_label, column_width in columns:
            centered = column_id in CENTERED_COLUMNS
            heading_kwargs = {"text": column_label}
            column_kwargs = {"width": column_width, "minwidth": 50, "stretch": True}
            if centered:
                heading_kwargs["anchor"] = "center"
                column_kwargs["anchor"] = "center"
            tree.heading(column_id, **heading_kwargs)
            tree.column(column_id, **column_kwargs)
        tree.tag_configure("even", background=ROW_EVEN)
        tree.tag_configure("odd",  background=ROW_ODD)

        vertical_sb.pack(side="right",  fill="y")
        horizontal_sb.pack(side="bottom", fill="x")
        tree.pack(side="left",  fill="both", expand=True)

        self._validation_tree = tree
        self._refresh_validation()

    def _refresh_validation(self):
        tree = getattr(self, "_validation_tree", None)
        if tree is None:
            return
        matches = []
        for index, function in enumerate(self._data.get("functions", [])):
            issue = validation_issue(function)
            if issue is not None:
                matches.append((index, function, issue))

        tree.delete(*tree.get_children())
        for row_number, (function_index, function, issue) in enumerate(matches):
            device_id, action_id = best_effort_ids(function)
            helios_type = function.get("heliosType", "")
            type_label = TAB_LABELS.get(helios_type, helios_type.split(".")[-1])
            values = (
                str(first_export(function).get("id", "")),
                type_label,
                function.get("device", ""),
                function.get("name", ""),
                device_id,
                action_id,
                issue,
            )
            shade = "even" if row_number % 2 == 0 else "odd"
            tree.insert("", "end", values=values, tags=(str(function_index), shade))

        count_label = getattr(self, "_validation_count_lbl", None)
        if count_label is not None:
            count = len(matches)
            count_label.configure(text=f"{count} issue{'' if count == 1 else 's'}")

    def _build_collisions_tab(self, frame):
        toolbar = tk.Frame(frame, bg=PANEL_BG, pady=6)
        toolbar.pack(fill="x", padx=8)
        tk.Label(toolbar,
                 text="Functions sharing an Export ID(Arg), a Device ID + Action ID, or a Device + Name",
                 bg=PANEL_BG, fg=TEXT_HEAD, font=FONT_HEAD).pack(side="left")
        tk.Button(toolbar, text="⟳  Refresh", bg=ACCENT, fg=DARK_BG, font=FONT_UI,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._refresh_collisions).pack(side="left", padx=(12, 0))
        self._collision_count_lbl = tk.Label(toolbar, text="", bg=PANEL_BG,
                                              fg=TEXT_SEC, font=FONT_UI)
        self._collision_count_lbl.pack(side="right")

        container = tk.Frame(frame, bg=PANEL_BG)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        canvas = tk.Canvas(container, bg=PANEL_BG, highlightthickness=0)
        vertical_sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vertical_sb.set)
        vertical_sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=PANEL_BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfig(window_id, width=event.width))
        self._collision_inner = inner
        self._refresh_collisions()

    @staticmethod
    def _collision_cells(entry):
        """The collision columns: ID, Name, Device Type, DeviceID, ActionID, plus
        a trailing Function label so each colliding row is identifiable."""
        export_id = first_export(entry).get("id", "")
        name = str(entry.get("name", "")).strip()
        device_type = TAB_LABELS.get(entry.get("heliosType", ""),
                                     entry.get("heliosType", "").split(".")[-1])
        device_id = get_primary_device_id(entry)
        action_id = get_primary_action_id(entry)
        function = " · ".join(part for part in (str(entry.get("device", "")).strip(),
                                                str(entry.get("name", "")).strip()) if part)
        return [str(export_id), name, str(device_type), str(device_id),
                str(action_id), function]

    @staticmethod
    def _group_by(functions, key_func):
        """Bucket functions by key_func(function), skipping falsy keys."""
        buckets = {}
        for function in functions:
            key = key_func(function)
            if key:
                buckets.setdefault(key, []).append(function)
        return buckets

    @staticmethod
    def _export_key(function):
        return str(first_export(function).get("id", "")).strip()

    @staticmethod
    def _dev_action_key(function):
        device_id = str(get_primary_device_id(function)).strip()
        action_id = str(get_primary_action_id(function)).strip()
        return (device_id, action_id) if device_id and action_id else None

    @staticmethod
    def _name_key(function):
        """The (Device, Name) pair. Two functions are treated as a duplicate-name
        collision only when BOTH their device and their name match."""
        device = str(function.get("device", "")).strip()
        name = str(function.get("name", "")).strip()
        return (device, name) if name else None

    @staticmethod
    def _find_collisions(functions):
        """Return collision groups. A group is 2+ functions that share either the
        same Export ID(Arg), the same (Device ID, Action ID) pair, or the same
        Device + Name (both must match). Each group names which column indices are
        shared so they can be highlighted."""
        groups = []
        for export_id, members in HeliosEditor._group_by(
                functions, HeliosEditor._export_key).items():
            if len(members) > 1:
                groups.append({
                    "label": f"⚠  Shared Export ID(Arg): {export_id}   ({len(members)} functions)",
                    "entries": members,
                    "highlight": {0},          # ID column
                })
        for (device_id, action_id), members in HeliosEditor._group_by(
                functions, HeliosEditor._dev_action_key).items():
            if len(members) > 1:
                groups.append({
                    "label": (f"⚠  Shared Device ID + Action ID: "
                              f"{device_id} / {action_id}   ({len(members)} functions)"),
                    "entries": members,
                    "highlight": {3, 4},       # DeviceID + ActionID columns
                })
        for (device, name), members in HeliosEditor._group_by(
                functions, HeliosEditor._name_key).items():
            if len(members) > 1:
                shared = " · ".join(part for part in (device, name) if part)
                groups.append({
                    "label": (f"⚠  Shared Device + Name: {shared}   "
                              f"({len(members)} functions)"),
                    "entries": members,
                    "highlight": {1},          # Name column
                })
        return groups

    @staticmethod
    def _collision_cell_style(shared):
        """(bg, fg, font) for a collision cell, emphasised when it's a shared
        (colliding) column."""
        if shared:
            return WARN, DARK_BG, FONT_HEAD
        return DARK_BG, TEXT_PRI, FONT_MONO

    def _render_collision_headers(self, inner, headers):
        for column, header in enumerate(headers):
            tk.Label(inner, text=header, bg=PANEL_BG, fg=ACCENT, font=FONT_HEAD,
                     anchor="w", padx=8, pady=4).grid(row=0, column=column, sticky="ew")
        inner.columnconfigure(len(headers) - 1, weight=1)

    def _render_collision_entry(self, inner, grid_row, entry, highlight):
        for column, value in enumerate(self._collision_cells(entry)):
            bg, fg, font = self._collision_cell_style(column in highlight)
            tk.Label(inner, text=value, bg=bg, fg=fg, font=font,
                     anchor="w", padx=8, pady=2).grid(row=grid_row, column=column, sticky="ew")

    def _render_collision_group(self, inner, grid_row, group, header_count):
        tk.Label(inner, text=group["label"], bg=MID_BG, fg=WARN, font=FONT_HEAD,
                 anchor="w", padx=8, pady=3).grid(
                     row=grid_row, column=0, columnspan=header_count, sticky="ew", pady=(8, 0))
        grid_row += 1
        for entry in group["entries"]:
            self._render_collision_entry(inner, grid_row, entry, group["highlight"])
            grid_row += 1
        return grid_row

    def _show_no_collisions(self, inner, header_count):
        tk.Label(inner, text="✓  No collisions found.", bg=PANEL_BG, fg=SUCCESS,
                 font=FONT_UI, anchor="w", padx=8, pady=8).grid(
                     row=1, column=0, columnspan=header_count, sticky="w")
        self._collision_count_lbl.configure(text="0 collisions")

    def _refresh_collisions(self):
        inner = getattr(self, "_collision_inner", None)
        if inner is None:
            return
        for child in inner.winfo_children():
            child.destroy()

        headers = ["ID", "Name", "Device Type", "DeviceID", "ActionID", "Function"]
        self._render_collision_headers(inner, headers)

        groups = self._find_collisions(self._data["functions"])
        if not groups:
            self._show_no_collisions(inner, len(headers))
            return

        grid_row = 1
        for group in groups:
            grid_row = self._render_collision_group(inner, grid_row, group, len(headers))

        plural = "s" if len(groups) != 1 else ""
        self._collision_count_lbl.configure(text=f"{len(groups)} collision group{plural}")

    def _build_full_view_tab(self, frame):
        toolbar = tk.Frame(frame, bg=PANEL_BG, pady=6)
        toolbar.pack(fill="x", padx=8)
        tk.Label(toolbar, text="All devices in save-file format (read-only)",
                 bg=PANEL_BG, fg=TEXT_HEAD, font=FONT_HEAD).pack(side="left")
        tk.Button(toolbar, text="⟳  Refresh", bg=ACCENT, fg=DARK_BG, font=FONT_UI,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._refresh_full_view).pack(side="left", padx=(12, 0))

        # Sort-method toggle (also drives the order used when saving).
        tk.Label(toolbar, text="Sort:", bg=PANEL_BG, fg=TEXT_SEC,
                 font=FONT_UI).pack(side="left", padx=(18, 4))
        self._sort_method_var = tk.StringVar(value=self._sort_method)

        def on_toggle():
            self._set_sort_method(self._sort_method_var.get())

        short_labels = {"deviceaction": "Device ID + Action ID",
                        "devicename": "Device Name + Name (A→Z)"}
        for key in SORT_METHODS:
            tk.Radiobutton(toolbar, text=short_labels.get(key, key),
                           variable=self._sort_method_var, value=key, command=on_toggle,
                           bg=PANEL_BG, fg=TEXT_PRI, selectcolor=MID_BG,
                           activebackground=PANEL_BG, activeforeground=ACCENT,
                           font=FONT_UI).pack(side="left", padx=(0, 4))

        container = tk.Frame(frame, bg=PANEL_BG)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        vertical_sb = ttk.Scrollbar(container, orient="vertical")
        horizontal_sb = ttk.Scrollbar(container, orient="horizontal")
        text = tk.Text(container, wrap="none", bg=MID_BG, fg=TEXT_PRI,
                       insertbackground=TEXT_PRI, relief="flat", font=FONT_MONO,
                       yscrollcommand=vertical_sb.set, xscrollcommand=horizontal_sb.set,
                       highlightthickness=0, borderwidth=0)
        vertical_sb.configure(command=text.yview)
        horizontal_sb.configure(command=text.xview)
        vertical_sb.pack(side="right", fill="y")
        horizontal_sb.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)

        self._full_view_text = text
        self._refresh_full_view()

    def _refresh_full_view(self):
        """Render the current profile in save-file JSON format into the Full
        View tab's read-only text box."""
        text = getattr(self, "_full_view_text", None)
        if text is None:
            return
        try:
            content = json.dumps(self._build_save_payload(), indent=2)
        except Exception as error:                       # never let the view crash
            content = f"// Unable to render save view: {error}"
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", content)
        text.configure(state="disabled")

    def _build_tab(self, frame, helios_type):
        # Toolbar
        toolbar = tk.Frame(frame, bg=PANEL_BG, pady=6)
        toolbar.pack(fill="x", padx=8)

        tk.Button(toolbar, text="＋  Add Entry", bg=ACCENT, fg=DARK_BG, font=FONT_HEAD,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=lambda h=helios_type: self._add_entry(h)).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="✎  Edit", bg=MID_BG, fg=TEXT_PRI, font=FONT_UI,
              relief="flat", padx=12, pady=4, cursor="hand2",
              command=lambda h=helios_type: self._edit_entry(h)).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="⎘  Duplicate Last  ★", bg=MID_BG, fg=TEXT_PRI, font=FONT_UI,
              relief="flat", padx=12, pady=4, cursor="hand2",
              activeforeground=TEXT_PRI, command=lambda h=helios_type: duplicate_last(self, h)).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="⎘  Duplicate Selected", bg=MID_BG, fg=TEXT_PRI, font=FONT_UI,
              relief="flat", padx=12, pady=4, cursor="hand2",
              command=lambda h=helios_type: duplicate_selected(self, h)).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="✕  Delete", bg=DANGER_BG, fg=DANGER_FG, font=FONT_UI,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=lambda h=helios_type: self._delete_entry(h)).pack(side="left", padx=(0, 6))
        tk.Button(toolbar, text="⇄  Change Type", bg=MID_BG, fg=ACCENT2, font=FONT_UI,
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=lambda h=helios_type: self._change_type(h)).pack(side="left", padx=(0, 6))

        tk.Label(toolbar, text="Click a column header to sort by value", bg=PANEL_BG, fg=TEXT_SEC,
                 font=FONT_UI).pack(side="left", padx=(16, 4))


        # Count of how many functions of this type (updated on every refresh).
        count_label = tk.Label(toolbar, text="", bg=PANEL_BG, fg=ACCENT2, font=FONT_HEAD)
        count_label.pack(side="right", padx=(8, 8))
        self._tab_count_lbls[helios_type] = count_label

        # Treeview
        columns = get_columns(helios_type)
        column_ids = [column[0] for column in columns]

        container = tk.Frame(frame, bg=PANEL_BG)
        container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        vertical_sb = ttk.Scrollbar(container, orient="vertical")
        horizontal_sb = ttk.Scrollbar(container, orient="horizontal")

        tree = ttk.Treeview(container, columns=column_ids, show="headings",
                            yscrollcommand=vertical_sb.set, xscrollcommand=horizontal_sb.set,
                            selectmode="extended")
        vertical_sb.configure(command=tree.yview)
        horizontal_sb.configure(command=tree.xview)

        for column_id, column_label, column_width in columns:
            centered = column_id in CENTERED_COLUMNS
            heading_kwargs = {
                "text": column_label,
                "command": lambda c=column_id, h=helios_type: self._sort_by_col(h, c),
            }
            column_kwargs = {"width": column_width, "minwidth": 50, "stretch": True}
            if centered:
                heading_kwargs["anchor"] = "center"
                column_kwargs["anchor"] = "center"
            tree.heading(column_id, **heading_kwargs)
            tree.column(column_id, **column_kwargs)

        tree.tag_configure("even", background=ROW_EVEN)
        tree.tag_configure("odd",  background=ROW_ODD)

        tree.bind("<Double-1>", lambda event, h=helios_type: self._edit_entry(h))

        vertical_sb.pack(side="right",  fill="y")
        horizontal_sb.pack(side="bottom", fill="x")
        tree.pack(side="left",  fill="both", expand=True)

        self._trees[helios_type] = tree

    # ── data ops ───────────────────────────────────────────────────────────────
    def _entries_for(self, helios_type):
        return [(index, function) for index, function in enumerate(self._data["functions"])
                if function.get("heliosType") == helios_type]

    def _sort_functions(self):
        """Sort the in-memory functions by device id then action id (the same
        order used when saving), so the grids stay ordered as soon as anything
        is added. Re-sorting renumbers every function's index, so callers must
        rebuild all tabs (not just one) afterward."""
        self._data["functions"].sort(key=device_action_sort_key)

    def _apply_descriptions(self):
        """Set every function's description from DESCRIPTION_BY_TYPE, keyed by
        its helios type. ScaledNetworkValue (mapped to None) is left untouched,
        so it stays blank as before."""
        self._sync_header_to_data()
        changed = 0
        for function in self._data["functions"]:
            desc = DESCRIPTION_BY_TYPE.get(function.get("heliosType", ""))
            if desc is None:                 # ScaledNetworkValue / unknown: leave as-is
                continue
            if function.get("description", "") != desc:
                function["description"] = desc
                changed += 1
        self._refresh_all()
        messagebox.showinfo(
            "Set Descriptions",
            f"Updated {changed} description"
            f"{'s' if changed != 1 else ''} by helios type.")

    @staticmethod
    def _ensure_export_id(function, new_id):
        """Give `function` an export id of `new_id` when it has none. Returns
        True if an id was assigned, False if it already had one. When the
        function has no export slot at all, one is created from the type's
        default export shape."""
        exports = function.get("exports")
        if isinstance(exports, list) and exports and isinstance(exports[0], dict):
            if str(exports[0].get("id", "")).strip() != "":
                return False
            exports[0]["id"] = new_id
            return True
        blank = make_blank_entry(function.get("heliosType", ""))
        blank_exports = blank.get("exports")
        new_export = dict(blank_exports[0]) if blank_exports else {}
        new_export["id"] = new_id
        function["exports"] = [new_export]
        return True

    @staticmethod
    def _show_autofill_result(assigned):
        plural = "s" if assigned != 1 else ""
        tail = "" if assigned else " Every device already has one."
        messagebox.showinfo("Auto-fill IDs", f"Assigned {assigned} new ID{plural}.{tail}")

    def _auto_fill_ids(self):
        """Assign an Export ID(Arg) to every device that doesn't already have one,
        counting up from the highest id currently in use. Devices that already
        have an id are left untouched; gaps in the existing numbering are not
        back-filled (per the rule: start at max id + 1)."""
        self._sync_header_to_data()
        functions = self._data.get("functions", [])
        next_id = max_id(functions) + 1
        assigned = 0
        for function in functions:
            if self._ensure_export_id(function, next_id):
                next_id += 1
                assigned += 1
        if assigned:
            self._refresh_all()
        self._show_autofill_result(assigned)

    def _add_entry(self, helios_type):
        self._sync_header_to_data()
        # Pre-fill the device name + id with whatever was on the last entry added
        # this session, so a run of additions to the same device doesn't require
        # retyping it each time.
        seed = None
        if self._last_added_device or self._last_added_device_id:
            seed = make_blank_entry(helios_type)
            seed["device"] = self._last_added_device
            set_primary_device_id(seed, self._last_added_device_id)
        dialog = EntryDialog(self, f"Add — {TAB_LABELS[helios_type]}", helios_type,
                             existing=seed, functions=self._data["functions"])
        self.wait_window(dialog)
        if dialog.result:
            self._data["functions"].append(dialog.result)
            dialog.result["_saved_session_index"] = self._next_saved_session_index
            self._next_saved_session_index += 1
            # Remember this entry for future Add / Duplicate actions.
            self._last_added_device = dialog.result.get("device", "")
            self._last_added_device_id = get_primary_device_id(dialog.result)
            self._last_added_function = dialog.result
            self._last_saved_function = dialog.result
            # Re-sort by device id then action id on every add. This reorders the
            # whole list, so refresh all tabs to rebuild their row indices.
            self._sort_functions()
            self._refresh_all()
            self._update_max_id()

    def _edit_entry(self, helios_type):
        tree = self._trees[helios_type]
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("No Selection", "Select a row to edit.", parent=self)
            return
        if len(selection) > 1:
            messagebox.showinfo("Select One",
                                "Edit works on a single row — select just one.\n"
                                "(Use Change Type to retype several at once.)",
                                parent=self)
            return
        item_id = selection[0]
        tags = tree.item(item_id, "tags")
        function_index = int(tags[0]) if tags else -1
        if function_index < 0:
            return
        entry = self._data["functions"][function_index]
        dialog = EntryDialog(self, f"Edit — {TAB_LABELS[helios_type]}", helios_type, existing=entry,
                             functions=self._data["functions"], edit_index=function_index)
        self.wait_window(dialog)
        if dialog.result:
            dialog.result["_saved_session_index"] = self._next_saved_session_index
            self._next_saved_session_index += 1
            self._last_saved_function = dialog.result
            self._data["functions"][function_index] = dialog.result
            self._refresh_tab(helios_type)
            self._update_max_id()

    @staticmethod
    def _selected_indices(tree):
        """Function indices behind the currently selected rows of `tree`
        (each row stores its index as its first tag)."""
        indices = []
        for item_id in tree.selection():
            tags = tree.item(item_id, "tags")
            index = int(tags[0]) if tags else -1
            if index >= 0:
                indices.append(index)
        return indices

    def _delete_prompt(self, indices):
        if len(indices) == 1:
            entry = self._data["functions"][indices[0]]
            return (f"Delete '{entry.get('name','')}' ({entry.get('device','')})?"
                    "\nThis cannot be undone.")
        return f"Delete {len(indices)} selected function(s)?\nThis cannot be undone."

    def _delete_entry(self, helios_type):
        indices = self._selected_indices(self._trees[helios_type])
        if not indices:
            messagebox.showinfo("No Selection", "Select one or more rows to delete.",
                                parent=self)
            return
        if messagebox.askyesno("Confirm Delete", self._delete_prompt(indices), parent=self):
            # Pop from the highest index down so earlier indices stay valid.
            for index in sorted(indices, reverse=True):
                self._data["functions"].pop(index)
            # Removal renumbers every function, so rebuild all tabs.
            self._refresh_all()
            self._update_max_id()

    def _ask_new_type(self, indices):
        """Prompt for the destination type for the selected rows; returns the
        chosen helios type, or None if the dialog was cancelled."""
        first_entry = self._data["functions"][indices[0]]
        dialog = ChangeTypeDialog(self, first_entry, count=len(indices))
        self.wait_window(dialog)
        return dialog.result

    @staticmethod
    def _carried_device_kept(carried_device, new_entry):
        return (carried_device not in ("", None)
                and get_primary_device_id(new_entry) not in ("", None))

    @staticmethod
    def _carried_action_kept(carried_action, new_entry):
        return (carried_action not in ("", None)
                and get_primary_action_id(new_entry) not in ("", None))

    def _convert_indices_to_type(self, indices, new_type):
        """Convert each function at `indices` to `new_type` in place, skipping
        ones already of that type. Returns (converted, kept_device, kept_action)."""
        converted = 0
        kept_device = False
        kept_action = False
        for index in indices:
            entry = self._data["functions"][index]
            if entry.get("heliosType", "") == new_type:
                continue
            carried_device = get_primary_device_id(entry)
            carried_action = get_primary_action_id(entry)
            new_entry = convert_entry_type(entry, new_type)
            self._data["functions"][index] = new_entry
            converted += 1
            if self._carried_device_kept(carried_device, new_entry):
                kept_device = True
            if self._carried_action_kept(carried_action, new_entry):
                kept_action = True
        return converted, kept_device, kept_action

    @staticmethod
    def _carried_ids_note(kept_device, kept_action):
        if kept_device and kept_action:
            return ", plus the device and action IDs.\n\n"
        if kept_device:
            return ", plus the device ID.\n\n"
        if kept_action:
            return ", plus the action ID.\n\n"
        return ".\n\n"

    def _show_type_changed(self, converted, new_type, indices, kept_device, kept_action):
        if converted == 1:
            head = (f"'{self._data['functions'][indices[0]].get('name','')}' "
                    f"is now a {TAB_LABELS[new_type]}.")
        else:
            head = f"Changed {converted} function(s) to {TAB_LABELS[new_type]}."
        note = self._carried_ids_note(kept_device, kept_action)
        messagebox.showinfo(
            "Type Changed",
            head + "\n\nKept: device, name, description and Export ID(Arg)" + note
            + "Other fields were reset to defaults — use Edit to fill them in.",
            parent=self)

    def _change_type(self, helios_type):
        """Change the helios type of every selected function. Preserves common
        fields + export id, resets type-specific fields, then moves the rows to
        the destination type's tab and selects them there."""
        indices = self._selected_indices(self._trees[helios_type])
        if not indices:
            messagebox.showinfo("No Selection",
                                "Select one or more rows to change their type.",
                                parent=self)
            return

        new_type = self._ask_new_type(indices)
        if not new_type:
            return

        converted, kept_device, kept_action = self._convert_indices_to_type(indices, new_type)
        if converted == 0:
            messagebox.showinfo("No Change",
                                "The selected function(s) are already that type.",
                                parent=self)
            return

        # The rows leave the old tab and appear in the new type's tab.
        self._refresh_tab(helios_type)
        self._refresh_tab(new_type)
        self._update_max_id()
        # Surface the converted entries where the user can see them.
        self._select_tab(new_type)
        self._select_functions(new_type, indices)
        self._show_type_changed(converted, new_type, indices, kept_device, kept_action)

    def _select_tab(self, helios_type):
        """Bring the tab for helios type `helios_type` to the front."""
        for tab_index in range(self._nb.index("end")):
            if self._nb.tab(tab_index, "text") == TAB_LABELS[helios_type]:
                self._nb.select(tab_index)
                return

    def _select_function(self, helios_type, function_index):
        """Select (and scroll to) the row whose function index is `function_index`
        in the tree for helios type `helios_type`."""
        tree = self._trees.get(helios_type)
        if tree is None:
            return
        for item_id in tree.get_children():
            tags = tree.item(item_id, "tags")
            if tags and tags[0] == str(function_index):
                tree.selection_set(item_id)
                tree.focus(item_id)
                tree.see(item_id)
                return

    def _select_functions(self, helios_type, function_indices):
        """Select (and scroll to) every row whose function index is in
        `function_indices`, in the tree for helios type `helios_type`."""
        tree = self._trees.get(helios_type)
        if tree is None:
            return
        wanted = {str(index) for index in function_indices}
        to_select = []
        for item_id in tree.get_children():
            tags = tree.item(item_id, "tags")
            if tags and tags[0] in wanted:
                to_select.append(item_id)
        if to_select:
            tree.selection_set(to_select)
            tree.focus(to_select[0])
            tree.see(to_select[0])

    def _sort_by_col(self, helios_type, column):
        previous = self._sort_col.get(helios_type, (None, False))
        reverse = (not previous[1]) if previous[0] == column else False
        self._sort_col[helios_type] = (column, reverse)
        self._refresh_tab(helios_type)

    # ── refresh ────────────────────────────────────────────────────────────────
    @staticmethod
    def _tab_sort_key(function, sort_column):
        """Sort key for a flattened entry within a type tab. ID columns sort
        numerically (blank / non-numeric last); other columns sort
        case-insensitively; with no sort column, sort by device then name."""
        flat = flatten_entry(function)
        if not sort_column:
            return (
                0,
                0,
                f"{str(flat.get('device', '')).lower()}\x00{str(flat.get('name', '')).lower()}",
            )
        raw = flat.get(sort_column, "")
        if sort_column not in ID_COLUMNS:
            return (0, 0, str(raw).lower())
        text = str(raw).strip()
        if text.lstrip("+-").isdigit():
            return (0, int(text), "")
        return (1, 0, text.lower())

    def _update_tab_count(self, helios_type, count):
        count_label = self._tab_count_lbls.get(helios_type)
        if count_label is None:
            return
        plural = "" if count == 1 else "s"
        count_label.configure(text=f"{count} {TAB_LABELS[helios_type]}{plural}")

    def _row_values(self, function, latest_entry, column_ids):
        """Build the display tuple for one grid row. Device/Name are prettified
        for display only; the stored values are left untouched, and the most
        recently saved function gets a ★ marker."""
        flat = flatten_entry(function)
        display = dict(flat)
        device_label = prettify_label(flat.get("device", ""))
        if function is latest_entry:
            device_label = "★ " + device_label
        display["device"] = device_label
        display["name"] = prettify_label(flat.get("name", ""))
        return tuple(display.get(column_id, "") for column_id in column_ids)

    def _refresh_tab(self, helios_type):
        tree = self._trees[helios_type]
        entries = self._entries_for(helios_type)
        self._update_tab_count(helios_type, len(entries))

        sort_column, reverse = self._sort_col.get(helios_type, (None, False))
        entries_sorted = sorted(
            entries, key=lambda ie: self._tab_sort_key(ie[1], sort_column), reverse=reverse)
        latest_entry = find_last_saved_function(self, helios_type)

        tree.delete(*tree.get_children())
        column_ids = [column[0] for column in get_columns(helios_type)]
        for row_number, (function_index, function) in enumerate(entries_sorted):
            values = self._row_values(function, latest_entry, column_ids)
            shade = "even" if row_number % 2 == 0 else "odd"
            tree.insert("", "end", values=values, tags=(str(function_index), shade))

    def _refresh_all(self):
        for helios_type in HELIOS_TYPES:
            self._refresh_tab(helios_type)
        self._refresh_full_view()
        self._refresh_collisions()
        self._refresh_validation()
        self._update_max_id()
        self._update_total_count()

    def _update_total_count(self):
        """Header readout of how many functions exist across all types."""
        label = getattr(self, "_total_count_lbl", None)
        if label is not None:
            label.configure(text=str(len(self._data.get("functions", []))))

    # ── unsaved-change tracking ──────────────────────────────────────────────────
    def _compute_state_signature(self):
        """Serialise the current profile (header + functions, private bookkeeping
        fields stripped) so it can be compared against the last clean state to
        detect unsaved changes."""
        if getattr(self, "_hdr_vars", None):
            self._sync_header_to_data()
        try:
            return json.dumps(strip_private_fields(self._data), sort_keys=True)
        except Exception:
            return repr(self._data)

    def _mark_clean(self):
        """Record the current state as the saved baseline (call after new / open
        / save)."""
        self._clean_signature = self._compute_state_signature()

    def _has_unsaved_changes(self):
        return self._compute_state_signature() != getattr(self, "_clean_signature", None)

    def _confirm_discard_changes(self, title="Unsaved Changes"):
        """When there are unsaved changes, ask the user whether to continue
        without saving. Returns True to proceed, False to abort."""
        if not self._has_unsaved_changes():
            return True
        return messagebox.askyesno(
            title,
            "You have unsaved changes that will be lost.\n\n"
            "Continue without saving?",
            parent=self)

    def _on_exit(self):
        """Quit, prompting first if there are unsaved changes."""
        if self._confirm_discard_changes(title="Exit"):
            self.destroy()

    def _on_tab_changed(self, _event=None):
        """Auto-refresh the Collisions / Full View / Validation tabs whenever
        they are brought to the front so they always reflect the current
        profile."""
        try:
            current = self._nb.tab(self._nb.select(), "text")
        except Exception:
            return
        if current == "Collisions":
            self._refresh_collisions()
        elif current == "Full View":
            self._refresh_full_view()
        elif current == "Value Check":
            self._refresh_validation()

    # ── file ops ───────────────────────────────────────────────────────────────
    def _new(self):
        if not self._confirm_discard_changes(title="New File"):
            return
        self._reset_to_new_profile()
        self._refresh_all()
        self._mark_clean()

    def _reset_to_new_profile(self):
        """Start a fresh, empty profile without prompting (the caller has
        already confirmed, e.g. the import-into-a-new-profile path)."""
        self._data = {"source": "User", "version": "Initial", "commit": "", "type": "DCS",
                      "name": "", "module": "", "vehicles": [], "functions": []}
        self._current_file = None
        self._last_added_device = ""
        self._last_added_device_id = ""
        self._last_added_function = None
        self._last_saved_function = None
        self._next_saved_session_index = 1
        self._next_created_session_index = 1
        self.title("Helios Interface Editor")
        self._sync_data_to_header()

    def _open(self):
        if not self._confirm_discard_changes(title="Open File"):
            return
        path = filedialog.askopenfilename(
            title="Open JSON Profile",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            # On open, cast every numeric-looking value back to a real number.
            loaded = cast_strings_to_numbers(loaded)
            self._data = loaded
            if "vehicles" not in self._data:
                self._data["vehicles"] = []
            if "functions" not in self._data:
                self._data["functions"] = []
            self._current_file = path
            self._last_added_device = ""
            self._last_added_device_id = ""
            self._last_added_function = None
            self._next_created_session_index = 1
            self.title(f"Helios Interface Editor — {os.path.basename(path)}")
            self._sync_data_to_header()
            # Auto-sort loaded items by device id then action id before display.
            self._sort_functions()
            self._refresh_all()
            # A just-opened profile is the new clean baseline.
            self._mark_clean()
        except Exception as error:
            messagebox.showerror("Open Failed", str(error))

    # ── DCS Lua import ───────────────────────────────────────────────────────────
    # def _import_dcs_folder(self):
    #     """Compile a DCS Cockpit folder of clickabledata Lua (+ devices/
    #     command_defs/draw_args) into Helios functions and load them into the
    #     editor. The chosen folder and all of its subfolders are searched for the
    #     appropriate files."""
    #     if not self._confirm_discard_changes(title="Import"):
    #         return
    #     folder = filedialog.askdirectory(
    #         title="Select DCS Cockpit folder (clickabledata.lua and supporting files; subfolders are searched)")
    #     if not folder:
    #         return
    #     try:
    #         from parser_engine import convert_clickabledata_to_hif
    #     except Exception as error:
    #         messagebox.showerror(
    #             "Import unavailable",
    #             "Could not load the DCS Lua compiler.\n\n"
    #             "Make sure 'parser_engine.py' "
    #             "is in the same folder as this program.\n\n"
    #             f"Details: {error}")
    #         return

    #     # Use the currently loaded profile as a label/style reference when it
    #     # already contains functions; otherwise the compiler auto-detects a
    #     # sibling .json in the folder.
    #     reference = self._data if self._data.get("functions") else None
    #     try:
    #         functions, result = convert_clickabledata_to_hif(
    #             folder, reference=reference, strip_source_notes=True)
    #     except FileNotFoundError as error:
    #         messagebox.showerror("No clickabledata found", str(error))
    #         return
    #     except Exception as error:
    #         messagebox.showerror("Import Failed", str(error))
    #         return

    #     self._ingest_imported_functions(functions, result, source=folder)

    def _apply_import_merge(self, functions, source):
        """Decide how to bring `functions` in (new profile vs append) and apply
        it. Returns False if the user cancelled, True otherwise."""
        existing = self._data.get("functions", [])
        if not existing:
            self._data["functions"] = list(functions)
            return True
        choice = messagebox.askyesnocancel(
            "Import",
            f"Compiled {len(functions)} function(s) from:\n{source}\n\n"
            f"Your profile already has {len(existing)} function(s).\n\n"
            "Do you want to import into a NEW profile?\n\n"
            "Yes  = start a new profile (the current data is cleared)\n"
            "No   = add the imported set to the current profile\n"
            "Cancel = abort import")
        if choice is None:
            return False
        if choice:
            # Start a fresh profile, then load the imported set into it.
            self._reset_to_new_profile()
            self._data["functions"] = list(functions)
        else:
            self._data["functions"] = existing + list(functions)
        return True

    @staticmethod
    def _append_warning_lines(lines, warnings):
        lines.append("")
        lines.append(f"Warnings ({len(warnings)}):")
        lines.extend("  • " + warning for warning in warnings[:6])
        if len(warnings) > 6:
            lines.append(f"  …and {len(warnings) - 6} more.")
        lines.append("")
        lines.append("Tip: IDs (device/action/arg) come straight from the "
                     "Lua and are reliable. Device labels, switch position "
                     "names and axis ranges are best-effort — review them "
                     "in the tabs and adjust as needed.")

    @staticmethod
    def _import_summary_lines(functions, result):
        """Build the multi-line import summary shown to the user."""
        lines = [
            f"Imported {len(functions)} function(s).",
            f"Devices resolved: {result.device_count}",
            f"Command tables:   {result.command_table_count}",
            f"Elements parsed:  {result.element_count}",
        ]
        if getattr(result, "unused_device_buttons", 0):
            lines.append(f"Unused devices →  {result.unused_device_buttons} "
                         "added as PushButtons")
        if getattr(result, "unpaired_arg_axes", 0):
            lines.append(f"Unpaired draw-args → {result.unpaired_arg_axes} "
                         "reassigned as Axes")
        if getattr(result, "unpaired_command_buttons", 0):
            lines.append(f"Unpaired commands → {result.unpaired_command_buttons} "
                         "reassigned as PushButtons")
        if result.helper_counts:
            top = sorted(result.helper_counts.items(), key=lambda item: -item[1])[:6]
            lines.append("Top helpers: "
                         + ", ".join(f"{helper}×{count}" for helper, count in top))
        if result.warnings:
            HeliosEditor._append_warning_lines(lines, result.warnings)
        return lines

    def _ingest_imported_functions(self, functions, result, source=""):
        """Merge compiled functions into the profile after asking the user how,
        then refresh the UI and report a summary."""
        if not functions:
            messagebox.showwarning(
                "Nothing imported",
                "The compiler ran but produced no functions.\n\n"
                + ("\n".join(result.warnings[:8]) if result.warnings else ""))
            return

        if not self._apply_import_merge(functions, source):
            return

        # Keep the device-then-action ordering for the bulk add too.
        self._sort_functions()
        self._refresh_all()
        messagebox.showinfo("DCS Lua Import",
                            "\n".join(self._import_summary_lines(functions, result)))

    def _save(self):
        if not self._current_file:
            self._save_as()
            return
        method = self._ask_save_sort_method()
        if method is None:
            return
        self._set_sort_method(method)
        self._write(self._current_file)

    def _save_as(self):
        method = self._ask_save_sort_method()
        if method is None:
            return
        self._set_sort_method(method)
        path = filedialog.asksaveasfilename(
            title="Save JSON Profile",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._current_file = path
        self._write(path)
        self.title(f"Helios Interface Editor — {os.path.basename(path)}")

    def _current_sort_key(self):
        """The sort-key function for the active save / Full View ordering."""
        return SORT_METHODS.get(self._sort_method, SORT_METHODS["deviceaction"])[1]

    def _set_sort_method(self, method):
        """Switch the active ordering, keep the Full View toggle in sync, and
        re-render the Full View."""
        if method not in SORT_METHODS:
            return
        self._sort_method = method
        var = getattr(self, "_sort_method_var", None)
        if var is not None and var.get() != method:
            var.set(method)
        self._refresh_full_view()

    def _ask_save_sort_method(self):
        """Modal prompt: how should functions be ordered in the saved file?
        Returns the chosen method key, or None if the user cancels."""
        dialog = tk.Toplevel(self)
        dialog.title("Save — Sort Order")
        dialog.configure(bg=DARK_BG)
        dialog.resizable(False, False)
        dialog.grab_set()

        tk.Label(dialog, text="Order functions in the saved file by:", bg=DARK_BG,
                 fg=TEXT_HEAD, font=FONT_HEAD).pack(anchor="w", padx=18, pady=(16, 10))

        choice = tk.StringVar(value=self._sort_method)
        for key, (label, _fn) in SORT_METHODS.items():
            tk.Radiobutton(dialog, text=label, variable=choice, value=key,
                           bg=DARK_BG, fg=TEXT_PRI, selectcolor=MID_BG,
                           activebackground=DARK_BG, activeforeground=ACCENT,
                           font=FONT_UI, anchor="w").pack(anchor="w", padx=24, pady=2)

        result = {"method": None}

        def confirm():
            result["method"] = choice.get()
            dialog.destroy()

        buttons = tk.Frame(dialog, bg=DARK_BG)
        buttons.pack(fill="x", padx=18, pady=(14, 16))
        tk.Button(buttons, text="✓  Save", bg=ACCENT, fg=DARK_BG, font=FONT_HEAD,
                  relief="flat", padx=16, pady=5, cursor="hand2",
                  command=confirm).pack(side="right", padx=(6, 0))
        tk.Button(buttons, text="✕  Cancel", bg=MID_BG, fg=TEXT_SEC, font=FONT_UI,
                  relief="flat", padx=16, pady=5, cursor="hand2",
                  command=dialog.destroy).pack(side="right")

        dialog.update_idletasks()
        width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
        screen_w, screen_h = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"+{(screen_w - width) // 2}+{(screen_h - height) // 2}")

        self.wait_window(dialog)
        return result["method"]

    def _build_save_payload(self):
        """Build the exact dict written to disk on Save: prettified device/name
        labels, functions ordered by the active sort method, and every number
        cast to a string. Shared by the writer and the read-only Full View tab
        so the two always agree."""
        self._sync_header_to_data()
        out = strip_private_fields(copy.deepcopy(self._data))

        # Prettify the Device and Name of every function on the way out, so the
        # saved file carries the cleaned-up labels (matches what the grid shows).
        # Also coerce the designated value fields (Switch positions, Axis bounds,
        # PushButton push/release values, ScaledNetworkValue calibration points)
        # to floats so the canonical SPECIAL_FLOAT_STRINGS form is applied even
        # when the source stored them as bare integers.
        for function in out["functions"]:
            function["device"] = prettify_label(function.get("device", ""))
            function["name"] = prettify_label(function.get("name", ""))
            normalize_special_floats(function)

        # Order by whichever method is active (device/action, or device-name then
        # name) — the same ordering the Full View shows.
        out["functions"] = sorted(out["functions"], key=self._current_sort_key())

        # On save, cast every numeric value to a string throughout the file.
        return cast_numbers_to_strings(out)

    def _write(self, path):
        # Warn about any collisions before committing the save.
        groups = self._find_collisions(self._data.get("functions", []))
        if groups:
            involved = sum(len(group["entries"]) for group in groups)
            proceed = messagebox.askyesno(
                "Collisions Detected",
                f"This profile has {len(groups)} collision"
                f"{'' if len(groups) == 1 else 's'} "
                f"involving {involved} function"
                f"{'' if involved == 1 else 's'} "
                "(shared Export ID(Arg), or Device ID + Action ID).\n\n"
                "These are listed on the Collisions tab.\n\n"
                "Do you want to proceed with saving anyway?",
                parent=self)
            if not proceed:
                return
        out = self._build_save_payload()
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(out, handle, indent=2)
            # A successful save makes the current state the clean baseline.
            self._mark_clean()
            messagebox.showinfo("Saved", f"File saved:\n{path}")
        except Exception as error:
            messagebox.showerror("Save Failed", str(error))


if __name__ == "__main__":
    app = HeliosEditor()
    app.mainloop()
