"""Attack-scenario and fixed turn-plan domain models."""

from dataclasses import dataclass

from .attack_models import AttackProfile, DamageDice


@dataclass(frozen=True)
class AttackScenario:
    name: str
    attack: AttackProfile
    bonus_damage_dice: tuple = ()
    advantage: bool = False
    disadvantage: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.attack, AttackProfile):
            raise TypeError("attack must be an AttackProfile")
        if not isinstance(self.advantage, bool):
            raise TypeError("advantage must be a boolean")
        if not isinstance(self.disadvantage, bool):
            raise TypeError("disadvantage must be a boolean")

        try:
            bonus_damage_dice = tuple(self.bonus_damage_dice)
        except TypeError as error:
            raise TypeError(
                "bonus_damage_dice must be an iterable of DamageDice"
            ) from error
        if not all(isinstance(pool, DamageDice) for pool in bonus_damage_dice):
            raise TypeError("every bonus damage pool must be DamageDice")

        object.__setattr__(self, "bonus_damage_dice", bonus_damage_dice)


@dataclass(frozen=True)
class FirstHitBonusDamage:
    name: str
    damage_dice: tuple
    eligible_attack_indices: tuple
    requires_advantage: bool = False
    allows_nearby_ally: bool = False

    def __post_init__(self):
        if not isinstance(self.allows_nearby_ally, bool):
            raise TypeError("allows_nearby_ally must be a boolean")
        if not isinstance(self.requires_advantage, bool):
            raise TypeError("requires_advantage must be a boolean")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")

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

        try:
            eligible_indices = tuple(self.eligible_attack_indices)
        except TypeError as error:
            raise TypeError(
                "eligible_attack_indices must be an iterable of integers"
            ) from error
        if not eligible_indices:
            raise ValueError("eligible_attack_indices cannot be empty")
        if not all(
            isinstance(index, int) and not isinstance(index, bool)
            for index in eligible_indices
        ):
            raise TypeError("every eligible attack index must be an integer")
        if any(index < 0 for index in eligible_indices):
            raise ValueError("eligible attack indices cannot be negative")
        if len(set(eligible_indices)) != len(eligible_indices):
            raise ValueError("eligible attack indices cannot contain duplicates")

        object.__setattr__(self, "damage_dice", damage_dice)
        object.__setattr__(self, "eligible_attack_indices", eligible_indices)


@dataclass(frozen=True)
class TurnPlan:
    name: str
    attacks: tuple
    first_hit_bonus_damage: FirstHitBonusDamage = None

    def __post_init__(self):
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("name cannot be empty")

        try:
            attacks = tuple(self.attacks)
        except TypeError as error:
            raise TypeError(
                "attacks must be an iterable of AttackScenario"
            ) from error
        if not attacks:
            raise ValueError("attacks must contain at least one AttackScenario")
        if not all(isinstance(attack, AttackScenario) for attack in attacks):
            raise TypeError("every attack must be an AttackScenario")
        if self.first_hit_bonus_damage is not None and not isinstance(
            self.first_hit_bonus_damage, FirstHitBonusDamage
        ):
            raise TypeError(
                "first_hit_bonus_damage must be FirstHitBonusDamage or None"
            )
        if self.first_hit_bonus_damage is not None and any(
            index >= len(attacks)
            for index in self.first_hit_bonus_damage.eligible_attack_indices
        ):
            raise ValueError("eligible attack index is outside the turn plan")

        object.__setattr__(self, "attacks", attacks)
