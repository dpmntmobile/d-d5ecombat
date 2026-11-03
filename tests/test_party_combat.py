import contextlib
import io
import json
import tempfile
import unittest
import importlib.util
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path

from dnd5ecombat.character_models import CharacterBuild
from dnd5ecombat.cli_workflows import main
from dnd5ecombat.models import AttackProfile, DamageDice, TargetProfile
from dnd5ecombat.party_combat import (
    MonsterGroup,
    PartyBattle,
    load_battle,
    save_battle,
    simulate_party_battle,
)
from dnd5ecombat.duel_simulation import simulate_duel
from dnd5ecombat.scenario_factory import build_duel_policy_matchups
from dnd5ecombat.simulation_core import SimulationCancelledError


ROOT = Path(__file__).resolve().parents[1]


class PartyCombatTests(unittest.TestCase):
    def setUp(self):
        self.attack = AttackProfile("Sword", 100, (DamageDice(1, 2),), 10)
        self.harmless = AttackProfile("Harmless", 0, (DamageDice(1, 2),), -100)
        self.hero = CharacterBuild(
            "Hero", self.attack, max_hp=100, initiative_bonus=100
        )
        self.monster = TargetProfile("Monster", 10, 1, attack_profiles=(self.harmless,))

    def test_repeated_monsters_have_independent_hp_and_duplicate_names(self):
        battle = PartyBattle((self.hero,), (MonsterGroup(self.monster, 3),))
        result = simulate_party_battle(battle, trials=5, seed=3)
        self.assertEqual(result.party_wins, 5)
        self.assertEqual(result.encounter_survivors, 0)
        self.assertEqual(result.party_hp, 500)
        self.assertGreaterEqual(result.total_rounds, 15)
        self.assertEqual(result, simulate_party_battle(battle, trials=5, seed=3))

    def test_two_heroes_act_in_same_round_and_skip_killed_enemies(self):
        battle = PartyBattle((self.hero, self.hero), (MonsterGroup(self.monster, 2),))
        result = simulate_party_battle(battle, trials=1, seed=42)
        self.assertEqual(result.party_wins, 1)
        self.assertEqual(result.total_rounds, 1)
        self.assertEqual(result.party_survivors, 2)

    def test_extra_attacks_retarget_and_choose_damage_for_each_opponent(self):
        from dnd5ecombat.combat import resolve_attack_sequence

        fire = replace(self.attack, name="Fire", damage_type="fire")
        cold = replace(self.attack, name="Cold", damage_type="cold")
        hero = replace(self.hero, attack_profile=fire, attack_profiles=(fire, cold),
                       attacks_per_action=2)
        first = replace(self.monster, damage_immunities=("cold",))
        second = replace(self.monster, damage_immunities=("fire",))
        battle = PartyBattle((hero,), (MonsterGroup(first), MonsterGroup(second)))
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence",
                   wraps=resolve_attack_sequence) as resolve:
            result = simulate_party_battle(battle, 1, seed=42)
        self.assertEqual(result.total_rounds, 1)
        self.assertEqual(result.party_wins, 1)
        self.assertEqual([call.args[0].name for call in resolve.call_args_list],
                         ["Fire", "Cold"])

    def test_monster_selects_attack_against_current_character(self):
        fire = replace(self.attack, name="Fire", damage_type="fire")
        cold = replace(self.attack, name="Cold", damage_type="cold")
        hero = replace(self.hero, max_hp=1, initiative_bonus=-100,
                       damage_immunities=("fire",), attack_profile=self.harmless,
                       attack_profiles=(self.harmless,))
        monster = replace(self.monster, initiative_bonus=100,
                          attack_profiles=(fire, cold))
        result = simulate_party_battle(PartyBattle((hero,), (MonsterGroup(monster),)),
                                      1, max_rounds_per_trial=1)
        self.assertEqual(result.encounter_wins, 1)

    def test_explicit_multiattack_retargets_without_changing_named_attacks(self):
        from dnd5ecombat.combat import resolve_attack_sequence

        bite = replace(self.attack, name="Bite")
        claw = replace(self.attack, name="Claw", damage_modifier=20)
        monster = replace(self.monster, max_hp=100, initiative_bonus=100,
                          attack_profiles=(bite, claw), multiattack=("Bite", "Claw"))
        hero = replace(self.hero, max_hp=1, initiative_bonus=-100)
        battle = PartyBattle((hero, hero), (MonsterGroup(monster),))
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence",
                   wraps=resolve_attack_sequence) as resolve:
            result = simulate_party_battle(battle, 1, seed=42)
        self.assertEqual(result.encounter_wins, 1)
        self.assertEqual(result.total_rounds, 1)
        self.assertEqual([call.args[0].name for call in resolve.call_args_list],
                         ["Bite", "Claw"])

    def test_retargeting_does_not_refresh_limited_attack_uses(self):
        limited = replace(self.attack, name="Limited", limited_uses=1)
        hero = replace(self.hero, attack_profile=limited, attack_profiles=(limited,),
                       attacks_per_action=2)
        battle = PartyBattle((hero,), (MonsterGroup(self.monster, 2),))
        result = simulate_party_battle(battle, 3, max_rounds_per_trial=1)
        self.assertEqual(result.draws, 3)
        self.assertEqual(result.encounter_survivors, 3)

    def test_spell_cast_does_not_gain_extra_attacks_after_kill(self):
        spell = replace(self.attack, name="Spell", spell_slot_level=1)
        hero = replace(self.hero, attack_profile=spell, attack_profiles=(spell,),
                       attacks_per_action=2, spell_slots={1: 3})
        battle = PartyBattle((hero,), (MonsterGroup(self.monster, 2),))
        result = simulate_party_battle(battle, 1, max_rounds_per_trial=1)
        self.assertEqual(result.draws, 1)
        self.assertEqual(result.encounter_survivors, 1)

    def test_first_hit_bonus_is_not_refreshed_when_plan_retargets(self):
        from dnd5ecombat.combat import resolve_attack_sequence
        from dnd5ecombat.models import AttackScenario, FirstHitBonusDamage, TurnPlan

        off = replace(self.attack, name="Off hand", action_type="bonus_action")
        rider = FirstHitBonusDamage("Once", (DamageDice(1, 6),), (0, 1))
        plan = TurnPlan("Two weapons", (AttackScenario("Main", self.attack),
                                       AttackScenario("Off", off)), rider)
        hero = replace(self.hero, turn_plans=(plan,))
        battle = PartyBattle((hero,), (MonsterGroup(self.monster, 2),))
        with patch("dnd5ecombat.duel_simulation.resolve_attack_sequence",
                   wraps=resolve_attack_sequence) as resolve:
            result = simulate_party_battle(battle, 1, seed=42)
        self.assertEqual(result.party_wins, 1)
        self.assertEqual(result.total_rounds, 1)
        self.assertEqual([call.args[0].name for call in resolve.call_args_list],
                         ["Sword", "Off hand"])
        self.assertEqual([bool(call.kwargs["bonus_damage_dice"])
                          for call in resolve.call_args_list], [True, False])

    def test_reaction_kill_stops_remaining_attacks_before_retargeting(self):
        from dnd5ecombat.models import SavingThrowDamageProfile

        rebuke = SavingThrowDamageProfile(
            "Rebuke", 100, (DamageDice(1, 2),), damage_modifier=100,
            save_ability="dex", damage_type="fire", action_type="reaction",
            spell_slot_level=1, range_feet=60,
            reaction_trigger="damaged_by_visible_creature",
        )
        hero = replace(self.hero, max_hp=10, attacks_per_action=3)
        monster = replace(self.monster, max_hp=100, spell_slots={1: 1},
                          saving_throw_profiles=(rebuke,))
        battle = PartyBattle((hero,), (MonsterGroup(monster, 2),))
        result = simulate_party_battle(battle, 1, seed=42)
        self.assertEqual(result.encounter_wins, 1)
        self.assertEqual(result.total_rounds, 1)
        self.assertEqual(result.encounter_survivors, 2)

    def test_mixed_encounter_remains_seeded_and_repeatable(self):
        hero = replace(self.hero, attacks_per_action=2)
        battle = PartyBattle((hero, hero), (
            MonsterGroup(self.monster, 2),
            MonsterGroup(replace(self.monster, armor_class=18, max_hp=25), 2),
        ))
        self.assertEqual(simulate_party_battle(battle, 20, seed=123),
                         simulate_party_battle(battle, 20, seed=123))

    def test_party_wipe_and_draws(self):
        hero = replace(
            self.hero,
            attack_profile=self.harmless,
            attack_profiles=(self.harmless,),
            max_hp=1,
            initiative_bonus=-100,
        )
        monster = replace(self.monster, attack_profiles=(self.attack,))
        result = simulate_party_battle(
            PartyBattle((hero, hero), (MonsterGroup(monster),)), 3
        )
        self.assertEqual(result.encounter_wins, 3)
        self.assertEqual(result.party_survivors, 0)
        result = simulate_party_battle(
            PartyBattle((hero,), (MonsterGroup(self.monster),)),
            2,
            max_rounds_per_trial=3,
        )
        self.assertEqual(result.draws, 2)
        self.assertEqual(result.total_rounds, 6)
        self.assertEqual(result.party_wins + result.encounter_wins + result.draws, 2)

    def test_one_on_one_matches_existing_duel(self):
        monster = replace(self.monster, max_hp=50, attack_profiles=(self.attack,))
        matchup = build_duel_policy_matchups(self.hero, monster)[0]
        duel = simulate_duel(20, matchup, seed=13)
        battle = simulate_party_battle(
            PartyBattle((self.hero,), (MonsterGroup(monster),)), 20, seed=13
        )
        self.assertEqual(duel.character_wins, battle.party_wins)
        self.assertEqual(duel.monster_wins, battle.encounter_wins)
        self.assertEqual(duel.total_rounds, battle.total_rounds)
        self.assertEqual(duel.total_character_remaining_hp, battle.party_hp)

    def test_validation_and_cancellation(self):
        for count in (0, -1, True, 1.5):
            with self.assertRaises((TypeError, ValueError)):
                MonsterGroup(self.monster, count)
        with self.assertRaises(ValueError):
            PartyBattle((), (MonsterGroup(self.monster),))
        battle = PartyBattle((self.hero,), (MonsterGroup(self.monster),))
        for trials in (0, True):
            with self.assertRaises((TypeError, ValueError)):
                simulate_party_battle(battle, trials)
        with self.assertRaises(SimulationCancelledError):
            simulate_party_battle(battle, cancellation_check=lambda: True)

    def test_action_uses_are_independent_and_reset_per_trial(self):
        from dnd5ecombat.combat import resolve_attack_sequence

        hero = replace(
            self.hero,
            attack_profile=self.harmless,
            attack_profiles=(self.harmless,),
            max_hp=10000,
        )
        limited = replace(self.attack, name="Limited", limited_uses=1)
        monster = replace(self.monster, attack_profiles=(limited,), max_hp=10000)
        battle = PartyBattle((hero,), (MonsterGroup(monster, 2),))
        with patch(
            "dnd5ecombat.duel_simulation.resolve_attack_sequence",
            wraps=resolve_attack_sequence,
        ) as resolve:
            result = simulate_party_battle(battle, 3, max_rounds_per_trial=4)
        uses = [
            call for call in resolve.call_args_list if call.args[0].name == "Limited"
        ]
        self.assertEqual(len(uses), 6)
        self.assertEqual(result.draws, 3)

    def test_round_trip_relative_paths_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "battle.json"
            save_battle(
                path,
                [ROOT / "characters/amara_summerfield.json"],
                [(ROOT / "monsters/goblin.json", 3)],
            )
            loaded = load_battle(path)
            self.assertEqual(len(loaded.party), 1)
            self.assertEqual(loaded.encounter[0].count, 3)
            self.assertEqual(len(loaded.combatants), 4)
            data = json.loads(path.read_text())
            data["encounter"][0]["count"] = True
            path.write_text(json.dumps(data))
            with self.assertRaises(TypeError):
                load_battle(path)

    def test_cli_battle_and_export(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            path = Path(directory) / "results.json"
            self.assertEqual(
                main(
                    [
                        "--party-battle",
                        str(ROOT / "scenarios/party-battle.json"),
                        "--trials",
                        "3",
                        "--export-results",
                        str(path),
                    ]
                ),
                0,
            )
            report = json.loads(path.read_text())
            self.assertEqual(report["trials"], 3)
            self.assertEqual(report["seed"], 42)
            self.assertEqual(report["max_rounds_per_trial"], 100)
            self.assertEqual(len(report["composition"]["party"]), 2)
            self.assertIn("application_version", report)
            self.assertAlmostEqual(
                report["party_win_rate"]
                + report["encounter_win_rate"]
                + report["draw_rate"],
                1,
            )


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 is not installed")
class PartyDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_catalog_selection_worker_and_save_load(self):
        from PySide6.QtCore import QEventLoop, QTimer
        from dnd5ecombat.party_dialog import PartyBattleDialog

        dialog = PartyBattleDialog()
        self.addCleanup(dialog.close)
        dialog.character_counts[0].setValue(2)
        dialog.monster_counts[0].setValue(3)
        chars, groups = dialog.selection()
        self.assertEqual(len(chars), 2)
        self.assertEqual(groups[0][1], 3)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "battle.json")
            with patch(
                "dnd5ecombat.party_dialog.QFileDialog.getSaveFileName",
                return_value=(path, ""),
            ):
                dialog.save()
            with patch(
                "dnd5ecombat.party_dialog.QFileDialog.getOpenFileName",
                return_value=(path, ""),
            ):
                dialog.load()
            self.assertEqual(len(dialog.loaded_battle.party), 2)
            dialog.trials.setValue(2)
            dialog.start_battle()
            loop = QEventLoop()
            dialog.worker.finished.connect(loop.quit)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            self.assertFalse(dialog.worker.isRunning())
            self.assertEqual(dialog.result_report["trials"], 2)
            self.assertIn("Party wins:", dialog.output.toPlainText())
            self.assertIn("%", dialog.output.toPlainText())
            self.assertTrue(dialog.export_button.isEnabled())
            captured = dialog.result_report.copy()
            dialog.monster_counts[0].setValue(4)
            self.assertIsNone(dialog.loaded_battle)
            self.assertIn("Catalog selection", dialog.composition.text())
            dialog.seed.setValue(99)
            export_path = str(Path(directory) / "results.json")
            with patch(
                "dnd5ecombat.party_dialog.QFileDialog.getSaveFileName",
                return_value=(export_path, ""),
            ):
                dialog.export_results()
            exported = json.loads(Path(export_path).read_text(encoding="utf-8"))
            self.assertEqual(exported["seed"], 42)
            self.assertEqual(exported["composition"], json.loads(json.dumps(
                captured["composition"], default=lambda value: value.value
            )))

    def test_cancel_and_close_wait_for_worker(self):
        from PySide6.QtCore import QEventLoop, QTimer
        from dnd5ecombat.party_dialog import PartyBattleDialog

        dialog = PartyBattleDialog()
        self.addCleanup(dialog.close)
        dialog.character_counts[0].setValue(1)
        dialog.monster_counts[0].setValue(1)
        dialog.trials.setValue(1000000)
        dialog.start_battle()
        self.assertFalse(dialog.seed.isEnabled())
        dialog.reject()
        self.assertTrue(dialog.worker.cancelled.is_set())
        loop = QEventLoop()
        dialog.worker.finished.connect(loop.quit)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        self.assertFalse(dialog.worker.isRunning())
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertIsNone(dialog.result_report)


if __name__ == "__main__":
    unittest.main()
