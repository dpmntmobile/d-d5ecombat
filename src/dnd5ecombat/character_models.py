"""Character-domain models shared by every application interface."""

from dataclasses import dataclass
from .tactical_rules import validate_traits

from .resource_models import normalize_spell_slots

from .models import AttackProfile, SavingThrowDamageProfile, TurnPlan
from .profile_validation import normalize_saving_throw_bonuses, normalize_string_tuple


@dataclass(frozen=True)
class CharacterBuild:
    """A validated, interface-independent player-character combat profile."""

    name: str
    attack_profile: AttackProfile
    armor_class: int = 16
    max_hp: int = 20
    save_bonus: int = 2
    initiative_bonus: int = 0
    attacks_per_action: int = 1
    description: str = ""
    equipment: tuple = ()
    attack_profiles: tuple = ()
    saving_throw_profiles: tuple = ()
    saving_throw_bonuses: tuple = ()
    damage_resistances: tuple = ()
    damage_vulnerabilities: tuple = ()
    damage_immunities: tuple = ()
    condition_immunities: tuple = ()
    creature_tags: tuple = ()
    turn_plans: tuple = ()
    spell_slots: tuple = ()
    pact_slots: tuple = ()
    spell_slot_capacity: tuple = ()
    pact_slot_capacity: tuple = ()
    pack_tactics: bool = False
    aggressive: bool = False
    nimble_escape: bool = False
    stealth_bonus: int = 0
    passive_perception: int = 10

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
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.attack_profile, AttackProfile):
            raise TypeError("attack_profile must be an AttackProfile")
        for field_name in ("armor_class", "max_hp", "save_bonus"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer")
        if self.max_hp < 1:
            raise ValueError("max_hp must be at least 1")
        if not isinstance(self.initiative_bonus, int) or isinstance(
            self.initiative_bonus, bool
        ):
            raise TypeError("initiative_bonus must be an integer")
        if not isinstance(self.attacks_per_action, int) or isinstance(
            self.attacks_per_action, bool
        ):
            raise TypeError("attacks_per_action must be an integer")
        if self.attacks_per_action < 1:
            raise ValueError("attacks_per_action must be at least 1")

        try:
            equipment = tuple(self.equipment)
        except TypeError as error:
            raise TypeError("equipment must be an iterable of strings") from error
        if not all(isinstance(item, str) for item in equipment):
            raise TypeError("equipment must contain strings")
        object.__setattr__(self, "equipment", equipment)

        attack_profiles = self.attack_profiles or (self.attack_profile,)
        attack_profiles = tuple(attack_profiles)
        if not all(isinstance(profile, AttackProfile) for profile in attack_profiles):
            raise TypeError("attack_profiles must contain AttackProfile instances")
        object.__setattr__(self, "attack_profiles", attack_profiles)

        saving_throw_profiles = tuple(self.saving_throw_profiles)
        if not all(
            isinstance(profile, SavingThrowDamageProfile)
            for profile in saving_throw_profiles
        ):
            raise TypeError(
                "saving_throw_profiles must contain SavingThrowDamageProfile instances"
            )
        object.__setattr__(self, "saving_throw_profiles", saving_throw_profiles)

        try:
            turn_plans = tuple(self.turn_plans)
        except TypeError as error:
            raise TypeError("turn_plans must be an iterable") from error
        if not all(isinstance(plan, TurnPlan) for plan in turn_plans):
            raise TypeError("turn_plans must contain TurnPlan instances")
        object.__setattr__(self, "turn_plans", turn_plans)

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
                normalize_string_tuple(getattr(self, field_name), field_name),
            )
