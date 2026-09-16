from dataclasses import dataclass
from enum import Enum

from .resource_models import validate_save_resources, validate_casting

from .profile_validation import (
    VALID_ABILITIES,
    normalize_string_tuple as _normalize_string_tuple,
)

class Condition(Enum):
    PRONE = "prone"
    PARALYZED = "paralyzed"
    POISONED = "poisoned"
    RESTRAINED = "restrained"
    STUNNED = "stunned"
    INCAPACITATED = "incapacitated"


@dataclass(frozen=True)
class SavingThrowConditionEffect:
    difficulty_class: int
    save_ability: str
    condition: Condition
    repeat_save_at_end_of_turn: bool = False
    immune_creature_tags: tuple = ()
    duration_turns: int = None

    def __post_init__(self):
        if not isinstance(self.difficulty_class, int) or isinstance(
            self.difficulty_class, bool
        ):
            raise TypeError("difficulty_class must be an integer")
        if self.difficulty_class < 1:
            raise ValueError("difficulty_class must be at least 1")
        if not isinstance(self.save_ability, str):
            raise TypeError("save_ability must be a string")
        ability = self.save_ability.strip().lower()
        if ability not in VALID_ABILITIES:
            raise ValueError(f"unsupported saving throw ability: {ability}")
        object.__setattr__(self, "save_ability", ability)
        if not isinstance(self.condition, Condition):
            raise TypeError("condition must be a Condition")
        if not isinstance(self.repeat_save_at_end_of_turn, bool):
            raise TypeError("repeat_save_at_end_of_turn must be a boolean")
        if self.duration_turns is not None:
            if not isinstance(self.duration_turns, int) or isinstance(self.duration_turns, bool):
                raise TypeError("duration_turns must be an integer or None")
            if self.duration_turns < 1:
                raise ValueError("duration_turns must be at least 1")
        object.__setattr__(
            self,
            "immune_creature_tags",
            _normalize_string_tuple(
                self.immune_creature_tags, "immune_creature_tags"
            ),
        )


@dataclass(frozen=True)
class DamageDice:
    number: int
    sides: int

    def __post_init__(self):
        if not isinstance(self.number, int) or isinstance(self.number, bool):
            raise TypeError("number must be an integer")
        if not isinstance(self.sides, int) or isinstance(self.sides, bool):
            raise TypeError("sides must be an integer")
        if self.number < 1:
            raise ValueError("number must be at least 1")
        if self.sides < 2:
            raise ValueError("sides must be at least 2")


@dataclass(frozen=True)
class AttackProfile:
    name: str
    attack_bonus: int
    damage_dice: tuple
    damage_modifier: int = 0
    damage_type: str = ""
    attack_mode: str = ""
    reach_feet: int = None
    normal_range_feet: int = None
    long_range_feet: int = None
    unmodeled_effects: tuple = ()
    condition_effect: SavingThrowConditionEffect = None
    reroll_damage_at_or_below: int = 0
    action_type: str = "action"
    limited_uses: int = None
    recharge_min_roll: int = None
    spell_slot_level: int = None
    spell_slot_pool: str = "spellcasting"
    allow_upcast: bool = False
    upcast_damage_dice: tuple = ()

    def __post_init__(self):
        validate_casting(self)
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.attack_bonus, int) or isinstance(
            self.attack_bonus, bool
        ):
            raise TypeError("attack_bonus must be an integer")
        if not isinstance(self.damage_modifier, int) or isinstance(
            self.damage_modifier, bool
        ):
            raise TypeError("damage_modifier must be an integer")
        if not isinstance(self.reroll_damage_at_or_below, int) or isinstance(
            self.reroll_damage_at_or_below, bool
        ):
            raise TypeError("reroll_damage_at_or_below must be an integer")
        if self.reroll_damage_at_or_below < 0:
            raise ValueError("reroll_damage_at_or_below cannot be negative")
        if not isinstance(self.damage_type, str):
            raise TypeError("damage_type must be a string")
        if not isinstance(self.attack_mode, str):
            raise TypeError("attack_mode must be a string")
        valid_attack_modes = {"", "melee", "ranged", "melee_or_ranged"}
        if self.attack_mode not in valid_attack_modes:
            raise ValueError(f"unsupported attack mode: {self.attack_mode}")
        if not isinstance(self.action_type, str):
            raise TypeError("action_type must be a string")
        for field_name, minimum, maximum in (
            ("limited_uses", 1, None), ("recharge_min_roll", 2, 6),
            ("spell_slot_level", 0, 9),
        ):
            value = getattr(self, field_name)
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise TypeError(f"{field_name} must be an integer or None")
                if value < minimum or (maximum is not None and value > maximum):
                    raise ValueError(f"invalid {field_name}: {value}")
        if self.limited_uses is not None and self.recharge_min_roll is not None:
            raise ValueError("an attack cannot combine limited_uses and recharge_min_roll")
        valid_action_types = {"action", "bonus_action", "reaction"}
        if self.action_type not in valid_action_types:
            raise ValueError(f"unsupported action type: {self.action_type}")

        for field_name in (
            "reach_feet",
            "normal_range_feet",
            "long_range_feet",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise ValueError(f"{field_name} must be a positive integer or None")
        if (
            self.normal_range_feet is not None
            and self.long_range_feet is not None
            and self.long_range_feet < self.normal_range_feet
        ):
            raise ValueError("long_range_feet cannot be less than normal_range_feet")

        try:
            damage_dice = tuple(self.damage_dice)
        except TypeError as error:
            raise TypeError(
                "damage_dice must be an iterable of DamageDice"
            ) from error
        if not damage_dice:
            raise ValueError("damage_dice must contain at least one pool")
        if not all(isinstance(pool, DamageDice) for pool in damage_dice):
            raise TypeError("every damage pool must be DamageDice")
        if any(
            self.reroll_damage_at_or_below >= pool.sides
            for pool in damage_dice
        ):
            raise ValueError(
                "reroll_damage_at_or_below must be below every damage die size"
            )

        object.__setattr__(self, "damage_dice", damage_dice)

        try:
            unmodeled_effects = tuple(self.unmodeled_effects)
        except TypeError as error:
            raise TypeError("unmodeled_effects must be an iterable of strings") from error
        if not all(
            isinstance(effect, str) and effect.strip()
            for effect in unmodeled_effects
        ):
            raise ValueError("unmodeled_effects must contain non-empty strings")
        object.__setattr__(self, "unmodeled_effects", unmodeled_effects)
        if self.condition_effect is not None and not isinstance(
            self.condition_effect, SavingThrowConditionEffect
        ):
            raise TypeError(
                "condition_effect must be SavingThrowConditionEffect or None"
            )


class SaveSuccessDamage(Enum):
    NO_DAMAGE = "no_damage"
    HALF_DAMAGE = "half_damage"


@dataclass(frozen=True)
class SavingThrowDamageProfile:
    name: str
    difficulty_class: int
    damage_dice: tuple
    damage_modifier: int = 0
    damage_on_success: SaveSuccessDamage = SaveSuccessDamage.NO_DAMAGE
    save_ability: str = ""
    damage_type: str = ""
    action_type: str = "action"
    unmodeled_effects: tuple = ()
    limited_uses: int = None
    recharge_min_roll: int = None
    spell_slot_level: int = None
    spell_slot_pool: str = "spellcasting"
    allow_upcast: bool = False
    upcast_damage_dice: tuple = ()
    range_feet: int = None

    def __post_init__(self):
        validate_save_resources(self)
        validate_casting(self)
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.difficulty_class, int) or isinstance(
            self.difficulty_class, bool
        ):
            raise TypeError("difficulty_class must be an integer")
        if not isinstance(self.damage_modifier, int) or isinstance(
            self.damage_modifier, bool
        ):
            raise TypeError("damage_modifier must be an integer")
        if not isinstance(self.damage_on_success, SaveSuccessDamage):
            raise TypeError("damage_on_success must be SaveSuccessDamage")
        if not isinstance(self.save_ability, str):
            raise TypeError("save_ability must be a string")
        if not isinstance(self.damage_type, str):
            raise TypeError("damage_type must be a string")
        if not isinstance(self.action_type, str):
            raise TypeError("action_type must be a string")
        valid_action_types = {"action", "bonus_action", "reaction"}
        if self.action_type not in valid_action_types:
            raise ValueError(f"unsupported action type: {self.action_type}")

        try:
            damage_dice = tuple(self.damage_dice)
        except TypeError as error:
            raise TypeError(
                "damage_dice must be an iterable of DamageDice"
            ) from error
        if not damage_dice:
            raise ValueError("damage_dice must contain at least one pool")
        if not all(isinstance(pool, DamageDice) for pool in damage_dice):
            raise TypeError("every damage pool must be DamageDice")

        object.__setattr__(self, "damage_dice", damage_dice)

        try:
            unmodeled_effects = tuple(self.unmodeled_effects)
        except TypeError as error:
            raise TypeError("unmodeled_effects must be an iterable of strings") from error
        if not all(
            isinstance(effect, str) and effect.strip()
            for effect in unmodeled_effects
        ):
            raise ValueError("unmodeled_effects must contain non-empty strings")
        object.__setattr__(self, "unmodeled_effects", unmodeled_effects)


@dataclass(frozen=True)
class SavingThrowScenario:
    name: str
    effect: SavingThrowDamageProfile
    target_save_bonus: int
    save_advantage: bool = False
    save_disadvantage: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.effect, SavingThrowDamageProfile):
            raise TypeError("effect must be a SavingThrowDamageProfile")
        if not isinstance(self.target_save_bonus, int) or isinstance(
            self.target_save_bonus, bool
        ):
            raise TypeError("target_save_bonus must be an integer")
        if not isinstance(self.save_advantage, bool):
            raise TypeError("save_advantage must be a boolean")
        if not isinstance(self.save_disadvantage, bool):
            raise TypeError("save_disadvantage must be a boolean")
