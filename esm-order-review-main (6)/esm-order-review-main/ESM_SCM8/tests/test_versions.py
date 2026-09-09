from core import versions
from core.versions import (
    EXPORT_VERSION_HISTORY,
    LOGIC_VERSION_HISTORY,
    ORDER_REVIEW_EXPORT_VERSION,
    ORDER_REVIEW_LOGIC_VERSION,
)


def test_order_review_versions_are_documented():
    assert ORDER_REVIEW_LOGIC_VERSION == 30
    assert ORDER_REVIEW_EXPORT_VERSION == 61
    assert ORDER_REVIEW_LOGIC_VERSION in LOGIC_VERSION_HISTORY
    assert ORDER_REVIEW_EXPORT_VERSION in EXPORT_VERSION_HISTORY


def test_core_exports_current_order_review_versions():
    assert versions.ORDER_REVIEW_LOGIC_VERSION == ORDER_REVIEW_LOGIC_VERSION
    assert versions.ORDER_REVIEW_EXPORT_VERSION == ORDER_REVIEW_EXPORT_VERSION

