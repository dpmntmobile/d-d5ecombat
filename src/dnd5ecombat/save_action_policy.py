"""Expected damage for single-target saving-throw duel actions."""
from .combat import apply_damage_defenses
from .models import SaveSuccessDamage, Condition
from .simulation_core import _damage_roll_distribution


def save_flags(effect, conditions):
    automatic_failure = effect.save_ability in {"str", "dex"} and conditions.has_rule("fails_physical_saves")
    disadvantage = effect.save_ability == "dex" and conditions.has_rule("dex_save_disadvantage")
    return automatic_failure, disadvantage


def expected_save_damage(effect, defender, conditions):
    automatic_failure, disadvantage = save_flags(effect, conditions)
    required = effect.difficulty_class - defender.get_saving_throw_bonus(effect.save_ability)
    bonuses = range(1, 5) if conditions.blessed else (0,)
    penalties = range(1, 5) if conditions.next_save_penalty else (0,)
    chances = [max(0, min(20, 21 - required + bonus - penalty)) / 20
               for bonus in bonuses for penalty in penalties]
    success = sum(c * c if disadvantage else c for c in chances) / len(chances)
    if automatic_failure:
        success = 0
    if (effect.flee_on_failed_save or effect.next_attack_disadvantage) and Condition.DEAFENED in conditions:
        success = 1
    if (effect.next_save_penalty or effect.next_attack_disadvantage) and conditions.invisible:
        return 0.0
    total = 0.0
    for damage, probability in _damage_roll_distribution(effect.damage_dice, effect.damage_modifier, 1):
        for passed, chance in ((False, 1 - success), (True, success)):
            applied = damage
            if passed:
                applied = damage // 2 if effect.damage_on_success is SaveSuccessDamage.HALF_DAMAGE else 0
            total += probability * chance * apply_damage_defenses(
                applied, effect.damage_type, defender.damage_resistances,
                defender.damage_vulnerabilities, defender.damage_immunities,
            )
    return total


def choose_save_action(effects, resources, defender, conditions, attack_damage):
    best = None
    best_damage = attack_damage
    for effect in effects:
        if not resources.available(effect):
            continue
        damage = expected_save_damage(effect, defender, conditions)
        if damage > best_damage:
            best, best_damage = effect, damage
    return best
