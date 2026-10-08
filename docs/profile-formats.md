# Profile formats

The two native formats are **native characters** and **monsters**. Both use
`schema_version: 1`. Roll20 exports are a separate import envelope: character
editing belongs in Roll20, followed by a fresh export. Native character files
describe the application's persistence contract and support programmatic use;
the desktop interface does not provide a character editor.

## Complete examples

| Format | Downloadable JSON | Schema |
| --- | --- | --- |
| Native character | [Example adventurer](examples/native-character.json) | [Version 1](../src/dnd5ecombat/schemas/v1/native-character.schema.json) |
| Monster | [Example sentinel](examples/monster.json) | [Version 1](../src/dnd5ecombat/schemas/v1/monster.schema.json) |

These are complete, loadable, synthetic profiles, not official character builds
or creature statistics. They demonstrate attacks, damage defenses, six saving
throws, spell pools, an upcastable save spell, and self-healing. The character
also has a named turn plan; the monster has multiattack and a prone rider.
Optional fields can be omitted. These examples do not enumerate every possible
spell or mutually exclusive resource configuration.

From the repository root, after installing the project:

```python
from dnd5ecombat.character_persistence import load_custom_build
from dnd5ecombat.monster_profiles import load_monster_profile

character = load_custom_build("docs/examples/native-character.json")
monster = load_monster_profile("docs/examples/monster.json")
print(character.name, monster.name)
```

The [generated field reference](profile-reference.md) lists every top-level
field. The schemas linked above specify the nested structures and constraints.
Examples are stored in each schema's standard `examples` annotation. Regenerate
the JSON files and field reference after changing the schemas:

```bash
python scripts/generate_profile_docs.py
python scripts/generate_profile_docs.py --check
```

The generator validates the examples against their schemas. Automated tests
also load and round-trip them through the application's persistence code and
detect stale generated files. Edit the schema annotations, not generated JSON.

## Shared contract

The [compatibility policy](compatibility.md) covers historical fixtures, future
schema migrations, and deprecation of CLI and Python interfaces.

Files contain one JSON object. Unknown native fields are rejected. Versionless
native files are interpreted as version 1; an explicitly unsupported version is
rejected. Validation errors identify the source and JSON path. The application
then checks model constraints, such as valid attack references and pool
capacities; passing JSON Schema validation alone does not guarantee a usable
combat model. See [the supported rules](supported-rules.md) for execution limits.

AC and maximum HP are positive integers. Saving throw bonuses use lowercase
`str`, `dex`, `con`, `int`, `wis`, and `cha`. Damage defenses and creature tags are
string arrays; record concrete damage types, such as `fire`, rather than prose
prerequisites. Text in `unmodeled_effects` or `unmodeled_traits` documents omitted
behavior and does not execute a rule.

Distances are feet. Attack positioning uses `attack_mode`, `reach_feet`,
`normal_range_feet`, and `long_range_feet`; save actions use `range_feet`.
Starting distance and each side's speed belong to encounter/scenario settings,
not these profiles. Positioned duels require normal range for ranged attacks
and `range_feet` for save actions. Melee or unspecified attack modes default to
5-foot reach when reach is omitted.

`spell_slot_level: null` (or omission) means a non-spell attack, `0` means a
cantrip, and `1` through `9` identify leveled spells. `spell_slot_pool` is
`spellcasting`, `pact`, or `any`. Pools map string levels to remaining counts;
capacity pools specify full counts for pre-duel recovery. Omitted capacities
default to the starting pools. Capacity cannot be below the remaining count.
Pact Magic has at most one level, and model validation restricts it to 1–5.

`allow_upcast` permits a higher slot; `upcast_damage_dice` is added once per
extra level. `limited_uses` and `recharge_min_roll` cannot both be integers on
the same action. Recharge uses a d6 threshold from 2 to 6. An omitted or null
limit means no such limit. `support_spells[].free_casts` adds casts that precede
slot spending and recover on a long rest; a free cast uses the base spell level.

Action types are `action`, `bonus_action`, and `reaction`, but a schema-accepted
action type alone does not create a reaction policy. The supported reaction
save spell uses `reaction_trigger: "damaged_by_visible_creature"`.

## Native characters

Only `schema_version` and `name` are required by the schema. Supply explicit
combat values for reproducible comparisons; omitted values use loader defaults,
not class- or level-derived statistics. The top-level attack fields preserve
the primary attack. `attack_profiles` contains named alternatives; if it is
present, the loader selects the entry matching `primary_attack_name`, or its
first entry if no name matches. Keep both representations consistent.

Character attack and save damage uses dice objects:

```json
{"damage_dice": [{"number": 2, "sides": 6}], "damage_modifier": 3}
```

This represents `2d6+3`. `attacks_per_action` defaults to one; Extra Attack is
not inferred. `turn_plans[].attacks[].attack_name` references an attack by its
exact name. A plan records an ordered sequence and a nullable
`first_hit_bonus_damage`. Its `eligible_attack_indices` are zero-based positions
in that sequence. `requires_advantage` and `allows_nearby_ally` express the
supported Sneak Attack eligibility routes, rather than arbitrary prerequisites.

## Monsters

`schema_version`, `name`, `armor_class`, and `max_hp` are required. A profile may
have no attacks (a passive target), or only saving throw actions. Weapon/spell
attacks live in `attacks`; `multiattack` is an ordered list of their exact names
and can repeat a name. Without explicit multiattack, the baseline uses one
attack. Monster turn plans cannot exceed the explicit multiattack action count
(or one without multiattack). The desktop monster editor can create and save
these profiles.

Monster attack and save dice use strings, with modifiers stored separately:

```json
{"damage_dice": "2d6", "damage_modifier": 3}
```

Mixed dice can use `1d6+1d4`. Do not put a flat modifier in `damage_dice`.
Monster `upcast_damage_dice` on attacks and save actions also uses a string.
In both formats, support-spell dice and turn-plan bonus dice use arrays of dice
objects. In a healing support spell, `damage_dice` and `damage_modifier` describe
healing despite their shared names.

`condition_effect` attaches a saving throw rider to a successful attack. It
specifies `difficulty_class`, `save_ability`, and `condition`, with optional
duration, end-of-turn repeat save, and immune creature tags. `undead_fortitude`
is a monster survival flag; `pack_tactics`, `aggressive`, and `nimble_escape`
have the encounter-dependent behavior described in the rules guide.

## Roll20 imports

Use the [maintained export script](../scripts/roll20_export.js) and the
[README instructions](../README.md#roll20-script-mod-to-export-the-character-jsons).
Do not transform an export into a native profile by adding `schema_version`.
Roll20's `export_metadata.version` is independent of the native schema version.
The [import-envelope schema](../src/dnd5ecombat/schemas/v1/roll20-character.schema.json)
allows unknown sheet sections so the exporter can preserve them. Preservation
does not imply simulation support: only explicit import mappings add mechanics.
