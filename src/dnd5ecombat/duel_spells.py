"""Per-trial reactions, short spell riders, healing, and concentration."""

from dataclasses import replace

from .combat import resolve_saving_throw, resolve_saving_throw_damage, resolve_attack_sequence
from .attack_models import Condition
from .duel_positioning import attack_range
from .save_action_policy import expected_save_damage, save_flags
from .simulation_core import calculate_attack_analytics
from .duel_turn_policy import attack_flags
from .turn_models import AttackScenario


class DuelSpellState:
    def __init__(self, combatants, hit_points, conditions, resources, hidden, rng):
        self.combatants = combatants
        self.hp = hit_points
        self.conditions = conditions
        self.resources = resources
        self.hidden = hidden
        self.rng = rng
        self.reactions = dict.fromkeys(combatants, True)
        self.turns = dict.fromkeys(combatants, 0)
        self.concentration = {}
        self.mockery_expiry = {}
        self.sliver_expiry = {}
        self.bonus_spell_turn = None
        self.has_reactions = any(s.reaction_trigger for c in combatants.values() for s in c.saving_throw_profiles)

    @property
    def handles_damage(self):
        return self.has_reactions or bool(self.concentration)

    def clear_concentration(self, key):
        self.concentration.pop(key, None)
        for target in self.conditions:
            self.conditions[target].illuminated = any(
                active[0] == target and active[2] == "faerie_fire" for active in self.concentration.values()
            )
            self.conditions[target].blessed = any(
                active[0] == target and active[2] == "bless" for active in self.concentration.values()
            )

    def start_turn(self, key):
        self.turns[key] += 1
        self.reactions[key] = True
        self.bonus_spell_turn = None
        active = self.concentration.get(key)
        if active and self.turns[key] >= active[1]:
            self.clear_concentration(key)
        self.check_incapacitated()

    def check_incapacitated(self):
        for key in tuple(self.concentration):
            if self.hp[key] <= 0 or self.conditions[key].has_rule("prevents_actions"):
                self.clear_concentration(key)

    def end_turn(self, key):
        if self.mockery_expiry.get(key, float("inf")) <= self.turns[key]:
            self.conditions[key].next_attack_disadvantage = False
            self.mockery_expiry.pop(key, None)
        for target, (caster, expiry) in tuple(self.sliver_expiry.items()):
            if caster == key and self.turns[key] >= expiry:
                self.conditions[target].next_save_penalty = False
                del self.sliver_expiry[target]

    def visible(self, key):
        return not self.hidden[key] and not self.conditions[key].invisible

    def apply_save_riders(self, spell, key, target_key, succeeded, distance, speed):
        if succeeded or self.hp[target_key] <= 0:
            return distance
        if spell.next_attack_disadvantage:
            self.apply_mockery(target_key)
        if spell.next_save_penalty:
            self.conditions[target_key].next_save_penalty = True
            self.sliver_expiry[target_key] = (key, self.turns[key] + 1)
        if (spell.flee_on_failed_save and self.reactions[target_key]
                and not self.conditions[target_key].has_rule("prevents_actions")):
            self.reactions[target_key] = False
            if self.conditions[target_key].has_rule("prevents_movement"):
                speed = 0
            if Condition.PRONE in self.conditions[target_key]:
                speed /= 2
            if distance is not None and speed > 0:
                # Reaction movement can provoke a single melee opportunity attack.
                self.opportunity_attack(key, target_key, distance, distance + speed)
                if self.hp[target_key] > 0:
                    distance += speed
        return distance

    def opportunity_attack(self, key, target_key, before, after):
        if (not self.reactions[key] or not self.visible(target_key)
                or self.conditions[key].has_rule("prevents_actions")):
            return
        actor, target = self.combatants[key], self.combatants[target_key]
        attacks = [a for a in actor.attack_sequence + actor.fallback_attacks
                   if a.attack_mode == "melee" and a.spell_slot_level is None
                   and self.resources[key].available(a)
                   and before <= (a.reach_feet or 5) < after]
        if not attacks:
            return
        attack = max(attacks, key=lambda a: calculate_attack_analytics(a, target.armor_class).expected_damage_per_attack)
        self.reactions[key] = False
        self.resources[key].spend(attack)
        _, advantage, disadvantage, critical = attack_flags(
            AttackScenario(attack.name, attack), self.conditions[key], self.conditions[target_key], before)
        advantage = advantage or not self.visible(key)
        self.hidden[key] = False
        self.conditions[key].next_attack_disadvantage = False
        if self.conditions[key].blessed:
            attack = replace(attack, attack_bonus=attack.attack_bonus + self.rng.randint(1, 4))
        result = resolve_attack_sequence(
            attack, target.armor_class, self.hp[target_key], advantage=advantage,
            disadvantage=disadvantage, critical_on_hit=critical,
            damage_resistances=target.damage_resistances,
            damage_vulnerabilities=target.damage_vulnerabilities,
            damage_immunities=target.damage_immunities, undead_fortitude=target.undead_fortitude,
            constitution_save_bonus=target.get_saving_throw_bonus("con"),
            saving_throw_resolver=self.conditions[target_key].resolve_save, rng=self.rng)
        self.hp[target_key] = result.remaining_hp
        self.damaged(target_key, key, result.damage, before)

    def apply_mockery(self, key):
        self.conditions[key].next_attack_disadvantage = True
        self.mockery_expiry[key] = self.turns[key] + 1

    def mockery_value(self, effect, key, target_key, distance, target_advantage=False):
        """Value the expected damage prevented on the opponent's next attack."""
        if not effect.next_attack_disadvantage or self.conditions[target_key].next_attack_disadvantage:
            return 0
        actor, target = self.combatants[key], self.combatants[target_key]
        if not target.attack_sequence or self.conditions[target_key].has_rule("prevents_actions"):
            return 0
        attack = target.attack_sequence[0]
        in_range, advantage, disadvantage, critical = attack_flags(
            AttackScenario(attack.name, attack), self.conditions[target_key], self.conditions[key], distance,
            target_visible=not self.hidden[key],
        )
        if not in_range or disadvantage:
            return 0
        options = dict(advantage=advantage or target_advantage or self.hidden[target_key],
                       damage_resistances=actor.damage_resistances,
                       damage_vulnerabilities=actor.damage_vulnerabilities,
                       damage_immunities=actor.damage_immunities, critical_on_hit=critical)
        normal = calculate_attack_analytics(attack, actor.armor_class, **options).expected_damage_per_attack
        penalized = calculate_attack_analytics(attack, actor.armor_class, disadvantage=True, **options).expected_damage_per_attack
        failure = max(0, min(20, effect.difficulty_class - target.get_saving_throw_bonus(effect.save_ability) - 1)) / 20
        return failure * max(0, normal - penalized)

    def damaged(self, target_key, source_key, damage, distance):
        if damage <= 0:
            return
        self.check_incapacitated()
        if target_key in self.concentration:
            passed = resolve_saving_throw(
                self.conditions[target_key].save_bonus(self.combatants[target_key].get_saving_throw_bonus("con"), self.rng),
                max(10, damage // 2), rng=self.rng,
            ).success
            if not passed:
                self.clear_concentration(target_key)
        if (self.hp[target_key] <= 0 or self.hp[source_key] <= 0
                or not self.reactions[target_key]
                or self.conditions[target_key].has_rule("prevents_actions")
                or not self.visible(source_key) or self.bonus_spell_turn == target_key):
            return
        defender = self.combatants[source_key]
        resource = self.resources[target_key]
        eligible = [s for s in self.combatants[target_key].saving_throw_profiles
                    if s.reaction_trigger == "damaged_by_visible_creature"
                    and resource.available(s)
                    and (distance is None or (s.range_feet is not None and distance <= s.range_feet))]
        if not eligible:
            return
        reaction = max(eligible, key=lambda s: expected_save_damage(resource.prepare(s), defender, self.conditions[source_key]))
        prepared = resource.prepare(reaction)
        if expected_save_damage(prepared, defender, self.conditions[source_key]) <= 0:
            return
        resource.spend(reaction)
        self.reactions[target_key] = False
        automatic, disadvantage = save_flags(prepared, self.conditions[source_key])
        result = resolve_saving_throw_damage(
            prepared, defender.get_saving_throw_bonus(prepared.save_ability),
            self.hp[source_key], disadvantage=disadvantage, automatic_failure=automatic,
            damage_resistances=defender.damage_resistances,
            damage_vulnerabilities=defender.damage_vulnerabilities,
            damage_immunities=defender.damage_immunities,
            undead_fortitude=defender.undead_fortitude,
            constitution_save_bonus=defender.get_saving_throw_bonus("con"), rng=self.rng,
            saving_throw_resolver=self.conditions[source_key].resolve_save,
        )
        self.hp[source_key] = result.remaining_hp
        if prepared.next_attack_disadvantage and not result.saving_throw.success:
            self.apply_mockery(source_key)
        self.damaged(source_key, target_key, result.applied_damage, distance)

    def cast_support(self, key, target_key, spell):
        resource = self.resources[key]
        prepared = resource.prepare(spell)
        resource.spend(spell)
        if spell.effect == "misty_step":
            self.bonus_spell_turn = key
            return
        if spell.effect == "healing":
            amount = prepared.damage_modifier + sum(
                self.rng.randint(1, d.sides) for d in prepared.damage_dice for _ in range(d.number)
            )
            self.hp[key] = min(self.combatants[key].max_hp, self.hp[key] + max(0, amount))
            return
        self.clear_concentration(key)
        if spell.effect == "bless":
            self.concentration[key] = (key, self.turns[key] + spell.duration_turns, "bless")
            self.conditions[key].blessed = True
            return
        target = self.combatants[target_key]
        if not self.conditions[target_key].save_succeeds(spell, target, resolve_saving_throw, self.rng):
            self.concentration[key] = (target_key, self.turns[key] + spell.duration_turns, "faerie_fire")
            self.conditions[target_key].illuminated = True

    def choose_support(self, key, target_key, distance, action_damage, tactical_advantage=False):
        """Heal when badly hurt; buff only if estimated future gain pays for the action.

        This is a bounded heuristic, not a forecast of optimal duel play.
        """
        actor, target = self.combatants[key], self.combatants[target_key]
        resource = self.resources[key]
        best, best_value = None, action_damage
        for spell in actor.support_spells:
            if spell.action_type != "action" or not resource.available(spell):
                continue
            prepared = resource.prepare(spell)
            if spell.effect == "healing":
                if (self.hp[key] > actor.max_hp / 2
                        or {"undead", "construct"} & set(actor.creature_tags)
                        or self.hp[target_key] <= action_damage):
                    continue
                average = sum(d.number * (d.sides + 1) / 2 for d in prepared.damage_dice) + prepared.damage_modifier
                value = min(actor.max_hp - self.hp[key], max(0, average))
            else:
                if (key in self.concentration or (spell.effect == "bless" and self.conditions[key].blessed)
                        or (spell.effect == "faerie_fire" and (
                            self.conditions[target_key].has_rule("grants_attack_advantage")
                            or tactical_advantage or self.hidden[target_key]
                            or (distance is not None and distance > spell.range_feet)))):
                    continue
                attacks = actor.attack_sequence
                normal = boosted = 0
                for attack in attacks:
                    options = dict(damage_resistances=target.damage_resistances,
                                   damage_vulnerabilities=target.damage_vulnerabilities,
                                   damage_immunities=target.damage_immunities,
                                   disadvantage=self.conditions[key].has_rule("attack_disadvantage"))
                    normal += calculate_attack_analytics(attack, target.armor_class, **options).expected_damage_per_attack
                    if spell.effect == "bless":
                        boosted += sum(calculate_attack_analytics(
                            replace(attack, attack_bonus=attack.attack_bonus + die), target.armor_class,
                            **options).expected_damage_per_attack for die in range(1, 5)) / 4
                    else:
                        boosted += calculate_attack_analytics(attack, target.armor_class, advantage=True, **options).expected_damage_per_attack
                failure = 1 if spell.effect == "bless" else max(0, min(20, spell.difficulty_class - target.get_saving_throw_bonus("dex") - 1)) / 20
                automatic, disadvantage = save_flags(spell, self.conditions[target_key])
                failure = 1 if automatic else 1 - (1 - failure) ** 2 if disadvantage else failure
                horizon = min(spell.duration_turns - 1, self.hp[target_key] / max(normal, 0.1))
                # Each future turn is discounted for death/concentration loss.
                value = failure * max(0, boosted - normal) * sum(0.75 ** n for n in range(1, max(1, int(horizon)) + 1))
            if value > best_value:
                best, best_value = spell, value
        return best

    def choose_teleport(self, key, entries, distance, movement):
        if distance is None or not entries:
            return None
        attacks = [s.attack for _, s in entries]
        if any(a.action_type != "action" or a.spell_slot_level not in (None, 0) for a in attacks):
            return None
        preferred = min(attack_range(a)[0] for a in attacks)
        destination = None
        if distance <= 5 and all(getattr(a, "attack_mode", "") == "ranged" for a in attacks):
            destination = min(distance + 30, preferred)
        elif distance - movement > preferred and distance - movement - 30 <= preferred:
            destination = max(preferred, distance - 30)
        if destination is None or destination == distance:
            return None
        spell = next((s for s in self.combatants[key].support_spells
                      if s.effect == "misty_step" and self.resources[key].available(s)), None)
        return (spell, destination) if spell is not None else None
