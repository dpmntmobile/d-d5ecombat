"""Target and duel combatant domain models."""

from dataclasses import dataclass
from .tactical_rules import validate_traits, validate_assumptions

from .resource_models import normalize_spell_slots

from .attack_models import AttackProfile, SavingThrowDamageProfile
from .duel_turn_policy import validate_duel_plan
from .duel_positioning import validate_distance
from .profile_validation import (
    normalize_saving_throw_bonuses,
    normalize_string_tuple as _normalize_string_tuple,
)


@dataclass(frozen=True)
class TargetProfile:
    name: str
    armor_class: int
    max_hp: int
    initiative_bonus: int = 0
    saving_throw_bonuses: tuple = ()
    ruleset: str = ""
    source_url: str = ""
    unmodeled_traits: tuple = ()
    attack_profiles: tuple = ()
    damage_resistances: tuple = ()
    damage_vulnerabilities: tuple = ()
    damage_immunities: tuple = ()
    condition_immunities: tuple = ()
    creature_tags: tuple = ()
    multiattack: tuple = ()
    undead_fortitude: bool = False
    spell_slots: tuple = ()
    pact_slots: tuple = ()
    spell_slot_capacity: tuple = ()
    pact_slot_capacity: tuple = ()
    pack_tactics: bool = False
    aggressive: bool = False
    nimble_escape: bool = False
    stealth_bonus: int = 0
    passive_perception: int = 10
    saving_throw_profiles: tuple = ()
    turn_plans: tuple = ()

    def __post_init__(self):
        validate_traits(self)
        object.__setattr__(self, "spell_slots", normalize_spell_slots(self.spell_slots))
        object.__setattr__(self, "pact_slots", normalize_spell_slots(self.pact_slots))
        for field, current in (("spell_slot_capacity", self.spell_slots), ("pact_slot_capacity", self.pact_slots)):
            capacity = normalize_spell_slots(getattr(self, field) or current)
            if any(dict(capacity).get(level, 0) < count for level, count in current):
                raise ValueError(f"{field} cannot be below remaining slots")
            object.__setattr__(self, field, capacity)
        if len(self.pact_slot_capacity) > 1 or any(level > 5 for level, _ in self.pact_slot_capacity):
            raise ValueError("pact_slot_capacity must have one level from 1 through 5")
        if self.pact_slots and self.pact_slot_capacity and self.pact_slots[0][0] != self.pact_slot_capacity[0][0]:
            raise ValueError("pact slot level must match its capacity")
        if len(self.pact_slots) > 1 or any(level > 5 for level, _ in self.pact_slots):
            raise ValueError("pact_slots must have one level from 1 through 5")
        saves = tuple(self.saving_throw_profiles)
        if not all(isinstance(effect, SavingThrowDamageProfile) for effect in saves):
            raise TypeError("saving_throw_profiles must contain SavingThrowDamageProfile instances")
        object.__setattr__(self, "saving_throw_profiles", saves)
        if not isinstance(self.undead_fortitude, bool):
            raise TypeError("undead_fortitude must be a boolean")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.armor_class, int) or isinstance(
            self.armor_class, bool
        ):
            raise TypeError("armor_class must be an integer")
        if not isinstance(self.max_hp, int) or isinstance(self.max_hp, bool):
            raise TypeError("max_hp must be an integer")
        if self.max_hp < 1:
            raise ValueError("max_hp must be at least 1")
        if not isinstance(self.initiative_bonus, int) or isinstance(
            self.initiative_bonus, bool
        ):
            raise TypeError("initiative_bonus must be an integer")

        object.__setattr__(
            self,
            "saving_throw_bonuses",
            normalize_saving_throw_bonuses(self.saving_throw_bonuses),
        )

        for field_name in ("ruleset", "source_url"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")

        try:
            unmodeled_traits = tuple(self.unmodeled_traits)
        except TypeError as error:
            raise TypeError("unmodeled_traits must be an iterable of strings") from error
        if not all(
            isinstance(trait, str) and trait.strip()
            for trait in unmodeled_traits
        ):
            raise ValueError("unmodeled_traits must contain non-empty strings")
        object.__setattr__(self, "unmodeled_traits", unmodeled_traits)

        try:
            attack_profiles = tuple(self.attack_profiles)
        except TypeError as error:
            raise TypeError("attack_profiles must be an iterable") from error
        if not all(
            isinstance(profile, AttackProfile) for profile in attack_profiles
        ):
            raise TypeError("attack_profiles must contain AttackProfile instances")
        object.__setattr__(self, "attack_profiles", attack_profiles)

        for field_name in (
            "damage_resistances",
            "damage_vulnerabilities",
            "damage_immunities",
            "condition_immunities",
            "creature_tags",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_string_tuple(getattr(self, field_name), field_name),
            )
        try:
            multiattack_values = tuple(self.multiattack)
        except TypeError as error:
            raise TypeError("multiattack must be an iterable of attack names") from error
        if not all(
            isinstance(name, str) and name.strip() for name in multiattack_values
        ):
            raise ValueError("multiattack must contain non-empty attack names")
        multiattack = tuple(name.strip() for name in multiattack_values)
        attack_names = {attack.name.lower() for attack in attack_profiles}
        missing_attacks = sorted(
            name for name in set(multiattack) if name.lower() not in attack_names
        )
        if missing_attacks:
            raise ValueError(
                "multiattack references unknown attack(s): "
                + ", ".join(missing_attacks)
            )
        object.__setattr__(self, "multiattack", multiattack)
        plans = tuple(self.turn_plans)
        for plan in plans:
            validate_duel_plan(plan, max(1, len(multiattack)))
        object.__setattr__(self, "turn_plans", plans)

    def get_saving_throw_bonus(self, ability, default=0):
        if not isinstance(ability, str):
            raise TypeError("ability must be a string")
        if not isinstance(default, int) or isinstance(default, bool):
            raise TypeError("default must be an integer")
        normalized_ability = ability.strip().lower()
        return dict(self.saving_throw_bonuses).get(normalized_ability, default)


@dataclass(frozen=True)
class DuelCombatant:
    name: str
    armor_class: int
    max_hp: int
    initiative_bonus: int
    attack_profile: AttackProfile
    attacks_per_turn: int = 1
    attack_sequence: tuple = ()
    saving_throw_bonuses: tuple = ()
    damage_resistances: tuple = ()
    damage_vulnerabilities: tuple = ()
    damage_immunities: tuple = ()
    condition_immunities: tuple = ()
    creature_tags: tuple = ()
    undead_fortitude: bool = False
    spell_slots: tuple = ()
    pact_slots: tuple = ()
    spell_slot_capacity: tuple = ()
    pact_slot_capacity: tuple = ()
    pack_tactics: bool = False
    aggressive: bool = False
    nimble_escape: bool = False
    stealth_bonus: int = 0
    passive_perception: int = 10
    saving_throw_profiles: tuple = ()
    fallback_attacks: tuple = ()
    bonus_attacks: tuple = ()
    turn_plans: tuple = ()

    def __post_init__(self):
        validate_traits(self)
        object.__setattr__(self, "spell_slots", normalize_spell_slots(self.spell_slots))
        object.__setattr__(self, "pact_slots", normalize_spell_slots(self.pact_slots))
        for field, current in (("spell_slot_capacity", self.spell_slots), ("pact_slot_capacity", self.pact_slots)):
            capacity = normalize_spell_slots(getattr(self, field) or current)
            if any(dict(capacity).get(level, 0) < count for level, count in current):
                raise ValueError(f"{field} cannot be below remaining slots")
            object.__setattr__(self, field, capacity)
        if len(self.pact_slot_capacity) > 1 or any(level > 5 for level, _ in self.pact_slot_capacity):
            raise ValueError("pact_slot_capacity must have one level from 1 through 5")
        if self.pact_slots and self.pact_slot_capacity and self.pact_slots[0][0] != self.pact_slot_capacity[0][0]:
            raise ValueError("pact slot level must match its capacity")
        if len(self.pact_slots) > 1 or any(level > 5 for level, _ in self.pact_slots):
            raise ValueError("pact_slots must have one level from 1 through 5")
        saves = tuple(self.saving_throw_profiles)
        if not all(isinstance(effect, SavingThrowDamageProfile) for effect in saves):
            raise TypeError("saving_throw_profiles must contain SavingThrowDamageProfile instances")
        if any(effect.action_type not in {"action", "bonus_action"} or effect.save_ability not in {"str", "dex", "con", "int", "wis", "cha"} for effect in saves):
            raise ValueError("duel save actions need action type and a valid saving throw ability")
        object.__setattr__(self, "saving_throw_profiles", saves)
        if not isinstance(self.undead_fortitude, bool):
            raise TypeError("undead_fortitude must be a boolean")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        for field_name in (
            "armor_class",
            "max_hp",
            "initiative_bonus",
            "attacks_per_turn",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer")
        if self.max_hp < 1:
            raise ValueError("max_hp must be at least 1")
        if self.attacks_per_turn < 1:
            raise ValueError("attacks_per_turn must be at least 1")
        if self.attack_profile is not None and not isinstance(self.attack_profile, AttackProfile):
            raise TypeError("attack_profile must be an AttackProfile")

        try:
            sequence = tuple(self.attack_sequence)
        except TypeError as error:
            raise TypeError("attack_sequence must be an iterable") from error
        if not sequence and self.attack_profile is not None:
            sequence = (self.attack_profile,) * self.attacks_per_turn
        if not all(isinstance(attack, AttackProfile) for attack in sequence):
            raise TypeError("attack_sequence must contain AttackProfile instances")
        if any(attack.action_type != "action" for attack in sequence):
            raise ValueError("attack_sequence must use actions; put bonus actions in turn_plans")
        if not sequence and not saves:
            raise ValueError("a combatant needs attacks or save actions")
        object.__setattr__(self, "attack_sequence", sequence)
        object.__setattr__(self, "attacks_per_turn", len(sequence))
        plans = tuple(self.turn_plans)
        for plan in plans:
            validate_duel_plan(plan, max(1, len(sequence)))
        object.__setattr__(self, "turn_plans", plans)
        bonuses = tuple(self.bonus_attacks)
        if not all(isinstance(a, AttackProfile) and a.action_type == "bonus_action" for a in bonuses):
            raise ValueError("bonus_attacks must contain bonus-action attacks")
        object.__setattr__(self, "bonus_attacks", bonuses)
        fallback = tuple(self.fallback_attacks)
        if not all(isinstance(attack, AttackProfile) for attack in fallback):
            raise TypeError("fallback_attacks must contain AttackProfile instances")
        if any(attack.action_type != "action" for attack in fallback):
            raise ValueError("fallback_attacks must use the action action_type")
        object.__setattr__(self, "fallback_attacks", fallback)

        object.__setattr__(
            self,
            "saving_throw_bonuses",
            normalize_saving_throw_bonuses(self.saving_throw_bonuses),
        )

        for field_name in (
            "damage_resistances",
            "damage_vulnerabilities",
            "damage_immunities",
            "condition_immunities",
            "creature_tags",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_string_tuple(getattr(self, field_name), field_name),
            )

    def get_saving_throw_bonus(self, ability, default=0):
        return dict(self.saving_throw_bonuses).get(ability.strip().lower(), default)


@dataclass(frozen=True)
class DuelMatchup:
    character: DuelCombatant
    monster: DuelCombatant
    starting_distance_feet: int = None
    character_speed_feet: int = 30
    monster_speed_feet: int = 30
    character_ally_near_target: bool = False
    monster_ally_near_target: bool = False
    character_can_hide: bool = False
    monster_can_hide: bool = False
    rest_before_duel: str = "none"

    def __post_init__(self):
        validate_assumptions(self)
        if self.rest_before_duel not in {"none", "short", "long"}:
            raise ValueError("rest_before_duel must be none, short, or long")
        validate_distance(self.starting_distance_feet, "starting_distance_feet", optional=True)
        validate_distance(self.character_speed_feet, "character_speed_feet")
        validate_distance(self.monster_speed_feet, "monster_speed_feet")
        if not isinstance(self.character, DuelCombatant):
            raise TypeError("character must be a DuelCombatant")
        if not isinstance(self.monster, DuelCombatant):
            raise TypeError("monster must be a DuelCombatant")
