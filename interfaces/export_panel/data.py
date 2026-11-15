"""CSV-backed export data and pure filtering helpers."""

import csv
import re

from model.text import strip_rich_text_tags

from ..card_editor.fields import SigilList


EXPORT_TYPES = ("Cards", "Sigils", "Traits")
COST_FILTERS = (
    ("Blood", "blood"),
    ("Bones", "bone"),
    ("Energy", "energy"),
    ("Overcharge (max)", "max"),
    ("Emerald", "emerald"),
    ("Ruby", "ruby"),
    ("Sapphire", "sapphire"),
    ("Prism", "prism"),
    ("Shatters", "shattered"),
    ("Free", "free"),
)
STAT_OPERATORS = ("", "=", ">", ">=", "<", "<=", "!=")


def load_csv(path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def unique(values):
    return sorted({value.strip() for value in values if value and value.strip()}, key=str.casefold)


def display_name(value):
    return strip_rich_text_tags(value or "").strip()


def split_list(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def card_filter_values(row, category, field):
    value = row.get(field) or ""
    if category == "Tribes":
        return value.replace(",", " ").split()
    values = split_list(value)
    if category == "Sigils":
        return [SigilList._parse(item)[0] for item in values]
    return values


def cost_tokens(value):
    text = (value or "").lower()
    if not text or text == "none":
        return {"free"}
    tokens = set()
    if "free" in text:
        tokens.add("free")
    if "blood" in text:
        tokens.add("blood")
    if "bone" in text:
        tokens.add("bone")
    if "energy" in text or re.search(r"\b\d+\s*cell", text):
        tokens.add("energy")
    if "max" in text or "overcharge" in text:
        tokens.add("max")
    if "shattered" in text:
        tokens.add("shattered")
    for gem in ("emerald", "ruby", "sapphire", "prism"):
        if gem in text:
            tokens.add(gem)
    return tokens


def numeric_stat(value):
    cleaned = strip_rich_text_tags(str(value or "")).strip()
    if "_" in cleaned:
        cleaned = cleaned.rsplit("_", 1)[-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def matches_stat(value, operator, target):
    if not operator or not target.strip():
        return True
    actual = numeric_stat(value)
    try:
        expected = float(target)
    except ValueError:
        return False
    if actual is None:
        return False
    results = {
        "=": actual == expected,
        ">": actual > expected,
        ">=": actual >= expected,
        "<": actual < expected,
        "<=": actual <= expected,
        "!=": actual != expected,
    }
    return results[operator]


def crop_card_art(art):
    crop_left = round(art.width() * 0.1)
    crop_right = round(art.width() * 0.1)
    crop_top = round(art.height() * 0.2)
    crop_bottom = round(art.height() * 0.40)
    return art.copy(crop_left, crop_top, art.width() - crop_left - crop_right, art.height() - crop_top - crop_bottom,)
