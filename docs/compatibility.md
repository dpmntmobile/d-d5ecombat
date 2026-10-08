# Compatibility and deprecation policy

This policy governs future changes to profile files, documented commands, and
public Python APIs. The current application version is 0.4.0; the roadmap's
milestone names do not establish that a release was published. The available
Git history has no release tags, and only native schema version 1 is present.
No CLI option or public Python API is formally deprecated by this change.

## Profile and scenario files

Application versions and schema versions are independent. Native characters,
monsters, and scenarios currently write `schema_version: 1`. Files without that
field are legacy version-1 inputs. Explicit version 0, unknown versions, strings,
booleans, and null are rejected with a source path and `$.schema_version` error.
Loading does not rewrite a file. Saving writes the current schema version; save
to a separate destination when retaining an original is important.

Within a schema version, additive optional fields must preserve the meaning of
existing valid inputs. New fields need backward-compatible defaults. Old files
need not acquire new mechanics merely because a field is now available. Older
application binaries may reject newer optional fields under their strict
schemas: backward readability by new code does not promise forward readability
by old code. Bug fixes to combat rules may change results without changing file
format; record such changes in release notes.

A breaking field rename, type change, or change in stored meaning requires a new
schema version and an explicit migration. Before shipping that version:

1. Preserve the historical input fixtures for every supported previous version.
2. Add fixtures and tests for the new version, including required defaults,
   nested attacks/spells, conditions, resources, and encounter assumptions.
3. Test each supported old version through load/migrate/save/reload, checking
   semantic values and verifying that reading leaves the source unchanged.
4. Document which versions can be read and written, transformations, and any
   information that cannot be represented. Reject unsupported inputs rather
   than guessing or silently discarding data.

There is currently no version-2 migration and no downgrade facility. Today's
migration coverage is legacy/version-1 normalization and serialization to the
current version, including older files without the spell-extension fields.

The [frozen fixture record](../tests/fixtures/compatibility/README.md) identifies
the source commits and synthetic fixture provenance. These inputs must not be
regenerated from the current schemas. The separate
[documentation examples](profile-formats.md) can be regenerated.

Roll20 has an independent `export_metadata.version`. Its import-envelope schema
accepts positive integer export versions and unknown sheet sections; this is
structural tolerance, not a promise to understand future sheet mechanics.
Exports are not native profiles and do not receive a native version on import.
Do not reject an export simply because its metadata version differs from the
native schema version. Unsupported effects still require explicit mappings.

## Command-line interface

Supported entry points are `python -m dnd5ecombat`, `dnd5ecombat`, and
`dnd5ecombat-gui` (the latter requires the GUI dependency). Documented flags,
argument meanings, and scenario loading/override behavior are compatibility
contracts. `--target-file` remains an alias of `--monster-file`; use
`--monster-file` in new examples. The alias currently emits no warning and has
no scheduled removal.

Human-readable console table layouts, wording, spacing, and progress output may
change. Use the documented structured result export for data interchange, and
retain its application version and run metadata. A seed supports repeatability
with the same implementation and inputs; numerical results and random-number
consumption are not guaranteed identical across application versions.

## Python API

Prefer the established facade modules for application integrations:

| Module | Intended public surface |
| --- | --- |
| `dnd5ecombat.models` | Exported combat model classes and enums. |
| `dnd5ecombat.simulation` | Exported simulation functions and result models. |
| `dnd5ecombat.character_profiles` | Exported native persistence and Roll20 import helpers. |
| `dnd5ecombat.roll20_import` | Exported Roll20 parsing and conversion helpers. |
| `dnd5ecombat.monster_profiles` | `load_monster_profile`, `save_monster_profile`, `monster_from_dict`, `monster_to_dict`. |
| `dnd5ecombat.scenario_persistence` | `load_scenario`, `save_scenario`. |

Existing imports through `dnd5ecombat.main`, `dnd5ecombat.cli`, and
`dnd5ecombat.legacy_cli` remain supported compatibility paths. In particular,
`load_target_profile(path)` continues to load a monster profile. The module name
`legacy_cli` does not itself constitute a deprecation notice. Direct imports
used in the profile guide, such as `character_persistence.load_custom_build`,
also remain supported. Preserve signatures, return meanings, and documented
error behavior when moving implementations behind these paths.

Underscore-prefixed helpers, incidental imported dependencies such as `os`, GUI
widget internals, and undocumented implementation details are not public API
commitments merely because Python allows importing them. Prefer keyword arguments
for optional model fields; compatibility tests should retain existing valid
positional calls when signatures evolve.

## Introducing a deprecation

Retain the current documented APIs and CLI aliases through the 1.0 transition.
A future deprecation must name its replacement, explain migration, and state
the earliest removal release in documentation and release notes. Python calls
should issue `DeprecationWarning` with a caller-facing stack level; CLI uses
should issue a concise warning on stderr while retaining behavior and leaving
structured stdout intact. Tests must cover the warning and replacement parity.

Keep a deprecated public interface for at least one subsequent minor release
before removing it, and remove it only in a later major release. Patch releases
must not remove documented interfaces. If a correctness or security defect
requires an exception, document the reason, affected versions, and migration
path explicitly. These are requirements for future changes, not warnings or
removals introduced in the current application.
