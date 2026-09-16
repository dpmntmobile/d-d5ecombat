import unittest

from dnd5ecombat.models import (
    AttackProfile,
    AttackScenario,
    DamageDice,
    FirstHitBonusDamage,
    SaveSuccessDamage,
    SavingThrowDamageProfile,
    SavingThrowScenario,
    TargetProfile,
    TurnPlan,
)


class AttackProfileTests(unittest.TestCase):
    def test_damage_dice_are_stored_as_an_immutable_tuple(self):
        source_dice = [DamageDice(1, 8)]

        attack = AttackProfile("Rapier", 5, source_dice, 3)
        source_dice.append(DamageDice(2, 6))

        self.assertEqual(attack.damage_dice, (DamageDice(1, 8),))

    def test_name_cannot_be_empty(self):
        with self.assertRaises(ValueError):
            AttackProfile("  ", 5, [DamageDice(1, 8)], 3)

    def test_attack_bonus_and_damage_modifier_must_be_integers(self):
        with self.assertRaises(TypeError):
            AttackProfile("Rapier", 5.5, [DamageDice(1, 8)], 3)

        with self.assertRaises(TypeError):
            AttackProfile("Rapier", 5, [DamageDice(1, 8)], True)

    def test_base_damage_dice_cannot_be_empty(self):
        with self.assertRaises(ValueError):
            AttackProfile("Rapier", 5, [], 3)

    def test_every_base_damage_pool_must_be_damage_dice(self):
        with self.assertRaises(TypeError):
            AttackProfile("Rapier", 5, [(1, 8)], 3)

    def test_attack_metadata_is_stored_and_validated(self):
        attack = AttackProfile(
            "Shortbow",
            4,
            (DamageDice(1, 6),),
            2,
            damage_type="piercing",
            attack_mode="ranged",
            normal_range_feet=80,
            long_range_feet=320,
            unmodeled_effects=["Example rider"],
        )

        self.assertEqual(attack.damage_type, "piercing")
        self.assertEqual(attack.attack_mode, "ranged")
        self.assertEqual(attack.normal_range_feet, 80)
        self.assertEqual(attack.long_range_feet, 320)
        self.assertEqual(attack.unmodeled_effects, ("Example rider",))

        with self.assertRaises(ValueError):
            AttackProfile(
                "Invalid range",
                4,
                (DamageDice(1, 6),),
                normal_range_feet=80,
                long_range_feet=30,
            )


class SavingThrowDamageProfileTests(unittest.TestCase):
    def test_profile_stores_immutable_damage_dice(self):
        damage_dice = [DamageDice(2, 6)]

        effect = SavingThrowDamageProfile(
            "Generic save effect",
            13,
            damage_dice,
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE,
        )
        damage_dice.clear()

        self.assertEqual(effect.damage_dice, (DamageDice(2, 6),))
        self.assertIs(effect.damage_on_success, SaveSuccessDamage.HALF_DAMAGE)

    def test_profile_defaults_to_no_damage_on_success(self):
        effect = SavingThrowDamageProfile(
            "Generic save effect", 13, [DamageDice(1, 6)]
        )

        self.assertIs(effect.damage_on_success, SaveSuccessDamage.NO_DAMAGE)

    def test_profile_requires_valid_name_dc_and_modifier(self):
        with self.assertRaises(ValueError):
            SavingThrowDamageProfile("", 13, [DamageDice(1, 6)])

        with self.assertRaises(TypeError):
            SavingThrowDamageProfile("Effect", 13.5, [DamageDice(1, 6)])

        with self.assertRaises(TypeError):
            SavingThrowDamageProfile(
                "Effect", 13, [DamageDice(1, 6)], damage_modifier=True
            )

    def test_profile_requires_damage_dice(self):
        with self.assertRaises(ValueError):
            SavingThrowDamageProfile("Effect", 13, [])

        with self.assertRaises(TypeError):
            SavingThrowDamageProfile("Effect", 13, [(1, 6)])

    def test_success_damage_policy_must_use_the_enum(self):
        with self.assertRaises(TypeError):
            SavingThrowDamageProfile(
                "Effect",
                13,
                [DamageDice(1, 6)],
                damage_on_success="half_damage",
            )


class SavingThrowScenarioTests(unittest.TestCase):
    def setUp(self):
        self.effect = SavingThrowDamageProfile(
            "Generic effect", 13, [DamageDice(2, 6)]
        )

    def test_scenario_stores_explicit_target_save_assumptions(self):
        scenario = SavingThrowScenario(
            "Target save +2 with advantage",
            self.effect,
            target_save_bonus=2,
            save_advantage=True,
        )

        self.assertEqual(scenario.target_save_bonus, 2)
        self.assertTrue(scenario.save_advantage)
        self.assertFalse(scenario.save_disadvantage)

    def test_scenario_requires_a_name_and_effect(self):
        with self.assertRaises(ValueError):
            SavingThrowScenario("", self.effect, 2)

        with self.assertRaises(TypeError):
            SavingThrowScenario("Invalid", "effect", 2)

    def test_target_save_bonus_must_be_an_integer(self):
        with self.assertRaises(TypeError):
            SavingThrowScenario("Invalid", self.effect, True)

    def test_save_advantage_flags_must_be_booleans(self):
        with self.assertRaises(TypeError):
            SavingThrowScenario(
                "Invalid", self.effect, 2, save_advantage=1
            )


class TargetProfileTests(unittest.TestCase):
    def test_target_profile_stores_valid_data(self):
        target = TargetProfile(
            "Generic target",
            15,
            30,
            initiative_bonus=2,
            saving_throw_bonuses={"dex": 3, "wis": -1},
            ruleset="2014",
            source_url="https://example.com/monster",
            unmodeled_traits=["Example trait"],
        )

        self.assertEqual(target.name, "Generic target")
        self.assertEqual(target.armor_class, 15)
        self.assertEqual(target.max_hp, 30)
        self.assertEqual(target.initiative_bonus, 2)
        self.assertEqual(target.get_saving_throw_bonus("DEX"), 3)
        self.assertEqual(target.get_saving_throw_bonus("str", 4), 4)
        self.assertIsInstance(target.saving_throw_bonuses, tuple)
        self.assertEqual(target.ruleset, "2014")
        self.assertEqual(target.unmodeled_traits, ("Example trait",))

    def test_target_name_cannot_be_empty(self):
        with self.assertRaises(ValueError):
            TargetProfile("", 15, 30)

    def test_target_ac_and_hp_must_be_integers(self):
        with self.assertRaises(TypeError):
            TargetProfile("Generic target", 15.5, 30)

        with self.assertRaises(TypeError):
            TargetProfile("Generic target", 15, True)

    def test_target_max_hp_must_be_positive(self):
        with self.assertRaises(ValueError):
            TargetProfile("Generic target", 15, 0)

    def test_target_initiative_and_save_bonuses_are_validated(self):
        with self.assertRaises(TypeError):
            TargetProfile("Generic target", 15, 30, initiative_bonus=True)

        with self.assertRaises(ValueError):
            TargetProfile(
                "Generic target", 15, 30, saving_throw_bonuses={"luck": 2}
            )

        with self.assertRaises(TypeError):
            TargetProfile(
                "Generic target", 15, 30, saving_throw_bonuses={"dex": 2.5}
            )


class AttackScenarioTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Rapier", 5, [DamageDice(1, 8)], 3)

    def test_bonus_damage_dice_are_stored_as_an_immutable_tuple(self):
        bonus_dice = [DamageDice(2, 6)]

        scenario = AttackScenario("Rapier with bonus damage", self.attack, bonus_dice)
        bonus_dice.clear()

        self.assertEqual(scenario.bonus_damage_dice, (DamageDice(2, 6),))

    def test_advantage_and_disadvantage_are_explicit_scenario_data(self):
        scenario = AttackScenario(
            "Contested circumstances",
            self.attack,
            advantage=True,
            disadvantage=True,
        )

        self.assertTrue(scenario.advantage)
        self.assertTrue(scenario.disadvantage)

    def test_scenario_name_and_attack_are_validated(self):
        with self.assertRaises(ValueError):
            AttackScenario("", self.attack)

        with self.assertRaises(TypeError):
            AttackScenario("Invalid", "attack")

    def test_scenario_tactical_flags_must_be_booleans(self):
        with self.assertRaises(TypeError):
            AttackScenario("Invalid", self.attack, advantage=1)

    def test_scenario_bonus_damage_must_use_damage_dice(self):
        with self.assertRaises(TypeError):
            AttackScenario("Invalid", self.attack, bonus_damage_dice=[(2, 6)])


class TurnPlanTests(unittest.TestCase):
    def setUp(self):
        attack = AttackProfile("Weapon attack", 5, [DamageDice(1, 8)], 3)
        self.scenario = AttackScenario("Weapon attack", attack)

    def test_attacks_are_stored_as_an_immutable_tuple(self):
        attacks = [self.scenario]

        turn_plan = TurnPlan("One attack", attacks)
        attacks.clear()

        self.assertEqual(turn_plan.attacks, (self.scenario,))

    def test_turn_plan_requires_a_name(self):
        with self.assertRaises(ValueError):
            TurnPlan("", [self.scenario])

    def test_turn_plan_requires_at_least_one_attack(self):
        with self.assertRaises(ValueError):
            TurnPlan("No attacks", [])

    def test_every_turn_plan_attack_must_be_an_attack_scenario(self):
        with self.assertRaises(TypeError):
            TurnPlan("Invalid", ["attack"])

    def test_first_hit_bonus_indices_must_exist_in_turn_plan(self):
        bonus = FirstHitBonusDamage(
            "First-hit bonus", [DamageDice(1, 6)], [1]
        )

        with self.assertRaises(ValueError):
            TurnPlan("One attack", [self.scenario], bonus)


class FirstHitBonusDamageTests(unittest.TestCase):
    def test_data_is_stored_as_immutable_tuples(self):
        damage_dice = [DamageDice(2, 6)]
        eligible_indices = [0, 1]

        bonus = FirstHitBonusDamage(
            "First-hit bonus", damage_dice, eligible_indices
        )
        damage_dice.clear()
        eligible_indices.clear()

        self.assertEqual(bonus.damage_dice, (DamageDice(2, 6),))
        self.assertEqual(bonus.eligible_attack_indices, (0, 1))

    def test_damage_dice_cannot_be_empty(self):
        with self.assertRaises(ValueError):
            FirstHitBonusDamage("First-hit bonus", [], [0])

    def test_eligible_indices_cannot_be_empty_negative_or_duplicated(self):
        damage_dice = [DamageDice(1, 6)]

        with self.assertRaises(ValueError):
            FirstHitBonusDamage("First-hit bonus", damage_dice, [])

        with self.assertRaises(ValueError):
            FirstHitBonusDamage("First-hit bonus", damage_dice, [-1])

        with self.assertRaises(ValueError):
            FirstHitBonusDamage("First-hit bonus", damage_dice, [0, 0])


if __name__ == "__main__":
    unittest.main()
