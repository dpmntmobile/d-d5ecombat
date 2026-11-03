# Release readiness notes ? unreleased

The source application version is 0.5.0. Party combat adds saved character
parties, counted monster groups, shared initiative, independent creature state,
seeded trial statistics, CLI JSON export, and a cancellable desktop dialog.
The party dialog now shows win/draw percentages and average rounds, HP, and
survivors, with a separate next-run composition summary. Desktop and CLI JSON
exports retain the completed run's seed, round limit, application version,
and full effective character/monster profiles. Desktop settings are disabled
during simulation; changing them afterward preserves the completed export.
Remaining party-battle attacks now retarget after a kill. Ordinary attacks
select against the current opponent's defenses; explicit multiattacks and
turn plans retain their chosen entries. Resource pools, spell action limits,
and once-per-turn bonuses remain shared across targets within a turn.
Group-state regressions cover ally eligibility for Pack Tactics and Sneak
Attack after death/incapacitation, condition isolation when retargeting,
concentration cleanup, and reactions across multiple opponents. The packaged
smoke test now exercises repeatable party battles and the offscreen party
dialog, including composition persistence, results, export, and cancellation.
See the README for battle file examples and targeting limitations. No release
or tag has been created. The earlier work below records the 1.0 readiness milestone.

## Prepared changes

- Explicit duel mappings for Hellish Rebuke, Vicious Mockery, Mind Sliver,
  Dissonant Whispers, Cure Wounds, Faerie Fire, Bless, and Misty Step.
- Extended profile schemas, generated examples, persistence, and compatibility
  fixtures. See [compatibility policy](compatibility.md).
- Scrollable setup, visible action buttons, explanatory tooltips, keyboard
  shortcuts, accessible result text, elapsed feedback, and font-aware charts.
- Installer lifecycle automation before release artifact publication.

## Combat exclusions retained for 1.0

These limitations remain documented rather than expanded in this milestone.

| Area | Retained limitation |
| --- | --- |
| Wolf | Keen Hearing and Smell remains in `unmodeled_traits`; sensory perception benefits are not simulated. |
| Character features | Preserved Roll20 traits, inventory, and spell text may lack combat mappings. Empty exclusion lists do not establish complete feature support. |
| Multiple creatures | Party battles use shared initiative and counted monster groups; roster comparisons remain independent pairs. No area targeting or ally healing/buff selection. Bless and Cure Wounds target self. |
| Battlefield | One separation distance, without terrain, cover, elevation, obstacles, hazardous paths, or complete perception/hearing. |
| Reactions | No general opportunity attacks or arbitrary reactions. Supported exceptions include Hellish Rebuke, Nimble Escape repositioning, and Dissonant Whispers fleeing with one eligible caster melee opportunity attack. |
| Spells | Arbitrary secondary effects, components, and concentration effects require mappings. Attack spells resolve one attack roll; repeated attacks do not model multiple rays/beams per casting. |
| Upcasting/imports | Automatic scaling covers mapped linear dice only. Additional targets, attacks, durations, complex ranges, and unrecognized formulas need explicit handling. Unsupported nonempty scaling produces exclusion notes; ambiguous Fey Touched choices are not guessed. |
| Conditions/traits | Only documented conditions and structured traits affect combat. Legendary actions, lair actions, and arbitrary free-text prerequisites are absent. |
| Policy | Immediate damage and bounded support estimates do not establish optimal play or future slot conservation. Support action spells replace the selected plan, including bonus attacks. |
| Modes | One-sided comparisons omit full duel spell state and resource depletion. Combat stops at zero HP without death saves; round limits can leave duels unfinished. |
| Seeds | Repeatability requires the same implementation and inputs. Results may change between application versions. |

The 2026-10-08 audit loaded all six bundled monsters and four bundled characters
through application loaders. Wolf's Keen Hearing and Smell was the only
nonempty recorded monster trait or action-effect exclusion. Loaded character
actions had no nonempty effect-exclusion entries. This audits recorded entries,
not every preserved Roll20 feature. The [rules guide](supported-rules.md)
defines the implemented subset and additional spell-policy constraints.

## Release validation checkpoint: 2026-11-03

Isolated Windows installer validation passed in
[draft PR #2](https://github.com/dpmntmobile/d-d5ecombat/pull/2), including clean
install, synthetic-baseline upgrade, installed smoke tests, and uninstall.
The synthetic older installer uses the current payload and does not test
historical binaries. Keyboard, Narrator, themes, Windows scaling, and the
party-dialog flow are user-validated; see the
[accessibility checklist](accessibility.md). The Windows executable was rebuilt
on 2026-11-03 and passed its expanded packaged smoke test. All 540 tests pass,
Ruff passes, and coverage is 83%; the desktop and party tests also pass with
200% Qt scaling. Inno Setup 6.7.3 was installed and the 0.5.0 installer compiled
successfully. Both Linux/Python 3.10 and 3.12 CI jobs passed in draft PR #2.
See the [0.5.0 review record](release-review-0.5.0.md) for validation evidence
and commit/release scope.

User validation (2026-11-03): the rebuilt executable's party-dialog flow passed
multiple-profile selection, save/load, run/export, cancellation, and close.
The user also confirmed keyboard/Escape, 150% and 200% Windows scaling,
light/dark/high-contrast themes, and Narrator checks all passed. No issues were
reported. All recorded party-combat follow-up tasks are complete. The initial
installer CI job timed out without diagnostics; the subprocess runner now uses
direct process handles, bounded waits, progress messages, and transcript logs,
and the retry passes. No merge or release publication has occurred.
