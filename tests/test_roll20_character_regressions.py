import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dnd5ecombat.character_persistence import load_custom_build, save_custom_build
from dnd5ecombat.gui_service import SimulationSettings, run_simulations
from dnd5ecombat.profile_catalog import load_character_build
from dnd5ecombat.roll20_import import import_from_roll20
from dnd5ecombat.monster_profiles import load_monster_profile


PROJECT_DIR = Path(__file__).resolve().parents[1]
CHARACTERS_DIR = PROJECT_DIR / "characters"
MONSTERS_DIR = PROJECT_DIR / "monsters"


class FelicityRoll20RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = CHARACTERS_DIR / "felicity.json"
        cls.imported = import_from_roll20(cls.path)
        cls.build = load_character_build(cls.path)

    def test_save_template_flags_create_save_profiles_instead_of_attack_rolls(self):
        self.assertEqual(
            {attack.name for attack in self.build.attack_profiles},
            {"Dagger", "Eldritch Blast", "Mace", "Light Crossbow"},
        )
        self.assertNotIn(
            12, {attack.attack_bonus for attack in self.build.attack_profiles}
        )
        self.assertEqual(
            {profile.name for profile in self.build.saving_throw_profiles},
            {
                "Dissonant Whispers",
                "Hellish Rebuke",
                "Vicious Mockery",
                "Mind Sliver",
            },
        )

    def test_save_details_and_action_type_are_preserved(self):
        profiles = {
            profile.name: profile for profile in self.build.saving_throw_profiles
        }

        self.assertEqual(
            (
                profiles["Dissonant Whispers"].save_ability,
                profiles["Dissonant Whispers"].difficulty_class,
                profiles["Dissonant Whispers"].damage_on_success.value,
            ),
            ("wis", 12, "half_damage"),
        )
        self.assertEqual(
            (
                profiles["Hellish Rebuke"].save_ability,
                profiles["Hellish Rebuke"].damage_on_success.value,
                profiles["Hellish Rebuke"].action_type,
            ),
            ("dex", "half_damage", "reaction"),
        )
        self.assertEqual(profiles["Vicious Mockery"].save_ability, "wis")
        self.assertEqual(profiles["Mind Sliver"].save_ability, "int")

    def test_primary_attack_and_racial_resistance_are_inferred(self):
        self.assertEqual(self.imported["primary_attack_name"], "Eldritch Blast")
        self.assertEqual(self.build.attack_profile.name, "Eldritch Blast")
        self.assertIn("fire", self.build.damage_resistances)


class BlackleafRoll20RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = CHARACTERS_DIR / "blackleaf.json"
        cls.imported = import_from_roll20(cls.path)
        cls.build = load_character_build(cls.path)

    def test_primary_and_off_hand_action_type_are_inferred(self):
        profiles = {profile.name: profile for profile in self.build.attack_profiles}

        self.assertEqual(self.imported["primary_attack_name"], "Shortsword")
        self.assertEqual(self.build.attack_profile.name, "Shortsword")
        self.assertEqual(profiles["Dagger Off Hand"].action_type, "bonus_action")
        self.assertEqual(profiles["Shortsword"].action_type, "action")

    def test_sneak_attack_and_two_weapon_turn_plans_are_created(self):
        plans = {plan.name: plan for plan in self.build.turn_plans}
        combined = plans[
            "Shortsword + Dagger Off Hand + Sneak Attack (when eligible)"
        ]

        self.assertEqual(
            tuple(scenario.attack.name for scenario in combined.attacks),
            ("Shortsword", "Dagger Off Hand"),
        )
        self.assertEqual(combined.first_hit_bonus_damage.name, "Sneak Attack")
        self.assertEqual(
            tuple(
                (dice.number, dice.sides)
                for dice in combined.first_hit_bonus_damage.damage_dice
            ),
            ((1, 6),),
        )
        self.assertEqual(
            combined.first_hit_bonus_damage.eligible_attack_indices, (0, 1)
        )

    def test_fey_ancestry_sleep_immunity_is_preserved(self):
        self.assertIn("magical sleep", self.build.condition_immunities)

    def test_turn_results_include_combined_plan_but_not_off_hand_alone(self):
        goblin = load_monster_profile(MONSTERS_DIR / "goblin.json")
        tables = run_simulations(
            self.build,
            goblin,
            SimulationSettings(trials=5, seed=7),
            sections=("turns",),
        )
        plan_names = {row[0] for row in tables.turns.rows}

        self.assertIn(
            "Shortsword + Dagger Off Hand + Sneak Attack (when eligible)",
            plan_names,
        )
        self.assertNotIn("Dagger Off Hand × 1", plan_names)

    def test_turn_plans_and_action_types_survive_native_round_trip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "blackleaf-native.json"
            save_custom_build(self.build, path)
            loaded = load_custom_build(path)

        profiles = {profile.name: profile for profile in loaded.attack_profiles}
        self.assertEqual(profiles["Dagger Off Hand"].action_type, "bonus_action")
        self.assertEqual(loaded.turn_plans, self.build.turn_plans)


if __name__ == "__main__":
    unittest.main()
