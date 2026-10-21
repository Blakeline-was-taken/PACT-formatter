import logging, json, os
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_config(temple=None, tier=None, bg_modifier=None):
    config_tree = json.load(open(ROOT / "config.json", "r", encoding="utf-8"))

    default_temple = config_tree["default"]
    temple = temple.lower() if temple else "default"
    temple_config = config_tree.get(temple, default_temple)
    tier = tier.lower() if tier else "default"
    bg_modifier = bg_modifier.lower() if bg_modifier else "default"
    config = {}

    def apply_section(section):
        if isinstance(section, dict):
            config.update(section)

    apply_section(default_temple["default"]["default"])
    
    if temple != "default":
        apply_section(temple_config.get("default", {}).get("default"))

    if tier:
        apply_section(default_temple.get(tier, {}).get("default"))
        if temple != "default":
            apply_section(temple_config.get(tier, {}).get("default"))

    if bg_modifier != "default":
        apply_section(default_temple["default"].get(bg_modifier))
        if temple != "default":
            apply_section(temple_config.get("default", {}).get(bg_modifier))
        if tier:
            apply_section(default_temple.get(tier, {}).get(bg_modifier))
            if temple != "default":
                apply_section(temple_config.get(tier, {}).get(bg_modifier))

    return config

DEFAULT_CONFIG = load_config()
ASSETS_DIR = ROOT / DEFAULT_CONFIG["assets_dir"]
GENERAL_ASSETS_DIR = ASSETS_DIR / "general_assets"
FONT = ROOT / "data" / "fonts" / f"{DEFAULT_CONFIG['font']}.TTF"

logging.basicConfig(
    filename='error.log', 
    level=logging.ERROR, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_color_mapping(temple, tier=None, bg_modifier=None, config_override=None):
    """
    Loads and returns the color mapping dictionary for a specific temple and tier.
    Maps general color keys (from general_assets/colors.png) to temple/tier-specific colors.
    """
    temple = temple.lower()
    tier_name = tier.lower() if tier else None
    
    # Clean up the bg_modifier
    bg_name = bg_modifier.replace('_bg', '') if bg_modifier else None

    # Build a list of potential filenames, checking the most specific first
    filenames_to_check = []
    if tier_name and bg_name:
        filenames_to_check.append(f"{tier_name}_{bg_name}_colors.png")
    if tier_name:
        filenames_to_check.append(f"{tier_name}_colors.png")
    if bg_name:
        filenames_to_check.append(f"{bg_name}_colors.png")
    filenames_to_check.append("colors.png")

    # Find the first file in the list that actually exists
    color_path = None
    for filename in filenames_to_check:
        path = ASSETS_DIR / temple / filename
        if os.path.exists(path):
            color_path = path
            break

    if not color_path:
        color_path = GENERAL_ASSETS_DIR / "colors.png"  # Fallback to general colors

    config = config_override or load_config(temple, tier, bg_modifier)
    color_keys = list(Image.open(GENERAL_ASSETS_DIR / "colors.png").getdata())
    colors = list(Image.open(color_path).getdata())

    mapping = {}
    standard_indices = [
        "flavor_text_color", 
        "metadata_color", 
        "art_credit_color",
        "trait_color",
        "arcane_dark_color",
        "arcane_light_color",
        "tribal_dark_color",
        "tribal_light_color",
        "hint_color"
    ]
    for i in range(len(color_keys)):
        if i < len(colors):
            # Map standard indices
            for ind in standard_indices:
                if i == config[ind + "_index"] - 1:
                    mapping[ind] = colors[i]
            # Map the raw color-to-color replacement if applicable
            mapping[color_keys[i]] = colors[i]
    mapping["palette_colors"] = colors
    return mapping


def apply_temple_colors(image, temple, tier=None, bg_modifier=None):
    """
    Applies temple, tier, and background-specific color replacements to the image.
    """
    # Make sure we pass the bg_modifier down to get_color_mapping
    color_map = get_color_mapping(temple, tier, bg_modifier)
    
    if color_map:
        # TODO : Possible optimization - use ImageOps or pixel mapping if performance is a bottleneck
        for x in range(image.width):
            for y in range(image.height):
                original_color = image.getpixel((x, y))
                if original_color in color_map:
                    image.putpixel((x, y), color_map[original_color])
    return image
