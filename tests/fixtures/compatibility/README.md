# Frozen compatibility fixtures

These files are historical inputs, separate from the regeneratable documentation
examples. Do not rewrite them when changing the current schema or serializers.
Add a new version directory and explicit upgrade expectations instead.

Only native schema version 1 exists in the repository history. There are no Git
release tags in this checkout, so these fixtures establish the available source
baseline rather than claiming independently verified published releases.

| Fixture | Provenance |
| --- | --- |
| `v1/native-character.json` | Synthetic old-format character, validated against `dfd4dc2:src/dnd5ecombat/schemas/v1/native-character.schema.json` (the imported 0.4.0 baseline). Exercises attack plans, damage riders, saves, upcasting, and separate slot pools without subsequent spell-extension fields. |
| `v1/monster.json` | Unmodified `dfd4dc2:monsters/ghoul.json`, including timed paralysis, repeat saves, and immunity tags. |
| `v1/scenario.json` | Unmodified `7d40d6e:scenarios/ranged-duel.json`, the first scenario implementation. |

Tests derive versionless copies from these files to exercise legacy normalization,
then save to a separate destination and reload. They check combat semantics,
new-field defaults, the current output version, and that source bytes stay intact.
The version inventory test requires fixture coverage when a schema directory is
added. Roll20 export metadata uses an independent version and is tested separately;
it is not a native profile migration.
