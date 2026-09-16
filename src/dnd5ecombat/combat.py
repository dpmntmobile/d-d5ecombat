from dataclasses import dataclass

from .dice import roll_d20, roll_dice
from .models import (
    AttackProfile,
    DamageDice,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
)


@dataclass(frozen=True)
class AttackResult:
    natural_roll: int
    total: int
    hit: bool
    critical: bool
    rolls: tuple


@dataclass(frozen=True)
class AttackSequenceResult:
    attack: AttackResult
    damage: int
    remaining_hp: int


@dataclass(frozen=True)
class SavingThrowResult:
    natural_roll: int
    total: int
    success: bool
    rolls: tuple


@dataclass(frozen=True)
class SavingThrowDamageResult:
    saving_throw: SavingThrowResult
    rolled_damage: int | None
    applied_damage: int
    remaining_hp: int


@dataclass(frozen=True)
class InitiativeParticipant:
    name: str
    modifier: int = 0

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.modifier, int) or isinstance(self.modifier, bool):
            raise TypeError("modifier must be an integer")


@dataclass(frozen=True)
class InitiativeResult:
    participant: InitiativeParticipant
    natural_roll: int
    total: int
    tie_break_rolls: tuple = ()


def roll_initiative(initiative_modifier, rng=None):
    """Roll initiative as d20 + initiative modifier, matching the default 5e rule."""
    if not isinstance(initiative_modifier, int) or isinstance(initiative_modifier, bool):
        raise TypeError("initiative_modifier must be an integer")
    return roll_d20(rng=rng) + initiative_modifier


def resolve_initiative_order(participants, rng=None):
    """Roll and rank combatants, rerolling tied combatants as allowed in 2014 5e."""
    try:
        participants = tuple(participants)
    except TypeError as error:
        raise TypeError(
            "participants must be an iterable of InitiativeParticipant"
        ) from error
    if not participants:
        raise ValueError("participants must contain at least one combatant")
    if not all(isinstance(item, InitiativeParticipant) for item in participants):
        raise TypeError("every participant must be an InitiativeParticipant")
    if len({item.name for item in participants}) != len(participants):
        raise ValueError("participant names must be unique")

    entries = [
        {
            "participant": participant,
            "natural_roll": (natural_roll := roll_d20(rng=rng)),
            "total": natural_roll + participant.modifier,
            "tie_break_rolls": [],
        }
        for participant in participants
    ]

    def resolve_tied_group(group):
        if len(group) <= 1:
            return group
        buckets = {}
        for entry in group:
            tie_roll = roll_d20(rng=rng)
            entry["tie_break_rolls"].append(tie_roll)
            buckets.setdefault(tie_roll, []).append(entry)
        ordered = []
        for tie_roll in sorted(buckets, reverse=True):
            ordered.extend(resolve_tied_group(buckets[tie_roll]))
        return ordered

    by_total = {}
    for entry in entries:
        by_total.setdefault(entry["total"], []).append(entry)
    ordered_entries = []
    for total in sorted(by_total, reverse=True):
        ordered_entries.extend(resolve_tied_group(by_total[total]))

    return tuple(
        InitiativeResult(
            participant=entry["participant"],
            natural_roll=entry["natural_roll"],
            total=entry["total"],
            tie_break_rolls=tuple(entry["tie_break_rolls"]),
        )
        for entry in ordered_entries
    )


def resolve_attack(
    attack_bonus,
    target_ac,
    advantage=False,
    disadvantage=False,
    rng=None,
):
    """Resolve one attack roll against a target's Armor Class."""
    if not isinstance(attack_bonus, int) or isinstance(attack_bonus, bool):
        raise TypeError("attack_bonus must be an integer")
    if not isinstance(target_ac, int) or isinstance(target_ac, bool):
        raise TypeError("target_ac must be an integer")
    if not isinstance(advantage, bool):
        raise TypeError("advantage must be a boolean")
    if not isinstance(disadvantage, bool):
        raise TypeError("disadvantage must be a boolean")

    roll_count = 2 if advantage != disadvantage else 1
    rolls = tuple(roll_d20(rng=rng) for _ in range(roll_count))

    if advantage and not disadvantage:
        natural_roll = max(rolls)
    elif disadvantage and not advantage:
        natural_roll = min(rolls)
    else:
        natural_roll = rolls[0]

    total = natural_roll + attack_bonus

    if natural_roll == 1:
        hit = False
        critical = False
    elif natural_roll == 20:
        hit = True
        critical = True
    else:
        hit = total >= target_ac
        critical = False

    return AttackResult(
        natural_roll=natural_roll,
        total=total,
        hit=hit,
        critical=critical,
        rolls=rolls,
    )


def resolve_saving_throw(
    save_bonus,
    difficulty_class,
    advantage=False,
    disadvantage=False,
    rng=None,
):
    """Resolve one ordinary saving throw against a Difficulty Class."""
    if not isinstance(save_bonus, int) or isinstance(save_bonus, bool):
        raise TypeError("save_bonus must be an integer")
    if not isinstance(difficulty_class, int) or isinstance(
        difficulty_class, bool
    ):
        raise TypeError("difficulty_class must be an integer")
    if not isinstance(advantage, bool):
        raise TypeError("advantage must be a boolean")
    if not isinstance(disadvantage, bool):
        raise TypeError("disadvantage must be a boolean")

    roll_count = 2 if advantage != disadvantage else 1
    rolls = tuple(roll_d20(rng=rng) for _ in range(roll_count))

    if advantage and not disadvantage:
        natural_roll = max(rolls)
    elif disadvantage and not advantage:
        natural_roll = min(rolls)
    else:
        natural_roll = rolls[0]

    total = natural_roll + save_bonus
    return SavingThrowResult(
        natural_roll=natural_roll,
        total=total,
        success=total >= difficulty_class,
        rolls=rolls,
    )


def resolve_saving_throw_damage(
    effect,
    save_bonus,
    current_hp,
    advantage=False,
    disadvantage=False,
    damage_resistances=(),
    damage_vulnerabilities=(),
    damage_immunities=(),
    rng=None,
    undead_fortitude=False,
    constitution_save_bonus=0,
    automatic_failure=False,
):
    """Resolve a single-target saving throw through damage and HP reduction."""
    if not isinstance(effect, SavingThrowDamageProfile):
        raise TypeError("effect must be a SavingThrowDamageProfile")

    if not isinstance(automatic_failure, bool):
        raise TypeError("automatic_failure must be a boolean")

    validated_hp = reduce_hit_points(current_hp, 0)
    saving_throw = SavingThrowResult(0, 0, False, ()) if automatic_failure else resolve_saving_throw(
        save_bonus,
        effect.difficulty_class,
        advantage=advantage,
        disadvantage=disadvantage,
        rng=rng,
    )

    if (
        saving_throw.success
        and effect.damage_on_success is SaveSuccessDamage.NO_DAMAGE
    ):
        return SavingThrowDamageResult(
            saving_throw=saving_throw,
            rolled_damage=None,
            applied_damage=0,
            remaining_hp=validated_hp,
        )

    rolled_damage = resolve_damage(
        effect.damage_dice,
        effect.damage_modifier,
        rng=rng,
    )
    if (
        saving_throw.success
        and effect.damage_on_success is SaveSuccessDamage.HALF_DAMAGE
    ):
        applied_damage = rolled_damage // 2
    else:
        applied_damage = rolled_damage
    applied_damage = apply_damage_defenses(
        applied_damage,
        effect.damage_type,
        resistances=damage_resistances,
        vulnerabilities=damage_vulnerabilities,
        immunities=damage_immunities,
    )

    return SavingThrowDamageResult(
        saving_throw=saving_throw,
        rolled_damage=rolled_damage,
        applied_damage=applied_damage,
        remaining_hp=resolve_damage_hit_points(
            validated_hp, applied_damage, effect.damage_type,
            undead_fortitude=undead_fortitude,
            constitution_save_bonus=constitution_save_bonus, rng=rng,
        ),
    )


def _normalize_damage_dice(damage_dice, allow_empty=False):
    try:
        pools = tuple(damage_dice)
    except TypeError as error:
        raise TypeError("damage_dice must be an iterable of DamageDice") from error

    if not pools and not allow_empty:
        raise ValueError("damage_dice must contain at least one pool")
    if not all(isinstance(pool, DamageDice) for pool in pools):
        raise TypeError("every damage pool must be DamageDice")
    return pools


def resolve_damage(
    damage_dice,
    modifier=0,
    critical=False,
    reroll_at_or_below=0,
    rng=None,
):
    """Roll one or more attack-damage dice pools."""
    if not isinstance(critical, bool):
        raise TypeError("critical must be a boolean")
    if not isinstance(modifier, int) or isinstance(modifier, bool):
        raise TypeError("modifier must be an integer")
    if not isinstance(reroll_at_or_below, int) or isinstance(
        reroll_at_or_below, bool
    ):
        raise TypeError("reroll_at_or_below must be an integer")
    if reroll_at_or_below < 0:
        raise ValueError("reroll_at_or_below cannot be negative")

    pools = _normalize_damage_dice(damage_dice)
    if any(reroll_at_or_below >= pool.sides for pool in pools):
        raise ValueError("reroll_at_or_below must be below every damage die size")
    dice_multiplier = 2 if critical else 1
    dice_total = 0
    for pool in pools:
        for _ in range(pool.number * dice_multiplier):
            value = roll_dice(1, pool.sides, rng=rng)
            if value <= reroll_at_or_below:
                value = roll_dice(1, pool.sides, rng=rng)
            dice_total += value

    return max(0, dice_total + modifier)


def reduce_hit_points(current_hp, damage):
    """Reduce current hit points by damage, to a minimum of zero."""
    if not isinstance(current_hp, int) or isinstance(current_hp, bool):
        raise TypeError("current_hp must be an integer")
    if not isinstance(damage, int) or isinstance(damage, bool):
        raise TypeError("damage must be an integer")
    if current_hp < 0:
        raise ValueError("current_hp cannot be negative")
    if damage < 0:
        raise ValueError("damage cannot be negative")

    return max(0, current_hp - damage)


def resolve_damage_hit_points(
    current_hp, damage, damage_type="", *, critical=False,
    undead_fortitude=False, constitution_save_bonus=0, rng=None,
):
    """Apply damage already adjusted for defenses, including survival traits."""
    remaining_hp = reduce_hit_points(current_hp, damage)
    if not isinstance(undead_fortitude, bool):
        raise TypeError("undead_fortitude must be a boolean")
    if (
        undead_fortitude and current_hp > 0 and damage > 0
        and remaining_hp == 0 and not critical
        and damage_type.strip().lower() != "radiant"
    ):
        saving_throw = resolve_saving_throw(
            constitution_save_bonus, 5 + damage, rng=rng
        )
        if saving_throw.success:
            return 1
    return remaining_hp


def apply_damage_defenses(
    damage,
    damage_type="",
    resistances=(),
    vulnerabilities=(),
    immunities=(),
):
    """Apply 5e immunity, resistance, and vulnerability to one damage total."""
    if not isinstance(damage, int) or isinstance(damage, bool):
        raise TypeError("damage must be an integer")
    if damage < 0:
        raise ValueError("damage cannot be negative")
    if not isinstance(damage_type, str):
        raise TypeError("damage_type must be a string")

    def normalized(values, field_name):
        try:
            values = tuple(values)
        except TypeError as error:
            raise TypeError(f"{field_name} must be an iterable of strings") from error
        if not all(isinstance(value, str) for value in values):
            raise TypeError(f"{field_name} must contain strings")
        return {value.strip().lower() for value in values}

    damage_type = damage_type.strip().lower()
    resistance_types = normalized(resistances, "resistances")
    vulnerability_types = normalized(vulnerabilities, "vulnerabilities")
    immunity_types = normalized(immunities, "immunities")
    if damage_type and damage_type in immunity_types:
        return 0
    resistant = bool(damage_type and damage_type in resistance_types)
    vulnerable = bool(damage_type and damage_type in vulnerability_types)
    if resistant:
        damage //= 2
    if vulnerable:
        damage *= 2
    return damage


def resolve_attack_sequence(
    attack,
    target_ac,
    current_hp,
    bonus_damage_dice=(),
    advantage=False,
    disadvantage=False,
    critical_on_hit=False,
    damage_resistances=(),
    damage_vulnerabilities=(),
    damage_immunities=(),
    rng=None,
    undead_fortitude=False,
    constitution_save_bonus=0,
):
    """Resolve one attack from its d20 roll through target HP reduction."""
    if not isinstance(attack, AttackProfile):
        raise TypeError("attack must be an AttackProfile")
    integer_inputs = {
        "target_ac": target_ac,
        "current_hp": current_hp,
    }
    for name, value in integer_inputs.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")

    if current_hp < 0:
        raise ValueError("current_hp cannot be negative")
    if not isinstance(advantage, bool):
        raise TypeError("advantage must be a boolean")
    if not isinstance(disadvantage, bool):
        raise TypeError("disadvantage must be a boolean")
    if not isinstance(critical_on_hit, bool):
        raise TypeError("critical_on_hit must be a boolean")

    bonus_pools = _normalize_damage_dice(bonus_damage_dice, allow_empty=True)
    damage_pools = attack.damage_dice + bonus_pools

    attack_result = resolve_attack(
        attack.attack_bonus,
        target_ac,
        advantage=advantage,
        disadvantage=disadvantage,
        rng=rng,
    )
    if not attack_result.hit:
        return AttackSequenceResult(
            attack=attack_result,
            damage=0,
            remaining_hp=current_hp,
        )

    rolled_damage = resolve_damage(
        damage_pools,
        attack.damage_modifier,
        critical=attack_result.critical or critical_on_hit,
        reroll_at_or_below=attack.reroll_damage_at_or_below,
        rng=rng,
    )
    damage = apply_damage_defenses(
        rolled_damage,
        attack.damage_type,
        resistances=damage_resistances,
        vulnerabilities=damage_vulnerabilities,
        immunities=damage_immunities,
    )
    remaining_hp = resolve_damage_hit_points(
        current_hp, damage, attack.damage_type,
        critical=attack_result.critical or critical_on_hit,
        undead_fortitude=undead_fortitude,
        constitution_save_bonus=constitution_save_bonus, rng=rng,
    )
    return AttackSequenceResult(
        attack=attack_result,
        damage=damage,
        remaining_hp=remaining_hp,
    )
