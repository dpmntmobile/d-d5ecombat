"""Low-level parsing helpers for Roll20 sheet values and formulas."""

import ast
import re

from .dice_parser import extract_damage_dice
from .models import DamageDice


def parse_damage_dice(dice_text, default_number=1, default_sides=8):
    if not dice_text or not dice_text.strip():
        return (DamageDice(default_number, default_sides),)
    try:
        return extract_damage_dice(dice_text, default_number, default_sides)
    except ValueError:
        raise ValueError("Damage dice must use the format like 1d8 or 2d6.")
    except TypeError:
        raise TypeError("Damage dice must be a string.")
def _resolve_roll20_modifier(raw_value, stat_lookup):
    """Resolve a Roll20 modifier value such as @{dexterity_mod} or 2 into an integer."""
    if raw_value is None:
        return 0

    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        return int(raw_value)

    text = str(raw_value).strip()
    if not text or text in {"-", "--"}:
        return 0

    match = re.search(r"@\{([^}]+)\}", text)
    if match:
        stat_name = match.group(1)
        if stat_name in stat_lookup:
            return int(stat_lookup[stat_name] or 0)
        return 0

    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)

    number_match = re.search(r"[-+]?\d+", text)
    return int(number_match.group(0)) if number_match else 0


def _resolve_roll20_formula(raw_value, stat_lookup, default=0):
    """Resolve a numeric Roll20 expression without evaluating arbitrary code."""
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        return int(raw_value)
    text = str(raw_value or "").strip()
    if not text:
        return default

    def replace_reference(match):
        return str(int(stat_lookup.get(match.group(1), 0) or 0))

    expression = re.sub(r"@\{([^}]+)\}", replace_reference, text)
    if not re.fullmatch(r"[\d\s()+\-*/.]+", expression):
        return default

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)
        ):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            return left / right
        raise ValueError("unsupported Roll20 expression")

    try:
        return int(evaluate(ast.parse(expression, mode="eval")))
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
        return default


def _roll20_flag_enabled(raw_value, flag_name):
    """Recognize both compact Roll20 flags and generated roll-template flags."""
    text = str(raw_value or "").strip().lower()
    if text in {"1", "on", "true"}:
        return True
    return re.search(r"\{\{\s*" + re.escape(flag_name) + r"\s*=\s*1\s*\}\}", text) is not None


def _group_repeating_rows(section, marker_field):
    """Group repeating Roll20 fields without assuming row IDs lack underscores."""
    groups = {}
    marker_suffix = f"_{marker_field}"
    for key, value in section.items():
        if not key.endswith(marker_suffix):
            continue
        row_prefix = key[: -len(marker_suffix)]
        fields = {}
        field_prefix = f"{row_prefix}_"
        for candidate, candidate_value in section.items():
            if candidate.startswith(field_prefix):
                fields[candidate[len(field_prefix) :]] = candidate_value.get(
                    "current", ""
                )
        groups[row_prefix] = fields
    return groups


def _normalize_save_ability(raw_value):
    ability = str(raw_value or "").strip().lower()
    aliases = {
        "strength": "str",
        "dexterity": "dex",
        "constitution": "con",
        "intelligence": "int",
        "wisdom": "wis",
        "charisma": "cha",
    }
    return aliases.get(ability, ability)


def _roll20_action_type(casting_time, attack_name=""):
    text = str(casting_time or "").strip().lower()
    if text.startswith("reaction"):
        return "reaction"
    if text.startswith("bonus action") or text.startswith("1 bonus action"):
        return "bonus_action"
    normalized_name = str(attack_name).lower().replace("-", " ")
    if "off hand" in normalized_name or "offhand" in normalized_name:
        return "bonus_action"
    return "action"


def _average_damage(damage_text, modifier):
    try:
        dice = parse_damage_dice(damage_text)
    except (TypeError, ValueError):
        return float(modifier)
    return sum(pool.number * (pool.sides + 1) / 2 for pool in dice) + modifier


def _preferred_attack_name(attacks, target_armor_class=15):
    """Choose a legal, repeatable action using expected damage as a baseline."""
    candidates = [
        attack for attack in attacks if attack.get("action_type", "action") == "action"
    ]
    if not candidates:
        candidates = list(attacks)

    def expected_damage(attack):
        bonus = int(attack.get("bonus", 0))
        hit_probability = max(0.05, min(0.95, (21 + bonus - target_armor_class) / 20))
        base_average = _average_damage(
            attack.get("damage_dice", ""), attack.get("damage_modifier", 0)
        )
        dice_average = _average_damage(attack.get("damage_dice", ""), 0)
        return hit_probability * base_average + 0.05 * dice_average

    return max(candidates, key=expected_damage)["name"] if candidates else None
