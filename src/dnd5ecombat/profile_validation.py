"""Normalization shared by character, target, and duel profile models."""

VALID_ABILITIES = frozenset({"str", "dex", "con", "int", "wis", "cha"})


def normalize_string_tuple(value, field_name):
    try:
        values = tuple(value)
    except TypeError as error:
        raise TypeError(f"{field_name} must be an iterable of strings") from error
    if not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError(f"{field_name} must contain non-empty strings")
    normalized = tuple(item.strip().lower() for item in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return normalized


def normalize_saving_throw_bonuses(value):
    if hasattr(value, "items"):
        value = value.items()
    try:
        bonuses = tuple(value)
    except TypeError as error:
        raise TypeError(
            "saving_throw_bonuses must be a mapping or iterable of pairs"
        ) from error

    normalized = []
    seen = set()
    for entry in bonuses:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise TypeError("every saving throw bonus must be an ability/bonus pair")
        ability, bonus = entry
        if not isinstance(ability, str):
            raise TypeError("saving throw abilities must be strings")
        ability = ability.strip().lower()
        if ability not in VALID_ABILITIES:
            raise ValueError(f"unsupported saving throw ability: {ability}")
        if ability in seen:
            raise ValueError(f"duplicate saving throw ability: {ability}")
        if not isinstance(bonus, int) or isinstance(bonus, bool):
            raise TypeError("saving throw bonuses must be integers")
        normalized.append((ability, bonus))
        seen.add(ability)
    return tuple(normalized)
