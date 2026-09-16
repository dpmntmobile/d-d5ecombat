"""Primary launcher for the D&D 5e combat simulator.

The full command-line interface lives in :mod:`cli`.  Public imports are kept
here for backward compatibility with existing users and tests.
"""

from .cli import *  # noqa: F403
from .cli import main as _cli_main


def main(argv=None):
    return _cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
