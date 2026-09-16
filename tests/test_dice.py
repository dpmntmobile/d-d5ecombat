import random
import unittest

from dnd5ecombat.dice import roll_d20, roll_dice


class RollDiceTests(unittest.TestCase):
    def test_seeded_roll_is_reproducible(self):
        first_rng = random.Random(42)
        second_rng = random.Random(42)

        first_results = [roll_dice(2, 6, 3, rng=first_rng) for _ in range(5)]
        second_results = [roll_dice(2, 6, 3, rng=second_rng) for _ in range(5)]

        self.assertEqual(first_results, second_results)

    def test_modifier_is_added_to_dice_total(self):
        rng = random.Random(42)

        unmodified = roll_dice(1, 8, rng=random.Random(42))
        modified = roll_dice(1, 8, 3, rng=rng)

        self.assertEqual(modified, unmodified + 3)

    def test_negative_modifier_is_allowed(self):
        result = roll_dice(1, 2, -3, rng=random.Random(42))

        self.assertEqual(result, -2)

    def test_roll_d20_uses_d20_range(self):
        rng = random.Random(42)

        results = [roll_d20(rng=rng) for _ in range(100)]

        self.assertTrue(all(1 <= result <= 20 for result in results))

    def test_number_must_be_at_least_one(self):
        with self.assertRaises(ValueError):
            roll_dice(0, 6)

    def test_sides_must_be_at_least_two(self):
        with self.assertRaises(ValueError):
            roll_dice(1, 1)

    def test_dice_arguments_must_be_integers(self):
        invalid_arguments = [
            (1.5, 6, 0),
            (1, "6", 0),
            (1, 6, 0.5),
            (True, 6, 0),
        ]

        for number, sides, modifier in invalid_arguments:
            with self.subTest(number=number, sides=sides, modifier=modifier):
                with self.assertRaises(TypeError):
                    roll_dice(number, sides, modifier)


if __name__ == "__main__":
    unittest.main()
