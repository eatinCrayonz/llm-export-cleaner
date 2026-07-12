"""Desktop entry point: frozen-runtime Tcl/Tk setup, then the UI app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    runtime = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ.setdefault("TCL_LIBRARY", str(runtime / "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", str(runtime / "_tk_data"))

from llm_export_cleaner.ui.app import CleanerApp, main  # noqa: E402,F401


if __name__ == "__main__":
    main()
