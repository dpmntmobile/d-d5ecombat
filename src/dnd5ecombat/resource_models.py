"""Validated spell-slot pools and save-action resource metadata."""


def normalize_spell_slots(value):
    entries = value.items() if hasattr(value, "items") else value
    result = {}
    for level, count in entries:
        if isinstance(level, str) and level in tuple(str(i) for i in range(1, 10)):
            level = int(level)
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 9:
            raise ValueError("spell_slots levels must be 1 through 9")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("spell_slots counts must be non-negative integers")
        if level in result:
            raise ValueError("duplicate spell_slots level")
        result[level] = count
    return tuple(sorted(result.items()))


def validate_save_resources(effect):
    for name, low, high in (
        ("limited_uses", 1, None),
        ("recharge_min_roll", 2, 6),
        ("spell_slot_level", 0, 9),
        ("range_feet", 1, None),
    ):
        value = getattr(effect, name)
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer or None")
            if value < low or (high is not None and value > high):
                raise ValueError(f"invalid {name}: {value}")
    if effect.limited_uses is not None and effect.recharge_min_roll is not None:
        raise ValueError("cannot combine limited_uses and recharge_min_roll")


def duel_save_actions(profiles):
    return tuple(
        effect
        for effect in profiles
        if effect.action_type in {"action", "bonus_action"}
        and effect.save_ability
        and any(
            value is not None
            for value in (
                effect.spell_slot_level,
                effect.limited_uses,
                effect.recharge_min_roll,
            )
        )
    )


def validate_casting(effect):
    from .attack_models import DamageDice

    if effect.spell_slot_pool not in {"spellcasting", "pact", "any"}:
        raise ValueError("spell_slot_pool must be spellcasting, pact, or any")
    if not isinstance(effect.allow_upcast, bool):
        raise TypeError("allow_upcast must be a boolean")
    dice = tuple(effect.upcast_damage_dice)
    if not all(isinstance(pool, DamageDice) for pool in dice):
        raise TypeError("upcast_damage_dice must contain DamageDice")
    if (
        dice or effect.allow_upcast or effect.spell_slot_pool != "spellcasting"
    ) and not effect.spell_slot_level:
        raise ValueError("casting pool and upcasting require a leveled spell")
    object.__setattr__(effect, "upcast_damage_dice", dice)
