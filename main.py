from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from live_captions.config import load_settings
from live_captions.ui import CaptionsWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Live Captions")
    app.setOrganizationName("Local")
    app.setStyle("Fusion")
    app.setFont(QFont("Sans Serif", 10))

    try:
        settings = load_settings()
    except RuntimeError as exc:
        QMessageBox.critical(None, "Configuration required", str(exc))
        return 1

    window = CaptionsWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
