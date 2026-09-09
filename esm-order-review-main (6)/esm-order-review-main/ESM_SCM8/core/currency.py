"""Pure Decimal-based conversion helpers for CMS invoice amounts.

This module deliberately contains no HTTP or FastAPI dependencies.  Callers
fetch CMS invoices separately and pass either one invoice to
``convert_invoice`` or the complete response array to ``convert_invoices``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from types import MappingProxyType
from typing import TypeAlias


DecimalInput: TypeAlias = Decimal | str | int | None


# CMS 온라인 판매 리포트의 법인별 기준통화 로직을 따른다. EU/SKO 법인은
# 원통화금액을 xrate로 나누고, 그 밖의 법인은 xrate를 곱한다.
DIVIDE_BY_XRATE_COMPANIES = frozenset({"CO000013", "CO000016"})

# biz_curr 숫자 코드는 CMS BASE_DB.dbo.TB_CODE(gbn_cd='C005') 기준이다.
CMS_CURRENCY_CODE_BY_BIZ_CURR: Mapping[str, str] = MappingProxyType(
    {
        "1": "KRW",
        "2": "USD",
        "6": "EUR",
        "7": "GBP",
        "8": "SGD",
        "9": "CAD",
        "12": "MYR",
        "13": "RUB",
        "15": "AUD",
        "16": "MXN",
        "17": "VND",
        "18": "AED",
    }
)

# 통화별 소수 자릿수 역시 TB_CODE(gbn_cd='C005')의 num_val 기준이다.
# JPY는 현재 전달받은 biz_curr 숫자 매핑에는 없지만, 0자리 통화의 공용 환산에도
# 같은 반올림 규칙을 사용할 수 있도록 자릿수 표에는 명시한다.
CMS_CURRENCY_DIGITS: Mapping[str, int] = MappingProxyType(
    {
        "KRW": 0,
        "USD": 2,
        "EUR": 2,
        "GBP": 2,
        "SGD": 2,
        "CAD": 2,
        "MYR": 2,
        "RUB": 2,
        "AUD": 2,
        "MXN": 2,
        "VND": 0,
        "AED": 2,
        "JPY": 0,
    }
)


class CurrencyConversionError(ValueError):
    """Base class for explicit CMS currency conversion failures."""


class InvalidDecimalError(CurrencyConversionError):
    """Raised when a CMS decimal string is absent or malformed."""


class InvalidExchangeRateError(CurrencyConversionError):
    """Raised when xrate is absent, malformed, zero, or negative."""


class UnsupportedCurrencyError(CurrencyConversionError):
    """Raised when biz_curr has no approved CMS currency mapping."""


class InvalidInvoiceError(CurrencyConversionError):
    """Raised when an invoice does not have a calculable structure."""


def _parse_decimal(value: DecimalInput, *, field_name: str) -> Decimal:
    if value is None:
        raise InvalidDecimalError(f"{field_name} 값이 없습니다.")
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidDecimalError(
            f"{field_name} 값은 float가 아닌 Decimal, 숫자 문자열 또는 int여야 합니다."
        )

    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            raise InvalidDecimalError(f"{field_name} 값이 비어 있습니다.")
    else:
        raw_value = value

    try:
        parsed = Decimal(raw_value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise InvalidDecimalError(f"{field_name} 값을 Decimal로 해석할 수 없습니다: {value!r}") from error
    if not parsed.is_finite():
        raise InvalidDecimalError(f"{field_name} 값은 유한한 숫자여야 합니다: {value!r}")
    return parsed


def _target_quantum(target_digit: int) -> Decimal:
    if isinstance(target_digit, bool) or not isinstance(target_digit, int) or target_digit < 0:
        raise CurrencyConversionError("target_digit은 0 이상의 정수여야 합니다.")
    return Decimal(1).scaleb(-target_digit)


def _quantize(value: Decimal, *, target_digit: int, field_name: str) -> Decimal:
    try:
        return value.quantize(_target_quantum(target_digit), rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise CurrencyConversionError(f"{field_name} 값을 대상 통화 자릿수로 반올림할 수 없습니다.") from error


def _validated_company_code(comp_cd: object) -> str:
    if not isinstance(comp_cd, str) or not comp_cd.strip():
        raise InvalidInvoiceError("comp_cd가 없어 환산 방향을 결정할 수 없습니다.")
    return comp_cd.strip().upper()


def _validated_exchange_rate(xrate: DecimalInput) -> Decimal:
    try:
        rate = _parse_decimal(xrate, field_name="xrate")
    except InvalidDecimalError as error:
        raise InvalidExchangeRateError(str(error)) from error
    if rate <= 0:
        raise InvalidExchangeRateError("xrate는 0보다 커야 합니다.")
    return rate


def convert_amount(
    amount: DecimalInput,
    xrate: DecimalInput,
    comp_cd: str,
    target_digit: int,
) -> Decimal:
    """Convert one amount with the CMS entity rule and ROUND_HALF_UP.

    ``CO000013`` and ``CO000016`` divide by ``xrate``; every other valid
    company code multiplies by it.  A missing or non-positive exchange rate is
    always an error, including in the multiplication branch and for KRW.
    """

    amount_decimal = _parse_decimal(amount, field_name="amount")
    rate_decimal = _validated_exchange_rate(xrate)
    company_code = _validated_company_code(comp_cd)
    quantum = _target_quantum(target_digit)

    # Leave enough guard digits for division before the one authoritative
    # quantize operation.  Decimal arithmetic remains isolated from float.
    precision = max(
        28,
        len(amount_decimal.as_tuple().digits)
        + len(rate_decimal.as_tuple().digits)
        + target_digit
        + 16,
    )
    with localcontext() as context:
        context.prec = precision
        if company_code in DIVIDE_BY_XRATE_COMPANIES:
            converted = amount_decimal / rate_decimal
        else:
            converted = amount_decimal * rate_decimal
        try:
            return converted.quantize(quantum, rounding=ROUND_HALF_UP)
        except InvalidOperation as error:
            raise CurrencyConversionError("환산 결과를 대상 통화 자릿수로 반올림할 수 없습니다.") from error


def _currency_spec(biz_curr: object) -> tuple[str, int, str]:
    if biz_curr is None:
        raise UnsupportedCurrencyError("biz_curr 값이 없습니다.")
    numeric_code = str(biz_curr).strip()
    if not numeric_code:
        raise UnsupportedCurrencyError("biz_curr 값이 비어 있습니다.")
    currency_code = CMS_CURRENCY_CODE_BY_BIZ_CURR.get(numeric_code)
    if currency_code is None:
        raise UnsupportedCurrencyError(f"지원하지 않는 CMS biz_curr 코드입니다: {numeric_code}")
    return currency_code, CMS_CURRENCY_DIGITS[currency_code], numeric_code


def _optional_converted_amount(
    value: object,
    *,
    field_name: str,
    xrate: DecimalInput,
    comp_cd: str,
    target_digit: int,
    warnings: list[str],
) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        warnings.append(f"{field_name} 값이 없어 해당 금액은 환산하지 않았습니다.")
        return None
    return convert_amount(value, xrate, comp_cd, target_digit)  # type: ignore[arg-type]


def convert_invoice(invoice_dict: Mapping[str, object]) -> dict[str, object]:
    """Convert one CMS invoice without mutating its input mapping.

    Line ``invc_amt`` values are converted and rounded first, then summed into
    ``converted_line_total``.  ``converted_invc_atot`` is calculated once at
    header level.  ``rounding_diff`` is always ``line total - header total`` so
    callers can select either total without this function mixing the levels.
    """

    if not isinstance(invoice_dict, Mapping):
        raise InvalidInvoiceError("invoice_dict는 매핑(dict)이어야 합니다.")

    currency_code, target_digit, biz_curr = _currency_spec(invoice_dict.get("biz_curr"))
    comp_cd = _validated_company_code(invoice_dict.get("comp_cd"))
    xrate = invoice_dict.get("xrate")
    # Validate once even when details is empty and optional totals are absent.
    _validated_exchange_rate(xrate)  # type: ignore[arg-type]

    converted_header_total = convert_amount(
        invoice_dict.get("invc_atot"),  # type: ignore[arg-type]
        xrate,  # type: ignore[arg-type]
        comp_cd,
        target_digit,
    )
    warnings: list[str] = []
    converted_header_vat = _optional_converted_amount(
        invoice_dict.get("invc_vtot"),
        field_name="invc_vtot",
        xrate=xrate,  # type: ignore[arg-type]
        comp_cd=comp_cd,
        target_digit=target_digit,
        warnings=warnings,
    )

    if "details" not in invoice_dict:
        details: Sequence[object] = ()
        warnings.append("details 키가 없어 라인 합계를 0으로 계산했습니다.")
    else:
        raw_details = invoice_dict.get("details")
        if raw_details is None:
            details = ()
            warnings.append("details 값이 null이어서 라인 합계를 0으로 계산했습니다.")
        elif isinstance(raw_details, Sequence) and not isinstance(raw_details, (str, bytes, bytearray)):
            details = raw_details
            if not details:
                warnings.append("details가 비어 있어 라인 합계를 0으로 계산했습니다.")
        else:
            raise InvalidInvoiceError("details는 배열이어야 합니다.")

    converted_details: list[dict[str, object]] = []
    line_amounts: list[Decimal] = []
    for index, raw_detail in enumerate(details):
        if not isinstance(raw_detail, Mapping):
            raise InvalidInvoiceError(f"details[{index}]는 매핑(dict)이어야 합니다.")
        detail = dict(raw_detail)
        converted_amount = convert_amount(
            raw_detail.get("invc_amt"),  # type: ignore[arg-type]
            xrate,  # type: ignore[arg-type]
            comp_cd,
            target_digit,
        )
        detail["converted_invc_amt"] = converted_amount
        detail["converted_invc_ucost"] = _optional_converted_amount(
            raw_detail.get("invc_ucost"),
            field_name=f"details[{index}].invc_ucost",
            xrate=xrate,  # type: ignore[arg-type]
            comp_cd=comp_cd,
            target_digit=target_digit,
            warnings=warnings,
        )
        converted_details.append(detail)
        line_amounts.append(converted_amount)

    converted_line_total = _quantize(
        sum(line_amounts, start=Decimal(0)),
        target_digit=target_digit,
        field_name="converted_line_total",
    )
    rounding_diff = _quantize(
        converted_line_total - converted_header_total,
        target_digit=target_digit,
        field_name="rounding_diff",
    )

    result = dict(invoice_dict)
    result.update(
        {
            "biz_curr": biz_curr,
            "currency_code": currency_code,
            "target_digit": target_digit,
            "conversion_operation": (
                "divide" if comp_cd in DIVIDE_BY_XRATE_COMPANIES else "multiply"
            ),
            "converted_invc_atot": converted_header_total,
            "converted_invc_vtot": converted_header_vat,
            "converted_line_total": converted_line_total,
            "rounding_diff": rounding_diff,
            "conversion_warnings": warnings,
            "details": converted_details,
        }
    )
    return result


def convert_invoices(invoices: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Convert every invoice in a PI lookup response, preserving array order."""

    if isinstance(invoices, Mapping):
        raise InvalidInvoiceError("인보이스 응답은 단일 dict가 아닌 배열이어야 합니다.")
    return [convert_invoice(invoice) for invoice in invoices]


__all__ = [
    "CMS_CURRENCY_CODE_BY_BIZ_CURR",
    "CMS_CURRENCY_DIGITS",
    "CurrencyConversionError",
    "DIVIDE_BY_XRATE_COMPANIES",
    "InvalidDecimalError",
    "InvalidExchangeRateError",
    "InvalidInvoiceError",
    "UnsupportedCurrencyError",
    "convert_amount",
    "convert_invoice",
    "convert_invoices",
]
