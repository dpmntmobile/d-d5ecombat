from pathlib import Path
import runpy
from PyInstaller.utils.hooks import copy_metadata


packaging_dir = Path(SPECPATH)
project_dir = packaging_dir.parent
version_tools = runpy.run_path(str(project_dir / "scripts" / "project_version.py"))
app_version = version_tools["read_project_version"](project_dir)
version_tuple = version_tools["windows_version_tuple"](app_version)
version_info_path = project_dir / "build" / "generated_version_info.txt"
version_info_path.parent.mkdir(parents=True, exist_ok=True)
version_template = (packaging_dir / "version_info.template.txt").read_text(
    encoding="utf-8"
)
version_info_path.write_text(
    version_template.replace("@APP_VERSION@", app_version).replace(
        "@VERSION_TUPLE@", repr(version_tuple)
    ),
    encoding="utf-8",
)

analysis = Analysis(
    [str(packaging_dir / "gui_entry.py")],
    pathex=[str(project_dir / "src")],
    binaries=[],
    datas=copy_metadata("dnd5ecombat") + [
        (str(project_dir / "assets"), "assets"),
        (str(project_dir / "characters"), "characters"),
        (str(project_dir / "monsters"), "monsters"),
        (
            str(project_dir / "src" / "dnd5ecombat" / "schemas"),
            "dnd5ecombat/schemas",
        ),
    ],
    hiddenimports=[
        "dnd5ecombat.application_service",
        "dnd5ecombat.character_models",
        "dnd5ecombat.character_profiles",
        "dnd5ecombat.character_persistence",
        "dnd5ecombat.roll20_import",
        "dnd5ecombat.desktop_gui",
        "dnd5ecombat.dice_parser",
        "dnd5ecombat.gui_service",
        "dnd5ecombat.monster_editor",
        "dnd5ecombat.monster_profiles",
        "dnd5ecombat.profile_catalog",
        "dnd5ecombat.profile_schema",
        "dnd5ecombat.profile_validation",
        "dnd5ecombat.scenario_factory",
        "dnd5ecombat.simulation_core",
        "dnd5ecombat.storage_paths",
        "dnd5ecombat.duel_simulation",
        "dnd5ecombat.attack_simulation",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Dnd5eCombatSimulator",
    icon=str(project_dir / "assets" / "app-icon.ico"),
    version=str(version_info_path),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
