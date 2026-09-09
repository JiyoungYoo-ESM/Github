"""The ``core`` package: pure SCM calculation/reporting logic.

Submodules import each other explicitly and module-qualified
(e.g. ``from core import transport as transport_mod`` then
``transport_mod.get_shipping(...)``). The package no longer re-exports a flat
namespace and no longer mutates module globals — import the specific submodule
you need (``from core.transport import get_shipping``) and patch that module
directly in tests (``monkeypatch.setattr(core.transport, "get_shipping", fn)``).

Importing the package eagerly loads every submodule so that ``core.<name>``
attribute access works after a bare ``import core``.
"""

from __future__ import annotations

from importlib import import_module

_MODULE_NAMES = [
    "core.common",
    "core.currency",
    "core.versions",
    "core.session",
    "core.loaders",
    "core.preprocess",
    "core.inventory",
    "core.sales",
    "core.transport",
    "core.inbound",
    "core.order_review_data",
    "core.order_review",
    "core.order_review_report",
    "core.eta",
    "core.kpi",
    "core.export_excel_util",
    "core.export_excel_sheets",
    "core.export_excel_order_sheet",
    "core.export_excel_report",
    "core.export_excel_debug",
    "core.export_excel",
    "core.validation",
]

for _name in _MODULE_NAMES:
    import_module(_name)
