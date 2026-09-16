"""Public command-line interface boundary."""

from .cli_api import *  # noqa: F403
from .cli_workflows import main as _workflow_main


def main(argv=None):
    return _workflow_main(argv)
