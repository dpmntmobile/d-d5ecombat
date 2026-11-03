"""Offscreen party-dialog checks for source and frozen Windows builds."""


def run_party_smoke_test():
    import os
    import json
    from pathlib import Path
    from tempfile import TemporaryDirectory

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from .party_dialog import PartyBattleDialog
    from .party_combat import load_battle, save_battle, save_battle_results

    app = QApplication.instance() or QApplication([])
    dialog = PartyBattleDialog()

    def require(condition, message):
        if not condition:
            raise RuntimeError(f"packaged party smoke test: {message}")

    def finish_worker():
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        dialog.worker.finished.connect(loop.quit)
        timer.start(30000)
        loop.exec()
        timer.stop()
        require(not dialog.worker.isRunning(), "worker timed out")
        app.processEvents()

    try:
        require(len(dialog.characters) >= 2 and len(dialog.monsters) >= 2,
                "multiple bundled profiles are required")
        dialog.character_counts[0].setValue(1)
        dialog.character_counts[1].setValue(1)
        dialog.monster_counts[0].setValue(2)
        dialog.monster_counts[1].setValue(1)
        chars, groups = dialog.selection()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "battle.json"
            save_battle(path, [c.source for c in chars],
                        [(m.source, count) for m, count in groups])
            dialog.loaded_battle = load_battle(path)
            dialog.update_composition()
            require("Loaded battle" in dialog.composition.text(), "loaded summary missing")
            dialog.trials.setValue(2)
            dialog.start_battle()
            finish_worker()
            require(dialog.result_report is not None, dialog.output.toPlainText())
            require(dialog.export_button.isEnabled(), "export not enabled")
            require("Party wins:" in dialog.output.toPlainText(), "results missing")
            export = Path(directory) / "results.json"
            save_battle_results(dialog.result_report, export)
            require(json.loads(export.read_text(encoding="utf-8"))["trials"] == 2,
                    "export round trip failed")
        dialog.monster_counts[0].setValue(3)
        require(dialog.loaded_battle is None, "catalog selection did not replace loaded battle")
        dialog.trials.setValue(1000000)
        dialog.start_battle()
        dialog.reject()
        finish_worker()
        require(dialog.result_report is None, "cancelled run retained results")
        require("cancelled" in dialog.output.toPlainText().lower(), "cancel status missing")
    finally:
        if dialog.worker and dialog.worker.isRunning():
            dialog.cancel()
            dialog.worker.wait(10000)
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
