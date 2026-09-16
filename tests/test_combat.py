import random
import unittest

from dnd5ecombat.combat import (
    apply_damage_defenses,
    AttackResult,
    AttackSequenceResult,
    InitiativeParticipant,
    InitiativeResult,
    SavingThrowResult,
    SavingThrowDamageResult,
    reduce_hit_points,
    resolve_attack,
    resolve_attack_sequence,
    resolve_damage,
    resolve_initiative_order,
    resolve_saving_throw,
    resolve_saving_throw_damage,
)
from dnd5ecombat.models import (
    AttackProfile,
    DamageDice,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
)


class FixedRng:
    def __init__(self, result):
        self.result = result

    def randint(self, minimum, maximum):
        if not minimum <= self.result <= maximum:
            raise ValueError("fixed result is outside the requested range")
        return self.result


class SequenceRng:
    def __init__(self, results):
        self.results = iter(results)

    def randint(self, minimum, maximum):
        result = next(self.results)
        if not minimum <= result <= maximum:
            raise ValueError("sequence result is outside the requested range")
        return result


class ResolveInitiativeOrderTests(unittest.TestCase):
    def test_combatants_are_ranked_by_initiative_total(self):
        fast = InitiativeParticipant("Fast", 3)
        slow = InitiativeParticipant("Slow", 0)

        result = resolve_initiative_order(
            (fast, slow), rng=SequenceRng([10, 12])
        )

        self.assertEqual(
            result,
            (
                InitiativeResult(fast, 10, 13),
                InitiativeResult(slow, 12, 12),
            ),
        )

    def test_tied_combatants_use_optional_d20_rerolls(self):
        first = InitiativeParticipant("First", 0)
        second = InitiativeParticipant("Second", 0)

        result = resolve_initiative_order(
            (first, second), rng=SequenceRng([10, 10, 5, 15])
        )

        self.assertEqual(result[0], InitiativeResult(second, 10, 10, (15,)))
        self.assertEqual(result[1], InitiativeResult(first, 10, 10, (5,)))


class ResolveAttackTests(unittest.TestCase):
    def test_natural_one_always_misses(self):
        result = resolve_attack(100, 10, rng=FixedRng(1))

        self.assertEqual(result, AttackResult(1, 101, False, False, (1,)))

    def test_natural_twenty_always_hits_and_is_critical(self):
        result = resolve_attack(-100, 30, rng=FixedRng(20))

        self.assertEqual(result, AttackResult(20, -80, True, True, (20,)))

    def test_ordinary_roll_hits_when_total_exceeds_ac(self):
        result = resolve_attack(5, 14, rng=FixedRng(10))

        self.assertEqual(result, AttackResult(10, 15, True, False, (10,)))

    def test_ordinary_roll_misses_when_total_is_below_ac(self):
        result = resolve_attack(3, 14, rng=FixedRng(10))

        self.assertEqual(result, AttackResult(10, 13, False, False, (10,)))

    def test_meeting_ac_exactly_is_a_hit(self):
        result = resolve_attack(4, 14, rng=FixedRng(10))

        self.assertEqual(result, AttackResult(10, 14, True, False, (10,)))

    def test_advantage_uses_the_higher_roll(self):
        result = resolve_attack(
            3, 15, advantage=True, rng=SequenceRng([5, 14])
        )

        self.assertEqual(result, AttackResult(14, 17, True, False, (5, 14)))

    def test_disadvantage_uses_the_lower_roll(self):
        result = resolve_attack(
            3, 15, disadvantage=True, rng=SequenceRng([18, 5])
        )

        self.assertEqual(result, AttackResult(5, 8, False, False, (18, 5)))

    def test_advantage_and_disadvantage_cancel(self):
        result = resolve_attack(
            3,
            15,
            advantage=True,
            disadvantage=True,
            rng=SequenceRng([12]),
        )

        self.assertEqual(result, AttackResult(12, 15, True, False, (12,)))

    def test_advantage_can_select_a_natural_twenty(self):
        result = resolve_attack(
            -100, 30, advantage=True, rng=SequenceRng([2, 20])
        )

        self.assertEqual(result, AttackResult(20, -80, True, True, (2, 20)))

    def test_disadvantage_can_select_a_natural_one(self):
        result = resolve_attack(
            100, 10, disadvantage=True, rng=SequenceRng([20, 1])
        )

        self.assertEqual(result, AttackResult(1, 101, False, False, (20, 1)))

    def test_attack_inputs_must_be_integers(self):
        invalid_arguments = [
            (1.5, 10),
            (1, "10"),
            (True, 10),
            (1, False),
        ]

        for attack_bonus, target_ac in invalid_arguments:
            with self.subTest(attack_bonus=attack_bonus, target_ac=target_ac):
                with self.assertRaises(TypeError):
                    resolve_attack(attack_bonus, target_ac, rng=FixedRng(10))

    def test_advantage_inputs_must_be_booleans(self):
        with self.assertRaises(TypeError):
            resolve_attack(0, 10, advantage=1)

        with self.assertRaises(TypeError):
            resolve_attack(0, 10, disadvantage=1)


class ResolveSavingThrowTests(unittest.TestCase):
    def test_save_succeeds_when_total_exceeds_dc(self):
        result = resolve_saving_throw(3, 12, rng=FixedRng(10))

        self.assertEqual(result, SavingThrowResult(10, 13, True, (10,)))

    def test_save_fails_when_total_is_below_dc(self):
        result = resolve_saving_throw(1, 12, rng=FixedRng(10))

        self.assertEqual(result, SavingThrowResult(10, 11, False, (10,)))

    def test_meeting_dc_exactly_succeeds(self):
        result = resolve_saving_throw(2, 12, rng=FixedRng(10))

        self.assertEqual(result, SavingThrowResult(10, 12, True, (10,)))

    def test_natural_one_is_not_an_automatic_failure(self):
        result = resolve_saving_throw(100, 20, rng=FixedRng(1))

        self.assertEqual(result, SavingThrowResult(1, 101, True, (1,)))

    def test_natural_twenty_is_not_an_automatic_success(self):
        result = resolve_saving_throw(-100, 20, rng=FixedRng(20))

        self.assertEqual(result, SavingThrowResult(20, -80, False, (20,)))

    def test_advantage_uses_the_higher_roll(self):
        result = resolve_saving_throw(
            2, 15, advantage=True, rng=SequenceRng([5, 14])
        )

        self.assertEqual(result, SavingThrowResult(14, 16, True, (5, 14)))

    def test_disadvantage_uses_the_lower_roll(self):
        result = resolve_saving_throw(
            2, 15, disadvantage=True, rng=SequenceRng([18, 5])
        )

        self.assertEqual(result, SavingThrowResult(5, 7, False, (18, 5)))

    def test_advantage_and_disadvantage_cancel(self):
        result = resolve_saving_throw(
            2,
            15,
            advantage=True,
            disadvantage=True,
            rng=SequenceRng([13]),
        )

        self.assertEqual(result, SavingThrowResult(13, 15, True, (13,)))

    def test_save_inputs_are_validated(self):
        invalid_integer_arguments = [
            (1.5, 10),
            (1, "10"),
            (True, 10),
            (1, False),
        ]

        for save_bonus, difficulty_class in invalid_integer_arguments:
            with self.subTest(
                save_bonus=save_bonus, difficulty_class=difficulty_class
            ):
                with self.assertRaises(TypeError):
                    resolve_saving_throw(save_bonus, difficulty_class)

        with self.assertRaises(TypeError):
            resolve_saving_throw(0, 10, advantage=1)

        with self.assertRaises(TypeError):
            resolve_saving_throw(0, 10, disadvantage=1)


class ResolveSavingThrowDamageTests(unittest.TestCase):
    def test_failed_save_applies_full_damage(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)], damage_modifier=2
        )

        result = resolve_saving_throw_damage(
            effect, save_bonus=0, current_hp=10, rng=SequenceRng([5, 6])
        )

        self.assertEqual(
            result,
            SavingThrowDamageResult(
                SavingThrowResult(5, 5, False, (5,)),
                rolled_damage=8,
                applied_damage=8,
                remaining_hp=2,
            ),
        )

    def test_successful_no_damage_save_skips_damage_roll(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)]
        )

        result = resolve_saving_throw_damage(
            effect, save_bonus=0, current_hp=10, rng=SequenceRng([15])
        )

        self.assertEqual(result.rolled_damage, None)
        self.assertEqual(result.applied_damage, 0)
        self.assertEqual(result.remaining_hp, 10)

    def test_successful_half_damage_save_rounds_down(self):
        effect = SavingThrowDamageProfile(
            "Generic effect",
            10,
            [DamageDice(1, 8)],
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE,
        )

        result = resolve_saving_throw_damage(
            effect, save_bonus=0, current_hp=10, rng=SequenceRng([15, 5])
        )

        self.assertEqual(result.rolled_damage, 5)
        self.assertEqual(result.applied_damage, 2)
        self.assertEqual(result.remaining_hp, 8)

    def test_half_damage_uses_combined_dice_and_modifier_total(self):
        effect = SavingThrowDamageProfile(
            "Generic effect",
            10,
            [DamageDice(1, 6), DamageDice(1, 8)],
            damage_modifier=2,
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE,
        )

        result = resolve_saving_throw_damage(
            effect, save_bonus=0, current_hp=10, rng=SequenceRng([10, 3, 4])
        )

        self.assertEqual(result.rolled_damage, 9)
        self.assertEqual(result.applied_damage, 4)

    def test_save_damage_never_critically_doubles_dice(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 20, [DamageDice(1, 8)]
        )

        result = resolve_saving_throw_damage(
            effect, save_bonus=-100, current_hp=10, rng=SequenceRng([20, 5])
        )

        self.assertFalse(result.saving_throw.success)
        self.assertEqual(result.rolled_damage, 5)
        self.assertEqual(result.applied_damage, 5)

    def test_saving_throw_advantage_is_passed_through(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)]
        )

        result = resolve_saving_throw_damage(
            effect,
            save_bonus=0,
            current_hp=10,
            advantage=True,
            rng=SequenceRng([5, 15]),
        )

        self.assertEqual(result.saving_throw.rolls, (5, 15))
        self.assertTrue(result.saving_throw.success)
        self.assertIsNone(result.rolled_damage)

    def test_applied_damage_cannot_reduce_hp_below_zero(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)]
        )

        result = resolve_saving_throw_damage(
            effect, save_bonus=0, current_hp=3, rng=SequenceRng([5, 8])
        )

        self.assertEqual(result.applied_damage, 8)
        self.assertEqual(result.remaining_hp, 0)

    def test_inputs_are_validated_before_rolling(self):
        effect = SavingThrowDamageProfile(
            "Generic effect", 10, [DamageDice(1, 8)]
        )

        with self.assertRaises(TypeError):
            resolve_saving_throw_damage(
                "effect", 0, 10, rng=SequenceRng([])
            )

        with self.assertRaises(ValueError):
            resolve_saving_throw_damage(
                effect, 0, -1, rng=SequenceRng([])
            )


class ResolveDamageTests(unittest.TestCase):
    def test_damage_dice_can_be_rerolled_once(self):
        result = resolve_damage(
            [DamageDice(2, 6)],
            4,
            reroll_at_or_below=2,
            rng=SequenceRng([1, 6, 2, 1]),
        )

        self.assertEqual(result, 11)

    def test_normal_damage_rolls_listed_dice_and_adds_modifier(self):
        result = resolve_damage([DamageDice(1, 8)], 3, rng=FixedRng(4))

        self.assertEqual(result, 7)

    def test_multiple_damage_pools_are_combined(self):
        result = resolve_damage(
            [DamageDice(1, 8), DamageDice(1, 6)],
            3,
            rng=SequenceRng([4, 2]),
        )

        self.assertEqual(result, 9)

    def test_critical_hit_doubles_damage_dice(self):
        result = resolve_damage(
            [DamageDice(1, 8)],
            3,
            critical=True,
            rng=SequenceRng([4, 5]),
        )

        self.assertEqual(result, 12)

    def test_critical_hit_doubles_every_damage_pool(self):
        result = resolve_damage(
            [DamageDice(1, 8), DamageDice(1, 6)],
            3,
            critical=True,
            rng=SequenceRng([4, 5, 2, 3]),
        )

        self.assertEqual(result, 17)

    def test_critical_hit_adds_modifier_only_once(self):
        result = resolve_damage(
            [DamageDice(2, 6), DamageDice(1, 4)],
            2,
            critical=True,
            rng=FixedRng(1),
        )

        self.assertEqual(result, 8)

    def test_damage_cannot_be_negative(self):
        result = resolve_damage([DamageDice(1, 4)], -5, rng=FixedRng(1))

        self.assertEqual(result, 0)

    def test_seeded_damage_is_reproducible(self):
        first_rng = random.Random(42)
        second_rng = random.Random(42)

        damage_dice = [DamageDice(2, 6)]
        first_results = [
            resolve_damage(damage_dice, 3, rng=first_rng) for _ in range(5)
        ]
        second_results = [
            resolve_damage(damage_dice, 3, rng=second_rng) for _ in range(5)
        ]

        self.assertEqual(first_results, second_results)

    def test_critical_must_be_a_boolean(self):
        with self.assertRaises(TypeError):
            resolve_damage([DamageDice(1, 8)], critical=1)

    def test_damage_dice_pool_values_are_validated(self):
        with self.assertRaises(TypeError):
            DamageDice(True, 8)

        with self.assertRaises(TypeError):
            DamageDice(1, "8")

        with self.assertRaises(ValueError):
            DamageDice(0, 8)

        with self.assertRaises(ValueError):
            DamageDice(1, 1)

    def test_damage_dice_cannot_be_empty(self):
        with self.assertRaises(ValueError):
            resolve_damage([])

    def test_every_damage_pool_must_be_damage_dice(self):
        with self.assertRaises(TypeError):
            resolve_damage([DamageDice(1, 8), (1, 6)])


class ReduceHitPointsTests(unittest.TestCase):
    def test_damage_reduces_current_hp(self):
        self.assertEqual(reduce_hit_points(10, 4), 6)

    def test_damage_can_reduce_current_hp_to_zero(self):
        self.assertEqual(reduce_hit_points(10, 10), 0)

    def test_damage_cannot_reduce_current_hp_below_zero(self):
        self.assertEqual(reduce_hit_points(10, 15), 0)

    def test_zero_damage_does_not_change_current_hp(self):
        self.assertEqual(reduce_hit_points(10, 0), 10)

    def test_damage_at_zero_hp_remains_zero(self):
        self.assertEqual(reduce_hit_points(0, 5), 0)

    def test_hp_inputs_must_be_integers(self):
        invalid_arguments = [
            (10.5, 2),
            (10, "2"),
            (True, 2),
            (10, False),
        ]

        for current_hp, damage in invalid_arguments:
            with self.subTest(current_hp=current_hp, damage=damage):
                with self.assertRaises(TypeError):
                    reduce_hit_points(current_hp, damage)

    def test_hp_inputs_cannot_be_negative(self):
        invalid_arguments = [
            (-1, 2),
            (10, -1),
        ]

        for current_hp, damage in invalid_arguments:
            with self.subTest(current_hp=current_hp, damage=damage):
                with self.assertRaises(ValueError):
                    reduce_hit_points(current_hp, damage)


class ResolveAttackSequenceTests(unittest.TestCase):
    def test_damage_defenses_apply_after_damage_is_rolled(self):
        attack = AttackProfile(
            "Test attack", 5, [DamageDice(1, 8)], 3, damage_type="fire"
        )

        resistant = resolve_attack_sequence(
            attack,
            15,
            20,
            damage_resistances=("fire",),
            rng=SequenceRng([10, 4]),
        )
        vulnerable = resolve_attack_sequence(
            attack,
            15,
            20,
            damage_vulnerabilities=("fire",),
            rng=SequenceRng([10, 4]),
        )
        immune = resolve_attack_sequence(
            attack,
            15,
            20,
            damage_immunities=("fire",),
            rng=SequenceRng([10, 4]),
        )

        self.assertEqual(resistant.damage, 3)
        self.assertEqual(vulnerable.damage, 14)
        self.assertEqual(immune.damage, 0)

    def test_resistance_then_vulnerability_preserves_rounding_order(self):
        self.assertEqual(
            apply_damage_defenses(
                7,
                "fire",
                resistances=("fire",),
                vulnerabilities=("fire",),
            ),
            6,
        )

    def test_miss_deals_no_damage_and_does_not_change_hp(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 8)], 3)
        result = resolve_attack_sequence(
            attack, 10, 10, rng=SequenceRng([5])
        )

        self.assertEqual(
            result,
            AttackSequenceResult(AttackResult(5, 5, False, False, (5,)), 0, 10),
        )

    def test_normal_hit_rolls_damage_and_reduces_hp(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        result = resolve_attack_sequence(
            attack, 15, 10, rng=SequenceRng([10, 4])
        )

        self.assertEqual(
            result,
            AttackSequenceResult(
                AttackResult(10, 15, True, False, (10,)), 7, 3
            ),
        )

    def test_critical_hit_doubles_damage_dice(self):
        attack = AttackProfile("Test attack", 0, [DamageDice(1, 8)], 3)
        result = resolve_attack_sequence(
            attack,
            30,
            20,
            rng=SequenceRng([20, 4, 5]),
        )

        self.assertEqual(
            result,
            AttackSequenceResult(
                AttackResult(20, 20, True, True, (20,)), 12, 8
            ),
        )

    def test_attack_sequence_passes_through_advantage(self):
        attack = AttackProfile("Test attack", 3, [DamageDice(1, 8)], 2)
        result = resolve_attack_sequence(
            attack,
            15,
            10,
            advantage=True,
            rng=SequenceRng([5, 14, 4]),
        )

        self.assertEqual(result.attack.rolls, (5, 14))
        self.assertTrue(result.attack.hit)
        self.assertEqual(result.damage, 6)
        self.assertEqual(result.remaining_hp, 4)

    def test_damage_cannot_reduce_hp_below_zero(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)])
        result = resolve_attack_sequence(
            attack, 15, 5, rng=SequenceRng([10, 8])
        )

        self.assertEqual(result.damage, 8)
        self.assertEqual(result.remaining_hp, 0)

    def test_inputs_are_validated_before_the_attack_roll(self):
        with self.assertRaises(TypeError):
            resolve_attack_sequence("attack", 10, 10, rng=SequenceRng([]))

    def test_attack_sequence_supports_multiple_damage_pools(self):
        attack = AttackProfile("Test attack", 5, [DamageDice(1, 8)], 3)
        result = resolve_attack_sequence(
            attack,
            15,
            30,
            bonus_damage_dice=[DamageDice(2, 6)],
            rng=SequenceRng([10, 4, 2, 5]),
        )

        self.assertEqual(result.damage, 14)
        self.assertEqual(result.remaining_hp, 16)


if __name__ == "__main__":
    unittest.main()
