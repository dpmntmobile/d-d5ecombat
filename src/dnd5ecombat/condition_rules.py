"""Condition modifiers and independently timed effects for duel combat."""

from dataclasses import dataclass

from .attack_models import Condition, SavingThrowConditionEffect


@dataclass(frozen=True)
class ConditionRules:
    prevents_actions: bool = False
    prevents_movement: bool = False
    attack_disadvantage: bool = False
    grants_attack_advantage: bool = False
    fails_physical_saves: bool = False
    dex_save_disadvantage: bool = False


CONDITION_RULES = {
    Condition.PRONE: ConditionRules(attack_disadvantage=True),
    Condition.PARALYZED: ConditionRules(
        prevents_actions=True,
        prevents_movement=True,
        grants_attack_advantage=True,
        fails_physical_saves=True,
    ),
    Condition.POISONED: ConditionRules(attack_disadvantage=True),
    Condition.RESTRAINED: ConditionRules(
        prevents_movement=True,
        attack_disadvantage=True,
        grants_attack_advantage=True,
        dex_save_disadvantage=True,
    ),
    Condition.STUNNED: ConditionRules(
        prevents_actions=True,
        prevents_movement=True,
        grants_attack_advantage=True,
        fails_physical_saves=True,
    ),
    Condition.INCAPACITATED: ConditionRules(prevents_actions=True),
}


@dataclass
class ActiveCondition:
    effect: SavingThrowConditionEffect
    remaining_turns: int = None


class ConditionState:
    """One combatant's effects, keyed by source; modifiers never stack."""

    def __init__(self):
        self.effects = {}

    def __contains__(self, condition):
        return any(
            active.effect.condition == condition for active in self.effects.values()
        )

    def has_rule(self, rule):
        return any(
            getattr(CONDITION_RULES[active.effect.condition], rule)
            for active in self.effects.values()
        )

    def apply(self, effect, source):
        self.effects[source] = ActiveCondition(effect, effect.duration_turns)

    def remove(self, condition):
        sources = [
            key
            for key, active in self.effects.items()
            if active.effect.condition == condition
        ]
        for source in sources:
            del self.effects[source]
        return bool(sources)

    def save_succeeds(self, effect, combatant, resolve_save, rng):
        if effect.save_ability in {"str", "dex"} and self.has_rule(
            "fails_physical_saves"
        ):
            return False
        return resolve_save(
            combatant.get_saving_throw_bonus(effect.save_ability),
            effect.difficulty_class,
            disadvantage=effect.save_ability == "dex"
            and self.has_rule("dex_save_disadvantage"),
            rng=rng,
        ).success

    def end_turn(self, combatant, resolve_save, rng):
        # Resolve all simultaneous saves with the conditions present at this boundary.
        expired = []
        for source, active in self.effects.items():
            if active.remaining_turns is not None:
                active.remaining_turns -= 1
                if active.remaining_turns == 0:
                    expired.append(source)
                    continue
            if active.effect.repeat_save_at_end_of_turn and self.save_succeeds(
                active.effect, combatant, resolve_save, rng
            ):
                expired.append(source)
        for source in expired:
            del self.effects[source]


def condition_effect_to_dict(effect):
    if effect is None:
        return None
    return {
        "difficulty_class": effect.difficulty_class,
        "save_ability": effect.save_ability,
        "condition": effect.condition.value,
        "repeat_save_at_end_of_turn": effect.repeat_save_at_end_of_turn,
        "immune_creature_tags": list(effect.immune_creature_tags),
        "duration_turns": effect.duration_turns,
    }


def condition_effect_from_dict(data):
    if data is None:
        return None
    return SavingThrowConditionEffect(
        difficulty_class=data["difficulty_class"],
        save_ability=data["save_ability"],
        condition=Condition(data["condition"]),
        repeat_save_at_end_of_turn=data.get("repeat_save_at_end_of_turn", False),
        immune_creature_tags=data.get("immune_creature_tags", ()),
        duration_turns=data.get("duration_turns"),
    )
