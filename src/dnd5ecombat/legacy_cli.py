"""Backward-compatible import path for the former monolithic console module."""

from .cli_api import *  # noqa: F403
from .cli_workflows import main


if __name__ == "__main__":
    raise SystemExit(main())
