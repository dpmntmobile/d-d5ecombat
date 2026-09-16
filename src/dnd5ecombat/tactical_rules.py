"""2014 structured traits and encounter-dependent eligibility."""

TRAITS = ("pack_tactics", "aggressive", "nimble_escape")
ASSUMPTIONS = (
    "character_ally_near_target",
    "monster_ally_near_target",
    "character_can_hide",
    "monster_can_hide",
)


def validate_traits(profile):
    for name in TRAITS:
        if not isinstance(getattr(profile, name), bool):
            raise TypeError(f"{name} must be a boolean")
    for name in ("stealth_bonus", "passive_perception"):
        value = getattr(profile, name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")


def validate_assumptions(value):
    for name in ASSUMPTIONS:
        if not isinstance(getattr(value, name), bool):
            raise TypeError(f"{name} must be a boolean")
