"""Compile check plus formatter behavior used by the dashboard."""

import py_compile
import sys
from pathlib import Path


def test_formatters_use_na_for_missing_values():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "frontend"))
    from components.formatters import fmt_int, fmt_money

    assert fmt_money(None) == "N/A"
    assert fmt_int(None) == "N/A"
    assert fmt_money(1.5) == "$1.50"


def test_pages_compile():
    root = Path(__file__).resolve().parents[1] / "frontend"
    for path in root.rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
