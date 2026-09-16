"""Two-sided duel simulation and action-policy selection."""

from .combat import (
    InitiativeParticipant,
    resolve_attack_sequence,
    resolve_initiative_order,
    resolve_saving_throw,
    resolve_saving_throw_damage,
)
from .condition_rules import ConditionState
from .action_resources import AttackResources
from .save_action_policy import expected_save_damage, save_flags
from .attack_policy import expected_attacks_to_defeat
from .duel_positioning import approach, attack_range
from .duel_turn_policy import (
    attack_flags,
    choose_turn_plan,
    first_hit_dice,
    plan_attacks,
)
from .turn_models import AttackScenario
from .models import (
    AttackProfile,
    Condition,
    DuelMatchup,
    TargetProfile,
    SavingThrowDamageProfile,
)
from .simulation_core import (
    DuelSimulationResult,
    _check_cancellation,
    _create_random_source,
    _process_map,
    _validate_trials,
    _validate_workers,
    calculate_attack_analytics,
)


def select_best_attack(
    attack_profiles,
    target_ac,
    damage_resistances=(),
    damage_vulnerabilities=(),
    damage_immunities=(),
    *,
    undead_fortitude=False,
    target_hp=None,
    constitution_save_bonus=0,
    attacks_per_action=1,
):
    """Choose action damage, or expected attacks per action against Fortitude.

    Fortitude selection requires target_hp and keeps one attack for the duel.
    Ties retain profile order. Positioning and condition riders are not scored.
    Spells make one attack per cast; weapons use attacks_per_action attacks.
    """
    try:
        attack_profiles = tuple(attack_profiles)
    except TypeError as error:
        raise TypeError("attack_profiles must be an iterable") from error
    if not attack_profiles:
        raise ValueError("attack_profiles must contain at least one attack")
    if not all(isinstance(attack, AttackProfile) for attack in attack_profiles):
        raise TypeError("attack_profiles must contain AttackProfile instances")

    if not isinstance(undead_fortitude, bool):
        raise TypeError("undead_fortitude must be a boolean")
    if not isinstance(attacks_per_action, int) or isinstance(attacks_per_action, bool):
        raise TypeError("attacks_per_action must be an integer")
    if attacks_per_action < 1:
        raise ValueError("attacks_per_action must be positive")

    def attacks_per_cast_or_action(attack):
        return 1 if attack.spell_slot_level is not None else attacks_per_action

    if undead_fortitude:
        target = TargetProfile(
            "Selection target",
            target_ac,
            target_hp,
            saving_throw_bonuses={"con": constitution_save_bonus},
            damage_resistances=damage_resistances,
            damage_vulnerabilities=damage_vulnerabilities,
            damage_immunities=damage_immunities,
            undead_fortitude=True,
        )
        return min(
            attack_profiles,
            key=lambda attack: (
                expected_attacks_to_defeat(attack, target)
                / attacks_per_cast_or_action(attack)
            ),
        )

    best_attack = attack_profiles[0]
    best_damage = calculate_attack_analytics(
        best_attack,
        target_ac,
        damage_resistances=damage_resistances,
        damage_vulnerabilities=damage_vulnerabilities,
        damage_immunities=damage_immunities,
    ).expected_damage_per_attack * attacks_per_cast_or_action(best_attack)
    for attack in attack_profiles[1:]:
        expected_damage = calculate_attack_analytics(
            attack,
            target_ac,
            damage_resistances=damage_resistances,
            damage_vulnerabilities=damage_vulnerabilities,
            damage_immunities=damage_immunities,
        ).expected_damage_per_attack * attacks_per_cast_or_action(attack)
        if expected_damage > best_damage:
            best_attack = attack
            best_damage = expected_damage
    return best_attack


def select_attack_sequence(
    attack_profiles,
    multiattack,
    target_ac,
    damage_resistances=(),
    damage_vulnerabilities=(),
    damage_immunities=(),
):
    """Resolve an explicit multiattack or fall back to the best single attack."""
    attack_profiles = tuple(attack_profiles)
    multiattack = tuple(multiattack)
    if not multiattack:
        return (
            select_best_attack(
                attack_profiles,
                target_ac,
                damage_resistances,
                damage_vulnerabilities,
                damage_immunities,
            ),
        )
    attacks_by_name = {
        attack.name.strip().lower(): attack for attack in attack_profiles
    }
    try:
        return tuple(attacks_by_name[name.strip().lower()] for name in multiattack)
    except KeyError as error:
        raise ValueError(
            f"multiattack references unknown attack: {error.args[0]}"
        ) from error


def simulate_duel(
    trials,
    matchup,
    max_rounds_per_trial=10_000,
    seed=None,
    rng=None,
    cancellation_check=None,
):
    """Simulate initiative-ordered attack turns until one combatant reaches 0 HP."""
    _validate_trials(trials)
    if not isinstance(matchup, DuelMatchup):
        raise TypeError("matchup must be a DuelMatchup")
    if not isinstance(max_rounds_per_trial, int) or isinstance(
        max_rounds_per_trial, bool
    ):
        raise TypeError("max_rounds_per_trial must be an integer")
    if max_rounds_per_trial < 1:
        raise ValueError("max_rounds_per_trial must be at least 1")

    def can_damage(attacker, defender):
        return (
            any(
                calculate_attack_analytics(
                    attack,
                    defender.armor_class,
                    damage_resistances=defender.damage_resistances,
                    damage_vulnerabilities=defender.damage_vulnerabilities,
                    damage_immunities=defender.damage_immunities,
                ).expected_damage_per_attack
                > 0
                for attack in attacker.attack_sequence
                + attacker.fallback_attacks
                + attacker.bonus_attacks
                + plan_attacks(attacker)
            )
            or any(
                expected_save_damage(effect, defender, ConditionState()) > 0
                for effect in attacker.saving_throw_profiles
            )
            or any(
                calculate_attack_analytics(
                    scenario.attack,
                    defender.armor_class,
                    bonus_damage_dice=scenario.bonus_damage_dice
                    + (
                        plan.first_hit_bonus_damage.damage_dice
                        if plan.first_hit_bonus_damage is not None
                        and index in plan.first_hit_bonus_damage.eligible_attack_indices
                        else ()
                    ),
                    damage_resistances=defender.damage_resistances,
                    damage_vulnerabilities=defender.damage_vulnerabilities,
                    damage_immunities=defender.damage_immunities,
                ).expected_damage_per_attack
                > 0
                for plan in attacker.turn_plans
                for index, scenario in enumerate(plan.attacks)
            )
        )

    if not can_damage(matchup.character, matchup.monster) and not can_damage(
        matchup.monster, matchup.character
    ):
        raise ValueError("duel cannot end because neither combatant can deal damage")

    positioned = matchup.starting_distance_feet is not None
    if positioned:
        for combatant in (matchup.character, matchup.monster):
            for attack in (
                combatant.attack_sequence
                + combatant.fallback_attacks
                + combatant.bonus_attacks
                + plan_attacks(combatant)
            ):
                attack_range(attack)
            for effect in combatant.saving_throw_profiles:
                if effect.range_feet is None:
                    raise ValueError(f"{effect.name}: positioning requires range_feet")

    random_source = _create_random_source(seed, rng)
    character_wins = 0
    monster_wins = 0
    character_initiative_wins = 0
    total_rounds = 0
    total_character_remaining_hp = 0
    total_monster_remaining_hp = 0

    combatants = {
        "character": matchup.character,
        "monster": matchup.monster,
    }
    participants = (
        InitiativeParticipant("character", matchup.character.initiative_bonus),
        InitiativeParticipant("monster", matchup.monster.initiative_bonus),
    )

    for trial_number in range(1, trials + 1):
        _check_cancellation(cancellation_check)
        initiative_order = resolve_initiative_order(participants, rng=random_source)
        turn_order = tuple(result.participant.name for result in initiative_order)
        if turn_order[0] == "character":
            character_initiative_wins += 1

        hit_points = {
            "character": matchup.character.max_hp,
            "monster": matchup.monster.max_hp,
        }
        conditions = {"character": ConditionState(), "monster": ConditionState()}
        resources = {
            key: AttackResources(
                combatant.attack_sequence
                + combatant.fallback_attacks
                + combatant.saving_throw_profiles
                + combatant.bonus_attacks
                + plan_attacks(combatant),
                combatant.spell_slots,
                combatant.pact_slots,
                combatant.spell_slot_capacity,
                combatant.pact_slot_capacity,
            )
            for key, combatant in combatants.items()
        }
        if matchup.rest_before_duel != "none":
            for state in resources.values():
                state.rest(matchup.rest_before_duel)
        hidden = {"character": False, "monster": False}
        distance = matchup.starting_distance_feet
        trial_rounds = 0
        while hit_points["character"] > 0 and hit_points["monster"] > 0:
            _check_cancellation(cancellation_check)
            if trial_rounds >= max_rounds_per_trial:
                raise RuntimeError(
                    f"trial {trial_number} exceeded "
                    f"max_rounds_per_trial={max_rounds_per_trial}"
                )
            trial_rounds += 1

            for attacker_key in turn_order:
                defender_key = "monster" if attacker_key == "character" else "character"
                attacker = combatants[attacker_key]
                defender = combatants[defender_key]

                attacker_conditions = conditions[attacker_key]
                can_act = not attacker_conditions.has_rule("prevents_actions")
                can_move = not attacker_conditions.has_rule("prevents_movement")
                speed = (
                    getattr(matchup, f"{attacker_key}_speed_feet") if can_move else 0
                )
                movement = speed
                if can_move and (not positioned or speed > 0):
                    if attacker_conditions.remove(Condition.PRONE):
                        movement /= 2
                attacker_resources = resources[attacker_key]
                attacker_resources.start_turn(random_source)
                attack_sequence = attacker_resources.plan(
                    attacker.attack_sequence,
                    attacker.fallback_attacks,
                    lambda available: select_best_attack(
                        available,
                        defender.armor_class,
                        defender.damage_resistances,
                        defender.damage_vulnerabilities,
                        defender.damage_immunities,
                        undead_fortitude=defender.undead_fortitude,
                        target_hp=hit_points[defender_key],
                        constitution_save_bonus=defender.get_saving_throw_bonus("con"),
                        attacks_per_action=max(1, len(attacker.attack_sequence)),
                    ),
                )
                entries = tuple(
                    (i, AttackScenario(a.name, a))
                    for i, a in enumerate(attack_sequence)
                )
                bonus_policy = None
                attack_damage = 0.0
                nearby_ally = getattr(matchup, f"{attacker_key}_ally_near_target")
                tactical_advantage = attacker.pack_tactics and nearby_ally
                if can_act and (
                    attacker.turn_plans
                    or attacker.saving_throw_profiles
                    or attacker.bonus_attacks
                ):
                    entries, bonus_policy, attack_damage = choose_turn_plan(
                        attack_sequence,
                        attacker.turn_plans,
                        attacker_resources,
                        defender,
                        attacker_conditions,
                        conditions[defender_key],
                        distance,
                        movement,
                        speed,
                        saves=attacker.saving_throw_profiles,
                        bonus_attacks=attacker.bonus_attacks,
                        tactical_advantage=tactical_advantage,
                        nearby_ally=nearby_ally,
                    )
                    attack_sequence = tuple(s.attack for _, s in entries)
                bonus_used = any(
                    s.attack.action_type == "bonus_action" for _, s in entries
                )
                if can_act and not bonus_used and positioned and attack_sequence:
                    preferred = min(attack_range(a)[0] for a in attack_sequence)
                    if attacker.aggressive and distance - movement > preferred:
                        movement += speed
                        bonus_used = True
                    elif (
                        attacker.nimble_escape
                        and distance <= 5
                        and preferred > distance
                        and movement > 0
                        and all(
                            getattr(a, "attack_mode", "") == "ranged"
                            for a in attack_sequence
                        )
                    ):
                        # Bonus-action Disengage, then ordinary movement to bow range.
                        distance = min(preferred, distance + movement)
                        movement = 0
                        bonus_used = True
                if positioned and attack_sequence:
                    distance, can_attack = approach(
                        attack_sequence, distance, movement, speed if can_act else 0
                    )
                    if not can_attack:
                        entries = tuple(
                            (i, s)
                            for i, s in entries
                            if s.attack.action_type == "bonus_action"
                            and (
                                s.attack.spell_slot_level is not None
                                or isinstance(s.attack, SavingThrowDamageProfile)
                            )
                        )
                if (
                    can_act
                    and attacker.nimble_escape
                    and not bonus_used
                    and not hidden[attacker_key]
                    and getattr(matchup, f"{attacker_key}_can_hide")
                ):
                    stealth = random_source.randint(1, 20)
                    if Condition.POISONED in attacker_conditions:
                        stealth = min(stealth, random_source.randint(1, 20))
                    perception = defender.passive_perception
                    if Condition.POISONED in conditions[defender_key]:
                        perception -= 5
                    hidden[attacker_key] = stealth + attacker.stealth_bonus > perception
                    bonus_used = True
                if not can_act:
                    entries = ()
                first_hit_available = True
                weapon_action_attempted = False
                for attack_index, scenario in entries:
                    attack = scenario.attack
                    defender_conditions = conditions[defender_key]
                    in_range, advantage, disadvantage, critical = attack_flags(
                        scenario,
                        attacker_conditions,
                        defender_conditions,
                        distance,
                    )
                    advantage = advantage or tactical_advantage or hidden[attacker_key]
                    disadvantage = disadvantage or hidden[defender_key]
                    if not in_range:
                        continue
                    if (
                        attack.action_type == "bonus_action"
                        and attack.spell_slot_level is None
                        and not isinstance(attack, SavingThrowDamageProfile)
                        and not weapon_action_attempted
                    ):
                        continue
                    if (
                        attack.action_type == "action"
                        and attack.spell_slot_level is None
                        and not isinstance(attack, SavingThrowDamageProfile)
                    ):
                        weapon_action_attempted = True
                    if isinstance(attack, SavingThrowDamageProfile):
                        prepared = attacker_resources.prepare(attack)
                        attacker_resources.spend(attack)
                        automatic_failure, save_disadvantage = save_flags(
                            prepared, defender_conditions
                        )
                        result = resolve_saving_throw_damage(
                            prepared,
                            defender.get_saving_throw_bonus(prepared.save_ability),
                            hit_points[defender_key],
                            disadvantage=save_disadvantage,
                            automatic_failure=automatic_failure,
                            damage_resistances=defender.damage_resistances,
                            damage_vulnerabilities=defender.damage_vulnerabilities,
                            damage_immunities=defender.damage_immunities,
                            undead_fortitude=defender.undead_fortitude,
                            constitution_save_bonus=defender.get_saving_throw_bonus(
                                "con"
                            ),
                            rng=random_source,
                        )
                        hit_points[defender_key] = result.remaining_hp
                        if result.remaining_hp == 0:
                            break
                        continue
                    conditional_bonus = first_hit_dice(
                        bonus_policy,
                        attack_index,
                        first_hit_available,
                        advantage,
                        disadvantage,
                        nearby_ally,
                    )
                    hidden[attacker_key] = False
                    prepared = attacker_resources.prepare(attack)
                    attacker_resources.spend(attack)
                    result = resolve_attack_sequence(
                        prepared,
                        defender.armor_class,
                        hit_points[defender_key],
                        advantage=advantage,
                        disadvantage=disadvantage,
                        critical_on_hit=critical,
                        bonus_damage_dice=scenario.bonus_damage_dice
                        + conditional_bonus,
                        damage_resistances=defender.damage_resistances,
                        damage_vulnerabilities=defender.damage_vulnerabilities,
                        damage_immunities=defender.damage_immunities,
                        undead_fortitude=defender.undead_fortitude,
                        constitution_save_bonus=defender.get_saving_throw_bonus("con"),
                        rng=random_source,
                    )
                    if conditional_bonus and result.attack.hit:
                        first_hit_available = False
                    hit_points[defender_key] = result.remaining_hp
                    if hit_points[defender_key] == 0:
                        break

                    effect = attack.condition_effect
                    if result.attack.hit and effect is not None:
                        immune_by_tag = bool(
                            set(effect.immune_creature_tags)
                            & set(defender.creature_tags)
                        )
                        immune_to_condition = (
                            effect.condition.value in defender.condition_immunities
                        )
                        if not immune_by_tag and not immune_to_condition:
                            if not defender_conditions.save_succeeds(
                                effect, defender, resolve_saving_throw, random_source
                            ):
                                defender_conditions.apply(
                                    effect, (attacker_key, attack)
                                )

                attacker_conditions.end_turn(
                    attacker, resolve_saving_throw, random_source
                )
                if hit_points[defender_key] == 0:
                    break

        total_rounds += trial_rounds
        if hit_points["monster"] == 0:
            character_wins += 1
            total_character_remaining_hp += hit_points["character"]
        else:
            monster_wins += 1
            total_monster_remaining_hp += hit_points["monster"]

    return DuelSimulationResult(
        trials=trials,
        character_wins=character_wins,
        monster_wins=monster_wins,
        character_initiative_wins=character_initiative_wins,
        total_rounds=total_rounds,
        total_character_remaining_hp=total_character_remaining_hp,
        total_monster_remaining_hp=total_monster_remaining_hp,
    )


def _simulate_duel_job(job):
    matchup, trials, max_rounds_per_trial, seed = job
    return simulate_duel(
        trials,
        matchup,
        max_rounds_per_trial=max_rounds_per_trial,
        seed=seed,
    )


def simulate_duel_batch(
    matchups,
    trials,
    seed=None,
    max_rounds_per_trial=10_000,
    workers=1,
    cancellation_check=None,
):
    """Simulate independent duel matchups, optionally in worker processes."""
    try:
        matchups = tuple(matchups)
    except TypeError as error:
        raise TypeError("matchups must be an iterable of DuelMatchup") from error
    if not matchups:
        raise ValueError("matchups must contain at least one DuelMatchup")
    if not all(isinstance(matchup, DuelMatchup) for matchup in matchups):
        raise TypeError("every matchup must be a DuelMatchup")
    _validate_trials(trials)
    _validate_workers(workers)
    if workers == 1 and cancellation_check is not None:
        return tuple(
            simulate_duel(
                trials,
                matchup,
                max_rounds_per_trial=max_rounds_per_trial,
                seed=seed,
                cancellation_check=cancellation_check,
            )
            for matchup in matchups
        )
    jobs = ((matchup, trials, max_rounds_per_trial, seed) for matchup in matchups)
    return _process_map(_simulate_duel_job, jobs, workers)


def select_best_monster_duel_policy(matchups, results):
    """Select the simulated monster policy that performs best in the duel."""
    matchups = tuple(matchups)
    results = tuple(results)
    if not matchups or len(matchups) != len(results):
        raise ValueError("matchups and results must have the same non-zero length")
    if not all(isinstance(matchup, DuelMatchup) for matchup in matchups):
        raise TypeError("matchups must contain DuelMatchup instances")
    if not all(isinstance(result, DuelSimulationResult) for result in results):
        raise TypeError("results must contain DuelSimulationResult instances")

    best_index = min(
        range(len(results)),
        key=lambda index: (
            results[index].character_wins,
            -results[index].total_monster_remaining_hp,
            results[index].total_rounds,
            index,
        ),
    )
    return matchups[best_index], results[best_index], best_index
