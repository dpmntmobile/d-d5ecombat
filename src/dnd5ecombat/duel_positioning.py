"""One-dimensional approach policy for optional positioned duels."""


def validate_distance(value, field_name, optional=False):
    if optional and value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def attack_range(attack):
    """Return preferred and maximum distances; unknown attacks use 5-ft melee."""
    if hasattr(attack, "range_feet"):
        if attack.range_feet is None:
            raise ValueError(f"{attack.name}: positioning requires range_feet")
        return attack.range_feet, attack.range_feet
    reach = attack.reach_feet or 5
    if attack.attack_mode in {"ranged", "melee_or_ranged"}:
        normal = attack.normal_range_feet
        if normal is None:
            raise ValueError(f"{attack.name}: positioning requires normal_range_feet")
        maximum = attack.long_range_feet or normal
        if attack.attack_mode == "melee_or_ranged":
            return reach, max(reach, maximum)
        return normal, maximum
    return reach, reach


def attack_position(attack, distance):
    """Return (in range, ranged attack, long-range disadvantage)."""
    _, maximum = attack_range(attack)
    if hasattr(attack, "range_feet"):
        return distance <= maximum, False, False
    ranged = attack.attack_mode == "ranged" or (
        attack.attack_mode == "melee_or_ranged"
        and distance > (attack.reach_feet or 5)
    )
    return (
        distance <= maximum,
        ranged,
        ranged and distance > attack.normal_range_feet,
    )


def approach(sequence, distance, movement, speed):
    """Move toward preferred range; Dash only if no attack can reach afterward."""
    preferred = min(attack_range(attack)[0] for attack in sequence)
    distance = max(preferred, distance - movement) if distance > preferred else distance
    can_attack = any(attack_position(attack, distance)[0] for attack in sequence)
    if not can_attack:
        distance = max(preferred, distance - speed)
    return distance, can_attack
