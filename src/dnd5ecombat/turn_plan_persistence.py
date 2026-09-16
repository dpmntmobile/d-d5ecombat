"""Shared explicit attack-plan JSON contract for monster profiles."""

from .turn_models import AttackScenario, FirstHitBonusDamage, TurnPlan
from .attack_models import DamageDice


def plan_from_dict(data, profiles):
    by_name = {a.name: a for a in profiles}
    attacks = tuple(
        AttackScenario(
            s["name"],
            by_name[s["attack_name"]],
            tuple(DamageDice(**d) for d in s.get("bonus_damage_dice", ())),
            s.get("advantage", False),
            s.get("disadvantage", False),
        )
        for s in data["attacks"]
    )
    bonus = data.get("first_hit_bonus_damage")
    if bonus is not None:
        bonus = FirstHitBonusDamage(
            bonus["name"],
            tuple(DamageDice(**d) for d in bonus["damage_dice"]),
            bonus["eligible_attack_indices"],
            bonus.get("requires_advantage", False),
            bonus.get("allows_nearby_ally", False),
        )
    return TurnPlan(data["name"], attacks, bonus)


def plan_to_dict(plan):
    def dice(values):
        return [dict(number=d.number, sides=d.sides) for d in values]

    bonus = plan.first_hit_bonus_damage
    return dict(
        name=plan.name,
        attacks=[
            dict(
                name=s.name,
                attack_name=s.attack.name,
                bonus_damage_dice=dice(s.bonus_damage_dice),
                advantage=s.advantage,
                disadvantage=s.disadvantage,
            )
            for s in plan.attacks
        ],
        first_hit_bonus_damage=None
        if bonus is None
        else dict(
            name=bonus.name,
            damage_dice=dice(bonus.damage_dice),
            eligible_attack_indices=list(bonus.eligible_attack_indices),
            requires_advantage=bonus.requires_advantage,
            allows_nearby_ally=bonus.allows_nearby_ally,
        ),
    )
