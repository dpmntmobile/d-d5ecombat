# Desktop accessibility and usability

Buttons, checkboxes, and selection controls include hover explanations of their
behavior, including encounter assumptions, resource choices, and editor actions.
Numeric simulation settings also explain their effect on a run.

The setup area scrolls on smaller displays and at larger font sizes. Simulate,
Compare multiple, and Cancel remain outside that area. Use Tab and Shift+Tab
to move between controls; arrow keys select profiles and result tabs. Results
tables support keyboard navigation and expose full labels and numerical values.
Best-result cells include an accessible textual explanation as well as bold text.
Charts show only the rows that fit, state the displayed count, and refer users
to the complete table. Chart values use the current font's measured width.

| Shortcut | Action |
| --- | --- |
| Ctrl+Enter | Run the selected simulations |
| Escape | Request cancellation of active work |
| Ctrl+I | Import a character |
| Ctrl+O | Load scenario settings |
| Ctrl+S | Save scenario settings |
| Ctrl+Tab / Ctrl+Shift+Tab | Change result tabs |

During a run, focus moves to Cancel. The status describes the active section,
the progress bar counts completed sections, and an elapsed timer updates once
per second. Section counts are not a time estimate. Cancellation is cooperative;
its message stays visible while active work stops. Focus returns to Simulate
when the worker finishes. Previous results remain available during a run.

## Validation checkpoint: 2026-10-08

The latest draft PR checks pass on Linux/Python 3.10 and 3.12 and on the isolated
Windows installer runner. Local tests cover 516 cases; Ruff passes. Windows
installer validation includes clean install, synthetic-baseline upgrade,
installed-application smoke tests, and uninstall. Simulation workers use spawn
rather than inheriting Qt state through fork.

Offscreen GUI tests cover a 640-by-480 window, keyboard cancellation, preserved
cancellation feedback, accessible best-result text, and chart rendering with a
24-point font. GUI tests also passed at 200% Qt scaling at an earlier checkpoint.
The real-worker GUI lifecycle regression was removed after intermittent
process exits; cancellation/restart remains a manual check. The earlier 517-test
and 83% coverage measurements are historical, not measurements of this suite.

Palette review led to theme-aware chart bars and matched best-result foreground
and background colors. Offscreen render text appeared as missing glyphs, so
those images only established color behavior. They do not validate actual
Windows text readability, Narrator, or desktop scaling.

User validation (2026-10-08): the initial packaged-app keyboard pass was
reported to work fine. This covers setup navigation, a small simulation,
keyboard navigation of results, Escape cancellation, and starting another run.
The separate dialog/export, scaling, Narrator, and theme checks below remain open.

User visual validation (2026-10-08): after the resize/scaling/readability and
tooltip check, the user reported that it looks good. No clipping or overlap was
reported. Exact Windows scaling levels exercised were not specified; this does
not independently confirm all three requested levels. Narrator and theme checks
remain open.

User Narrator validation (2026-10-08): the user reported that the Narrator
check works. No unnamed controls or confusing announcements were reported.

User theme validation (2026-10-08): the user reported that the theme check
works, with no readability issues reported. Exact themes exercised were not
listed, so high-contrast coverage is not independently confirmed.

Before closing the README accessibility milestone, perform this manual pass
on the rebuilt Windows application:

- [ ] Navigate import, scenario loading, monster editing, and roster selection,
  with keyboard alone. CSV export now succeeds after the serializer fix. Confirm visible focus and no trapped
  controls; Escape should close dialogs.
- [ ] Confirm any Windows scaling levels not exercised in the visual pass; inspect small and maximized windows,
  large text, long profile names, tables, and charts for clipping. Verify setup
  scrolling keeps every field reachable and action buttons remain visible.
- [x] With Windows Narrator, check profile selectors, numeric settings, validation
  links, result headers and cells, and best-result announcements. Verify status
  changes are discoverable. The user reported that the Narrator check works;
  detailed live-announcement behavior was not separately described.
- [x] Inspect light, dark, and high-contrast themes. Confirm focus, errors, selected
  rows, and best results remain readable without relying on color alone.
- [x] Start a large single-worker and multi-worker run, inspect elapsed/status
  feedback, request cancellation, and confirm a new run can start afterward.

The executable was rebuilt on 2026-10-08 with the GUI and tooltip changes and
passed its packaged smoke test. Manual validation and resulting fixes remain
outstanding.

Manual CSV export finding (2026-10-08): exporting metadata containing a
Condition enum failed with a JSON serialization error. The export serializer
now writes enum values, covered by Wolf/prone and Ghoul/paralyzed JSON and CSV
companion regressions. The executable was rebuilt and smoke-tested; the user confirmed that
packaged-app export works on retry. The fix also passed Linux test and Windows
installer CI on draft PR #1.

User cancellation validation (2026-10-08): the user confirmed the one-worker
and two-worker cancellation checks work, including a successful 100-trial run
after cancellation.
