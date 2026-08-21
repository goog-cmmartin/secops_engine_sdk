"""SecOps Desktop Application Launcher."""

import os
import sys

from PySide6.QtWidgets import QApplication

# Ensure secops-lean is on pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from adapters.google_secops import GoogleSecOpsAdapter
from clients.desktop.main_window import SecOpsMainWindow
from engine import SecOpsEngine


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Google SecOps Lean Client")

    adapter = GoogleSecOpsAdapter()
    engine = SecOpsEngine(adapter)

    window = SecOpsMainWindow(engine)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
