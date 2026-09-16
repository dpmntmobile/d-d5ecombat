"""Independent rules and complete-import regressions for 2014 Roll20 features."""

from pathlib import Path
import unittest

from dnd5ecombat.profile_catalog import load_character_build
from dnd5ecombat.roll20_feature_rules import (
    map_traits,
    map_sneak_attack,
    map_turn_plans,
)
from dnd5ecombat.roll20_spell_resources import (
    casting_pools,
    casting_capacities,
    upcast_dice,
)


class FeatureMappingTests(unittest.TestCase):
    def test_exact_named_defenses_and_fighting_style_aliases(self):
        traits = tuple(
            dict(name=name)
            for name in (
                "Celestial Resistance",
                "Hellish Resistance",
                "Fey Ancestry",
                "Fighting Style: Great Weapon Fighting",
            )
        )
        self.assertEqual(
            map_traits(traits),
            (("necrotic", "radiant", "fire"), ("magical sleep",), True),
        )
        self.assertTrue(map_traits((dict(name="Great Weapon Fighting"),))[2])

    def test_descriptive_or_unknown_feature_names_do_not_grant_effects(self):
        self.assertEqual(
            map_traits(
                (
                    dict(name="Improved Celestial Resistance"),
                    dict(name="A trait", description="Great Weapon Fighting"),
                )
            ),
            ((), (), False),
        )

    def test_sneak_damage_row_takes_precedence_over_trait_description(self):
        traits = (
            dict(name="Sneak Attack", description="You deal an extra 1d6 damage."),
        )
        attrs = {
            "repeating_damagemod_row_global_damage_name": {"current": "Sneak Attack"},
            "repeating_damagemod_row_global_damage_damage": {"current": "3d6"},
        }
        self.assertEqual(map_sneak_attack(traits, attrs), "3d6")
        self.assertEqual(map_sneak_attack(traits, {}), "1d6")
        self.assertEqual(
            map_sneak_attack((dict(name="Other", description="extra 9d6 damage"),), {}),
            "",
        )

    def test_turn_mapping_requires_weapon_eligibility_and_spell_timing(self):
        weapon = dict(
            name="Sword",
            action_type="action",
            spell_slot_level=None,
            sneak_attack_eligible=True,
            two_weapon_eligible=True,
        )
        offhand = dict(weapon, name="Dagger", action_type="bonus_action")
        spell = dict(
            weapon,
            name="Ray",
            spell_slot_level=1,
            sneak_attack_eligible=False,
            two_weapon_eligible=False,
        )
        bonus = dict(spell, name="Bonus ray", action_type="bonus_action")
        plans = map_turn_plans((weapon, offhand, spell, bonus), "2d6")
        names = {tuple(p["attack_names"]) for p in plans}
        self.assertIn(("Sword", "Dagger"), names)
        self.assertIn(("Sword", "Bonus ray"), names)
        self.assertNotIn(("Ray", "Dagger"), names)
        self.assertNotIn(("Ray", "Bonus ray"), names)
        self.assertTrue(
            all(
                p["first_hit_allows_nearby_ally"]
                for p in plans
                if "first_hit_bonus_damage" in p
            )
        )

    def test_pure_warlock_uses_exported_pool_without_inventing_slots(self):
        data = dict(
            hp_and_level={"class": {"current": "Warlock"}},
            other_attributes={
                "lvl2_slots_total": {"current": 2},
                "lvl2_slots_expended": {"current": 0},
                "lvl1_slots_total": {"current": 0},
            },
        )
        self.assertEqual(casting_pools(data), ({}, {2: 0}))
        self.assertEqual(casting_capacities(data), ({}, {2: 2}))
        self.assertEqual(
            casting_pools(dict(hp_and_level=data["hp_and_level"])), ({}, {})
        )

    def test_multiclass_export_has_independent_current_and_full_pools(self):
        data = dict(
            hp_and_level={"class": {"current": "Warlock"}},
            other_attributes={
                "multiclass1_flag": {"current": 1},
                "lvl1_slots_total": {"current": 4},
                "lvl1_slots_expended": {"current": 1},
                "pact_slots_level": {"current": 3},
                "pact_slots_remaining": {"current": 0},
                "pact_slots_total": {"current": 2},
            },
        )
        self.assertEqual(casting_pools(data), ({1: 1}, {3: 0}))
        self.assertEqual(casting_capacities(data), ({1: 4}, {3: 2}))

    def test_invalid_or_ambiguous_pact_pools_are_rejected(self):
        for attrs in (
            {"pact_slots_level": {"current": 6}},
            {"pact_slots_level": {"current": 2}},
            {
                "pact_slots_level": {"current": 2},
                "pact_slots_remaining": {"current": -1},
            },
            {"lvl1_slots_total": {"current": 1}, "lvl2_slots_total": {"current": 1}},
        ):
            with self.subTest(attrs=attrs), self.assertRaises(ValueError):
                casting_pools(
                    dict(
                        hp_and_level={"class": {"current": "Warlock"}},
                        other_attributes=attrs,
                    )
                )

    def test_upcast_mapping_recognizes_linear_dice_without_macro_execution(self):
        macro = (
            "{{hldmg=[[(1*?{Cast at what level?|Level 1,0|Level 2,1|Level 3,2})d6]]}}"
        )
        self.assertEqual(upcast_dice({"hldmg": macro}, {}), "1d6")
        self.assertEqual(upcast_dice({}, {"spellhldmg": "2d8"}), "2d8")
        self.assertEqual(upcast_dice({"hldmg": "@{arbitrary_formula}"}, {}), "")

    def test_bundled_warlock_is_pact_caster_and_imports_upcast_dice(self):
        root = Path(__file__).resolve().parents[1]
        build = load_character_build(root / "characters" / "felicity.json")
        self.assertEqual(build.spell_slots, ())
        self.assertEqual(build.pact_slots, ((1, 1),))
        spell = next(
            s for s in build.saving_throw_profiles if s.name == "Dissonant Whispers"
        )
        self.assertEqual(spell.spell_slot_pool, "any")
        self.assertTrue(spell.allow_upcast)
        self.assertEqual(
            [(d.number, d.sides) for d in spell.upcast_damage_dice], [(1, 6)]
        )


if __name__ == "__main__":
    unittest.main()
