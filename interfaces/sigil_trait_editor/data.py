"""Sigil, trait, and card-reference persistence."""

import csv
import os
import tempfile
from pathlib import Path

from model import DEFAULT_CONFIG
from ..gui_helpers import ROOT, _join, _split

SIGIL_PATH = ROOT / DEFAULT_CONFIG["sigils_file_path"]
TRAIT_PATH = ROOT / DEFAULT_CONFIG["traits_file_path"]
SIGIL_ICON_DIR = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "sigils"
CONDUIT_SIGIL_ICON_DIR = ROOT / DEFAULT_CONFIG["assets_dir"] / "general_assets" / "conduit_sigil_indicators"

def normalize_sigil_name(name):
    """Convert a display name to the filename convention used for sigil icons."""
    return name.translate(str.maketrans("", "", " ',-!?"))


def _csv_rows(path):
    """Load item rows from a CSV with the required item columns."""
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise csv.Error(f"{path} has no CSV header")
        missing_fields = {"Name", "Description", "Tags"} - set(reader.fieldnames)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise csv.Error(f"{path} is missing required CSV columns: {missing}")
        return [dict(row) for row in reader]


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
        """Replace or move an item while retaining its position when possible."""
        updated = {}
        replaced_names = {name}
        if old_name:
            replaced_names.add(old_name)
        source_section = None
        source_index = None
        if old_name:
            for section in ("Sigils", "Traits"):
                source_index = next((index for index, row in enumerate(data[section]) if row.get("Name") == old_name), None)
                if source_index is not None:
                    source_section = section
                    break
        for section in ("Sigils", "Traits"):
            updated[section] = [row for row in data[section] if row.get("Name") not in replaced_names]
        new_row = {"Name": name, "Description": item["Description"], "Tags": item["Tags"]}
        if source_section == target_section and source_index is not None:
            insertion_index = sum(row.get("Name") not in replaced_names for row in data[source_section][:source_index])
            updated[target_section].insert(insertion_index, new_row)
        else:
            updated[target_section].append(new_row)
        self.save_items(updated)
        return updated

    def delete_item(self, data, section, name):
        """Remove one item from its section and persist both item files."""
        updated = {key: [row for row in rows if key != section or row.get("Name") != name] for key, rows in data.items()}
        self.save_items(updated)
        return updated

    def save_items(self, data):
        """Atomically replace each section using the shared item CSV columns."""
        temporary_paths = {}
        try:
            for section, path in self.paths.items():
                with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8", dir=path.parent, delete=False) as handle:
                    temporary_path = Path(handle.name)
                    temporary_paths[temporary_path] = path
                    writer = csv.DictWriter(handle, fieldnames=["Name", "Description", "Tags"])
                    writer.writeheader()
                    writer.writerows(data[section])

            for temporary_path, path in temporary_paths.items():
                os.replace(temporary_path, path)
        finally:
            for temporary_path in temporary_paths:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    def update_card_references(self, old_name, new_name, source_section, target_section):
        """Move matching card references when an item changes between types."""
        with self.cards_path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

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
