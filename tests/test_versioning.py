import runpy
import unittest
from importlib.metadata import version
from pathlib import Path

import dnd5ecombat


PROJECT_DIR = Path(__file__).resolve().parents[1]


class ProjectVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.version_tools = runpy.run_path(
            str(PROJECT_DIR / "scripts" / "project_version.py")
        )

    def test_pyproject_is_the_authoritative_installed_version(self):
        project_version = self.version_tools["read_project_version"](PROJECT_DIR)

        self.assertEqual(project_version, version("dnd5ecombat"))
        self.assertEqual(project_version, dnd5ecombat.__version__)

    def test_windows_version_tuple_is_derived_from_project_version(self):
        convert = self.version_tools["windows_version_tuple"]

        self.assertEqual(convert("1.2.3"), (1, 2, 3, 0))
        self.assertEqual(convert("1.2.3.4"), (1, 2, 3, 4))
        self.assertEqual(convert("1.2.3rc1"), (1, 2, 3, 0))

    def test_windows_version_tuple_rejects_unsupported_versions(self):
        convert = self.version_tools["windows_version_tuple"]

        with self.assertRaisesRegex(ValueError, "unsupported Windows version"):
            convert("1.two.3")


if __name__ == "__main__":
    unittest.main()
