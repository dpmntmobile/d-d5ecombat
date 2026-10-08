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

Latest theme validation: all 516 tests and Ruff pass. The rebuilt executable
passes its packaged smoke test. The real-worker GUI lifecycle regression was
removed after intermittent offscreen process exits; cancellation/restart remains
a manual release check. Earlier 517-test/coverage counts are historical.


Palette review found fixed colors on best-result cells, chart bars, and profile
warnings. These now follow the application palette; best cells use its matched
highlight and highlighted-text colors, retaining bold and accessible text.
Offscreen light, dark, and high-contrast renders confirm the color changes.
The offscreen platform rendered text as missing glyphs, so these images do not
establish text readability or replace the real Windows desktop review.

Real background GUI runs now have an integration regression covering one and
two worker processes: request cancellation with Escape, wait for controls to
recover, and complete a subsequent run. The serial run also exercises elapsed
feedback during a large trial request. Parallel cancellation waits for active
worker batches to finish; high trial counts can make that wait substantial.
The GUI tooltip and cancellation message explain this delay.

All 517 tests pass under branch coverage measurement (83% total; 70% floor),
and Ruff passes. The executable was rebuilt again with the cancellation message
and passed its packaged smoke test. These checks still do not verify Narrator
or actual Windows desktop themes and scaling.

Automated offscreen GUI checks pass at normal and 200% Qt scaling, including
a 640×480 window, keyboard cancellation, preserved cancellation feedback,
accessible best-result text, and chart rendering with a 24-point font.
These checks do not establish screen-reader compatibility or visual quality.

Before closing the README accessibility milestone, perform this manual pass
on the rebuilt Windows application:

- Navigate setup, import, scenario loading, monster editing, roster selection,
  result tabs, and CSV export with keyboard alone. Confirm visible focus and
  no trapped controls; Escape should close dialogs or cancel an active run.
- At Windows 100%, 150%, and 200% scaling, inspect small and maximized windows,
  large text, long profile names, tables, and charts for clipping. Verify setup
  scrolling keeps every field reachable and action buttons remain visible.
- With Windows Narrator, check profile selectors, numeric settings, validation
  links, result headers and cells, and best-result announcements. Verify status
  changes are discoverable; live announcements have not been verified.
- Inspect light, dark, and high-contrast themes. Confirm focus, errors, selected
  rows, and best results remain readable without relying on color alone.
- Start a large single-worker and multi-worker run, inspect elapsed/status
  feedback, request cancellation, and confirm a new run can start afterward.

The executable was rebuilt on 2026-10-08 with the GUI and tooltip changes and
passed its packaged smoke test. Manual validation and resulting fixes remain
outstanding.
