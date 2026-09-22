# D&D 5e Combat Simulator

A lightweight Python project for modeling simple D&D 5e combat outcomes, including:

- attack resolution against armor class
- critical hits and advantage/disadvantage handling
- damage rolls and hit point reduction
- saving throw effects with half-damage or no-damage outcomes
- comparing attack scenarios and turn plans using repeated simulations

## Project layout

- `src/dnd5ecombat/` - application source package
- `characters/` - selectable character profiles
- `monsters/` - selectable enemy profiles
- `scenarios/` - reusable encounter settings for the CLI and GUI
- `assets/` - application icons and other static files
- `tests/` - unit tests and test-only fixtures
- `scripts/` - build, signing, and Roll20 helper scripts
- `packaging/` - PyInstaller and Windows installer configuration

## Project status and roadmap

Last reviewed: 2026-09-22. All 460 automated tests pass, Ruff reports no
lint errors, and coverage with branch measurement enabled is 81% (70% CI
floor). The Windows 0.4.0 executable previously passed its build and packaged
smoke test; it has not been rebuilt for the ongoing 0.5.0 changes.

This checklist is the project's planning record. Check an item only after its
implementation, tests, and relevant documentation are complete. Add newly
discovered work to the appropriate milestone instead of keeping a separate
undocumented task list.

### Completed foundation

- [x] Implement validated combat models, dice rolling, attacks, critical hits,
  saving throws, damage, and hit-point reduction.
- [x] Add seeded Monte Carlo simulations, exact attack analytics, confidence
  margins, cancellation, and deterministic multi-process execution.
- [x] Support attack comparisons, turn plans, damaging save spells, initiative,
  and two-sided character-versus-monster duels.
- [x] Model damage resistance, vulnerability, immunity, explicit multiattack,
  and the prone and paralyzed condition riders.
- [x] Import Roll20 characters while preserving attacks, spells, equipment,
  traits, saving throws, and combat metadata.
- [x] Load, validate, create, edit, and persist monster profiles.
- [x] Provide both a command-line interface and a desktop GUI with sortable
  tables, charts, CSV export, saved settings, and background execution.
- [x] Move the application into the standard `src/dnd5ecombat/` package layout
  with module and installed-command entry points.
- [x] Add automated unit, integration, architecture, and GUI-service tests plus
  Ruff checks in GitHub Actions.
- [x] Add reproducible Windows executable, installer, signing, and tagged-release
  workflows.

### 0.3.0 - Data contracts and reliability

Work through this milestone from top to bottom.

- [x] Define versioned JSON Schemas for native characters and monsters; validate
  imported and bundled profiles and provide clear field-level errors.
- [x] Audit every bundled profile against its recorded source so each combat
  trait is either modeled or explicitly listed in `unmodeled_traits` or
  `unmodeled_effects`.
- [x] Add coverage reporting and fill the thinnest integration areas: GUI
  interactions, profile persistence failures, malformed Roll20 input, installed
  CLI entry points, and packaged-application startup.
- [x] Use one authoritative application version for Python metadata, the package,
  Windows file metadata, the installer, and release artifact names.
- [x] Add regression-tested Roll20 mappings for template-form save flags,
  save-spell metadata, primary attack selection, racial defenses, Sneak Attack,
  and main-hand/off-hand turn plans.
- [x] Break up the largest modules along existing boundaries while preserving
  their public APIs and test behavior:
  - [x] `desktop_gui.py`
  - [x] `attack_simulation.py`
  - [x] `models.py`
  - [x] `cli_setup.py`
  - [x] `roll20_import.py`

### 0.4.0 - Tactical combat depth

Resumed audit (2026-09-16): all feature implementations and their focused
regressions were already present at the previous checkpoint. The full suite
now confirms those features together. Documentation covers mixed actions,
structured tactics and encounter assumptions, rider eligibility, monster
editor persistence, Roll20 mappings, Pact Magic, upcasting, and rests.

The audit also found two packaging gaps: explicitly bundle installed version
metadata, and wait for the windowed executable's smoke-test process before
checking its exit code. Both are corrected, with a regression that rejects
missing application version metadata. The application and installed package are now version 0.4.0; Windows file
metadata also reports 0.4.0. The offline Windows build and its packaged
resource/schema/profile/version smoke test pass. This completes the 0.4.0
milestone locally; no tag or release has been published.

Validation used Python 3.10 on Windows. The Python 3.12/Linux CI matrix was not
run locally. Inno Setup is unavailable here, so installer creation and clean
install/upgrade/uninstall checks remain unverified; installer lifecycle testing
is still recorded under 1.0.0.

- [x] Add starting distance, movement, reach, normal range, long-range
  disadvantage, and out-of-range decisions to duel scenarios.
- [x] Generalize condition handling, then add common conditions such as poisoned,
  restrained, stunned, and incapacitated with duration and repeat-save rules.
- [x] Model common structured traits and riders, beginning with currently recorded
  exclusions before expanding the bundled bestiary.
  - [x] Model 2014 Undead Fortitude in attacks, turns, save spells, and duels;
    persist the trait in monster profiles and expose it in the editor.
  - [x] Address remaining exclusions such as Pack Tactics, Aggressive, and
    Nimble Escape as their encounter and action requirements become supported.
  - [x] Account for survival traits when selecting character attacks for duels,
    including radiant attacks that bypass Undead Fortitude.
- [x] Represent limited-use actions and resources so spell slots, recharge
  abilities, bonus actions, and once-per-turn damage can participate in policy
  selection.
  - [x] Track per-attack limited uses and d6 recharge in duels, with fallback
    attacks, trial resets, profile persistence, and monster editor controls.
  - [x] Model shared spell-slot pools and save-based limited-use actions.
  - [x] Add slot costs for attack-roll spells and map exported Roll20 spell
    levels, ranges, and slot pools.
  - [x] Include bonus-action attack plans and once-per-turn damage in duel
    policies, including off-hand attacks and legal attack-spell combinations.
  - [x] Extend turn policies to mixed save/attack bonus actions, monster profile
    persistence/editor support, and encounter-dependent rider eligibility.
  - [x] Distinguish Warlock Pact Magic from per-level Spellcasting pools,
    including multiclass pool selection, upcast damage, and rest recovery.
- [x] Move Roll20 feature recognition into explicit, independently tested mapping
  rules so supported sheet traits are easy to add and audit.

### 0.5.0 - Scenario workflow and results

- [x] Add reusable scenario files for encounter assumptions such as distance,
  tactical roll modes, resources, and trial settings.
- [x] Let the CLI and GUI compare multiple characters and monsters in one run
  without manually repeating simulations.
- [x] Export complete result metadata alongside tables so a result records its
  seed, trials, profiles, assumptions, and application version.
- [x] Improve validation and empty-state guidance in the GUI, including direct
  links from an error to the profile or setting that caused it.

### 1.0.0 - Release readiness

- [ ] Document the supported rules subset and both profile formats with complete
  examples generated from the schemas.
- [ ] Add migration tests for every released profile-schema version and document
  the compatibility policy for deprecated CLI and Python APIs.
- [ ] Run automated Windows installer and packaged-application smoke tests on
  release candidates, including clean install, upgrade, and uninstall paths.
- [ ] Complete an accessibility and usability pass for keyboard navigation,
  scaling, chart readability, and long-running simulation feedback.
- [ ] Resolve all remaining recorded combat exclusions selected for 1.0, or list
  them explicitly in the release notes as supported limitations.

### Profile schema contracts

Version 1 schemas are bundled with the Python package under
[`src/dnd5ecombat/schemas/v1/`](src/dnd5ecombat/schemas/v1/):

- `native-character.schema.json` defines profiles saved by this application.
- `monster.schema.json` defines editable and bundled monster profiles.
- `roll20-character.schema.json` validates the Roll20 export envelope while
  allowing the exporter to preserve unknown sheet sections.
- `scenario.schema.json` defines reusable encounter and simulation settings.

New native character and monster files include `"schema_version": 1`.
Versionless native files remain compatible and are interpreted as version 1;
files declaring an unsupported version are rejected rather than guessed at.
Roll20 files retain their independent `export_metadata.version` value.

Validation happens before profile conversion. Errors include the source filename
and JSON path, for example:

```text
broken.json: $.attacks[0].attack_bonus: 'four' is not of type 'integer'
```

## Run the project

From the repository root:

```bash
python -m dnd5ecombat
```

## Desktop GUI

The optional desktop interface provides character and monster selectors,
simulation controls, sortable tables, and charts for attacks, turns, saving
throws, and duels. Install its dependency and launch it from the repository
root:

```bash
python -m pip install -e ".[gui]"
python -m dnd5ecombat --gui
```

You can also launch it with `dnd5ecombat-gui`. The GUI runs simulations
in a background thread so the window remains responsive. The existing CLI does
not require PySide6 and remains available without installing GUI dependencies.

The GUI can run every result tab or only the currently selected tab. It reports
progress between simulation categories and supports trial-level cancellation
when using one worker. Multi-process runs finish the active category before
cancellation takes effect. Roll20 character JSON files can be imported into
`characters/` and refreshed without restarting. Roll20 is the sole source of
truth for characters: this application intentionally does not create or edit
them. When a simulation needs additional character information, add it to the
Roll20 export script and re-export the character. Monsters can be created and
edited directly, including damage defenses, saving throws, attacks, multiattack
sequences, condition riders, and unmodeled traits. Invalid profile files are
reported instead of silently appearing in the selectors.

Tables support sorting, explanatory tooltips, best-result highlighting, CSV
export, and a compact chart of the primary metric. The last character, monster,
simulation settings, selected tab, and window geometry are restored on the next
launch.

When profiles cannot be loaded, **Review errors and files** shows the full file
paths and validation messages, with links to open each file in its associated
application. Correct the reported fields and press **Refresh**. Characters
remain managed in Roll20: correct the sheet/export and import the new export.
Import and scenario-load errors also link to the source file; scenario errors
that name a setting offer **Review setting** to focus its control. Failed
simulations retain diagnostic details and links to the profiles used in the run,
including every selected roster profile.

An empty catalog offers links to import a character or create a monster, and
disables actions that require missing profiles. Empty result tabs explain how
to proceed: saving throws require an imported damaging save effect, and duels
require an eligible monster attack or save action. Their links lead to the
relevant selector or import action. For roster results, inspect the per-pair
notes to identify which profiles need changes.

### Export results with run metadata

**Export CSV...** saves the selected result table and a companion file named
`<filename>.csv.json`. Keep the companion with the CSV: it contains the raw
numeric table values, column descriptions, notes and exclusions, application
version, seed, trials, workers, and all effective scenario settings. It also
captures the character and monster combat models, including attacks, defenses,
resources, and initiative overrides. These snapshots describe the inputs used
for the completed run; changing GUI controls or editing profiles afterward does
not change an existing result's metadata.

For CLI comparisons, add `--export-results FILE` with explicit character and
monster files (singular or roster options):

```bash
python -m dnd5ecombat --character-file characters/tobias_wren.json --monster-file monsters/goblin.json --trials 100 --seed 7 --export-results results.json
python -m dnd5ecombat --character-files characters/tobias_wren.json characters/amara_summerfield.json --monster-files monsters/goblin.json monsters/wolf.json --duels --export-results duels.json
```

This runs the same profile comparison tables as the GUI: attacks and turns by
default, or duels with `--duels`. CLI export requires non-interactive mode and
explicit profiles; generic AC sweeps and interactive-menu exports are not
supported. Each roster pair starts with the recorded seed. Roster labels link
table rows to their profile snapshots, and empty tables retain their explanatory
notes. JSON exports use `result_format_version: 1` and a `tables` object whose
entries contain `columns`, `rows`, `note`, `details`, and `metadata`. Profile
snapshots are records of simulation models, not importable character/monster
files. Existing JSON exports are replaced only after the new document is fully
written. CSV and its companion are separate files; a write error is reported
and may leave only the companion file updated.

### Reusable scenarios

Use **Save scenario...** and **Load scenario...** in the GUI to reuse encounter
settings with the currently selected character and monster. The same JSON files
work in the CLI:

```bash
python -m dnd5ecombat --save-scenario encounter.json --starting-distance-feet 60 --rest-before-duel long --trials 5000 --seed 7
python -m dnd5ecombat --scenario encounter.json --character-file characters/tobias_wren.json --monster-file monsters/goblin.json --duels
python -m dnd5ecombat --scenario scenarios/ranged-duel.json --trials 100 --duels
```

`--save-scenario` writes the effective settings and exits without running a
simulation. Combine it with `--scenario` to save a modified copy. Explicit CLI
options override the loaded file regardless of argument order. Boolean options
also have negative forms, such as `--no-include-advantage` and
`--no-character-can-hide`; `--abstract-positioning` resets the starting distance
to `null`, disabling movement and range rules.

The version 1 format contains `schema_version` and a `settings` object. Missing
settings use the application defaults; a missing version means version 1.
Unknown fields, unsupported versions, and invalid values are rejected with the
filename and JSON field path. Files record trials, seed, workers, advantage and
disadvantage variants, distance, movement, ally/concealment assumptions, and the
rest before each duel. Resource amounts and capacities still come from the
selected profiles; the saved rest determines their recovery. Character/monster
selection, comparison mode or GUI tab, and generic-target overrides such as
`--target-hp` are not stored. Choose these separately when reusing a scenario.
The GUI reports values outside its 32-bit integer range rather than changing
them silently. CLI scenario options require non-interactive mode; in the GUI,
use the load/save buttons.

### Compare multiple profiles

In the GUI, choose **Compare multiple...**, check the characters and monsters,
and press **Compare**. Every checked character is compared with every checked
monster using the current scenario settings and the All tabs/Current tab choice.
The dialog shows the number of comparisons before starting. Progress and Cancel
work across the whole run. Each result tab combines the rows with character and
monster profile columns; sorting and CSV export include those columns. Hover over
the result note for each pair's assumptions, exclusions, or missing actions.
Combined tables omit overall best highlighting and charts because different
opponents do not make a single comparable ranking. Roster selections are temporary
and are not stored in scenario files.

The CLI accepts lists of paths:

```bash
python -m dnd5ecombat --character-files characters/tobias_wren.json characters/amara_summerfield.json --monster-files monsters/goblin.json monsters/wolf.json --trials 100 --duels
```

This runs four independent matchups, not a party-versus-group encounter. Omit
`--duels` for attack and turn comparisons. You can combine one plural option with
the other side's singular option, for example `--character-files ... --monster-file
monsters/goblin.json`, and add `--scenario scenarios/ranged-duel.json`. Both sides
must be specified; repeated paths are evaluated once. All profiles are loaded
before simulation, and invalid files stop the run with an error. CLI output is
tab-separated, with probabilities expressed as fractions from 0 to 1.

Each pair starts from fresh profile resources with the same seed and settings,
so its results match a separate run and do not depend on roster ordering.
Increasing the roster multiplies the work; start with a small trial count.
The selected monster profiles supply target defenses rather than generic-target
options such as `--target-hp` or `--armor-classes`.

### Other command-line options

```bash
python -m dnd5ecombat --trials 5000 --seed 7 --target-hp 30 --armor-classes 12 14 16 18 20
```

CPU-bound comparisons can use multiple worker processes:

```bash
python -m dnd5ecombat --trials 50000 --workers 4
```

One worker is the default because process startup can cost more than it saves for
small runs. Parallel and sequential runs preserve the same ordered results for a
fixed seed.

Two-sided character-versus-monster duels can be run against every included
monster that has an attack profile:

```bash
python -m dnd5ecombat --character-file characters/tobias_wren.json --duels
```

Supply `--monster-file` as well to duel a single monster. In duel mode, each
side rolls initiative and attacks until one combatant reaches 0 HP. The
character uses its configured `attacks_per_action`; monsters currently make one
attack per turn unless their profile defines a `multiattack` sequence. Without
an explicit sequence, every monster attack is evaluated as a fixed action policy
in a full set of duels. The simulator selects the policy that produces the lowest
character win rate, so damage defenses and supported condition riders influence
the choice. This uses the configured trial count for every candidate action.

Enable distance and movement in duels with:

```bash
python -m dnd5ecombat --character-file characters/tobias_wren.json --monster-file monsters/goblin.json --duels --starting-distance-feet 60 --character-speed-feet 30 --monster-speed-feet 30
```

In the GUI, enable **Duel positioning** and set the starting distance and both
speeds in feet. These controls are saved between launches. They affect only the
Duels tab. CLI and GUI results report the positioning assumptions used.

Positioning is opt-in: without a starting distance, duels retain the original
abstract behavior. Speeds are explicit scenario assumptions (30 feet by default),
not imported creature speeds; set them to match the combatants. Zero speed is
allowed. Each trial resets to the configured starting distance.

The positioned duel uses a simple approach policy on open ground. Each combatant
moves toward its fixed attack policy's reach or normal range, then attacks. If no
attack can reach after movement, it uses its action to Dash. Attacks beyond their
maximum range are skipped, including individual attacks in a multiattack.
Ranged attacks beyond normal range have disadvantage, as do ranged attacks within
5 feet of an opponent who can take actions. Mixed melee/ranged weapons use melee
within reach and their ranged bands farther away. The character retains its
highest expected-damage weapon; it does not switch weapons during a duel.

Standing from prone costs half the combatant's speed; a zero-speed, restrained,
stunned, or paralyzed combatant cannot stand. Prone target modifiers and paralysis critical hits use
actual distance. These mechanics follow the
[2014 Basic Rules combat rules](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/combat).
Attacks without a mode are assumed to be melee, with a default reach of 5 feet.
Ranged or mixed attacks require a recorded normal range; missing range data
produces an error. A missing long range means normal range is the maximum.
The ordinary policy does not retreat. Nimble Escape can Disengage and move
out of close bow range (see tactical traits below). Terrain, cover bonuses,
opportunity attacks outside that Disengage policy, and ammunition are not modeled. Duels that cannot finish stop at the round
limit with an error rather than being counted as wins or losses.

Attack comparisons show only the normal attack profiles from the character sheet
by default. Tactical roll modes can be included explicitly:

```bash
python -m dnd5ecombat --character-file characters/tobias_wren.json --include-advantage
python -m dnd5ecombat --include-advantage --include-disadvantage
```

These flags add a clearly labelled variant of every attack. They represent an
explicit comparison assumption; the simulator does not infer whether the combat
situation grants advantage or disadvantage.

Enemy profiles live in `monsters/` and can be selected in interactive mode. A
monster can also be selected directly from the command line:

```bash
python -m dnd5ecombat --character-file characters/tobias_wren.json --monster-file monsters/goblin.json
```

```json
{
  "schema_version": 1,
  "name": "Goblin",
  "armor_class": 15,
  "max_hp": 7,
  "initiative_bonus": 2,
  "saving_throw_bonuses": {
    "str": -1,
    "dex": 2,
    "con": 0,
    "int": 0,
    "wis": -1,
    "cha": -1
  }
}
```

`schema_version`, `name`, `armor_class`, and `max_hp` are required for new
files. Versionless legacy files are read as schema version 1. Initiative
defaults to `0`, and omitted saving-throw abilities use `--target-save-bonus`
(default `+2`).
When a monster file is supplied, its AC and HP replace the generic AC sweep and
HP setting, its initiative bonus is used in initiative, and each save spell uses
the bonus for the ability named by that spell. `--enemy-initiative-bonus` remains
an explicit command-line override.

`--target-file` remains available as a backward-compatible alias for
`--monster-file`.

Included 2014 Basic Rules profiles are `orc.json`, `goblin.json`,
`skeleton.json`, `wolf.json`, `zombie.json`, and `ghoul.json`. Each profile
records its online source and ruleset. Profiles can also list
`unmodeled_traits`; the program prints these as warnings when a monster is
selected. Structured damage defenses and the zombie's 2014 Undead Fortitude
are modeled. Enable the latter with `"undead_fortitude": true` in a monster
profile or the monster editor checkbox; omitted values default to false.
Lethal damage triggers a Constitution save against DC 5 plus damage taken
(after defenses and any successful spell save), leaving 1 HP on success.
Radiant damage and critical hits bypass the trait. The rule follows the
[2014 zombie profile](https://www.dndbeyond.com/monsters/17077-zombie).
It applies to attack comparisons, turn plans, save spells, and duels, including
AC sweeps and multiple workers. Exact attack damage analytics still describe
damage dealt per attack; the simulated attacks-to-zero results include survival.
Against a monster with Undead Fortitude, duel character attack selection chooses
the attack with the fewest expected repeated uses to defeat it from full HP.
The calculation includes damage distributions, accuracy, critical hits, defenses,
damage rerolls, and the Constitution save. This can favor a weaker radiant attack;
a sufficiently stronger ordinary attack can still win. Selection is deterministic,
and ties retain profile order. Other targets retain expected-damage selection.
The preferred attack remains fixed; if spent, an available fallback is used.
This score does not optimize
weapon switching, movement/range, condition riders, or overall duel win probability.

Attack profiles can specify `"limited_uses": 2` for two available uses at the
start of each duel, or `"recharge_min_roll": 5` for one use that recharges on a
5 or 6. These fields are mutually exclusive; omitted or null values mean no
limit. The monster editor exposes both fields, and native character attack
profiles preserve them as well. Roll20 spell-slot recognition is described below;
arbitrary limited-use traits and recharge abilities are not inferred from text.

Uses are spent on attempted attacks, including misses, but not when out of
range or unable to act. An expended recharge attack rolls a d6 at the start of
its owner's turn, including turns when it cannot act, following the
[2014 recharge rules](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/monsters).
Each trial begins with fresh resources. Repeated references to an identical
attack in a sequence share its uses. Each attack attempt costs one use; these
fields do not represent shared spell slots or whole multiattack action costs.

Duel policies use their preferred attack sequence when available. When a
preferred attack is spent, an available action attack from the same combatant
is substituted, chosen by expected damage (or expected attacks to defeat a
target with Undead Fortitude). Spell-versus-weapon choices account for one
casting versus the configured number of weapon attacks per action. Once
recharged, the preferred attack is used
again. With no available fallback, that attack is skipped. Fallback choices
do not optimize range, resource conservation, or overall win probability.
The existing round limit still stops duels that cannot finish after resources
run out. Attack/turn comparison tables and exact analytics assume unlimited
repetition; only duels enforce these resource fields.

Character `turn_plans` now participate in duel selection. The simulator compares
available plans against the preferred action and eligible save actions each
turn, including the damage from one bonus action and a first-hit rider. It
reserves limited uses and slots before scoring without spending the actual
resources. Depleted plan entries are skipped, retaining their original rider
eligibility indices; the ordinary action fallback remains available. Ties keep
the existing action and then profile order. Plans score current roll modes,
damage defenses, range after approach, and automatic critical hits from
paralysis. They do not forecast new condition riders, future turns, or slot
conservation. The existing Undead Fortitude preference remains the baseline;
additional plans compete on expected immediate damage.

A duel attack plan must contain action attacks followed by at most one bonus
attack, within the configured action attack count. Off-hand weapon attacks
require an attempted, in-range weapon action that turn; a miss still qualifies.
Casting an action spell cannot also produce extra weapon attacks. An explicit
bonus-action attack spell can follow weapon attacks or an action cantrip, but
not a leveled action spell, following the
[2014 bonus-action spell rule](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/spellcasting#BonusAction).
A bonus-action spell can also be cast after Dashing into range. Incapacitation
prevents both actions. Save and attack actions can share a turn with one legal bonus action. The policy
compares weapon-plus-save, save-plus-attack, and save-plus-save combinations.
A bonus-action spell permits only an action cantrip; an independent non-spell
bonus save ability can follow a leveled action spell. Off-hand weapon attacks
still require an attempted weapon Attack action. Saves never trigger hit riders.
Dash permits independent bonus save abilities and bonus spells, but no off-hand
weapon attack. Resource reservation includes both parts of the turn.

`first_hit_bonus_damage` applies its dice to the first hit at an eligible attack
index each turn. Misses preserve it for later attacks, including the off-hand
attack; a hit consumes it even when damage is resisted or negated. Its dice
double on a critical hit and use the triggering attack's damage type. The
optional `requires_advantage` boolean defaults to false for existing native
profiles. When true, the actual attack must have advantage without cancelling
disadvantage. The same requirement applies to one-sided turn comparisons;
enabling advantage/disadvantage comparisons adds variants of imported plans.

Roll20 Sneak Attack mappings set `requires_advantage: true` and
`allows_nearby_ally: true`. An explicit nearby-ally assumption enables the ally
route to [2014 Sneak Attack](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/classes#SneakAttack)
when the roll does not have disadvantage. Advantage and disadvantage cancel,
so a normal roll after cancellation can qualify through the ally route.
Without that assumption, an imported rider requires actual advantage.
One-sided comparisons have no ally assumption and retain the advantage rule.
Finesse/ranged eligibility comes from the exported weapon metadata, and extra
weapon attacks share one rider across the turn. Exported off-hand attacks and
bonus-action attack spells produce legal combined plans automatically; Extra
Attack repeats only the main weapon attacks. Reactions, non-damaging bonus actions other than the structured traits below,
and arbitrary free-text prerequisites remain unsupported.

Monsters and native characters can declare starting slots by level, for example
`"spell_slots": {"1": 2, "2": 1}`. Their `saving_throw_profiles` can specify
`spell_slot_level` (0 for a cantrip, 1-9 for a slot), `limited_uses`,
`recharge_min_roll`, and `range_feet`. The monster editor has a **Saving throws
and slots** tab. A minimal monster with a save action looks like this:

```json
{
  "schema_version": 1,
  "name": "Example caster",
  "armor_class": 12,
  "max_hp": 20,
  "spell_slots": {"1": 2},
  "saving_throw_profiles": [{
    "name": "Fire burst",
    "difficulty_class": 13,
    "save_ability": "dex",
    "damage_dice": "2d6",
    "damage_type": "fire",
    "damage_on_success": "half_damage",
    "spell_slot_level": 1,
    "range_feet": 30
  }]
}
```

Native character save profiles use the existing dice-array format instead of
the monster dice string. Attack and save spells drawing from the same slot level
share that pool. A casting spends one slot even if the attack misses, the target saves, or is
immune; availability is reset for each trial. A missing pool has zero slots.
For legacy native profiles, `spell_slot_level` still names the exact casting
level. To permit higher slots, set `allow_upcast: true`. Set
`upcast_damage_dice` to the extra damage per slot level: `"1d6"` in a monster
profile or `[{"number": 1, "sides": 6}]` in a native character profile. Only
linear damage-dice scaling is supported; target counts, additional attack rolls,
durations, and other higher-level effects remain explicit exclusions. These
fields implement the damage portion of the
[2014 spell-slot rules](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/spellcasting).
Attack profiles also accept `spell_slot_level`: omit it or use null for a
weapon or other non-spell attack, use 0 for a cantrip, and 1-9 for a spell.
The monster attack editor exposes this field. An attack spell makes one attack
roll and consumes its declared action or bonus action. Action spells replace
the entire Attack action, including when the combatant has Extra
Attack; a depleted spell falls back to the available weapon action. Multiple
rays or beams per casting are not modeled by repeating the spell in a
multiattack sequence. Positioning uses the attack's existing reach and range
fields. Out-of-range attempts and turns when actions are prevented do not spend
slots. Dashing spends no slot unless an eligible bonus-action spell is cast
afterward. This follows the distinction between the Attack and Cast
a Spell actions in the
[2014 combat rules](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/combat).

Roll20 imports map spell levels from attack rows or linked spell rows, with
the repeating section supplying the level when the row omits it. Cantrips
map to level 0. An attack's range takes priority over the linked spell range;
numeric foot ranges and Touch (5 feet) are supported. Unknown or complex
save-spell ranges remain unset and require correction in the Roll20 export
before positioned duels. Attack IDs containing underscores remain linked.

For each level, `lvlN_slots_expended` supplies the starting **remaining**
slots, including an explicit zero. Despite its attribute name, this is the
sheet's Slots Remaining value; it is not subtracted from the total. If absent
or blank, `lvlN_slots_total` supplies a full starting pool. Missing levels
provide no slots, and invalid counts are rejected with the attribute name.
These fields are already preserved by `scripts/roll20_export.js`; no exporter
upgrade is required. The mapping follows the
[Roll20 2014 sheet's spell fields](https://help.roll20.net/hc/en-us/articles/360037773573-D-D-5E-by-Roll20).
Class levels never imply missing slot counts. A pure Warlock export maps its
per-level sheet slots into `pact_slots`, including a depleted pool identified by
its exported total. Multiclass exports can provide the explicit sheet attributes
`pact_slots_level`, `pact_slots_remaining`, and `pact_slots_total`; the ordinary
`lvlN_slots_*` fields then describe only Spellcasting. These attributes are
already preserved by the exporter. Keep the two sources separate in Roll20.

Imported leveled spells use `spell_slot_pool: "any"` and allow higher slots.
Simple `spellhldmg` dice strings and linear `hldmg` casting-level dice macros
provide extra damage per level. Unrecognized nonempty upcast formulas disable automatic upcasting for that
spell and appear in its `unmodeled_effects`; they are never evaluated as code.

Only save profiles with `action_type: "action"` or `"bonus_action"`, a named saving throw ability,
and explicit slot/uses/recharge metadata enter duel selection. Existing
unmapped imports stay comparison-only. Each turn, available save actions
compete as legal action/bonus-action combinations by expected immediate damage;
ties retain the baseline and then profile order. Casting an action spell replaces
the Attack action, including extra weapon attacks. If it cannot cast, the combatant uses its
available weapon plan. Slot conservation and future turns are not optimized.

Save actions apply damage defenses, save-success damage, Undead Fortitude,
and condition-based automatic failures or disadvantage. Positioning requires
`range_feet`; the combatant approaches that range and may Dash instead of
casting. Actions affect only the opposing combatant: area damage, concentration,
ongoing spell effects, and components are not modeled. A save-only monster is
supported, but a duel can reach its round limit if depleted resources leave
neither side able to finish. Resource limits do not apply to the one-sided
save comparison table.

These monster profiles also contain their official attacks. Each attack records
its attack bonus, damage formula and type, melee reach and/or ranged bands, plus
any `unmodeled_effects` attached to that attack. For example:

```json
{
  "name": "Bite",
  "attack_bonus": 4,
  "damage_dice": "2d4",
  "damage_modifier": 2,
  "damage_type": "piercing",
  "attack_mode": "melee",
  "reach_feet": 5,
  "condition_effect": {
    "difficulty_class": 11,
    "save_ability": "str",
    "condition": "prone"
  },
  "unmodeled_effects": []
}
```

Monster-level combat fields include `damage_resistances`,
`damage_vulnerabilities`, `damage_immunities`, `condition_immunities`,
`creature_tags`, and `multiattack`. A multiattack is an ordered array of attack
names and may repeat a name, such as `["Claw", "Claw"]`.

Monster attacks are loaded, validated, displayed, and used by the two-sided duel
simulation. Duel results include the character's win rate with an approximate
95% confidence-interval margin, average combat length, remaining HP on wins or
losses, and the rate at which the character wins initiative.

Damage resistances, vulnerabilities, and immunities apply to attack and imported
save-spell damage. Explicit monster multiattack sequences are resolved in order.
The duel engine supports hit-triggered condition riders on both combatants.
Condition immunities and `immune_creature_tags` prevent their application.
Supported combat modifiers follow the
[2014 condition rules](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/appendix-a-conditions):

| Condition | Modeled effects |
| --- | --- |
| Prone | Attack disadvantage; attackers have advantage within 5 feet, disadvantage farther away; standing costs movement. |
| Poisoned | Attack disadvantage. |
| Restrained | No movement; attack disadvantage; attackers gain advantage; Dexterity save disadvantage. |
| Stunned | No actions or movement; attackers gain advantage; Strength and Dexterity saves automatically fail. |
| Incapacitated | No actions, including Dash; ordinary movement remains available. |
| Paralyzed | Stunned combat modifiers, plus hits within 5 feet become critical hits. |

Abstract duels retain their melee/ranged approximation for prone and paralysis.
Ability checks, speech, reactions, and condition-driven spellcasting restrictions
are outside the current duel action model. The other simulation tabs do not
apply condition riders.

Every `condition_effect` can optionally specify `duration_turns`, a positive
integer counting the affected combatant's turns. It expires at the end of the
last turn, including a turn skipped because of the condition. Omitted or `null`
duration has no time limit, preserving older profiles. The monster editor's
**Duration (turns)** column accepts a positive number or a blank for no limit.
For example, an attack can include:

```json
"condition_effect": {
  "difficulty_class": 13,
  "save_ability": "con",
  "condition": "stunned",
  "duration_turns": 2,
  "repeat_save_at_end_of_turn": true
}
```

A failed initial save applies the effect. If enabled, repeat saves occur at the
end of each affected turn and may end it early; expiration needs no save.
Existing conditions modify initial and repeat saves alike. At a turn boundary,
all repeat saves use the conditions present before any end-of-turn removals.
An effect requiring a Strength or Dexterity repeat save while stunned or
paralyzed therefore needs a finite duration or another removal mechanism.

Different attacks retain independent condition timers and repeat saves.
Reapplying the same attack's rider refreshes its timer; modifiers do not stack.
Standing removes all prone instances. Each trial starts with no conditions.
Native character and monster JSON preserve these fields under schema version 1.
Roll20 defense, fighting-style, Sneak Attack, and turn-plan recognition is
implemented as independently tested functions in `roll20_feature_rules.py`.
Slot, Pact Magic, and upcast mappings live in `roll20_spell_resources.py`.
Unknown trait names remain preserved without inferred combat effects.

The bundled ghoul now uses a ten-turn limit for its one-minute paralysis,
with Constitution repeat saves, matching the duration recorded in its
[2014 profile](https://www.dndbeyond.com/monsters/16872-ghoul) using this
simulator's affected-turn timing convention.

Terrain, general retreat/opportunity-attack policies, and arbitrary free-text
traits or attack riders remain outside the duel model. The supported Nimble
Escape movement is always accompanied by Disengage. Any recorded `unmodeled_traits` and
`unmodeled_effects` are printed with duel results so those exclusions remain
visible.

### Tactical traits and encounter assumptions (0.4.0)

Native characters and monsters accept `pack_tactics`, `aggressive`, and
`nimble_escape` booleans, plus `stealth_bonus` (default 0) and
`passive_perception` (default 10). Monster editor controls expose these fields.
The bundled wolf, orc, and goblin now record their corresponding modeled traits.
The wolf's Keen Hearing and Smell remains an explicit exclusion.

- **Pack Tactics:** grants attack advantage only when that side's
  `ally_near_target` assumption is enabled. It means a living, non-incapacitated
  ally is within 5 feet of the opponent. The ally grants eligibility only;
  it does not take turns or deal damage.
- **Aggressive:** uses an otherwise free bonus action to add up to the
  combatant's speed to approach movement when ordinary movement cannot reach
  the preferred attack distance. The opponent is assumed visible. Conditions
  that prevent actions or movement still apply.
- **Nimble Escape:** with an otherwise free bonus action, a ranged attacker
  within 5 feet can Disengage and use ordinary movement toward its normal bow
  range. Otherwise, when `can_hide` is enabled, it can Hide after movement:
  d20 plus Stealth must exceed the opponent's passive Perception. Poisoned
  imposes disadvantage on this check and reduces passive Perception by 5.
  Successful hiding gives advantage to the next attack attempt, then ends
  whether the attack hits or misses. Attacks against a still-hidden combatant
  have disadvantage. `can_hide` explicitly assumes suitable concealment at
  the chosen position; the engine does not derive it from terrain.

These traits follow the recorded [wolf](https://www.dndbeyond.com/monsters/17062-wolf),
[orc](https://www.dndbeyond.com/monsters/16972-orc), and
[goblin](https://www.dndbeyond.com/monsters/16907-goblin) 2014 profiles.
A selected damaging bonus action takes priority over these non-damaging
options; the policy does not forecast later turns or optimize concealment.

CLI flags are `--character-ally-near-target`, `--monster-ally-near-target`,
`--character-can-hide`, and `--monster-can-hide`. All default to false. The
corresponding GUI checkboxes persist between sessions. Results print enabled
assumptions alongside positioning. Movement traits need positioning enabled;
Pack Tactics, Hide, and the Sneak Attack ally route also work in abstract duels.

Monsters can now persist `turn_plans` using the same attack-name/scenario and
first-hit rider contract as native characters. Use the **Turn plans and riders**
editor tab to enter an action sequence and optional bonus attack, rider dice,
and eligible positions (the GUI counts from 1; JSON indices count from 0).
A plan's action count cannot exceed its monster's explicit multiattack count,
or one without multiattack. Mixed save/attack combinations are generated from
eligible save profiles and bonus attack profiles automatically.

### Pact Magic, upcasting, and rests (0.4.0)

`spell_slots` and `pact_slots` record separate starting remaining pools.
`pact_slots` has at most one level, from 1 through 5. For example:

```json
"spell_slots": {"1": 1},
"spell_slot_capacity": {"1": 4},
"pact_slots": {"3": 0},
"pact_slot_capacity": {"3": 2}
```

`spell_slot_capacity` and `pact_slot_capacity` record full pools for recovery.
Omitting a capacity uses that profile's starting pool as the capacity. A capacity
cannot be below its remaining count. The monster editor exposes current and
full pools; Roll20 imports use exported totals as capacities.

A leveled attack/save spell can choose `spell_slot_pool: "spellcasting"`
(the native default), `"pact"`, or `"any"`. The last option supports multiclass
cross-casting. Policy reservation and actual casting use the lowest sufficient
available slot, preferring Pact Magic when both pools have that level. Higher
levels require `allow_upcast: true`; available `upcast_damage_dice` are added
once per extra slot level in both policy scoring and damage resolution. A
casting consumes one slot from exactly one pool, even on a miss or successful
save. Once spent, the other pool remains available for subsequent castings.
The policy does not deliberately spend a larger slot for more damage while a
smaller sufficient slot is available.

Use `--rest-before-duel short` to refill Pact Magic or
`--rest-before-duel long` to refill both pools before each trial. The GUI has
the same selector. The default is `none`. Rest is a scenario assumption before
combat; combatants never rest during a duel. Each trial starts independently
from the recorded profile, applies the selected rest, and resets conditions
and encounter resources. These rules follow
[2014 Pact Magic](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/classes#Warlock)
and [multiclass spellcasting](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/customization-options#Spellcasting).

## Run tests

```bash
python -m unittest discover -s tests -q
```

## Development

Project metadata and optional dependency groups are defined in
`pyproject.toml`. A typical development setup is:

```bash
python -m venv .venv
python -m pip install -e ".[gui,dev]"
python -m ruff check .
python -m coverage run -m unittest discover -s tests -q
python -m coverage report
```

The project version in `pyproject.toml` is authoritative. Python package
metadata reads it during installation, while the Windows build derives both
executable and installer versions from it automatically.

GitHub Actions runs linting and the full test suite on Python 3.10 and 3.12.
The Linux jobs install the GUI dependencies and use `QT_QPA_PLATFORM=offscreen`
so the GUI tests run without a display and count toward the 70% coverage floor.
Use the same environment variable when running the suite on a headless machine.

## Build a Windows executable

The PyInstaller specification bundles the branded GUI, built-in character data,
and monster profiles. From PowerShell:

```powershell
.\scripts\build_windows.ps1
```

When the packaging dependencies are already installed, an offline rebuild can
skip dependency installation:

```powershell
.\scripts\build_windows.ps1 -SkipDependencyInstall
```

The executable is written to `dist\Dnd5eCombatSimulator.exe`. In a packaged
application, imported characters are stored under
`%LOCALAPPDATA%\Dnd5eCombatSimulator\characters` so they persist between runs.
Created or edited monsters are stored in the corresponding `monsters` folder.

To also build an installer, install Inno Setup and run:

```powershell
.\scripts\build_windows.ps1 -Installer
```

Authenticode signing is optional and requires the Windows SDK `signtool.exe`
plus a certificate in the Windows certificate store. Set
`WINDOWS_CERT_THUMBPRINT`, then use `-Sign` (and optionally `-Installer`):

```powershell
.\scripts\build_windows.ps1 -Sign -Installer
```

Pushing a `v*` tag runs the Windows release workflow, builds the executable and
installer, uploads both as workflow artifacts, and attaches them to the GitHub
release. Signing remains opt-in because certificate material is deployment
specific.

## Roll20 script mod to export the character jsons

The complete exporter is maintained in
[`scripts/roll20_export.js`](scripts/roll20_export.js). Install that file as a
Roll20 Mod (API) script, then run this command in Roll20 chat:

```text
!exportjson CHARACTER_ID
```

Copy the JSON between the START and END markers in the Mod Console into a
`.json` file under `characters/`. In addition to attacks and core sheet values,
the exporter preserves traits and features, inventory, resources, and unknown
repeating sections so future combat mechanics can be added without changing the
export format again.

## Notes

The included example compares a few attack options across several armor classes and prints summary tables for:

- average attacks to reduce a target to 0 HP
- average turns to reduce a durable target to 0 HP using the character's attacks per action
- average save uses for imported damaging spells that explicitly require saving throws

The attack table also shows each scenario's signed attack bonus and damage dice
expression, such as `+4` and `1d8+2`, so imported values can be checked directly
against the character sheet. An asterisk marks the lowest average
attacks-to-zero in each AC column, including ties.

Attacks-to-zero values include an approximate 95% confidence-interval margin.
Overlapping intervals warn that a small numerical difference may be simulation
noise even when one value receives the per-column asterisk.
The analytical check calculates exact hit chance, critical chance, and expected
damage from the complete dice distributions, then shows the pooled Monte Carlo
damage beside it as a convergence check.

Initiative order is rolled for the character and target using their initiative
bonuses. Ties use the 2014 rule's optional d20 reroll. Initiative does not change
the one-sided attacks-to-zero comparison, but it does affect two-sided duel
results.

Imported characters default to one attack per Attack action. A JSON build must
explicitly provide `"attacks_per_action": 2` (or another positive integer) for a
larger turn plan; the simulator does not infer Extra Attack from class or level.
All six saving-throw bonuses are read from Roll20's exported
`<ability>_save_bonus` attributes for monster condition riders.
Exported traits are retained for combat mappings; Celestial Resistance currently
adds necrotic and radiant resistance automatically. Attack modes and ranges are
derived from Roll20 attack and inventory properties, including thrown weapons.
Great Weapon Fighting is applied to eligible melee attacks with two-handed
weapons, rerolling each damage-die result of 1 or 2 once in simulations and
exact expected-damage calculations.

This makes it useful for quick rough comparisons of simple build and tactic choices.
