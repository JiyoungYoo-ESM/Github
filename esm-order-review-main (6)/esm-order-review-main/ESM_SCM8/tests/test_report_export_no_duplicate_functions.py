from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path


REPORT_EXPORT_MODULE = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "services"
    / "report_template_export.py"
)


def test_report_export_has_no_duplicate_top_level_function_names() -> None:
    """Prevent Python's last-definition-wins behavior from hiding report code."""

    module = ast.parse(REPORT_EXPORT_MODULE.read_text(encoding="utf-8"))
    names = [
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)

    assert duplicates == [], (
        "Duplicate top-level report-export functions silently override earlier "
        f"implementations: {', '.join(duplicates)}"
    )
