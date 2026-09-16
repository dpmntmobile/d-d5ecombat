import unittest
from types import SimpleNamespace

from dnd5ecombat.models import AttackProfile, DamageDice, TargetProfile
from dnd5ecombat.scenario_factory import build_duel_policy_matchups


class DuelPolicyFactoryTests(unittest.TestCase):
    def setUp(self):
        self.slash = AttackProfile("Slash", 4, (DamageDice(1, 6),), 2)
        self.bite = AttackProfile("Bite", 3, (DamageDice(1, 8),), 1)
        self.build = SimpleNamespace(
            name="Hero",
            armor_class=15,
            max_hp=20,
            initiative_bonus=2,
            attack_profiles=(self.slash,),
            attacks_per_action=1,
            saving_throw_bonuses=(),
            damage_resistances=(),
            damage_vulnerabilities=(),
            damage_immunities=(),
            condition_immunities=(),
            creature_tags=("humanoid",),
        )

    def test_each_single_attack_becomes_a_policy(self):
        monster = TargetProfile(
            "Monster",
            13,
            12,
            attack_profiles=(self.slash, self.bite),
        )

        policies = build_duel_policy_matchups(self.build, monster)

        self.assertEqual(len(policies), 2)
        self.assertEqual(
            tuple(policy.monster.attack_sequence for policy in policies),
            ((self.slash,), (self.bite,)),
        )

    def test_explicit_multiattack_remains_one_ordered_policy(self):
        monster = TargetProfile(
            "Monster",
            13,
            12,
            attack_profiles=(self.slash, self.bite),
            multiattack=("Bite", "Slash", "Slash"),
        )

        policies = build_duel_policy_matchups(self.build, monster)

        self.assertEqual(len(policies), 1)
        self.assertEqual(
            tuple(attack.name for attack in policies[0].monster.attack_sequence),
            ("Bite", "Slash", "Slash"),
        )

    def test_character_attack_count_is_preserved(self):
        build = SimpleNamespace(**{
            **self.build.__dict__,
            "attacks_per_action": 2,
        })
        monster = TargetProfile(
            "Monster", 13, 12, attack_profiles=(self.bite,)
        )

        matchup = build_duel_policy_matchups(build, monster)[0]

        self.assertEqual(matchup.character.attacks_per_turn, 2)


if __name__ == "__main__":
    unittest.main()
