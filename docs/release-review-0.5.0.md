# 0.5.0 review record

Prepared 2026-11-03. Candidate `3daa41e` is committed and pushed on
`review/party-combat-0.5.0` in [draft PR #2](https://github.com/dpmntmobile/d-d5ecombat/pull/2).
No merge or release tag has been made. The existing 1.0.0 readiness milestone
remains later work.

## Change scope

- Version 0.5.0 in `pyproject.toml`; package and Windows metadata use that version.
- Party/encounter definitions, relative profile references, counted monster
  instances, shared initiative, independent creature state, seeded statistics,
  draws, cancellation, and atomic JSON result export in `party_combat.py`.
- Party execution in `duel_simulation.py`, with file-order retargeting after
  kills and ordinary attack selection against each current opponent's defenses.
  Explicit plans and multiattacks preserve their selected entries; resources,
  spell action limits, and first-hit bonuses persist across targets.
- CLI options/workflow, the bundled `scenarios/party-battle.json`, and a desktop
  entry point with a cancellable worker, saved compositions, a next-run summary,
  readable results, and export of captured profiles/settings.
- Party combat/dialog tests, group-state regressions, and expanded source/frozen
  smoke tests. The desktop comparison buttons occupy a separate row to preserve
  the existing 640-pixel small-window behavior.
- README, supported-rules documentation, and unreleased notes explain the
  supported subset and retained targeting/spell limits.

The complete tracked diff and new source/test/scenario files were reviewed
together. Existing duel tests and the one-on-one party/duel comparison pass.
Build output under `build/` and `dist/` is ignored and is not part of the source
commit. The candidate commit includes the new party modules, smoke module,
tests, example scenario, and this review record.

## Validation

Windows, Python 3.10.6, project `.venv`:

- Ruff: passes.
- Full coverage run: 540 tests pass with Qt offscreen; total coverage 83%.
- Desktop tests (22) and party tests (18): pass at 200% Qt scaling.
- `git diff --check`: passes.
- Bundled party battle: 1,000 trials, seed 42, round limit 100, JSON export
  with full profiles and run metadata. Party wins 13.7%, encounter wins 86.3%,
  draws 0%, average rounds 3.671. These are simulation results, not an optimal
  tactics claim.
- `scripts/build_windows.ps1 -SkipDependencyInstall`: passes with PyInstaller
  6.22.2. `dist/Dnd5eCombatSimulator.exe` is rebuilt as version 0.5.0 and passes
  the packaged smoke test: resources/schemas/version, serial/parallel agreement,
  seeded party repeatability, and offscreen party-dialog completion, persistence,
  export, cancellation, and safe close.
- The local installer compiled successfully with Inno Setup 6.7.3:
  `dist/installer/Dnd5eCombatSimulator-Setup-0.5.0.exe`.
- [Linux CI](https://github.com/dpmntmobile/d-d5ecombat/actions/runs/41704841952)
  passed both Python 3.10 and 3.12 jobs for candidate `3daa41e`.
- The user confirmed the remaining accessibility checks all passed on
  2026-11-03: keyboard navigation/Escape, 150% and 200% Windows scaling,
  light/dark/high-contrast themes, and Narrator counts/settings/buttons/results.
- The first isolated Windows job built the executable and installer, then
  timed out during lifecycle validation without retained logs. The lifecycle
  process runner now uses direct process handles, bounded waits, progress
  messages, and a transcript. Local probes verify successful exits, nonzero
  exit rejection, timeout termination, and PowerShell syntax. CI is being retried.

The automated dialog smoke uses the persistence helpers and loaded-composition
state; the source GUI tests exercise the file-dialog callbacks with selected
paths. The user subsequently confirmed the rebuilt executable's interactive
party flow worked on 2026-11-03: multiple profiles, save/load, run/export,
cancellation, and close. No issues were reported. This validates the packaged
flow; a separate manual source-GUI run was not reported.

## Remaining checks before distribution

- [x] Review the rebuilt executable interactively. Open **Party
  battle...**, select multiple characters/monster types, save/load a composition,
  run trials, export, change counts, cancel a longer run, and close the dialog.
  Confirm the next-run summary and completed-result composition are clear.
- [x] Check keyboard access, Windows display scaling,
  Narrator, and themes using the [accessibility checklist](accessibility.md).
- [ ] Build the installer when Inno Setup is available. Run clean install,
  upgrade, and uninstall validation on a disposable Windows environment;
  `scripts/test_windows_installer.ps1` deliberately requires a GitHub Actions
  runner. Synthetic-baseline upgrade tests do not prove historical binary
  compatibility.
- [x] Run the Linux/Python 3.10 and 3.12 CI matrix.

Inno Setup was installed during the final validation pass; installer compilation
now passes. Isolated installer lifecycle checks are running on the draft PR,
so README step 6 remains open pending their result. The packaged party-dialog
flow and accessibility checks are user-validated. Creating/pushing a release tag publishes
artifacts through the release workflow and requires approval after review.
