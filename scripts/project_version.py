"""Read the authoritative project version from pyproject.toml."""

import re
from pathlib import Path


def read_project_version(project_directory=None):
    project_directory = Path(project_directory or Path(__file__).resolve().parents[1])
    pyproject = project_directory / "pyproject.toml"
    match = re.search(
        r'^version\s*=\s*"([^"]+)"\s*$',
        pyproject.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(f"project version not found in {pyproject}")
    return match.group(1)


def windows_version_tuple(project_version):
    release = project_version.split("+", 1)[0].split("-", 1)[0]
    match = re.fullmatch(
        r"(\d+(?:\.\d+){0,3})(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?",
        release,
    )
    if match is None:
        raise ValueError(f"unsupported Windows version: {project_version}")
    release = match.group(1)
    try:
        parts = tuple(int(part) for part in release.split("."))
    except ValueError as error:
        raise ValueError(f"unsupported Windows version: {project_version}") from error
    if not 1 <= len(parts) <= 4:
        raise ValueError(f"unsupported Windows version: {project_version}")
    return parts + (0,) * (4 - len(parts))


if __name__ == "__main__":
    print(read_project_version())
