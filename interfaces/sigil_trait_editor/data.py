"""Sigil, trait, and card-reference persistence."""

import csv

from model import DEFAULT_CONFIG
from ..gui_helpers import ROOT, _join, _split

SIGIL_PATH = ROOT / DEFAULT_CONFIG["sigils_file_path"]
TRAIT_PATH = ROOT / DEFAULT_CONFIG["traits_file_path"]
SIGIL_ICON_DIR = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "sigils"
CONDUIT_SIGIL_ICON_DIR = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "conduit_sigil_indicators"

SIGIL_TAG_OPTIONS = [
    "power_sigil",
    "health_sigil",
    "conduit_sigil",
    "mox_green",
    "mox_orange",
    "mox_blue",
    "mox_prism",
]


def normalize_sigil_name(name):
    """Convert a display name to the filename convention used for sigil icons."""
    return name.translate(str.maketrans("", "", " ',-!?"))


def _csv_rows(path):
    """Load item rows from a CSV, returning an empty list when unavailable."""
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error):
        return []


class SigilTraitRepository:
    """Load and persist sigils, traits, and references in card CSV files."""

    def __init__(self, sigil_path=SIGIL_PATH, trait_path=TRAIT_PATH, cards_path=None):
        """Set the data-file locations used by the repository."""
        self.paths = {"Sigils": sigil_path, "Traits": trait_path}
        self.cards_path = cards_path or ROOT / DEFAULT_CONFIG["cards_file_path"]

    def load_items(self):
        """Load both item types into the editor's section-keyed data structure."""
        return {section: _csv_rows(path) for section, path in self.paths.items()}

    def write_item(self, data, old_name, name, item, target_section):
        """Replace an existing item or rename it, then persist both item files."""
        updated = {}
        replaced_names = {name}
        if old_name:
            replaced_names.add(old_name)
        for section in ("Sigils", "Traits"):
            updated[section] = [row for row in data[section] if row.get("Name") not in replaced_names]
        updated[target_section].append({"Name": name, "Description": item["Description"], "Tags": item["Tags"]})
        self.save_items(updated)
        return updated

    def delete_item(self, data, section, name):
        """Remove one item from its section and persist both item files."""
        updated = {key: [row for row in rows if key != section or row.get("Name") != name] for key, rows in data.items()}
        self.save_items(updated)
        return updated

    def save_items(self, data):
        """Write each section using the shared item CSV columns."""
        for section, path in self.paths.items():
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Name", "Description", "Tags"])
                writer.writeheader()
                writer.writerows(data.get(section, []))

    def update_card_references(self, old_name, new_name, source_section, target_section):
        """Move matching card references when an item changes between types."""
        try:
            with self.cards_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            return

        source_field = "Sigils" if source_section == "Sigils" else "Traits"
        target_field = "Sigils" if target_section == "Sigils" else "Traits"
        for row in rows:
            source_values = _split(row.get(source_field, ""))
            if old_name in source_values:
                source_values = [value for value in source_values if value != old_name]
                target_values = _split(row.get(target_field, ""))
                if new_name not in target_values:
                    target_values.append(new_name)
                row[source_field] = _join(source_values)
                row[target_field] = _join(target_values)
        fieldnames = list(rows[0].keys()) if rows else [
            "Card Name", "Art File", "Temple", "Tier", "Cost", "Power", "Health",
            "Sigils", "Token", "Traits", "Tribes", "Flavor Text", "Credit", "Tags",
        ]
        with self.cards_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
