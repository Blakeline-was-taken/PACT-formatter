"""Card CSV access and shared card-editor data definitions."""

import csv

from model import DEFAULT_CONFIG
from ..gui_helpers import ROOT, _join, _split

CARDS_PATH = ROOT / DEFAULT_CONFIG["cards_file_path"]
ASSET_PATH = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "card_art"
DATA_PATH = ROOT / "data"

# Keep this order aligned with data/cards.csv so newly written files remain
# compatible with the existing CLI and renderer.
CARD_FIELDS = [
    "Card Name", "Art File", "Temple", "Tier", "Cost", "Power", "Health",
    "Sigils", "Token", "Traits", "Tribes", "Flavor Text", "Credit", "Tags",
]
TAG_OPTIONS = [
    "conduit_indicator", "mox_indicator", "mox_green",
    "mox_orange", "mox_blue", "mox_prism", "gemified_vanilla",
    "conduit_sigil_indicator",
]
COST_OPTIONS = [
    "blood", "bones", "energy", "max",
    "emerald", "sapphire", "ruby", "prism",
    "shattered emerald", "shattered sapphire", "shattered ruby", "shattered prism",
    "asterisk",
]


def parse_card_tags(value):
    """Decode editor-specific background, symbol, and extra-cell tags."""
    tags = _split(value)
    background = next((tag[:-3] for tag in tags if tag.lower().endswith("_bg") and tag[:-3]), "").lower()
    symbols = {"left": "", "right": ""}
    for tag in tags:
        for side in symbols:
            suffix = f"_{side}_symbol"
            if tag.lower().endswith(suffix) and tag[:-len(suffix)].strip():
                symbols[side] = tag[:-len(suffix)].strip()
                break
    extra_cells = 0
    for tag in tags:
        count = tag.split("_", 1)[0]
        if tag.endswith("_extra_cell") and count.isdigit():
            extra_cells = int(count)
    return {
        "background": background,
        "tags": set(tags),
        "symbols": symbols,
        "extra_cells": extra_cells,
    }


def format_card_tags(background, selected_tags, left_symbol, right_symbol, extra_cells):
    """Encode editor tag controls in their established CSV order."""
    tags = [f"{background.strip().lower()}_bg"] if background.strip() else []
    tags.extend(selected_tags)
    if left_symbol.strip():
        tags.append(f"{left_symbol.strip()}_left_symbol")
    if right_symbol.strip():
        tags.append(f"{right_symbol.strip()}_right_symbol")
    if extra_cells > 0:
        tags.append(f"{extra_cells}_extra_cell")
    return _join(tags)


class CardRepository:
    """Read and persist card records and CSV-backed editor suggestions."""

    def __init__(self, cards_path=CARDS_PATH, data_path=DATA_PATH):
        """Set the CSV locations, with defaults rooted in the project config."""
        self.cards_path = cards_path
        self.data_path = data_path

    def load_cards(self):
        """Read card rows and preserve the file's existing column order."""
        with self.cards_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return reader.fieldnames or CARD_FIELDS, [dict(row) for row in reader]

    def load_names(self, filename, key):
        """Return a named column for editor suggestions when the CSV is readable."""
        try:
            with (self.data_path / filename).open(newline="", encoding="utf-8") as handle:
                return [row[key] for row in csv.DictReader(handle) if row.get(key)]
        except (OSError, csv.Error, KeyError):
            return []

    def save_cards(self, rows, fieldnames):
        """Write card rows using the supplied column order."""
        with self.cards_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
