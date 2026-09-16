"""Regression coverage for the 2014 zombie survival trait."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dnd5ecombat.application_service import SimulationSettings, evaluate_attacks
from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.combat import resolve_attack_sequence, resolve_saving_throw_damage
from dnd5ecombat.models import (
    AttackProfile, AttackScenario, DamageDice, DuelCombatant,
    DuelMatchup, SaveSuccessDamage, SavingThrowDamageProfile, SavingThrowScenario,
    TargetProfile, TurnPlan,
)
from dnd5ecombat.monster_profiles import load_monster_profile, save_monster_profile
from dnd5ecombat.profile_schema import validate_profile, ProfileValidationError
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation import (
    simulate_attacks_to_zero, simulate_turns_to_zero,
    simulate_saving_throw_uses_to_zero, simulate_duel,
)


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)

    def randint(self, low, high):
        value = next(self.values)
        assert low <= value <= high
        return value


class UndeadFortitudeTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile(
            "Sword", 10, (DamageDice(1, 6),), damage_type="slashing"
        )
        self.target = TargetProfile(
            "Zombie", 8, 1, saving_throw_bonuses={"con": 3},
            undead_fortitude=True,
        )

    def hit(self, rolls, **kwargs):
        return resolve_attack_sequence(
            self.attack, 8, 1, undead_fortitude=True,
            constitution_save_bonus=3, rng=Rolls(*rolls), **kwargs,
        )

    def test_save_uses_full_damage_and_succeeds_at_exact_dc(self):
        # Six damage sets DC 11 even though the target has only one HP.
        self.assertEqual(self.hit((10, 6, 8)).remaining_hp, 1)
        self.assertEqual(self.hit((10, 6, 7)).remaining_hp, 0)

    def test_repeated_lethal_hits_each_get_a_save(self):
        result = simulate_attacks_to_zero(
            1, self.attack, self.target, rng=Rolls(10, 6, 8, 10, 6, 8, 10, 6, 7)
        )
        self.assertEqual(result.total_attacks, 3)
        self.assertEqual(result.total_hp_removed, 1)
        self.assertEqual(result.total_rolled_damage, 18)

    def test_radiant_and_both_kinds_of_critical_bypass_save(self):
        self.assertEqual(self.hit((20, 6, 6)).remaining_hp, 0)
        self.assertEqual(self.hit((10, 6, 6), critical_on_hit=True).remaining_hp, 0)
        radiant = replace(self.attack, damage_type="radiant")
        result = resolve_attack_sequence(
            radiant, 8, 1, undead_fortitude=True, rng=Rolls(10, 6)
        )
        self.assertEqual(result.remaining_hp, 0)

    def test_defenses_apply_before_save_dc(self):
        result = self.hit((10, 6, 5), damage_resistances=("slashing",))
        self.assertEqual((result.damage, result.remaining_hp), (3, 1))
        result = self.hit((10, 6, 13), damage_vulnerabilities=("slashing",))
        self.assertEqual((result.damage, result.remaining_hp), (12, 0))

    def test_no_save_for_miss_immunity_nonlethal_damage_or_dead_target(self):
        self.assertEqual(self.hit((1,)).remaining_hp, 1)
        self.assertEqual(
            self.hit((10, 6), damage_immunities=("slashing",)).remaining_hp, 1
        )
        for hp, expected in ((10, 4), (0, 0)):
            result = resolve_attack_sequence(
                self.attack, 8, hp, undead_fortitude=True, rng=Rolls(10, 6)
            )
            self.assertEqual(result.remaining_hp, expected)

    def test_saving_throws_do_not_have_automatic_success_or_failure(self):
        for bonus, roll, expected in ((-10, 20, 0), (20, 1, 1)):
            result = resolve_attack_sequence(
                self.attack, 8, 1, undead_fortitude=True,
                constitution_save_bonus=bonus, rng=Rolls(10, 6, roll),
            )
            self.assertEqual(result.remaining_hp, expected)

    def test_save_spell_applies_half_damage_before_fortitude(self):
        effect = SavingThrowDamageProfile(
            "Fire", 10, (DamageDice(1, 6),),
            damage_on_success=SaveSuccessDamage.HALF_DAMAGE, damage_type="fire",
        )
        result = resolve_saving_throw_damage(
            effect, 0, 1, undead_fortitude=True, constitution_save_bonus=3,
            rng=Rolls(10, 6, 5),
        )
        self.assertEqual((result.applied_damage, result.remaining_hp), (3, 1))
        radiant = replace(effect, damage_type="radiant")
        result = resolve_saving_throw_damage(
            radiant, 0, 1, undead_fortitude=True, rng=Rolls(10, 6)
        )
        self.assertEqual(result.remaining_hp, 0)
        harmless = replace(effect, damage_on_success=SaveSuccessDamage.NO_DAMAGE)
        result = resolve_saving_throw_damage(
            harmless, 0, 1, undead_fortitude=True, rng=Rolls(10)
        )
        self.assertEqual(result.remaining_hp, 1)

    def test_turns_and_save_simulations_preserve_trait(self):
        plan = TurnPlan("Two swings", (AttackScenario("Sword", self.attack),) * 2)
        result = simulate_turns_to_zero(
            1, plan, self.target, rng=Rolls(10, 6, 8, 10, 6, 7)
        )
        self.assertEqual((result.total_turns, result.total_attacks), (1, 2))
        effect = SavingThrowDamageProfile("Fire", 10, (DamageDice(1, 6),))
        scenario = SavingThrowScenario("Fire", effect, 0)
        result = simulate_saving_throw_uses_to_zero(
            1, scenario, self.target, rng=Rolls(1, 6, 8, 1, 6, 7)
        )
        self.assertEqual((result.total_uses, result.total_hp_removed), (2, 1))

    def test_duel_survivor_gets_to_retaliate(self):
        hero = DuelCombatant("Hero", 8, 1, 0, self.attack)
        zombie = DuelCombatant(
            "Zombie", 8, 1, 0, self.attack,
            saving_throw_bonuses={"con": 3}, undead_fortitude=True,
        )
        result = simulate_duel(
            1, DuelMatchup(hero, zombie), rng=Rolls(20, 1, 10, 6, 8, 10, 6)
        )
        self.assertEqual(result.monster_wins, 1)

    def test_application_ac_sweep_and_workers_preserve_trait(self):
        scenarios = (
            AttackScenario("Sword", self.attack),
            AttackScenario("Another sword", self.attack),
        )
        expected = simulate_attacks_to_zero(50, self.attack, self.target, seed=42)
        for workers in (1, 2):
            result = evaluate_attacks(
                scenarios, self.target, SimulationSettings(trials=50, workers=workers)
            ).sweep.scenario_comparisons[0].results[0]
            self.assertEqual(result, expected)

    def test_profile_round_trip_and_duel_factory_preserve_trait(self):
        zombie = load_monster_profile(Path(__file__).parents[1] / "monsters/zombie.json")
        self.assertTrue(zombie.undead_fortitude)
        with TemporaryDirectory() as directory:
            filename = Path(directory) / "zombie.json"
            save_monster_profile(zombie, filename)
            self.assertEqual(load_monster_profile(filename), zombie)
        matchups = build_duel_policy_matchups(CharacterBuild("Hero", self.attack), zombie)
        self.assertTrue(matchups[0].monster.undead_fortitude)
        self.assertEqual(matchups[0].monster.get_saving_throw_bonus("con"), 3)

    def test_profile_validation_rejects_non_boolean_and_defaults_off(self):
        data = {"name": "Target", "armor_class": 8, "max_hp": 1}
        validate_profile(data, "monster")
        self.assertFalse(TargetProfile(**data).undead_fortitude)
        for value in (1, "true", None):
            with self.assertRaisesRegex(TypeError, "undead_fortitude"):
                TargetProfile(**data, undead_fortitude=value)
            with self.assertRaises(ProfileValidationError):
                validate_profile(dict(data, undead_fortitude=value), "monster")


if __name__ == "__main__":
    unittest.main()
