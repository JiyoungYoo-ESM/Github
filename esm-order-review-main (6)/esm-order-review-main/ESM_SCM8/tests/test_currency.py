from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from core.currency import (
    InvalidDecimalError,
    InvalidExchangeRateError,
    UnsupportedCurrencyError,
    convert_amount,
    convert_invoice,
    convert_invoices,
)


def _invoice(
    *,
    comp_cd: str = "CO000001",
    biz_curr: str = "2",
    xrate: str | None = "1",
    invc_atot: str = "10",
    invc_vtot: str | None = "0",
    details: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "invc_no": "INV-TEST",
        "invc_dt": "2026-08-01",
        "comp_cd": comp_cd,
        "biz_curr": biz_curr,
        "xrate": xrate,
        "invc_atot": invc_atot,
        "invc_vtot": invc_vtot,
        "details": details
        if details is not None
        else [
            {
                "invc_seq": 1,
                "prod_cd": "SKU-1",
                "invc_qty": 1,
                "invc_ucost": invc_atot,
                "invc_amt": invc_atot,
            }
        ],
    }


def test_general_company_usd_multiplies_and_rounds_to_two_digits() -> None:
    assert convert_amount("10.005", "1", "CO000001", 2) == Decimal("10.01")

    result = convert_invoice(_invoice(invc_atot="10.005"))

    assert result["conversion_operation"] == "multiply"
    assert result["currency_code"] == "USD"
    assert result["target_digit"] == 2
    assert result["converted_invc_atot"] == Decimal("10.01")
    assert result["converted_line_total"] == Decimal("10.01")


def test_co000016_eur_uses_division_path() -> None:
    result = convert_invoice(
        _invoice(comp_cd="CO000016", biz_curr="6", xrate="1.2", invc_atot="12")
    )

    assert result["conversion_operation"] == "divide"
    assert result["currency_code"] == "EUR"
    assert result["converted_invc_atot"] == Decimal("10.00")


def test_co000013_usd_uses_division_path() -> None:
    result = convert_invoice(
        _invoice(comp_cd="CO000013", biz_curr="2", xrate="4", invc_atot="10")
    )

    assert result["conversion_operation"] == "divide"
    assert result["converted_invc_atot"] == Decimal("2.50")


def test_krw_with_normal_unit_rate_is_unchanged_and_has_zero_digits() -> None:
    result = convert_invoice(
        _invoice(biz_curr="1", xrate="1.00", invc_atot="1234")
    )

    assert result["currency_code"] == "KRW"
    assert result["target_digit"] == 0
    assert result["converted_invc_atot"] == Decimal("1234")
    assert result["converted_line_total"] == Decimal("1234")


@pytest.mark.parametrize("comp_cd", ["CO000001", "CO000016"])
def test_zero_exchange_rate_is_an_error_for_both_directions(comp_cd: str) -> None:
    with pytest.raises(InvalidExchangeRateError, match="0보다 커야"):
        convert_amount("10", "0", comp_cd, 2)


@pytest.mark.parametrize("xrate", [None, "", "   "])
def test_missing_or_blank_exchange_rate_is_an_error(xrate: str | None) -> None:
    with pytest.raises(InvalidExchangeRateError):
        convert_amount("10", xrate, "CO000001", 2)


def test_line_sum_and_header_conversion_report_rounding_difference() -> None:
    result = convert_invoice(
        _invoice(
            invc_atot="0.008",
            details=[
                {
                    "invc_seq": 1,
                    "prod_cd": "SKU-1",
                    "invc_qty": 1,
                    "invc_ucost": "0.004",
                    "invc_amt": "0.004",
                },
                {
                    "invc_seq": 2,
                    "prod_cd": "SKU-2",
                    "invc_qty": 1,
                    "invc_ucost": "0.004",
                    "invc_amt": "0.004",
                },
            ],
        )
    )

    assert result["converted_line_total"] == Decimal("0.00")
    assert result["converted_invc_atot"] == Decimal("0.01")
    assert result["rounding_diff"] == Decimal("-0.01")


def test_empty_and_missing_details_are_handled_explicitly() -> None:
    empty_result = convert_invoice(_invoice(invc_atot="12", details=[]))
    missing_invoice = _invoice(invc_atot="12")
    del missing_invoice["details"]
    missing_result = convert_invoice(missing_invoice)

    for result in (empty_result, missing_result):
        assert result["details"] == []
        assert result["converted_line_total"] == Decimal("0.00")
        assert result["rounding_diff"] == Decimal("-12.00")
        assert result["conversion_warnings"]


@pytest.mark.parametrize(
    ("biz_curr", "currency_code"),
    [("1", "KRW"), ("17", "VND")],
)
def test_zero_digit_currencies_do_not_accumulate_fractional_residue(
    biz_curr: str,
    currency_code: str,
) -> None:
    result = convert_invoice(
        _invoice(
            biz_curr=biz_curr,
            invc_atot="1.47",
            details=[
                {
                    "invc_seq": sequence,
                    "prod_cd": f"SKU-{sequence}",
                    "invc_qty": 1,
                    "invc_ucost": "0.49",
                    "invc_amt": "0.49",
                }
                for sequence in range(1, 4)
            ],
        )
    )

    assert result["currency_code"] == currency_code
    assert result["target_digit"] == 0
    assert [line["converted_invc_amt"] for line in result["details"]] == [
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    ]
    assert result["converted_line_total"] == Decimal("0")
    assert result["converted_invc_atot"] == Decimal("1")
    assert result["rounding_diff"] == Decimal("-1")


def test_decimal_parse_failures_and_float_inputs_are_not_silently_coerced() -> None:
    for amount in (None, "", "not-a-number", 1.25):
        with pytest.raises(InvalidDecimalError):
            convert_amount(amount, "1", "CO000001", 2)  # type: ignore[arg-type]


def test_optional_amounts_are_not_filled_with_zero() -> None:
    invoice = _invoice(invc_vtot=None)
    invoice["details"][0]["invc_ucost"] = ""

    result = convert_invoice(invoice)

    assert result["converted_invc_vtot"] is None
    assert result["details"][0]["converted_invc_ucost"] is None
    assert len(result["conversion_warnings"]) == 2


def test_unknown_biz_currency_has_no_default_digit_fallback() -> None:
    with pytest.raises(UnsupportedCurrencyError, match="999"):
        convert_invoice(_invoice(biz_curr="999"))


def test_all_invoices_for_one_pi_are_converted_without_mutating_input() -> None:
    invoices = [
        _invoice(invc_atot="10"),
        _invoice(comp_cd="CO000013", biz_curr="6", xrate="2", invc_atot="8"),
    ]
    invoices[0]["invc_no"] = "INV-1"
    invoices[1]["invc_no"] = "INV-2"
    original = deepcopy(invoices)

    converted = convert_invoices(invoices)

    assert [invoice["invc_no"] for invoice in converted] == ["INV-1", "INV-2"]
    assert [invoice["converted_invc_atot"] for invoice in converted] == [
        Decimal("10.00"),
        Decimal("4.00"),
    ]
    assert invoices == original
