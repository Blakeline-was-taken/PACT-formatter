"""Known renderer tags and their user-facing explanations."""

TAG_TOOLTIPS = {
    "conduit_indicator": "Show a conduit overlay on the card's upper frame.",
    "mox_indicator": "Show a Mox indicator using selected gem tags.",
    "mox_green": "Add a green gem to the card's Mox indicator.",
    "mox_orange": "Add an orange gem to the card's Mox indicator.",
    "mox_blue": "Add a blue gem to the card's Mox indicator.",
    "mox_prism": "Add a prism gem to the card's Mox indicator.",
    "gemified_vanilla": "Use the vanilla-style gemification rendering.",
    "conduit_sigil_indicator": "Show a standard Null Conduit sigil indicator if no specific conduit sigil is assigned.",
    "power_sigil": "Replace the card's power with an icon.",
    "health_sigil": "Replace the card's health with an icon.",
    "conduit_sigil": "Show matching sigil conduit indicator art when available.",
}

TAG_OPTIONS = tuple(TAG_TOOLTIPS)


def tag_tooltip(tag):
    """Return help for a known tag or explain that a custom tag has no renderer behavior."""
    return TAG_TOOLTIPS.get(tag.strip().casefold(), None)
