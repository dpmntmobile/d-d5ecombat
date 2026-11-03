"""Launch the optional PySide6 desktop interface."""

import multiprocessing
import sys


def run_smoke_test():
    """Verify packaged resources and parallel simulation without opening a window."""
    from . import __version__
    from .profile_catalog import discover_character_catalog, discover_monster_catalog
    from .profile_schema import load_profile_schema

    if __version__ == "0+unknown":
        raise RuntimeError("application version metadata is required")
    for profile_kind in ("native-character", "monster", "roll20-character"):
        load_profile_schema(profile_kind)
    characters = discover_character_catalog()
    monsters = discover_monster_catalog()
    issues = characters.issues + monsters.issues
    if issues:
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise RuntimeError(f"packaged profile validation failed: {details}")
    if not characters.items or not monsters.items:
        raise RuntimeError("packaged character and monster profiles are required")
    from .gui_service import SimulationSettings, run_simulations
    from .roster_service import run_roster_simulations

    # Exercise frozen multiprocessing: imports alone cannot catch spawn failures.
    sections = ("attacks", "turns")
    roster = (characters.items[:1], monsters.items[:1])
    serial = run_roster_simulations(*roster, SimulationSettings(trials=2), sections)
    parallel = run_roster_simulations(*roster, SimulationSettings(trials=2, workers=2), sections)
    single_profile = run_simulations(
        characters.items[0].value, monsters.items[0].value,
        SimulationSettings(trials=2, workers=2), sections,
    )
    for section in sections:
        if getattr(serial, section).rows != getattr(parallel, section).rows:
            raise RuntimeError("packaged parallel results differ from serial results")
        if tuple(row[2:] for row in getattr(serial, section).rows) != getattr(single_profile, section).rows:
            raise RuntimeError("packaged shared-pool results differ from serial results")
    from .party_combat import MonsterGroup, PartyBattle, simulate_party_battle

    battle = PartyBattle(tuple(c.value for c in characters.items[:2]),
                         tuple(MonsterGroup(m.value, 2) for m in monsters.items[:2]))
    result = simulate_party_battle(battle, trials=2, seed=42)
    if result != simulate_party_battle(battle, trials=2, seed=42):
        raise RuntimeError("packaged party results are not repeatable")
    from importlib.util import find_spec

    if find_spec("PySide6") is not None:
        from .party_smoke import run_party_smoke_test

        run_party_smoke_test()
    return 0


def main(argv=None):
    multiprocessing.freeze_support()
    arguments = list(sys.argv if argv is None else argv)
    if "--smoke-test" in arguments[1:]:
        return run_smoke_test()
    try:
        from .desktop_gui import launch_gui
    except ModuleNotFoundError as error:
        if error.name == "PySide6":
            print(
                "PySide6 is required for the desktop GUI. "
                'Install it with: python -m pip install -e ".[gui]"',
                file=sys.stderr,
            )
            return 1
        raise
    return launch_gui(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
