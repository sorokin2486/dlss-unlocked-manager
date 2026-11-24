"""Double-click launcher for the DLSS Unlocked manager window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dlss_manager.ui.app import run_gui  # noqa: E402

run_gui()
