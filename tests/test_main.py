import io
import unittest
from contextlib import redirect_stdout

from dnd5ecombat import main


class MainCliTests(unittest.TestCase):
    def test_parse_args_reads_overrides(self):
        arguments = main.parse_args(
            [
                "--trials",
                "5000",
                "--seed",
                "7",
                "--target-hp",
                "30",
                "--armor-classes",
                "12",
                "14",
                "16",
                "--initiative-bonus",
                "4",
                "--enemy-initiative-bonus",
                "2",
                "--target-save-bonus",
                "3",
                "--workers",
                "3",
                "--include-advantage",
                "--include-disadvantage",
                "--monster-file",
                "monsters/ogre.json",
                "--duels",
            ]
        )

        self.assertEqual(arguments.trials, 5000)
        self.assertEqual(arguments.seed, 7)
        self.assertEqual(arguments.target_hp, 30)
        self.assertEqual(arguments.armor_classes, [12, 14, 16])
        self.assertEqual(arguments.initiative_bonus, 4)
        self.assertEqual(arguments.enemy_initiative_bonus, 2)
        self.assertEqual(arguments.target_save_bonus, 3)
        self.assertEqual(arguments.workers, 3)
        self.assertTrue(arguments.include_advantage)
        self.assertTrue(arguments.include_disadvantage)
        self.assertEqual(arguments.target_file, "monsters/ogre.json")
        self.assertTrue(arguments.duels)

    def test_parse_args_uses_sensible_defaults(self):
        arguments = main.parse_args([])

        self.assertEqual(arguments.trials, 10_000)
        self.assertEqual(arguments.seed, 42)
        self.assertEqual(arguments.target_hp, 20)
        self.assertEqual(arguments.armor_classes, [12, 14, 16, 18, 20])
        self.assertEqual(arguments.workers, 1)
        self.assertFalse(arguments.include_advantage)
        self.assertFalse(arguments.include_disadvantage)

    def test_parse_args_supports_interactive_mode(self):
        arguments = main.parse_args(["--interactive"])

        self.assertTrue(arguments.interactive)

    def test_parse_args_supports_gui_mode(self):
        arguments = main.parse_args(["--gui"])

        self.assertTrue(arguments.gui)

    def test_run_interactive_menu_uses_user_choice(self):
        responses = iter(["", "0", "2", "30", "12 14 16", "5", "42"])
        settings = main.run_interactive_menu(
            input_func=lambda prompt: next(responses),
            output_func=lambda *args, **kwargs: None,
        )

        self.assertEqual(settings["mode"], "attacks")
        self.assertEqual(settings["target_hp"], 30)
        self.assertEqual(settings["armor_classes"], [12, 14, 16])
        self.assertEqual(settings["trials"], 5)
        self.assertEqual(settings["seed"], 42)

    def test_character_builds_include_tobias(self):
        builds = main.build_character_presets()
        choices = {build.name: build for build in builds}

        self.assertIn("Tobias", choices)
        self.assertEqual(choices["Tobias"].attack_profile.attack_bonus, 5)
        self.assertEqual(choices["Tobias"].attack_profile.damage_modifier, 3)
        self.assertIn("Rapier", choices["Tobias"].equipment)

    def test_run_interactive_menu_supports_single_combat(self):
        responses = iter(["", "0", "6", "15", "12", "100", "7"])
        settings = main.run_interactive_menu(
            input_func=lambda prompt: next(responses),
            output_func=lambda *args, **kwargs: None,
        )

        self.assertEqual(settings["mode"], "single")
        self.assertEqual(settings["target_hp"], 15)
        self.assertEqual(settings["enemy_armor_class"], 12)
        self.assertEqual(settings["trials"], 100)
        self.assertEqual(settings["seed"], 7)

    def test_interactive_menu_selects_a_monster_file(self):
        responses = iter(["", "goblin.json", "2", "5", "42"])

        settings = main.run_interactive_menu(
            input_func=lambda prompt: next(responses),
            output_func=lambda *args, **kwargs: None,
        )

        self.assertEqual(settings["mode"], "attacks")
        self.assertEqual(settings["target_profile"].name, "Goblin")
        self.assertEqual(settings["target_profile"].armor_class, 15)
        self.assertEqual(settings["target_profile"].max_hp, 7)

    def test_interactive_menu_supports_duels(self):
        responses = iter(["", "goblin.json", "7", "5", "42"])

        settings = main.run_interactive_menu(
            input_func=lambda prompt: next(responses),
            output_func=lambda *args, **kwargs: None,
        )

        self.assertEqual(settings["mode"], "duels")
        self.assertEqual(settings["target_profile"].name, "Goblin")

    def test_prompt_custom_build_creates_personalized_profile(self):
        responses = iter([
            "Tobias v2",
            "6",
            "1d10",
            "4",
            "18",
            "24",
            "3",
            "Rapier, shield, leather",
        ])
        build = main.prompt_custom_build(input_func=lambda prompt: next(responses))

        self.assertEqual(build.name, "Tobias v2")
        self.assertEqual(build.attack_profile.attack_bonus, 6)
        self.assertEqual(build.attack_profile.damage_dice[0].number, 1)
        self.assertEqual(build.attack_profile.damage_dice[0].sides, 10)
        self.assertEqual(build.attack_profile.damage_modifier, 4)
        self.assertEqual(build.armor_class, 18)
        self.assertEqual(build.max_hp, 24)
        self.assertEqual(build.save_bonus, 3)
        self.assertEqual(build.equipment, ("Rapier", "shield", "leather"))

    def test_save_and_load_custom_build(self):
        import tempfile
        import os as os_module

        # Create a custom build
        original = main.CharacterBuild(
            name="Test Fighter",
            attack_profile=main.AttackProfile(
                name="Test attack",
                attack_bonus=7,
                damage_dice=(main.DamageDice(1, 12),),
                damage_modifier=2,
            ),
            armor_class=17,
            max_hp=30,
            save_bonus=1,
            equipment=("Longsword", "Heavy armor"),
        )

        # Save to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file = os_module.path.join(tmpdir, "test_build.json")
            main.save_custom_build(original, filename=temp_file)

            # Load it back
            loaded = main.load_custom_build(temp_file)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.name, "Test Fighter")
            self.assertEqual(loaded.attack_profile.attack_bonus, 7)
            self.assertEqual(loaded.armor_class, 17)
            self.assertEqual(loaded.max_hp, 30)
            self.assertEqual(loaded.equipment, ("Longsword", "Heavy armor"))

    def test_save_and_load_preserves_all_attack_profiles_and_primary(self):
        import tempfile
        import os as os_module

        first = main.AttackProfile("First", 5, (main.DamageDice(1, 8),), 3)
        second = main.AttackProfile(
            "Second",
            6,
            (main.DamageDice(2, 6),),
            2,
            damage_type="slashing",
            attack_mode="melee",
            reach_feet=5,
        )
        save_spell = main.SavingThrowDamageProfile(
            "Save spell",
            14,
            (main.DamageDice(3, 6),),
            damage_on_success=main.SaveSuccessDamage.HALF_DAMAGE,
            save_ability="dex",
        )
        original = main.CharacterBuild(
            name="Multiple attacks",
            attack_profile=second,
            attack_profiles=(first, second),
            attacks_per_action=2,
            saving_throw_profiles=(save_spell,),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            filename = os_module.path.join(tmpdir, "multiple.json")
            main.save_custom_build(original, filename)
            loaded = main.load_custom_build(filename)

        self.assertEqual(loaded.attack_profiles, (first, second))
        self.assertEqual(loaded.attack_profile, second)
        self.assertEqual(loaded.attacks_per_action, 2)
        self.assertEqual(loaded.saving_throw_profiles, (save_spell,))

    def test_import_from_roll20_json(self):
        roll20_data = main.import_from_roll20("tests/fixtures/test_roll20.json")

        self.assertIsNotNone(roll20_data)
        self.assertEqual(roll20_data["name"], "Ovehaw Ugijo")
        self.assertEqual(roll20_data["class"], "Fighter")
        self.assertEqual(roll20_data["armor_class"], 16)
        self.assertEqual(roll20_data["max_hp"], 11)
        self.assertEqual(roll20_data["level"], 1)
        self.assertEqual(roll20_data["strength_mod"], 3)

        # Check that attacks were parsed
        attacks = roll20_data.get("attacks", [])
        self.assertGreater(len(attacks), 0)

        # Verify specific attacks are present
        attack_names = {attack["name"] for attack in attacks}
        self.assertIn("Greatsword", attack_names)
        self.assertIn("Warhammer (One-Handed)", attack_names)
        self.assertIn("Warhammer (Two-Handed)", attack_names)
        self.assertIn("Light Crossbow", attack_names)
        self.assertEqual(roll20_data["attacks_per_action"], 1)
        self.assertEqual(roll20_data["saving_throw_attacks"], [])
        self.assertEqual(
            roll20_data["saving_throw_bonuses"],
            {"str": 5, "dex": 1, "con": 3, "int": 0, "wis": 1, "cha": 0},
        )
        self.assertEqual(roll20_data["creature_tags"], ("human", "humanoid"))

    def test_roll20_import_uses_explicit_attack_count_and_save_spells_only(self):
        import json
        import os as os_module
        import tempfile

        data = {
            "name": "Save caster",
            "attacks_per_action": 2,
            "stats": {
                "intelligence_mod": {"current": 3},
                "wisdom_mod": {"current": 0},
            },
            "hp_and_level": {
                "class": {"current": "Wizard"},
                "race": {"current": "Human"},
                "level": {"current": 5},
                "hp": {"max": 30},
                "ac": {"current": 14},
                "pb": {"current": "3"},
                "initiative_bonus": {"current": 2},
            },
            "other_attributes": {
                "spell_save_dc": {"current": 14},
            },
            "traits_and_features": {
                "repeating_traits_celestial_name": {
                    "current": "Celestial Resistance"
                },
                "repeating_traits_celestial_description": {
                    "current": "You have resistance to necrotic and radiant damage."
                },
                "repeating_traits_gwf_name": {
                    "current": "Fighting Style: Great Weapon Fighting"
                },
                "repeating_traits_gwf_description": {
                    "current": "Reroll a 1 or 2 on two-handed weapon damage dice."
                },
            },
            "inventory": {
                "repeating_inventory_dagger_itemproperties": {
                    "current": "Finesse, Light, Thrown (Range 20/60)"
                },
                "repeating_inventory_greatsword_itemproperties": {
                    "current": "Heavy, Two-Handed"
                },
            },
            "attacks_and_spellcasting": {
                "repeating_attack_spell_atkname": {"current": "Burning Hands"},
                "repeating_attack_spell_dmgbase": {"current": "3d6"},
                "repeating_attack_spell_dmgattr": {"current": "0"},
                "repeating_attack_spell_dmgtype": {"current": "Fire"},
                "repeating_attack_spell_spelllevel": {"current": "1"},
                "repeating_attack_spell_saveflag": {"current": "1"},
                "repeating_attack_spell_savedc": {
                    "current": "(@{intelligence_mod}+8+@{pb})"
                },
                "repeating_attack_spell_saveattr": {"current": "dex"},
                "repeating_attack_spell_saveeffect": {"current": "Half"},
                "repeating_attack_trap_atkname": {"current": "Not a spell"},
                "repeating_attack_trap_dmgbase": {"current": "2d6"},
                "repeating_attack_trap_dmgtype": {"current": "Fire"},
                "repeating_attack_trap_saveflag": {"current": "1"},
                "repeating_attack_dagger_atkname": {"current": "Dagger"},
                "repeating_attack_dagger_atkbonus": {"current": "+5"},
                "repeating_attack_dagger_dmgbase": {"current": "1d4"},
                "repeating_attack_dagger_dmgtype": {"current": "Piercing"},
                "repeating_attack_dagger_dmgattr": {"current": "0"},
                "repeating_attack_dagger_atkrange": {"current": "20/60"},
                "repeating_attack_dagger_itemid": {"current": "dagger"},
                "repeating_attack_greatsword_atkname": {"current": "Greatsword"},
                "repeating_attack_greatsword_atkbonus": {"current": "+5"},
                "repeating_attack_greatsword_dmgbase": {"current": "2d6"},
                "repeating_attack_greatsword_dmgtype": {"current": "Slashing"},
                "repeating_attack_greatsword_dmgattr": {"current": "0"},
                "repeating_attack_greatsword_itemid": {"current": "greatsword"},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            filename = os_module.path.join(tmpdir, "save-caster.json")
            with open(filename, "w", encoding="utf-8") as output_file:
                json.dump(data, output_file)
            imported = main.import_from_roll20(filename)

        self.assertEqual(imported["attacks_per_action"], 2)
        self.assertEqual(imported["damage_resistances"], ("necrotic", "radiant"))
        self.assertEqual(imported["attacks"][0]["attack_mode"], "melee_or_ranged")
        self.assertEqual(imported["attacks"][0]["normal_range_feet"], 20)
        self.assertEqual(imported["attacks"][0]["long_range_feet"], 60)
        self.assertEqual(len(imported["saving_throw_attacks"]), 1)
        save_spell = imported["saving_throw_attacks"][0]
        self.assertEqual(save_spell["name"], "Burning Hands")
        self.assertEqual(save_spell["save_dc"], 14)
        self.assertEqual(save_spell["save_ability"], "dex")
        self.assertEqual(save_spell["damage_on_success"], "half_damage")
        build = main.build_from_roll20_with_attack(
            imported,
            attack_bonus=5,
            damage_dice_text="1d8",
            damage_modifier=3,
        )
        scenarios = main.build_save_scenarios(build, target_save_bonus=4)
        self.assertEqual(build.attacks_per_action, 2)
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0].target_save_bonus, 4)
        self.assertEqual(scenarios[0].effect.save_ability, "dex")
        self.assertEqual(scenarios[0].effect.damage_type, "Fire")
        dagger = next(profile for profile in build.attack_profiles if profile.name == "Dagger")
        self.assertEqual(dagger.attack_mode, "melee_or_ranged")
        self.assertEqual(dagger.normal_range_feet, 20)
        greatsword = next(
            profile for profile in build.attack_profiles if profile.name == "Greatsword"
        )
        self.assertEqual(greatsword.reroll_damage_at_or_below, 2)


    def test_build_from_roll20_with_attack(self):
        roll20_data = main.import_from_roll20("tests/fixtures/test_roll20.json")
        build = main.build_from_roll20_with_attack(
            roll20_data,
            attack_bonus=6,
            damage_dice_text="1d8",
            damage_modifier=3,
            equipment_text="Longsword, Shield"
        )

        self.assertEqual(build.name, "Ovehaw Ugijo")
        self.assertEqual(build.attack_profile.attack_bonus, 6)
        self.assertEqual(build.armor_class, 16)
        self.assertEqual(build.max_hp, 11)
        self.assertIn("Longsword", build.equipment)
        self.assertIn("Shield", build.equipment)
        self.assertIn(build.attack_profile, build.attack_profiles)

    def test_parse_args_character_file(self):
        args = main.parse_args(["--character-file", "tests/fixtures/test_roll20.json"])
        self.assertEqual(args.character_file, "tests/fixtures/test_roll20.json")

    def test_target_file_remains_a_monster_file_alias(self):
        args = main.parse_args(["--target-file", "legacy-target.json"])

        self.assertEqual(args.target_file, "legacy-target.json")

    def test_load_target_profile_reads_combat_values(self):
        import json
        import os as os_module
        import tempfile

        target_data = {
            "name": "Training target",
            "armor_class": 17,
            "max_hp": 45,
            "initiative_bonus": 3,
            "saving_throw_bonuses": {"dex": 1, "wis": 4},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = os_module.path.join(tmpdir, "target.json")
            with open(filename, "w", encoding="utf-8") as output_file:
                json.dump(target_data, output_file)
            target = main.load_target_profile(filename)

        self.assertEqual(target.name, "Training target")
        self.assertEqual(target.armor_class, 17)
        self.assertEqual(target.max_hp, 45)
        self.assertEqual(target.initiative_bonus, 3)
        self.assertEqual(target.get_saving_throw_bonus("wis"), 4)

    def test_included_2014_monster_profiles_have_expected_core_stats(self):
        expected = {
            "orc.json": ("Orc", 13, 15, 1),
            "goblin.json": ("Goblin", 15, 7, 2),
            "skeleton.json": ("Skeleton", 13, 13, 2),
            "wolf.json": ("Wolf", 13, 11, 2),
            "zombie.json": ("Zombie", 8, 22, -2),
            "ghoul.json": ("Ghoul", 12, 22, 2),
        }

        for filename, core_stats in expected.items():
            with self.subTest(filename=filename):
                monster = main.load_monster_profile(
                    main.os.path.join(main.MONSTERS_DIR, filename)
                )
                self.assertEqual(
                    (
                        monster.name,
                        monster.armor_class,
                        monster.max_hp,
                        monster.initiative_bonus,
                    ),
                    core_stats,
                )
                self.assertEqual(
                    monster.ruleset, "D&D 5e Basic Rules (2014)"
                )
                self.assertTrue(monster.source_url.startswith("https://"))
                self.assertGreater(len(monster.attack_profiles), 0)

        zombie = main.load_monster_profile("monsters/zombie.json")
        self.assertEqual(zombie.get_saving_throw_bonus("wis"), 0)
        self.assertTrue(zombie.undead_fortitude)
        self.assertNotIn("Undead Fortitude", zombie.unmodeled_traits)
        self.assertEqual(zombie.attack_profiles[0].name, "Slam")
        self.assertEqual(zombie.attack_profiles[0].damage_type, "bludgeoning")

        orc = main.load_monster_profile("monsters/orc.json")
        javelin = next(
            attack for attack in orc.attack_profiles if attack.name == "Javelin"
        )
        self.assertEqual(javelin.attack_bonus, 5)
        self.assertEqual(javelin.normal_range_feet, 30)
        self.assertEqual(javelin.long_range_feet, 120)

        wolf = main.load_monster_profile("monsters/wolf.json")
        self.assertEqual(
            wolf.attack_profiles[0].condition_effect.condition.value, "prone"
        )

        ghoul = main.load_monster_profile("monsters/ghoul.json")
        claws = next(
            attack for attack in ghoul.attack_profiles if attack.name == "Claws"
        )
        self.assertEqual(claws.attack_bonus, 4)
        self.assertEqual(claws.condition_effect.condition.value, "paralyzed")
        self.assertTrue(claws.condition_effect.repeat_save_at_end_of_turn)

        skeleton = main.load_monster_profile("monsters/skeleton.json")
        self.assertEqual(skeleton.damage_vulnerabilities, ("bludgeoning",))
        self.assertEqual(skeleton.damage_immunities, ("poison",))

    def test_duel_roster_skips_profiles_without_attacks(self):
        monsters = main.load_duel_monsters()

        self.assertEqual(
            {monster.name for monster in monsters},
            {"Orc", "Goblin", "Skeleton", "Wolf", "Zombie", "Ghoul"},
        )

    def test_target_profile_supplies_the_spell_specific_save_bonus(self):
        effect = main.SavingThrowDamageProfile(
            "Test spell",
            14,
            (main.DamageDice(2, 6),),
            save_ability="dex",
        )
        build = main.CharacterBuild(
            "Caster",
            main.AttackProfile("Staff", 4, (main.DamageDice(1, 6),), 2),
            saving_throw_profiles=(effect,),
        )
        target = main.TargetProfile(
            "Target",
            15,
            20,
            saving_throw_bonuses={"dex": 5},
        )

        scenarios = main.build_save_scenarios(
            build, target_save_bonus=2, target_profile=target
        )

        self.assertEqual(scenarios[0].target_save_bonus, 5)

    def test_imported_roll20_build_keeps_all_attack_profiles(self):
        roll20_data = main.import_from_roll20("characters/tobias_wren.json")
        build = main.build_from_roll20_with_attack(
            roll20_data,
            attack_bonus=5,
            damage_dice_text="1d8",
            damage_modifier=3,
            equipment_text="",
        )

        self.assertGreater(len(build.attack_profiles), 1)
        self.assertIn("Fire Bolt", {profile.name for profile in build.attack_profiles})
        self.assertIn("Dagger", {profile.name for profile in build.attack_profiles})

    def test_imported_roll20_build_keeps_initiative_bonus(self):
        roll20_data = main.import_from_roll20("characters/tobias_wren.json")
        build = main.build_from_roll20_with_attack(
            roll20_data,
            attack_bonus=5,
            damage_dice_text="1d8",
            damage_modifier=3,
            equipment_text="",
        )

        self.assertEqual(build.initiative_bonus, 2)

    def test_imported_roll20_attack_data_keeps_per_attack_damage_modifiers(self):
        roll20_data = main.import_from_roll20("characters/tobias_wren.json")
        attack_by_name = {attack["name"]: attack for attack in roll20_data["attacks"]}

        self.assertEqual(attack_by_name["Dagger"]["damage_modifier"], 2)
        self.assertEqual(attack_by_name["Quarterstaff (One-Handed)"]["damage_modifier"], 0)
        self.assertGreater(attack_by_name["Dagger"]["bonus"], attack_by_name["Quarterstaff (One-Handed)"]["bonus"])

    def test_roll20_formula_uses_resolved_damage_dice(self):
        roll20_data = main.import_from_roll20("characters/tobias_wren.json")
        attack_by_name = {attack["name"]: attack for attack in roll20_data["attacks"]}

        self.assertEqual(attack_by_name["Fire Bolt"]["damage_dice"], "1d10")
        self.assertEqual(
            main.parse_damage_dice("[[round((@{level} + 1) / 6 + 0.5)]]d10"),
            (main.DamageDice(1, 10),),
        )

    def test_print_attack_summary_marks_best_scenario(self):
        selected = main.build_from_roll20_with_attack(
            main.import_from_roll20("characters/tobias_wren.json"),
            attack_bonus=5,
            damage_dice_text="1d10",
            damage_modifier=0,
            equipment_text="",
            selected_attack_name="Fire Bolt",
        )

        scenarios = main.build_custom_attack_scenarios(
            selected, include_advantage=True
        )
        sweep = main.compare_attack_scenarios_by_ac(
            scenarios=scenarios,
            armor_classes=(12, 14, 16),
            target_max_hp=20,
            trials=30,
            seed=7,
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main.print_attack_summary(sweep, 30, 7)

        output = buffer.getvalue()
        self.assertNotIn("Most effective overall:", output)
        self.assertNotIn("Recommended attack:", output)
        self.assertIn("* Best for that AC", output)
        self.assertIn("Damage", output)
        self.assertIn("1d8+2", output)
        self.assertIn("+4", output)
        self.assertIn("Fire Bolt", output)

        first_attack_line = next(
            line for line in output.splitlines() if "Fire Bolt" in line or "with advantage" in line
        )
        self.assertIn("Light Crossbow with advantage", first_attack_line)

    def test_custom_attack_scenarios_only_include_normal_attacks_by_default(self):
        selected = main.build_from_roll20_with_attack(
            main.import_from_roll20("characters/tobias_wren.json"),
            attack_bonus=5,
            damage_dice_text="1d10",
            damage_modifier=0,
            equipment_text="",
        )

        scenarios = main.build_custom_attack_scenarios(selected)

        self.assertEqual(len(scenarios), len(selected.attack_profiles))
        self.assertTrue(all(not scenario.advantage for scenario in scenarios))
        self.assertTrue(all(not scenario.disadvantage for scenario in scenarios))

    def test_tactical_flags_add_explicit_variants_for_each_attack(self):
        selected = main.build_character_presets()[0]

        scenarios = main.build_custom_attack_scenarios(
            selected,
            include_advantage=True,
            include_disadvantage=True,
        )

        self.assertEqual(len(scenarios), 3 * len(selected.attack_profiles))
        self.assertEqual(sum(scenario.advantage for scenario in scenarios), 1)
        self.assertEqual(sum(scenario.disadvantage for scenario in scenarios), 1)
        self.assertIn("with advantage", scenarios[1].name)
        self.assertIn("with disadvantage", scenarios[2].name)

    def test_attack_summary_marks_the_best_result_in_each_ac_column(self):
        from types import SimpleNamespace

        first_scenario = main.AttackScenario(
            "Low AC winner",
            main.AttackProfile("First", 5, (main.DamageDice(1, 8),), 3),
        )
        second_scenario = main.AttackScenario(
            "High AC winner",
            main.AttackProfile("Second", 7, (main.DamageDice(1, 6),), 2),
        )
        sweep = SimpleNamespace(
            target_name="Target",
            target_max_hp=20,
            armor_classes=(12, 20),
            scenario_comparisons=(
                SimpleNamespace(
                    scenario=first_scenario,
                    results=(
                        SimpleNamespace(
                            average_attacks_to_zero=2.0,
                            attacks_to_zero_95_margin=0.1,
                            average_rolled_damage_per_attack=5.0,
                        ),
                        SimpleNamespace(
                            average_attacks_to_zero=5.0,
                            attacks_to_zero_95_margin=0.2,
                            average_rolled_damage_per_attack=3.0,
                        ),
                    ),
                ),
                SimpleNamespace(
                    scenario=second_scenario,
                    results=(
                        SimpleNamespace(
                            average_attacks_to_zero=3.0,
                            attacks_to_zero_95_margin=0.1,
                            average_rolled_damage_per_attack=4.0,
                        ),
                        SimpleNamespace(
                            average_attacks_to_zero=4.0,
                            attacks_to_zero_95_margin=0.2,
                            average_rolled_damage_per_attack=3.5,
                        ),
                    ),
                ),
            ),
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            main.print_attack_summary(sweep, 10, 7)

        lines = buffer.getvalue().splitlines()
        low_ac_line = next(line for line in lines if line.startswith("Low AC winner"))
        high_ac_line = next(line for line in lines if line.startswith("High AC winner"))
        self.assertIn("2.000±0.100*", low_ac_line)
        self.assertNotIn("5.000±0.200*", low_ac_line)
        self.assertNotIn("3.000±0.100*", high_ac_line)
        self.assertIn("4.000±0.200*", high_ac_line)

    def test_menu_run_all_has_its_own_mode(self):
        responses = iter(["", "0", "5", "20", "", "5", "42"])
        settings = main.run_interactive_menu(
            input_func=lambda prompt: next(responses),
            output_func=lambda *args, **kwargs: None,
        )

        self.assertEqual(settings["mode"], "all")

    def test_damage_profile_formats_all_pools_and_signed_modifier(self):
        attack = main.AttackProfile(
            "Mixed damage",
            5,
            (main.DamageDice(1, 8), main.DamageDice(2, 6)),
            -2,
        )

        self.assertEqual(main.format_damage_profile(attack), "1d8+2d6-2")
        self.assertEqual(
            main.format_damage_profile(attack, (main.DamageDice(1, 4),)),
            "1d8+2d6+1d4-2",
        )

    def test_turn_plan_uses_only_explicit_attacks_per_action(self):
        scenarios = main.build_attack_scenarios()

        one_attack = main.build_turn_plans(scenarios, attacks_per_action=1)
        two_attacks = main.build_turn_plans(scenarios, attacks_per_action=2)

        self.assertEqual(len(one_attack), 1)
        self.assertEqual(len(one_attack[0].attacks), 1)
        self.assertEqual(len(two_attacks[0].attacks), 2)

    def test_save_scenarios_require_imported_save_profiles(self):
        build = main.build_character_presets()[0]

        self.assertEqual(main.build_save_scenarios(build, 3), ())


if __name__ == "__main__":
    unittest.main()
