"""Explicit non-damaging duel spells and their persistence contract."""

from dataclasses import asdict, dataclass

from .attack_models import DamageDice
from .resource_models import validate_casting, validate_save_resources


@dataclass(frozen=True)
class SupportSpell:
    name: str
    effect: str
    damage_dice: tuple = ()  # Healing dice; shared with the slot/upcast machinery.
    damage_modifier: int = 0
    difficulty_class: int = 10
    save_ability: str = "dex"
    range_feet: int = 60
    duration_turns: int = 10
    action_type: str = "action"
    spell_slot_level: int = 1
    spell_slot_pool: str = "spellcasting"
    allow_upcast: bool = True
    upcast_damage_dice: tuple = ()
    limited_uses: int = None
    recharge_min_roll: int = None
    free_casts: int = 0

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("support spell name must be non-empty")
        if self.effect not in {"healing", "faerie_fire", "bless", "misty_step"}:
            raise ValueError("unsupported support spell effect")
        expected_action = "bonus_action" if self.effect == "misty_step" else "action"
        if self.action_type != expected_action:
            raise ValueError(f"{self.effect} requires {expected_action}")
        if not isinstance(self.free_casts, int) or isinstance(self.free_casts, bool):
            raise TypeError("free_casts must be an integer")
        if self.free_casts < 0:
            raise ValueError("free_casts cannot be negative")
        for name in ("damage_modifier", "difficulty_class", "duration_turns"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
        if self.difficulty_class < 1 or self.duration_turns < 1:
            raise ValueError("DC and duration must be positive")
        if self.save_ability != "dex":
            raise ValueError("Faerie Fire requires a Dexterity save")
        dice = tuple(self.damage_dice)
        if not all(isinstance(d, DamageDice) for d in dice):
            raise TypeError("healing dice must contain DamageDice")
        if self.effect == "healing" and not dice:
            raise ValueError("healing requires dice")
        if self.effect != "healing" and (dice or self.damage_modifier or self.upcast_damage_dice):
            raise ValueError("non-healing support spells cannot have healing dice or modifiers")
        object.__setattr__(self, "damage_dice", dice)
        validate_save_resources(self)
        validate_casting(self)
        if not self.spell_slot_level or self.range_feet is None:
            raise ValueError("support spells require a leveled slot and range")


def validate_support_spells(combatant):
    spells = tuple(combatant.support_spells)
    if not all(isinstance(s, SupportSpell) for s in spells):
        raise TypeError("support_spells must contain SupportSpell instances")
    object.__setattr__(combatant, "support_spells", spells)


def support_spell_to_dict(spell):
    values = asdict(spell)
    for field in ("damage_dice", "upcast_damage_dice"):
        values[field] = list(values[field])
    return values


def support_spell_from_dict(data):
    values = dict(data)
    for field in ("damage_dice", "upcast_damage_dice"):
        values[field] = tuple(DamageDice(**d) for d in values.get(field, ()))
    return SupportSpell(**values)
