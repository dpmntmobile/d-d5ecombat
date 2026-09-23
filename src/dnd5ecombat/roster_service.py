"""Compare every selected character with every selected monster."""

from dataclasses import replace
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import multiprocessing

from .result_export import result_metadata
from .process_execution import process_worker_limit

from .gui_service import (
    SIMULATION_SECTIONS,
    SimulationTables,
    SimulationSettings,
    SimulationCancelled,
    TableColumn,
    TableData,
    run_simulations,
)


_roster_cancel_event = None


def _initialize_roster_worker(cancel_event):
    global _roster_cancel_event
    _roster_cancel_event = cancel_event


def _run_roster_job(build, monster, settings, section):
    # Parallelism belongs to the roster pool; never create nested process pools.
    tables = run_simulations(
        build, monster, settings, (section,),
        is_cancelled=_roster_cancel_event.is_set,
    )
    return getattr(tables, section)


def _parallel_roster_tables(characters, monsters, settings, sections, progress, cancelled):
    jobs = iter(
        (ci, mi, section)
        for ci in range(len(characters))
        for mi in range(len(monsters))
        for section in sections
    )
    total = len(characters) * len(monsters) * len(sections)
    worker_count = min(process_worker_limit(settings.workers), total)
    context = multiprocessing.get_context("spawn")
    cancel_event = context.Event()
    worker_settings = replace(settings, workers=1)
    results = {}

    def check_cancelled():
        if cancelled is not None and cancelled():
            raise SimulationCancelled("Simulation cancelled")

    check_cancelled()
    if progress is not None:
        progress(0, total, f"roster using up to {worker_count} workers")
    check_cancelled()
    with ProcessPoolExecutor(
        max_workers=worker_count, mp_context=context,
        initializer=_initialize_roster_worker, initargs=(cancel_event,),
    ) as executor:
        pending = {}

        def submit_next():
            job = next(jobs, None)
            if job is None:
                return
            ci, mi, section = job
            future = executor.submit(
                _run_roster_job, characters[ci].value, monsters[mi].value,
                worker_settings, section,
            )
            pending[future] = job

        try:
            for _ in range(worker_count):
                submit_next()
            while pending:
                check_cancelled()
                done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                for future in done:
                    job = pending.pop(future)
                    results[job] = future.result()
                    check_cancelled()
                    if progress is not None and len(results) < total:
                        progress(len(results), total, "remaining roster comparisons")
                    check_cancelled()
                    submit_next()
            return results
        finally:
            # Running jobs observe this between trials; queued jobs are discarded.
            cancel_event.set()
            for future in pending:
                future.cancel()


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
    if not isinstance(settings, SimulationSettings):
        raise TypeError("settings must be SimulationSettings")
    if not characters or not monsters:
        raise ValueError("Select at least one character and one monster")
    if not sections or set(sections) - set(SIMULATION_SECTIONS):
        raise ValueError("Select supported simulation sections")
    total = len(characters) * len(monsters) * len(sections)
    parallel = (
        _parallel_roster_tables(characters, monsters, settings, sections, progress_callback, is_cancelled)
        if settings.workers > 1 and total > 1 else None
    )
    columns, rows, notes = (
        {},
        {section: [] for section in sections},
        {section: [] for section in sections},
    )
    completed = 0
    for ci, character in enumerate(characters):
        for mi, monster in enumerate(monsters):
            label = f"{character.label} vs {monster.label}"

            def progress(count, _total, section):
                if progress_callback is not None and section != "complete":
                    progress_callback(completed + count, total, f"{label}: {section}")

            tables = SimulationTables(**{
                section: parallel[ci, mi, section] for section in sections
            }) if parallel is not None else run_simulations(
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
    metadata = result_metadata(
        settings,
        ((item.label, item.value) for item in characters),
        ((item.label, item.value) for item in monsters),
        sections,
    )
    return SimulationTables(
        **{
            section: TableData(
                columns[section],
                tuple(rows[section]),
                f"{len(characters)} characters × {len(monsters)} monsters; "
                f"{settings.trials:,} trials per scenario, seed {settings.seed}. "
                "No overall best across different opponents. Hover here for per-pair notes.",
                "\n".join(notes[section]),
                metadata=metadata,
            )
            for section in sections
        }
    )
