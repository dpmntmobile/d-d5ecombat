"""Explicit spell metadata and slot mappings for the Roll20 2014 sheet."""

import re


def spell_level(value, row_prefix=""):
    text = str(value if value is not None else "").strip().lower()
    if not text:
        match = re.match(r"repeating_spell-(cantrip|[1-9])_", row_prefix)
        text = match.group(1) if match else ""
    if text == "cantrip":
        return 0
    if text in tuple(str(i) for i in range(10)) and not isinstance(value, bool):
        return int(text)
    if text:
        raise ValueError(f"unsupported Roll20 spelllevel: {value!r}")
    return None


def spell_range(value):
    text = str(value or "").strip().lower()
    if text == "touch":
        return 5
    match = re.fullmatch(r"([1-9]\d*)\s*(?:feet|foot|ft\.?)?", text)
    return int(match.group(1)) if match else None


def spell_slots(attributes):
    """Use exported remaining slots; total alone supplies a full starting pool.

    The sheet calls its Slots Remaining attribute `lvlN_slots_expended`.
    Missing levels supply no slots; character class never implies a pool.
    """
    result = {}
    for level in range(1, 10):
        keys = (f"lvl{level}_slots_expended", f"lvl{level}_slots_total")
        for key in keys:
            value = attributes.get(key, {}).get("current")
            if value is None or value == "":
                continue
            text = str(value).strip()
            if not re.fullmatch(r"\d+", text) or isinstance(value, bool):
                raise ValueError(f"{key} must be a non-negative integer")
            result[level] = int(text)
            break
    return result


def casting_pools(data):
    """Keep pure-Warlock sheet slots separate; mixed sheets need explicit pools.

    Optional pact_slots_level / pact_slots_remaining / pact_slots_total sheet
    attributes disambiguate multiclass exports. Never derive counts from level.
    """
    attrs = data.get("other_attributes", {})
    ordinary = spell_slots(attrs)
    raw_level = attrs.get("pact_slots_level", {}).get("current")
    if raw_level not in (None, ""):
        level = spell_level(raw_level)
        if level is None or not 1 <= level <= 5:
            raise ValueError("pact_slots_level must be 1 through 5")
        mapped = {}
        for source, dest in (
            ("pact_slots_remaining", "expended"),
            ("pact_slots_total", "total"),
        ):
            if source in attrs:
                mapped[f"lvl{level}_slots_{dest}"] = attrs[source]
        pact = spell_slots(mapped)
        if level not in pact:
            raise ValueError(
                "pact_slots_level requires pact_slots_remaining or pact_slots_total"
            )
        return ordinary, pact
    primary_class = (
        str(data.get("hp_and_level", {}).get("class", {}).get("current", ""))
        .strip()
        .lower()
    )
    multiclass = any(
        str(attrs.get(f"multiclass{i}_flag", {}).get("current", "0")).lower()
        not in {"0", "", "false", "off", "none"}
        for i in range(1, 4)
    )
    if primary_class == "warlock" and not multiclass:
        # Zero-valued ordinary levels are sheet placeholders, not Pact pools.
        pact = {level: count for level, count in ordinary.items() if count > 0}
        if not pact:
            totals = {k: v for k, v in attrs.items() if k.endswith("_slots_total")}
            pact = {
                level: ordinary.get(level, 0)
                for level, count in spell_slots(totals).items()
                if count > 0
            }
        if len(pact) > 1 or any(level > 5 for level in pact):
            raise ValueError(
                "pure Warlock export has ambiguous Pact Magic slots; supply pact_slots_level"
            )
        return {}, pact
    return ordinary, {}


def upcast_dice(attack_fields, spell_fields):
    """Recognize one linear extra-dice expression; never evaluate sheet macros."""
    explicit = str(spell_fields.get("spellhldmg", "")).strip()
    if re.fullmatch(r"[1-9]\d*d(?:4|6|8|10|12|20)", explicit):
        return explicit
    macro = str(attack_fields.get("hldmg", "")).strip()
    match = re.fullmatch(
        r"\{\{hldmg=\[\[\(([1-9]\d*)\*\?\{Cast at what level\?\|[^{}]+\}\)d(4|6|8|10|12|20)\]\]\}\}",
        macro,
    )
    if not match:
        return ""
    options = macro.split("Cast at what level?|", 1)[1].split("}", 1)[0].split("|")
    values = [re.fullmatch(r"Level ([1-9]),([0-8])", option) for option in options]
    if not all(values):
        return ""
    base = int(values[0][1])
    if any(int(value[2]) != int(value[1]) - base for value in values):
        return ""
    return f"{match[1]}d{match[2]}"


def upcast_warnings(attack_fields, spell_fields):
    if upcast_dice(attack_fields, spell_fields):
        return ()
    raw = (spell_fields.get("spellhldmg", ""), attack_fields.get("hldmg", ""))
    if any(
        str(value or "").strip() not in {"", "0", "{{hldmg=[[0]]}}"} for value in raw
    ):
        return (
            "Unrecognized higher-slot damage formula; automatic upcasting disabled.",
        )
    return ()


def casting_capacities(data):
    from copy import deepcopy

    full = deepcopy(data)
    attrs = full.get("other_attributes", {})
    for level in range(1, 10):
        if attrs.get(f"lvl{level}_slots_total", {}).get("current") not in (None, ""):
            attrs.pop(f"lvl{level}_slots_expended", None)
    if attrs.get("pact_slots_total", {}).get("current") not in (None, ""):
        attrs.pop("pact_slots_remaining", None)
    return casting_pools(full)
