"""D&D 5e combat simulation package."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("dnd5ecombat")
except PackageNotFoundError:
    __version__ = "0+unknown"
