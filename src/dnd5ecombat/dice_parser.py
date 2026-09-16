"""Shared parsing for dice expressions embedded in profile data."""

import re

from .models import DamageDice


def extract_damage_dice(text, default_number=1, default_sides=8):
    """Extract every ``NdS`` term from a string as immutable damage pools."""
    if not isinstance(text, str):
        raise TypeError("dice expression must be a string")
    matches = re.findall(
        r"(?<![a-z0-9_])(\d*)d(\d+)", text.strip().lower().replace(" ", "")
    )
    if not matches:
        raise ValueError("dice expression does not contain an NdS term")
    return tuple(
        DamageDice(
            int(number_text or default_number),
            int(sides_text or default_sides),
        )
        for number_text, sides_text in matches
    )
