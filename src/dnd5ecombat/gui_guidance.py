"""Actionable desktop errors with explicit, locally controlled navigation."""

from html import escape
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QTextBrowser, QVBoxLayout


class GuidanceDialog(QDialog):
    """Display escaped error text and only application-supplied links."""

    def __init__(self, title, message, *, files=(), actions=(), navigate=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 400)
        self._files = tuple(files)
        self._actions = dict(actions)
        self._navigate = navigate
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        parts = [f"<p>{escape(message).replace(chr(10), '<br>')}</p>"]
        for index, path in enumerate(self._files):
            parts.append(f'<p><a href="file:{index}">Open {escape(str(path))}</a></p>')
        for key, label in actions:
            parts.append(f'<p><a href="action:{escape(key, quote=True)}">{escape(label)}</a></p>')
        self.browser.setHtml("".join(parts))
        self.browser.anchorClicked.connect(self._activate)
        layout.addWidget(self.browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _activate(self, url):
        if url.scheme() == "file":
            try:
                index = int(url.path())
            except ValueError:
                return
            if not 0 <= index < len(self._files):
                return
            path = Path(self._files[index]).resolve()
            if not path.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                QMessageBox.warning(self, "Could not open file", f"Open this file manually:\n{path}")
        elif url.scheme() == "action" and url.path() in self._actions and self._navigate:
            self.accept()
            self._navigate(url.path())
