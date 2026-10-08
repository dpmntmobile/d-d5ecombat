"""Named 2014 support spell mappings, sourced from exported spell rows."""

from dataclasses import asdict

from .roll20_fields import _group_repeating_rows, _resolve_roll20_modifier, parse_damage_dice
from .roll20_spell_resources import spell_level, spell_range
from .support_spells import SupportSpell


def map_support_spells(data, stat_lookup):
    result = []
    attrs = data.get("other_attributes", {})
    rows = _group_repeating_rows(data.get("other_repeating_attributes", {}), "spellname")
    traits = _group_repeating_rows(data.get("traits_and_features", {}), "name")
    fey_touched = any(str(t.get("name", "")).lower() == "fey touched" for t in traits.values())
    # Feat spells in these exports have no prepared checkbox. Infer the chosen
    # first-level spell only when that evidence identifies a unique candidate.
    fey_choices = [str(r.get("spellname", "")).lower() for p, r in rows.items()
                   if spell_level(r.get("spelllevel"), p) == 1
                   and str(r.get("spellschool", "")).lower() in {"divination", "enchantment"}
                   and "spellprepared" not in r]
    for prefix, fields in rows.items():
        name = str(fields.get("spellname", "")).strip()
        if name.lower() not in {"cure wounds", "faerie fire", "bless", "misty step"}:
            continue
        if str(fields.get("spellprepared", "1")).strip().lower() in {"0", "false", "off", ""}:
            continue
        level = spell_level(fields.get("spelllevel"), prefix)
        teleport = name.lower() == "misty step"
        if level != (2 if teleport else 1):
            continue
        modifier = _resolve_roll20_modifier(
            fields.get("spell_ability") or attrs.get("spellcasting_ability", {}).get("current"),
            stat_lookup,
        )
        dc = 8 + stat_lookup["pb"] + modifier + stat_lookup.get("spell_dc_mod", 0)
        healing = name.lower() == "cure wounds"
        dice = parse_damage_dice(str(fields.get("spellhealing") or "1d8")) if healing else ()
        spell = SupportSpell(
            name=name, effect="healing" if healing else name.lower().replace(" ", "_"),
            damage_dice=dice, damage_modifier=modifier if healing else 0,
            difficulty_class=dc, range_feet=spell_range(fields.get("spellrange", "")) or (5 if healing else 60),
            spell_slot_pool="any", upcast_damage_dice=parse_damage_dice("1d8") if healing else (),
            action_type="bonus_action" if teleport else "action",
            spell_slot_level=level,
            free_casts=int(fey_touched and (teleport or fey_choices == [name.lower()])),
        )
        result.append(asdict(spell))
    return result
