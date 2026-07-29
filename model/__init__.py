import logging, json, os
from PIL import Image, ImageDraw, ImageFont

def load_config(temple=None, tier=None, bg_modifier=None):
    config = {}
    files_to_load = ["general"]
    if temple:
        files_to_load.append(temple.lower())
    for filename in files_to_load:
        path = f"config/{filename}.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                config.update(json.load(f))

    # If no background modifier is passed, we assume it's the "default" background
    active_bg = bg_modifier if bg_modifier else "default"
    tier_lower = tier.lower() if tier else None

    if "overrides" in config and active_bg in config["overrides"]:
        bg_config = config["overrides"][active_bg]
        # 1. Apply the base shifts for this specific background type
        if "default" in bg_config and isinstance(bg_config["default"], dict):
            config.update(bg_config["default"])
        # 2. Apply the rarity-specific shifts for this background type
        if tier_lower and tier_lower in bg_config:
            config.update(bg_config[tier_lower])

    return config

logging.basicConfig(
    filename='error.log', 
    level=logging.ERROR, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

DEFAULT_CONFIG = load_config()
ASSETS_DIR = DEFAULT_CONFIG["assets_dir"]
FONT = "data/fonts/" + DEFAULT_CONFIG["font"] + ".TTF"


def get_color_mapping(temple, tier=None, bg_modifier=None):
    """
    Loads and returns the color mapping dictionary for a specific temple and tier.
    Maps general color keys (from general_assets/colors.png) to temple/tier-specific colors.
    """
    temple_name = temple.lower()
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
        path = f"{ASSETS_DIR}/{temple_name}/{filename}"
        if os.path.exists(path):
            color_path = path
            break

    if not color_path:
        return {}

    config = load_config(temple, tier, bg_modifier)
    color_keys = list(Image.open(f"{ASSETS_DIR}/general_assets/colors.png").getdata())
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
        "tribal_light_color"
    ]
    for i in range(len(color_keys)):
        if i < len(colors):
            # Map standard indices
            for ind in standard_indices:
                if i == config[ind + "_index"] - 1:
                    mapping[ind] = colors[i]
            # Map the raw color-to-color replacement if applicable
            mapping[color_keys[i]] = colors[i]
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
