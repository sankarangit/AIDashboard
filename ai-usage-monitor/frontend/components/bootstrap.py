"""Shared Streamlit layout. Pages call `open_page` before any other Streamlit command."""

from __future__ import annotations

import sys
from pathlib import Path


def open_page(file: str) -> None:
    frontend = Path(file).resolve().parent
    if frontend.name == "pages":
        frontend = frontend.parent
    if str(frontend) not in sys.path:
        sys.path.insert(0, str(frontend))
