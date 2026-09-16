"""Launch the optional PySide6 desktop interface."""

import multiprocessing
import sys


def run_smoke_test():
    """Verify packaged resources and profile loading without opening a window."""
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
