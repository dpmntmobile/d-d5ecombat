import importlib.util
import unittest

PYSIDE_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 is not installed")
class SaveActionEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_save_action_and_slots_survive_monster_editor(self):
        from PySide6.QtWidgets import QTableWidgetItem
        from dnd5ecombat.models import TargetProfile, SavingThrowDamageProfile, DamageDice
        from dnd5ecombat.monster_editor import MonsterEditorDialog
        effect = SavingThrowDamageProfile("Fire", 15, (DamageDice(2, 6),),
            save_ability="dex", spell_slot_level=1, range_feet=30,
            unmodeled_effects=("Area of effect",))
        monster = TargetProfile("Caster", 10, 20, saving_throw_profiles=(effect,), spell_slots={1: 2})
        dialog = MonsterEditorDialog(monster)
        self.assertEqual(dialog.monster().saving_throw_profiles, monster.saving_throw_profiles)
        self.assertEqual(dialog.monster().spell_slots, monster.spell_slots)
        editor = dialog.save_action_editor
        editor.slot_spins[1].setValue(1)
        editor.table.setItem(0, 10, QTableWidgetItem("0"))
        self.assertEqual(dialog.monster().spell_slots, ((1, 1),))
        self.assertEqual(dialog.monster().saving_throw_profiles[0].spell_slot_level, 0)
        editor.add_action()
        self.assertEqual(editor.table.rowCount(), 2)
        editor.table.selectRow(1)
        editor.remove_selected()
        self.assertEqual(editor.table.rowCount(), 1)
        dialog.close()

    def test_attack_spell_level_survives_editor_and_can_be_cleared(self):
        from PySide6.QtWidgets import QTableWidgetItem
        from dnd5ecombat.models import TargetProfile, AttackProfile, DamageDice
        from dnd5ecombat.monster_editor import MonsterEditorDialog
        attack = AttackProfile("Ray", 5, (DamageDice(1, 6),), spell_slot_level=1)
        monster = TargetProfile("Caster", 10, 20, attack_profiles=(attack,), spell_slots={1: 2})
        dialog = MonsterEditorDialog(monster)
        self.assertEqual(dialog.monster().attack_profiles, monster.attack_profiles)
        self.assertEqual(dialog.monster().spell_slots, monster.spell_slots)
        dialog.attacks.setItem(0, 18, QTableWidgetItem("0"))
        self.assertEqual(dialog.monster().attack_profiles[0].spell_slot_level, 0)
        dialog.attacks.setItem(0, 18, QTableWidgetItem(""))
        self.assertIsNone(dialog.monster().attack_profiles[0].spell_slot_level)
        dialog.close()

    def test_tactical_plan_casting_pools_and_capacities_survive_editor(self):
        from dnd5ecombat.models import (
            AttackProfile, AttackScenario, DamageDice, FirstHitBonusDamage,
            SavingThrowDamageProfile, TargetProfile, TurnPlan,
        )
        from dnd5ecombat.monster_editor import MonsterEditorDialog
        weapon = AttackProfile("Sword", 5, (DamageDice(1, 6),))
        bonus = AttackProfile("Ray", 5, (DamageDice(1, 8),), action_type="bonus_action",
            spell_slot_level=1, spell_slot_pool="any", allow_upcast=True,
            upcast_damage_dice=(DamageDice(1, 8),))
        save = SavingThrowDamageProfile("Flame", 12, (DamageDice(1, 6),), save_ability="dex",
            spell_slot_level=1, action_type="bonus_action", spell_slot_pool="pact",
            allow_upcast=True, upcast_damage_dice=(DamageDice(1, 6),))
        plan = TurnPlan("Sword and ray", (AttackScenario("Sword", weapon, advantage=True),
            AttackScenario("Ray", bonus)), FirstHitBonusDamage("Sneak", (DamageDice(1, 6),), (0,), True, True))
        monster = TargetProfile("Tactician", 12, 30, attack_profiles=(weapon, bonus),
            saving_throw_bonuses={ability: 0 for ability in ("str", "dex", "con", "int", "wis", "cha")},
            saving_throw_profiles=(save,), turn_plans=(plan,), pack_tactics=True,
            aggressive=True, nimble_escape=True, stealth_bonus=6, passive_perception=14,
            spell_slots={1: 1}, spell_slot_capacity={1: 3}, pact_slots={2: 0}, pact_slot_capacity={2: 2})
        dialog = MonsterEditorDialog(monster)
        self.assertEqual(dialog.monster(), monster)
        dialog.turn_plan_editor.table.selectRow(0)
        dialog.turn_plan_editor.remove_selected()
        self.assertEqual(dialog.monster().turn_plans, ())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
