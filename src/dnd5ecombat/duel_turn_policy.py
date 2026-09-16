"""Legal attack turn plans, resource reservations, and once-per-turn damage."""

from copy import copy
from dataclasses import dataclass, replace
from functools import lru_cache

from .attack_models import Condition, SavingThrowDamageProfile
from .duel_positioning import approach, attack_position
from .turn_models import AttackScenario, TurnPlan


def validate_duel_plan(plan, attacks_per_action):
    if not isinstance(plan, TurnPlan):
        raise TypeError("turn_plans must contain TurnPlan instances")
    actions = tuple(s.attack for s in plan.attacks if s.attack.action_type == "action")
    bonuses = tuple(
        s.attack for s in plan.attacks if s.attack.action_type == "bonus_action"
    )
    if len(actions) + len(bonuses) != len(plan.attacks):
        raise ValueError(f"{plan.name}: reactions are not supported in duel turn plans")
    if not actions or len(actions) > attacks_per_action or len(bonuses) > 1:
        raise ValueError(f"{plan.name}: needs one action and at most one bonus action")
    if any(s.attack.action_type != "action" for s in plan.attacks[: len(actions)]):
        raise ValueError(f"{plan.name}: action attacks must precede the bonus action")
    spells = tuple(a for a in actions if a.spell_slot_level is not None)
    if spells and len(actions) != 1:
        raise ValueError(f"{plan.name}: casting replaces the entire Attack action")
    if bonuses:
        bonus_spell = bonuses[0].spell_slot_level is not None
        if not bonus_spell and spells:
            raise ValueError(
                f"{plan.name}: off-hand attacks require a weapon Attack action"
            )
        if bonus_spell and any(a.spell_slot_level != 0 for a in spells):
            raise ValueError(
                f"{plan.name}: a bonus-action spell permits only an action cantrip"
            )


def plan_attacks(combatant):
    return tuple(s.attack for plan in combatant.turn_plans for s in plan.attacks)


def attack_flags(scenario, attacker_conditions, defender_conditions, distance):
    attack = scenario.attack
    if isinstance(attack, SavingThrowDamageProfile):
        return distance is None or distance <= attack.range_feet, False, False, False
    close = attack.attack_mode in {"melee", "melee_or_ranged"}
    in_range = True
    range_disadvantage = False
    if distance is not None:
        in_range, ranged, long_range = attack_position(attack, distance)
        close = distance <= 5
        range_disadvantage = long_range or (
            ranged and close and not defender_conditions.has_rule("prevents_actions")
        )
    prone = Condition.PRONE in defender_conditions
    advantage = (
        scenario.advantage
        or defender_conditions.has_rule("grants_attack_advantage")
        or (prone and close)
    )
    disadvantage = (
        scenario.disadvantage
        or (prone and not close)
        or range_disadvantage
        or attacker_conditions.has_rule("attack_disadvantage")
    )
    critical = Condition.PARALYZED in defender_conditions and close
    return in_range, advantage, disadvantage, critical


def first_hit_dice(bonus, index, available, advantage, disadvantage, nearby_ally=False):
    if (
        bonus is not None
        and available
        and index in bonus.eligible_attack_indices
        and (
            not bonus.requires_advantage
            or (advantage and not disadvantage)
            or (
                bonus.allows_nearby_ally
                and nearby_ally
                and (not disadvantage or advantage)
            )
        )
    ):
        return bonus.damage_dice
    return ()


def reserve_plan(plan, resources):
    """Skip depleted entries without changing their bonus eligibility indices."""
    reservation = copy(resources)
    reservation.remaining = resources.remaining.copy()
    reservation.spell_slots = resources.spell_slots.copy()
    reservation.pact_slots = resources.pact_slots.copy()
    entries = []
    weapon_action = False
    for index, scenario in enumerate(plan.attacks):
        attack = scenario.attack
        if not reservation.available(attack):
            continue
        if (
            attack.action_type == "bonus_action"
            and attack.spell_slot_level is None
            and not isinstance(attack, SavingThrowDamageProfile)
            and not weapon_action
        ):
            continue
        reservation.spend(attack)
        entries.append((index, scenario))
        if (
            attack.action_type == "action"
            and attack.spell_slot_level is None
            and not isinstance(attack, SavingThrowDamageProfile)
        ):
            weapon_action = True
    return tuple(entries)


def score_plan(
    entries,
    bonus,
    defender,
    attacker_conditions,
    defender_conditions,
    distance=None,
    movement=0,
    speed=0,
    resources=None,
    tactical_advantage=False,
    nearby_ally=False,
):
    if distance is not None and entries:
        distance, can_attack = approach(
            tuple(s.attack for _, s in entries), distance, movement, speed
        )
        if not can_attack:
            # Dash consumes the action, but a bonus-action spell remains legal.
            entries = tuple(
                (i, s)
                for i, s in entries
                if s.attack.action_type == "bonus_action"
                and (
                    s.attack.spell_slot_level is not None
                    or isinstance(s.attack, SavingThrowDamageProfile)
                )
            )
    if resources is not None:
        resources = copy_resources(resources)
    unused_bonus_probability = 1.0
    damage = 0.0
    weapon_action = False
    for index, scenario in entries:
        attack = scenario.attack
        in_range, advantage, disadvantage, critical = attack_flags(
            scenario,
            attacker_conditions,
            defender_conditions,
            distance,
        )
        advantage = advantage or tactical_advantage
        if not in_range:
            continue
        if (
            attack.action_type == "bonus_action"
            and attack.spell_slot_level is None
            and not isinstance(attack, SavingThrowDamageProfile)
            and not weapon_action
        ):
            continue
        if (
            attack.action_type == "action"
            and attack.spell_slot_level is None
            and not isinstance(attack, SavingThrowDamageProfile)
        ):
            weapon_action = True
        if resources is not None:
            if not resources.available(attack):
                continue
            prepared = resources.prepare(attack)
            resources.spend(attack)
            attack = prepared
        if isinstance(attack, SavingThrowDamageProfile):
            from .save_action_policy import expected_save_damage

            damage += expected_save_damage(attack, defender, defender_conditions)
            continue
        options = dict(
            advantage=advantage,
            disadvantage=disadvantage,
            critical_on_hit=critical,
            damage_resistances=defender.damage_resistances,
            damage_vulnerabilities=defender.damage_vulnerabilities,
            damage_immunities=defender.damage_immunities,
        )
        base = _attack_analytics(
            attack,
            defender.armor_class,
            bonus_damage_dice=scenario.bonus_damage_dice,
            **options,
        )
        damage += base.expected_damage_per_attack
        dice = first_hit_dice(bonus, index, True, advantage, disadvantage, nearby_ally)
        if dice:
            boosted = _attack_analytics(
                attack,
                defender.armor_class,
                bonus_damage_dice=scenario.bonus_damage_dice + dice,
                **options,
            )
            damage += unused_bonus_probability * (
                boosted.expected_damage_per_attack - base.expected_damage_per_attack
            )
            unused_bonus_probability *= 1 - base.hit_probability
    return damage


@lru_cache(maxsize=4096)
def _attack_analytics(
    attack,
    target_ac,
    bonus_damage_dice,
    advantage,
    disadvantage,
    damage_resistances,
    damage_vulnerabilities,
    damage_immunities,
    critical_on_hit,
):
    # Local import keeps domain validation independent of the models facade.
    from .simulation_core import calculate_attack_analytics

    return calculate_attack_analytics(
        attack,
        target_ac,
        bonus_damage_dice,
        advantage,
        disadvantage,
        damage_resistances,
        damage_vulnerabilities,
        damage_immunities,
        critical_on_hit=critical_on_hit,
    )


def choose_turn_plan(
    sequence,
    plans,
    resources,
    defender,
    attacker_conditions,
    defender_conditions,
    distance=None,
    movement=0,
    speed=0,
    saves=(),
    bonus_attacks=(),
    tactical_advantage=False,
    nearby_ally=False,
):
    entries = tuple((i, AttackScenario(a.name, a)) for i, a in enumerate(sequence))
    bonus = None
    best_damage = score_plan(
        entries,
        bonus,
        defender,
        attacker_conditions,
        defender_conditions,
        distance,
        movement,
        speed,
        resources,
        tactical_advantage,
        nearby_ally,
    )
    plans = tuple(plans) + mixed_plans(sequence, plans, saves, bonus_attacks)
    for plan in plans:
        candidate = reserve_plan(plan, resources)
        damage = score_plan(
            candidate,
            plan.first_hit_bonus_damage,
            defender,
            attacker_conditions,
            defender_conditions,
            distance,
            movement,
            speed,
            resources,
            tactical_advantage,
            nearby_ally,
        )
        if damage > best_damage:
            entries, bonus, best_damage = candidate, plan.first_hit_bonus_damage, damage
    return entries, bonus, best_damage


@dataclass(frozen=True)
class SaveEntry:
    attack: SavingThrowDamageProfile


@dataclass(frozen=True)
class ActionPlan:
    attacks: tuple
    first_hit_bonus_damage: object = None


def copy_resources(resources):
    result = copy(resources)
    result.remaining = resources.remaining.copy()
    result.spell_slots = resources.spell_slots.copy()
    result.pact_slots = resources.pact_slots.copy()
    return result


def mixed_plans(sequence, plans, saves, bonus_attacks):
    """Enumerate legal action/bonus combinations without inventing prerequisites."""
    actions = [ActionPlan(tuple(AttackScenario(a.name, a) for a in sequence))]
    for plan in plans:
        entries = tuple(s for s in plan.attacks if s.attack.action_type == "action")
        rider = plan.first_hit_bonus_damage
        if rider is not None:
            indices = tuple(
                i for i in rider.eligible_attack_indices if i < len(entries)
            )
            rider = replace(rider, eligible_attack_indices=indices) if indices else None
        actions.append(ActionPlan(entries, rider))
    actions.extend(
        ActionPlan((SaveEntry(s),)) for s in saves if s.action_type == "action"
    )
    bonuses = [SaveEntry(s) for s in saves if s.action_type == "bonus_action"]
    bonuses.extend(AttackScenario(a.name, a) for a in bonus_attacks)
    result = list(actions[1:])
    for action in actions:
        for bonus in bonuses:
            action_spells = [
                s.attack
                for s in action.attacks
                if s.attack.spell_slot_level is not None
            ]
            if bonus.attack.spell_slot_level is not None and any(
                a.spell_slot_level != 0 for a in action_spells
            ):
                continue
            if (
                isinstance(bonus, AttackScenario)
                and bonus.attack.spell_slot_level is None
            ):
                if (
                    not action.attacks
                    or any(isinstance(s, SaveEntry) for s in action.attacks)
                    or action_spells
                ):
                    continue
            result.append(
                ActionPlan(action.attacks + (bonus,), action.first_hit_bonus_damage)
            )
    # Bonus spells and independent save abilities can still be used without an action.
    result.extend(
        ActionPlan((b,))
        for b in bonuses
        if isinstance(b, SaveEntry) or b.attack.spell_slot_level is not None
    )
    return tuple(result)
