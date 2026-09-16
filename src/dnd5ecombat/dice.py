import random


def roll_dice(number, sides, modifier=0, rng=None):
    """Roll a number of same-sized dice and return their modified total."""
    if not isinstance(number, int) or isinstance(number, bool):
        raise TypeError("number must be an integer")
    if not isinstance(sides, int) or isinstance(sides, bool):
        raise TypeError("sides must be an integer")
    if not isinstance(modifier, int) or isinstance(modifier, bool):
        raise TypeError("modifier must be an integer")
    if number < 1:
        raise ValueError("number must be at least 1")
    if sides < 2:
        raise ValueError("sides must be at least 2")

    random_source = rng if rng is not None else random
    return sum(random_source.randint(1, sides) for _ in range(number)) + modifier


def roll_d20(rng=None):
    """Roll one twenty-sided die."""
    return roll_dice(1, 20, rng=rng)
