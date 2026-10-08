# Release readiness notes ? unreleased

The application remains version 0.4.0. These notes record local work for the
1.0 readiness milestone; no release or tag has been created.

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
| Multiple creatures | Roster comparisons are independent pairs. No party encounters, area targeting, ally turns, or ally healing/buffs. Bless and Cure Wounds target self. |
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

## Outstanding release validation

Installer validation needs an isolated Windows workflow run. Its synthetic older
installer uses the current payload and does not test historical binaries. Manual
keyboard, Narrator, theme, Windows scaling, and long-run checks remain in the
[accessibility checklist](accessibility.md). The Windows executable was rebuilt
on 2026-10-08 and passed its packaged smoke test with the GUI and tooltip changes.
