"""Template configuration defaults, layering, and file access."""

import csv
import json

from model import DEFAULT_CONFIG
from ..gui_helpers import ROOT

CONFIG_PATH = ROOT / "config.json"
COORDINATE_FIELDS = {
    "power_coord",
    "health_coord",
    "left_symbol",
    "right_symbol",
    "power_sigil_center",
    "health_sigil_center",
}

TEMPLATE_SECTIONS = {
    "Formatting": {
        "write_card_metadata": True,
        "write_art_credit": True,
        "show_power_sigil": True,
        "show_health_sigil": True,
        "allow_colored_sigils": True,
        "colorless_symbols": True,
        "display_tribe_icons": True,
        "show_conduit_sigil_indicators": True,
        "center_card_name": True,
        "traits_at_bottom": True,
        "allow_card_bottom_removal": True,
        "allow_default_formatting": True,
        "allow_shortened_formatting": True,
        "allow_base_game_display": True,
    },
    "Text": {
        "font": "heavyweight",
        "name_font_size": 110,
        "name_max_width": 870,
        "flavor_text_font_size": 45,
        "metadata_font_size": 45,
        "art_credit_font_size": 45,
        "stats_font_size": 110,
        "flavor_text_color_index": 6,
        "metadata_color_index": 6,
        "art_credit_color_index": 6,
        "trait_color_index": 6,
        "name_top_border": 138,
        "name_left_border": 138,
        "metadata_top_border": 15,
        "art_credit_top_border": 1510,
        "flavor_text_top_border": 962,
        "flavor_text_left_border": 300,
        "flavor_text_right_border": 1000,
        "power_coord": [198, 885],
        "health_coord": [895, 225],
        "sigil_name_font_size": 55,
        "sigil_description_font_size": 45,
        "trait_description_font_size": 40,
    },
    "Indicators": {
        "indicator_displacement": 15,
        "left_symbol": [130, 1440],
        "right_symbol": [1000, 1440],
        "tribes_top_border": 265,
        "tribes_left_border": 980,
        "tribes_vertical_displacement": -1,
        "extra_cells_top_border": 26,
        "extra_cells_left_border": 3,
    },
    "Cost": {
        "cost_right_border": 99,
        "cost_left_border": 67,
        "cost_bottom_border": 91,
    },
    "Sigils": {
        "sigil_img_scale": 100,
        "sigil_img_space": 180,
        "sigil_space": 880,
        "sigil_vertical_spacing": 5,
        "sigil_top_displacement": 3,
        "sigil_left_border": 120,
        "sigil_bottom_border": 1430,
        "power_sigil_center": [220, 925],
        "health_sigil_center": [915, 265],
        "traitline_vertical_spacing": 6,
        "trait_vertical_spacing": 0,
    },
    "Gemification": {
        "gemification_font_size": 80,
        "gemification_health_top_border": 17,
        "gemification_health_horizontal_center": 101,
        "gemification_health_text_top_border": 105,
        "gemification_health_text_horizontal_center": 1015,
        "gemification_power_bottom_border": 87,
        "gemification_power_horizontal_center": 9,
        "gemification_power_text_top_border": 865,
        "gemification_power_text_horizontal_center": 95,
        "gemification_cost_bottom_border": 84,
        "gemification_cost_horizontal_center": 103,
        "gemification_cost_text_top_border": 835,
        "gemification_cost_text_horizontal_center": 1035,
        "cost_right_border_gemification_displacement": -2,
        "gemification_sigil_top_displacement": 0,
        "gemification_sigil_bottom_displacement": 0,
        "gemification_sigil_gems_right_border": 14,
        "gemification_sigil_small_max_height": 150,
        "gemification_sigil_medium_max_height": 200,
    },
    "Sigil Conditional": {},
    "Rich Text Colors": {},
}

SUBSECTION_FIELDS = {
    "Cost": {
        "Blood": {"blood_right_displacement": 0},
        "Bones": {"bone_right_displacement": -1},
        "Energy": {},
        "Gems": {"gem_right_displacement": -1},
        "Asterisk": {"asterisk_right_displacement": -1},
    },
    "Sigil Conditional": {
        "Cell": {
            "cell_sigil_top_displacement": 0,
            "cell_sigil_bottom_displacement": 0,
            "cell_sigil_small_max_height": 150,
            "cell_sigil_medium_max_height": 200,
        },
        "Latch": {
            "latch_sigil_top_displacement": 0,
            "latch_sigil_bottom_displacement": 0,
            "left_latch_head_border": 110,
            "right_latch_head_border": 1010,
            "latch_sigil_small_max_height": 150,
            "latch_sigil_medium_max_height": 200,
        },
        "Arcane": {
            "arcane_sigil_top_displacement": -10,
            "arcane_sigil_bottom_displacement": -95,
            "arcane_text": "If you provide 2 mox colors:",
            "arcane_text_y": 20,
            "arcane_font_size": 43,
            "arcane_dark_color_index": 6,
            "arcane_light_color_index": 5,
        },
        "Tribal": {
            "tribal_sigil_top_displacement": -20,
            "tribal_sigil_bottom_displacement": -95,
            "tribal_text": "If this card shares a tribe with another:",
            "tribal_text_y": 30,
            "tribal_font_size": 43,
            "tribal_dark_color_index": 6,
            "tribal_light_color_index": 5,
        },
        "Hint": {"hint_color_index": 6},
    },
}

TEMPLATE_DEFAULTS = {
    **{
        key: value
        for section in TEMPLATE_SECTIONS.values()
        for key, value in section.items()
    },
    **{
        key: value
        for subsections in SUBSECTION_FIELDS.values()
        for fields in subsections.values()
        for key, value in fields.items()
    },
}


def layer_paths(temple, tier, modifier):
    """Return configuration layers from least to most specific."""
    paths = [("default", "default", "default")]
    if temple != "default":
        paths.append((temple, "default", "default"))
    if tier != "default":
        paths.append(("default", tier, "default"))
        if temple != "default":
            paths.append((temple, tier, "default"))
    if modifier != "default":
        paths.append(("default", "default", modifier))
        if temple != "default":
            paths.append((temple, "default", modifier))
        if tier != "default":
            paths.append(("default", tier, modifier))
            if temple != "default":
                paths.append((temple, tier, modifier))
    return paths


def effective_config(config_tree, temple, tier, modifier, exclude_path=None):
    """Merge applicable configuration layers in override order."""
    effective = {}
    for path in layer_paths(temple, tier, modifier):
        if path == exclude_path:
            continue
        section = config_tree
        for key in path:
            section = section.get(key, {}) if isinstance(section, dict) else {}
        if isinstance(section, dict):
            effective.update(section)
    return effective


def target_layer(config_tree, path, create=False):
    """Find a nested config layer, optionally creating missing dictionaries."""
    section = config_tree
    for key in path:
        if create:
            section = section.setdefault(key, {})
        else:
            section = section.get(key, {})
        if not isinstance(section, dict):
            raise ValueError(f"Configuration layer '{'.'.join(path)}' is not an object.")
    return section


def read_selector_values(cards_path):
    """Collect sorted temple, tier, and background names from the cards CSV."""
    temples, tiers, modifiers = set(), set(), set()
    with cards_path.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            temple = (row.get("Temple") or "").strip()
            tier = (row.get("Tier") or "").strip()
            if temple:
                temples.add(temple)
            if tier:
                tiers.add(tier)
            modifiers.update(tag.strip() for tag in (row.get("Tags") or "").split(",") if tag.strip().lower().endswith("_bg"))
    sort_values = lambda values: sorted(values, key=str.casefold)
    return sort_values(temples), sort_values(tiers), sort_values(modifiers)


def read_config(config_path=CONFIG_PATH):
    """Read and validate the root configuration object."""
    with config_path.open("r", encoding="utf-8") as handle:
        config_tree = json.load(handle)
    if not isinstance(config_tree, dict) or not isinstance(config_tree.get("default"), dict):
        raise ValueError("config.json must contain an object with a 'default' layer.")
    return config_tree


def write_config(config_tree, config_path=CONFIG_PATH):
    """Write the configuration tree as formatted UTF-8 JSON."""
    serialized = json.dumps(config_tree, indent=4, ensure_ascii=False) + "\n"
    config_path.write_text(serialized, encoding="utf-8")
