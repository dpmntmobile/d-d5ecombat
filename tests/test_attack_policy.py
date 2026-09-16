"""Exact survival scoring and the user-facing duel selection path."""

from dataclasses import replace
import math
import unittest

from dnd5ecombat.attack_policy import expected_attacks_to_defeat
from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.models import AttackProfile, DamageDice, TargetProfile
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import select_best_attack, simulate_attacks_to_zero


class AttackPolicyTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile(
            "Sword", 100, (DamageDice(1, 2),), damage_type="slashing"
        )
        self.target = TargetProfile(
            "Zombie", 8, 1, undead_fortitude=True,
            saving_throw_bonuses={"con": 3}, attack_profiles=(self.attack,),
        )

    def choose(self, attacks, target=None):
        target = target or self.target
        return select_best_attack(
            attacks, target.armor_class,
            target.damage_resistances, target.damage_vulnerabilities,
            target.damage_immunities, undead_fortitude=target.undead_fortitude,
            target_hp=target.max_hp,
            constitution_save_bonus=target.get_saving_throw_bonus("con"),
        )

    def test_one_hp_geometric_expectation_includes_critical_bypass(self):
        # 90% normal hit, averaging 12.5% failed Fortitude saves; 5% critical.
        expected = 1 / (0.9 * 0.125 + 0.05)
        self.assertAlmostEqual(expected_attacks_to_defeat(self.attack, self.target), expected)
        radiant = replace(self.attack, damage_type=" Radiant ")
        self.assertAlmostEqual(expected_attacks_to_defeat(radiant, self.target), 1 / 0.95)

    def test_two_hp_recurrence_includes_nonlethal_and_survival_transitions(self):
        one_hp = 1 / 0.1625
        expected = (1 + (0.45 + 0.45 * 0.85) * one_hp) / 0.95
        self.assertAlmostEqual(
            expected_attacks_to_defeat(self.attack, replace(self.target, max_hp=2)),
            expected,
        )

    def test_extreme_save_bonuses_do_not_add_automatic_save_results(self):
        for bonus, expected in ((100, 20), (-100, 1 / 0.95)):
            target = replace(self.target, saving_throw_bonuses={"con": bonus})
            self.assertAlmostEqual(expected_attacks_to_defeat(self.attack, target), expected)

    def test_defenses_and_zero_damage_change_the_exact_expectation(self):
        # Resistance: normal d2 deals 0 or 1; critical 2d2 always deals >= 1.
        resistant = replace(self.target, damage_resistances=("slashing",))
        self.assertAlmostEqual(
            expected_attacks_to_defeat(self.attack, resistant), 1 / (0.45 * 0.1 + 0.05)
        )
        vulnerable = replace(self.target, damage_vulnerabilities=("slashing",))
        self.assertAlmostEqual(
            expected_attacks_to_defeat(self.attack, vulnerable), 1 / (0.9 * 0.2 + 0.05)
        )
        immune = replace(self.target, damage_immunities=("slashing",))
        self.assertEqual(expected_attacks_to_defeat(self.attack, immune), math.inf)

    def test_damage_rerolls_affect_survival_scoring(self):
        # Rerolling ones on d2 gives P(1)=1/4, P(2)=3/4.
        attack = replace(self.attack, reroll_damage_at_or_below=1)
        expected = 1 / (0.9 * (0.25 * 0.1 + 0.75 * 0.15) + 0.05)
        self.assertAlmostEqual(expected_attacks_to_defeat(attack, self.target), expected)

    def test_critical_only_damage_and_impossible_attacks(self):
        # -2 modifier means ordinary d2 hits deal zero; critical 2d2 can hurt.
        attack = replace(self.attack, damage_modifier=-2)
        self.assertAlmostEqual(expected_attacks_to_defeat(attack, self.target), 1 / 0.0375)
        harmless = replace(self.attack, damage_modifier=-10)
        self.assertEqual(expected_attacks_to_defeat(harmless, self.target), math.inf)
        self.assertIs(self.choose((harmless, attack)), attack)

    def test_accuracy_and_stable_ties(self):
        radiant = replace(self.attack, name="Radiant", damage_type="radiant", attack_bonus=-100)
        self.assertIs(self.choose((radiant, self.attack)), self.attack)
        tied = replace(self.attack, name="Equal sword")
        self.assertIs(self.choose((tied, self.attack)), tied)
        immune = replace(self.target, damage_immunities=("slashing",))
        self.assertIs(self.choose((tied, self.attack), immune), tied)

    def test_factory_selects_weaker_radiant_when_it_finishes_sooner(self):
        sword = replace(self.attack, damage_dice=(DamageDice(1, 6),), damage_modifier=2)
        radiant = replace(self.attack, name="Radiant", damage_type="radiant")
        build = CharacterBuild("Hero", sword, attack_profiles=(sword, radiant), attacks_per_action=2)
        matchup = build_duel_policy_matchups(build, self.target)[0]
        self.assertEqual(matchup.character.attack_sequence, (radiant, radiant))
        ordinary = replace(self.target, undead_fortitude=False)
        self.assertIs(build_duel_policy_matchups(build, ordinary)[0].character.attack_profile, sword)

    def test_hp_and_radiant_immunity_can_make_stronger_ordinary_attack_better(self):
        sword = replace(self.attack, damage_dice=(DamageDice(1, 12),), damage_modifier=10)
        radiant = replace(self.attack, name="Radiant", damage_type="radiant")
        self.assertIs(self.choose((radiant, sword), replace(self.target, max_hp=22)), sword)
        immune = replace(self.target, damage_immunities=("radiant",))
        self.assertIs(self.choose((radiant, sword), immune), sword)

    def test_full_health_zombie_can_favor_slightly_weaker_radiant_attack(self):
        sword = replace(
            self.attack, attack_bonus=5, damage_dice=(DamageDice(1, 6),), damage_modifier=2
        )
        radiant = replace(sword, name="Radiant", damage_type="radiant", damage_modifier=1)
        target = replace(self.target, max_hp=22)
        self.assertIs(self.choose((sword, radiant), target), radiant)
        self.assertIs(self.choose((sword, radiant), replace(target, undead_fortitude=False)), sword)

    def test_factory_does_not_promote_bonus_actions_into_attack_actions(self):
        bonus = replace(self.attack, name="Bonus", damage_type="radiant", action_type="bonus_action")
        build = CharacterBuild("Hero", self.attack, attack_profiles=(bonus, self.attack))
        self.assertIs(
            build_duel_policy_matchups(build, self.target)[0].character.attack_profile,
            self.attack,
        )

    def test_exact_score_agrees_with_seeded_simulation(self):
        target = replace(self.target, max_hp=22, damage_resistances=("slashing",))
        attack = replace(
            self.attack, attack_bonus=5, damage_dice=(DamageDice(1, 6),),
            damage_modifier=2, reroll_damage_at_or_below=2,
        )
        exact = expected_attacks_to_defeat(attack, target)
        result = simulate_attacks_to_zero(6000, attack, target, seed=941)
        self.assertAlmostEqual(exact, result.average_attacks_to_zero, delta=0.25)

    def test_fortitude_selection_requires_valid_hp_and_save_bonus(self):
        for kwargs in ({}, {"target_hp": 0}, {"target_hp": 1, "constitution_save_bonus": True}):
            with self.assertRaises((TypeError, ValueError)):
                select_best_attack((self.attack,), 8, undead_fortitude=True, **kwargs)


if __name__ == "__main__":
    unittest.main()
