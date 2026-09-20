"""Compare every selected character with every selected monster."""

from dataclasses import replace

from .gui_service import (
    SIMULATION_SECTIONS,
    SimulationTables,
    TableColumn,
    TableData,
    run_simulations,
)


def run_roster_simulations(
    characters,
    monsters,
    settings,
    sections=SIMULATION_SECTIONS,
    progress_callback=None,
    is_cancelled=None,
):
    """Return combined tables for catalog items, preserving each pair's seed."""
    characters, monsters = tuple(characters), tuple(monsters)
    sections = tuple(dict.fromkeys(sections))
    if not characters or not monsters:
        raise ValueError("Select at least one character and one monster")
    if not sections or set(sections) - set(SIMULATION_SECTIONS):
        raise ValueError("Select supported simulation sections")
    total = len(characters) * len(monsters) * len(sections)
    columns, rows, notes = (
        {},
        {section: [] for section in sections},
        {section: [] for section in sections},
    )
    completed = 0
    for character in characters:
        for monster in monsters:
            label = f"{character.label} vs {monster.label}"

            def progress(count, _total, section):
                if progress_callback is not None and section != "complete":
                    progress_callback(completed + count, total, f"{label}: {section}")

            tables = run_simulations(
                character.value,
                monster.value,
                settings,
                sections,
                progress_callback=progress,
                is_cancelled=is_cancelled,
            )
            for section in sections:
                table = getattr(tables, section)
                # A global 'best' would compare different opponents and assumptions.
                columns[section] = (
                    TableColumn("Character profile"),
                    TableColumn("Monster profile"),
                    *(
                        replace(column, best="", chart=False)
                        for column in table.columns
                    ),
                )
                rows[section].extend(
                    (character.label, monster.label, *row) for row in table.rows
                )
                notes[section].append(f"{label}: {table.note}")
            completed += len(sections)
    if progress_callback is not None:
        progress_callback(total, total, "complete")
    return SimulationTables(
        **{
            section: TableData(
                columns[section],
                tuple(rows[section]),
                f"{len(characters)} characters × {len(monsters)} monsters; "
                f"{settings.trials:,} trials per scenario, seed {settings.seed}. "
                "No overall best across different opponents. Hover here for per-pair notes.",
                "\n".join(notes[section]),
            )
            for section in sections
        }
    )
