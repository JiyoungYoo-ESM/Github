from __future__ import annotations

import hashlib
import os
import re
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
from core.session import SessionContext, ensure_session_context

from core.common import (
    _DECISION_CACHE_PATH,
    _ORDER_REVIEW_LOGIC_VERSION,
    EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY,
    UPLOAD_COLUMN_GROUPS,
)
from core import kpi as kpi_mod, order_review as order_review_mod, transport as transport_mod

# upload_dataframe_score()의 행 개수 가산은 1,000행에서 캡되므로, 헤더 후보 판별용
# 미리보기는 이 값 이상만 읽으면 전체를 읽었을 때와 점수가 정확히 같다.
_HEADER_DETECTION_PREVIEW_ROWS = 1000


def _ensure_data_dir() -> None:
    os.makedirs(os.path.dirname(_DECISION_CACHE_PATH), exist_ok=True)


def normalize_party_name(name: object) -> str:
    s = str(name or "").strip().upper()
    s = re.sub(r"[^A-Z0-9]+", "", s)
    return s


def make_instance_key(row: pd.Series) -> str:
    sku = str(row.get("상품코드", row.get("SKU", ""))).strip()
    party = normalize_party_name(row.get("거래처명") or row.get("원본 거래처명") or row.get("브랜드") or "")
    invoice = str(row.get("Invoice 번호", row.get("Invoice No", row.get("INVOICE", "")))).strip()
    qty = str(int(float(row.get("수량", 0)))) if pd.notna(row.get("수량", None)) and str(row.get("수량", "")).strip() != "" else "0"
    note = str(row.get("Invoice 비고", row.get("원본값", row.get("비고", "")))).strip()
    h = hashlib.sha1(note.encode("utf-8")).hexdigest()[:8]
    return "::".join([sku, party, invoice, qty, h])


def make_pattern_key(row: pd.Series, keyword_list: list[str] | None = None) -> str:
    sku = str(row.get("상품코드", row.get("SKU", ""))).strip()
    party = normalize_party_name(row.get("거래처명") or row.get("원본 거래처명") or row.get("브랜드") or "")
    note = str(row.get("Invoice 비고", row.get("원본값", row.get("비고", "")))).upper()
    if keyword_list is None:
        keyword_list = ["GOODIE", "구디", "GOODY", "SAMPLE", "FOC", "무상"]
    matched = ";".join(k for k in keyword_list if k in note)
    amount_zero_flag = "1" if float(row.get("금액", row.get("입고가(KRW)", 0)) or 0) == 0 else "0"
    biz_purpose = str(row.get("거래유형", row.get("Biz Type", ""))).strip().upper()
    return "::".join([sku, party, matched or "-", amount_zero_flag, biz_purpose or "-"])


def load_exception_decisions() -> pd.DataFrame:
    _ensure_data_dir()
    if not os.path.exists(_DECISION_CACHE_PATH):
        cols = [
            "instance_key",
            "pattern_key",
            "SKU",
            "정규화 거래처명",
            "원본 거래처명",
            "Invoice 식별자",
            "수량",
            "금액",
            "통화",
            "Invoice 비고",
            "matched_keywords",
            "amount_zero_flag",
            "최초 exception_reason",
            "담당자 판단",
            "판단 사유",
            "판단일시",
        ]
        return pd.DataFrame(columns=cols)
    try:
        return pd.read_csv(_DECISION_CACHE_PATH, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame()


def save_exception_decisions(df: pd.DataFrame) -> None:
    _ensure_data_dir()
    df.to_csv(_DECISION_CACHE_PATH, index=False)


def upload_dataframe_score(df: pd.DataFrame, key: str | None = None) -> int:
    df = pd.DataFrame(df).copy()
    df.columns = [str(col) for col in df.columns]
    groups = [
        ["상품코드", "SKU", "품목코드", "itemcode"],
        ["상품명", "제품명", "품목명", "itemname"],
        ["브랜드", "브랜드명", "brand"],
        ["수량", "재고수량", "재고 수량", "가용수량", "가용 수량", "미입고수량"],
        ["금액", "환산금액", "출고금액", "EUR 금액"],
        ["출고일", "ETA", "입고예정일"],
    ]
    groups.extend(UPLOAD_COLUMN_GROUPS.get(key or "", []))
    score = 0
    for group in groups:
        if kpi_mod.find_column(df, group) is not None:
            score += 10
    score += min(len(df), 1_000) // 100
    return score


def dataframe_looks_like_html_document(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    column_text = " ".join(str(col) for col in df.columns[:3]).lower()
    if "<html" in column_text or "<table" in column_text or "schemas-microsoft-com:office" in column_text:
        return True
    sample_values = df.head(3).to_numpy().ravel()
    sample_text = " ".join(str(value) for value in sample_values[:10]).lower()
    return "<html" in sample_text or "<table" in sample_text or "schemas-microsoft-com:office" in sample_text


def bytes_look_like_html_excel(data: bytes) -> bool:
    sample = data[:4096].lstrip().lower()
    return (
        sample.startswith(b"<html")
        or b"<table" in sample
        or b"schemas-microsoft-com:office" in sample
        or b"excelworkbook" in sample
    )


def _store_shipping_read_debug(debug: dict, context: SessionContext | None = None) -> None:
    if debug.get("key") != "shipping":
        return
    if context is not None:
        context.shipping_read_debug = debug


def best_uploaded_dataframe(
    candidates: list[pd.DataFrame],
    key: str | None = None,
    context: SessionContext | None = None,
    debug: dict | None = None,
    read_method: str = "",
    selection_basis: str = "upload_dataframe_score",
    candidate_metadata: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    scored_candidates: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        if candidate is None:
            continue
        cleaned_candidate = clean_uploaded_dataframe(candidate, key=key)
        rejected = cleaned_candidate.empty or dataframe_looks_like_html_document(cleaned_candidate)
        score = upload_dataframe_score(cleaned_candidate, key) if not rejected else -1
        scored_candidates.append(
            {
                "index": idx,
                "raw": candidate,
                "cleaned": cleaned_candidate,
                "raw_shape": getattr(candidate, "shape", None),
                "cleaned_shape": getattr(cleaned_candidate, "shape", None),
                "score": score,
                "rejected": rejected,
            }
        )
    valid = [candidate for candidate in scored_candidates if not candidate["rejected"]]
    if not valid:
        return pd.DataFrame()
    selected = max(valid, key=lambda candidate: candidate["score"])
    if debug is not None:
        raw_df = selected["raw"]
        cleaned_df = selected["cleaned"]
        raw_qty_info = transport_mod._shipping_debug_qty_info(raw_df)
        debug.update(
            {
                "read_method": read_method,
                "selection_basis": selection_basis,
                "candidate_count": len(candidates),
                "candidate_shapes": [
                    {
                        **(
                            candidate_metadata[item["index"]]
                            if candidate_metadata and item["index"] < len(candidate_metadata)
                            else {}
                        ),
                        "index": item["index"],
                        "raw_shape": item["raw_shape"],
                        "cleaned_shape": item["cleaned_shape"],
                        "score": item["score"],
                        "rejected": item["rejected"],
                    }
                    for item in scored_candidates
                ],
                "selected_table_index": selected["index"],
                "selected_candidate_metadata": (candidate_metadata or [{}])[selected["index"]] if candidate_metadata and selected["index"] < len(candidate_metadata) else {},
                "selected_raw_shape": getattr(raw_df, "shape", None),
                "selected_cleaned_shape": getattr(cleaned_df, "shape", None),
                "selected_raw_columns": [str(col) for col in raw_df.columns],
                "selected_raw_column_tuples": [repr(col) for col in list(raw_df.columns)[:5]],
                "selected_raw_is_multiindex": isinstance(raw_df.columns, pd.MultiIndex),
                "selected_cleaned_columns": [str(col) for col in cleaned_df.columns],
                "selected_raw_preview": raw_df.head(5).astype(str).to_dict("records"),
                "selected_cleaned_preview": cleaned_df.head(5).astype(str).to_dict("records"),
                "selected_raw_qty_info": raw_qty_info,
            }
        )
        if key == "shipping":
            if context is not None:
                context.shipping_read_raw_df = raw_df.copy()
                context.shipping_read_cleaned_df = cleaned_df.copy()
    return selected["cleaned"]


class SimpleTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(" ".join("".join(self._current_cell).split()))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if any(str(cell).strip() for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            if self._current_table:
                self.tables.append(self._current_table)
            self._current_table = None


def lxml_html_table_candidates(data: bytes, errors: list[str] | None = None) -> list[pd.DataFrame]:
    """lxml C 확장을 직접 사용해 HTML 테이블을 파싱한다. pd.read_html보다 오버헤드가 적다."""
    try:
        import lxml.html  # type: ignore[import]
    except ImportError:
        return []
    try:
        root = lxml.html.fromstring(data)
    except Exception as exc:  # noqa: BLE001
        if errors is not None:
            errors.append(f"lxml.html.fromstring: {type(exc).__name__}: {exc}")
        return []
    candidates: list[pd.DataFrame] = []
    for table in root.findall(".//table"):
        rows: list[list[str]] = []
        for tr in table.findall(".//tr"):
            row = [" ".join("".join(cell.itertext()).split()) for cell in tr.findall("td") + tr.findall("th")]
            if any(row):
                rows.append(row)
        if len(rows) < 2:
            continue
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        for header_row in likely_header_rows(rows):
            header = [str(cell).strip() for cell in rows[header_row]]
            body = rows[header_row + 1:]
            if any(header):
                candidates.append(pd.DataFrame(body, columns=header))
        if len(rows) <= 10_000:
            candidates.append(pd.DataFrame(rows))
    return candidates


def html_table_candidates(data: bytes, errors: list[str] | None = None) -> list[pd.DataFrame]:
    candidates: list[pd.DataFrame] = []
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = data.decode(encoding)
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"HTML stdlib decode {encoding}: {type(exc).__name__}: {exc}")
            continue
        parser = SimpleTableParser()
        try:
            parser.feed(text)
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"HTML stdlib parse {encoding}: {type(exc).__name__}: {exc}")
            continue
        for table in parser.tables:
            width = max((len(row) for row in table), default=0)
            rows = [row + [""] * (width - len(row)) for row in table if row]
            if len(rows) < 2 or width == 0:
                continue
            for header_row in likely_header_rows(rows):
                header = [str(cell).strip() for cell in rows[header_row]]
                body = rows[header_row + 1:]
                if any(header):
                    candidates.append(pd.DataFrame(body, columns=header))
            if len(rows) <= 10_000:
                candidates.append(pd.DataFrame(rows))
        if candidates:
            break
    return candidates


def likely_header_rows(rows: list[list[str]], max_header_rows: int = 7) -> list[int]:
    scan_limit = min(max_header_rows, len(rows) - 1)
    if len(rows) <= 10_000:
        return list(range(scan_limit))

    scored_rows = []
    for idx in range(scan_limit):
        values = [str(cell).strip() for cell in rows[idx]]
        non_empty = [value for value in values if value]
        scored_rows.append((len(non_empty), len(set(non_empty)), -idx, idx))
    if not scored_rows:
        return []
    return [max(scored_rows)[3]]


def excel_dataframe_candidates(
    data: bytes | Path,
    engine: str,
    key: str | None = None,
    max_header_rows: int = 6,
    errors: list[str] | None = None,
    candidate_metadata: list[dict[str, object]] | None = None,
    debug: dict | None = None,
) -> list[pd.DataFrame]:
    candidates = []
    try:
        source = BytesIO(data) if isinstance(data, bytes) else data
        excel_file = pd.ExcelFile(source, engine=engine)
    except Exception as exc:  # noqa: BLE001
        if errors is not None:
            errors.append(f"{engine} open workbook: {type(exc).__name__}: {exc}")
        return candidates

    if debug is not None:
        debug["sheet_count"] = len(excel_file.sheet_names)
        debug["sheet_names"] = list(excel_file.sheet_names)
    sheet_names = excel_file.sheet_names[:1]
    if key in {"sales_history", "prod_list"} and sheet_names:
        sheet_name = sheet_names[0]
        try:
            candidate = pd.read_excel(excel_file, sheet_name=sheet_name, header=0)
            cleaned_candidate = clean_uploaded_dataframe(candidate, key=key)
            score = upload_dataframe_score(cleaned_candidate, key)
            if debug is not None:
                debug["fast_header0_score"] = score
                debug["fast_header0_shape"] = getattr(cleaned_candidate, "shape", None)
            if not cleaned_candidate.empty and not dataframe_looks_like_html_document(cleaned_candidate) and score >= 50:
                if candidate_metadata is not None:
                    candidate_metadata.append(
                        {
                            "index": 0,
                            "sheet_name": sheet_name,
                            "header_row": 0,
                            "shape": getattr(candidate, "shape", None),
                            "fast_path": True,
                        }
                    )
                return [cleaned_candidate]
            candidates.append(candidate)
            if candidate_metadata is not None:
                candidate_metadata.append(
                    {
                        "index": 0,
                        "sheet_name": sheet_name,
                        "header_row": 0,
                        "shape": getattr(candidate, "shape", None),
                        "fast_path": False,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"{engine} sheet={sheet_name} header=0 fast path: {type(exc).__name__}: {exc}")

    # 대용량 시트에서 헤더 후보(0~max_header_rows-1행)를 판별하려고 매번 시트 전체를
    # 다시 읽으면 파일 크기에 선형으로 비례해 시간이 늘어난다(실측: 30만행/12MB 1회
    # read_excel 33초 -> 179만행/97MB 파일을 6번 반복하면 20분 이상). upload_dataframe_score는
    # 컬럼명만 보고 행 개수는 1,000행에서 캡되므로(min(len(df), 1_000)), 헤더 후보 판별은
    # nrows로 제한한 미리보기로 채점해도 전체를 읽었을 때와 점수가 동일하다. 승자
    # header_row에 대해서만 시트 전체를 한 번 읽는다.
    header_row_scores: list[tuple[int, int, str]] = []
    for header_row in range(max_header_rows):
        for sheet_name in sheet_names:
            if key in {"sales_history", "prod_list"} and header_row == 0 and candidates:
                continue
            try:
                preview = pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row, nrows=_HEADER_DETECTION_PREVIEW_ROWS)
            except Exception as exc:  # noqa: BLE001
                if errors is not None:
                    errors.append(f"{engine} sheet={sheet_name} header={header_row} preview: {type(exc).__name__}: {exc}")
                continue
            cleaned_preview = clean_uploaded_dataframe(preview, key=key)
            rejected = cleaned_preview.empty or dataframe_looks_like_html_document(cleaned_preview)
            score = upload_dataframe_score(cleaned_preview, key) if not rejected else -1
            header_row_scores.append((score, header_row, sheet_name))

    if not header_row_scores:
        return candidates

    best_score = max(score for score, _, _ in header_row_scores)
    winning_rows = [
        (header_row, sheet_name) for score, header_row, sheet_name in header_row_scores if score == best_score
    ]

    for header_row, sheet_name in winning_rows:
        try:
            candidate = pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row)
            candidates.append(candidate)
            if candidate_metadata is not None:
                candidate_metadata.append(
                    {
                        "index": len(candidates) - 1,
                        "sheet_name": sheet_name,
                        "header_row": header_row,
                        "shape": getattr(candidate, "shape", None),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"{engine} sheet={sheet_name} header={header_row}: {type(exc).__name__}: {exc}")
            continue
    return candidates


def read_uploaded_file(uploaded_file, key: str | None = None, context: SessionContext | None = None) -> pd.DataFrame:
    """추후 CMS 엑셀 업로드 연결 시 공통으로 사용할 파일 로더."""
    suffix = Path(uploaded_file.name).suffix.lower()
    source = uploaded_file.get_source() if hasattr(uploaded_file, "get_source") else uploaded_file.getvalue()
    sample = uploaded_file.read_sample(4096) if hasattr(uploaded_file, "read_sample") else uploaded_file.getvalue()[:4096]
    errors: list[str] = []
    debug: dict | None = {
        "key": key,
        "file_name": uploaded_file.name,
        "suffix": suffix,
        "file_size_bytes": int(getattr(uploaded_file, "size", len(sample))),
        "looks_like_html_excel": bytes_look_like_html_excel(sample),
        "attempts": [],
    } if key == "shipping" else None
    if suffix == ".xlsx":
        candidate_metadata: list[dict[str, object]] = []
        candidates = excel_dataframe_candidates(source, engine="openpyxl", key=key, errors=errors, candidate_metadata=candidate_metadata, debug=debug)
        if debug is not None:
            debug["attempts"].append({"method": "read_excel/openpyxl", "candidate_count": len(candidates)})
        if candidates:
            result = best_uploaded_dataframe(candidates, key, context=context, debug=debug, read_method="read_excel/openpyxl", candidate_metadata=candidate_metadata)
            _store_shipping_read_debug(debug or {}, context)
            return result
        raise ValueError("파일을 읽지 못했습니다.\n" + "\n".join(errors))
    if suffix == ".xls":
        # CMS에서 .xls 확장자로 내려받아도 실제 내용은 HTML table 또는 TSV인 경우가 있다.
        # 진짜 구형 Excel -> HTML table -> 탭 구분 텍스트 순서로 안전하게 시도한다.
        if not bytes_look_like_html_excel(sample):
            candidate_metadata = []
            candidates = excel_dataframe_candidates(source, engine="xlrd", key=key, errors=errors, candidate_metadata=candidate_metadata, debug=debug)
            if debug is not None:
                debug["attempts"].append({"method": "read_excel/xlrd", "candidate_count": len(candidates)})
            if candidates:
                best = best_uploaded_dataframe(candidates, key, context=context, debug=debug, read_method="read_excel/xlrd", candidate_metadata=candidate_metadata)
                if not best.empty:
                    _store_shipping_read_debug(debug or {}, context)
                    return best
        # 1순위: lxml 직접 파싱 (C 확장, 타입 추론 없음 → 대용량 파일에서 가장 빠름)
        data = uploaded_file.getvalue()
        tables = lxml_html_table_candidates(data, errors=errors)
        if debug is not None:
            debug["attempts"].append({"method": "read_html/lxml_direct", "table_count": len(tables)})
        if tables:
            best = best_uploaded_dataframe(tables, key, context=context, debug=debug, read_method="read_html/lxml_direct", selection_basis="upload_dataframe_score among lxml table/header candidates")
            if not best.empty:
                _store_shipping_read_debug(debug or {}, context)
                return best
        # 2순위: pd.read_html + lxml + dtype=str (타입 추론 생략)
        try:
            tables = pd.read_html(BytesIO(data), dtype=str, flavor="lxml")
            if debug is not None:
                debug["attempts"].append({"method": "read_html/pandas_bytes_lxml", "table_count": len(tables)})
            if tables:
                best = best_uploaded_dataframe(tables, key, context=context, debug=debug, read_method="read_html/pandas_bytes_lxml", selection_basis="upload_dataframe_score among read_html tables")
                if not best.empty:
                    _store_shipping_read_debug(debug or {}, context)
                    return best
        except Exception as exc:  # noqa: BLE001
            errors.append(f"HTML bytes: {type(exc).__name__}: {exc}")
            if debug is not None:
                debug["attempts"].append({"method": "read_html/pandas_bytes_lxml", "error": f"{type(exc).__name__}: {exc}"})
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                tables = pd.read_html(StringIO(data.decode(encoding)), dtype=str, flavor="lxml")
                if debug is not None:
                    debug["attempts"].append({"method": f"read_html/pandas_string_lxml/{encoding}", "table_count": len(tables)})
                if tables:
                    best = best_uploaded_dataframe(tables, key, context=context, debug=debug, read_method=f"read_html/pandas_string_lxml/{encoding}", selection_basis="upload_dataframe_score among read_html tables")
                    if not best.empty:
                        _store_shipping_read_debug(debug or {}, context)
                        return best
            except Exception as exc:  # noqa: BLE001
                errors.append(f"HTML {encoding}: {type(exc).__name__}: {exc}")
                if debug is not None:
                    debug["attempts"].append({"method": f"read_html/pandas_string_lxml/{encoding}", "error": f"{type(exc).__name__}: {exc}"})
        # 3순위: stdlib HTMLParser (fallback)
        tables = html_table_candidates(data, errors=errors)
        if debug is not None:
            debug["attempts"].append({"method": "fallback/html_parser", "table_count": len(tables)})
        if tables:
            best = best_uploaded_dataframe(tables, key, context=context, debug=debug, read_method="fallback/html_parser", selection_basis="upload_dataframe_score among stdlib html table/header candidates")
            if not best.empty:
                _store_shipping_read_debug(debug or {})
                return best
        for encoding in ("utf-8-sig", "cp949", "euc-kr"):
            try:
                candidate = clean_uploaded_dataframe(pd.read_csv(BytesIO(data), sep="\t", encoding=encoding), key=key)
                if debug is not None:
                    debug["attempts"].append({"method": f"fallback/tsv/{encoding}", "shape": getattr(candidate, "shape", None)})
                if not candidate.empty and not dataframe_looks_like_html_document(candidate):
                    if debug is not None:
                        debug.update(
                            {
                                "read_method": f"fallback/tsv/{encoding}",
                                "selection_basis": "first non-empty TSV parse",
                                "candidate_count": 1,
                                "selected_table_index": 0,
                                "selected_raw_shape": getattr(candidate, "shape", None),
                                "selected_cleaned_shape": getattr(candidate, "shape", None),
                                "selected_raw_columns": [str(col) for col in candidate.columns],
                                "selected_raw_column_tuples": [repr(col) for col in list(candidate.columns)[:5]],
                                "selected_raw_is_multiindex": isinstance(candidate.columns, pd.MultiIndex),
                                "selected_cleaned_columns": [str(col) for col in candidate.columns],
                                "selected_raw_preview": candidate.head(5).astype(str).to_dict("records"),
                                "selected_cleaned_preview": candidate.head(5).astype(str).to_dict("records"),
                            }
                        )
                        if context is not None:
                            context.shipping_read_raw_df = candidate.copy()
                            context.shipping_read_cleaned_df = candidate.copy()
                        _store_shipping_read_debug(debug, context)
                    return candidate
            except Exception as exc:  # noqa: BLE001
                errors.append(f"TSV {encoding}: {type(exc).__name__}: {exc}")
                if debug is not None:
                    debug["attempts"].append({"method": f"fallback/tsv/{encoding}", "error": f"{type(exc).__name__}: {exc}"})
        raise ValueError("파일을 읽지 못했습니다.\n" + "\n".join(errors))
    data = uploaded_file.getvalue()
    if suffix == ".csv":
        try:
            candidate = clean_uploaded_dataframe(pd.read_csv(BytesIO(data), encoding="utf-8-sig"), key=key)
            if debug is not None:
                debug.update(
                    {
                        "read_method": "read_csv/utf-8-sig",
                        "selection_basis": "single CSV parse",
                        "candidate_count": 1,
                        "selected_table_index": 0,
                        "selected_raw_shape": getattr(candidate, "shape", None),
                        "selected_cleaned_shape": getattr(candidate, "shape", None),
                        "selected_raw_columns": [str(col) for col in candidate.columns],
                        "selected_raw_column_tuples": [repr(col) for col in list(candidate.columns)[:5]],
                        "selected_raw_is_multiindex": isinstance(candidate.columns, pd.MultiIndex),
                        "selected_cleaned_columns": [str(col) for col in candidate.columns],
                        "selected_raw_preview": candidate.head(5).astype(str).to_dict("records"),
                        "selected_cleaned_preview": candidate.head(5).astype(str).to_dict("records"),
                    }
                )
                if context is not None:
                    context.shipping_read_raw_df = candidate.copy()
                    context.shipping_read_cleaned_df = candidate.copy()
                _store_shipping_read_debug(debug, context)
            return candidate
        except UnicodeDecodeError:
            candidate = clean_uploaded_dataframe(pd.read_csv(BytesIO(data), encoding="cp949"), key=key)
            if debug is not None:
                debug.update(
                    {
                        "read_method": "read_csv/cp949",
                        "selection_basis": "single CSV parse",
                        "candidate_count": 1,
                        "selected_table_index": 0,
                        "selected_raw_shape": getattr(candidate, "shape", None),
                        "selected_cleaned_shape": getattr(candidate, "shape", None),
                        "selected_raw_columns": [str(col) for col in candidate.columns],
                        "selected_raw_column_tuples": [repr(col) for col in list(candidate.columns)[:5]],
                        "selected_raw_is_multiindex": isinstance(candidate.columns, pd.MultiIndex),
                        "selected_cleaned_columns": [str(col) for col in candidate.columns],
                        "selected_raw_preview": candidate.head(5).astype(str).to_dict("records"),
                        "selected_cleaned_preview": candidate.head(5).astype(str).to_dict("records"),
                    }
                )
                if context is not None:
                    context.shipping_read_raw_df = candidate.copy()
                    context.shipping_read_cleaned_df = candidate.copy()
                _store_shipping_read_debug(debug, context)
            return candidate
    raise ValueError("CSV 또는 Excel 파일만 업로드할 수 있습니다.")


def clean_uploaded_dataframe(df: pd.DataFrame, key: str | None = None) -> pd.DataFrame:
    """CMS 엑셀/HTML 엑셀에서 생기는 다단 헤더와 컬럼명 차이를 앱 표준 컬럼으로 정리한다."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        flattened = []
        for col in out.columns:
            parts = [str(part).strip() for part in col if str(part).strip() and not str(part).startswith("Unnamed")]
            flattened.append(parts[-1] if parts else "")
        out.columns = flattened
    else:
        out.columns = [str(col).strip() for col in out.columns]

    rename_map = {}
    unit_price_source_col = None
    normalized = {col: str(col).replace(" ", "").replace("\n", "") for col in out.columns}
    for col, compact in normalized.items():
        if compact in {"상품코드", "품목코드", "SKU"}:
            rename_map[col] = "상품코드"
        elif compact in {"상품명", "제품명", "품목명", "itemname", "productname"}:
            rename_map[col] = "상품명"
        elif compact == "바코드":
            rename_map[col] = "바코드"
        elif compact in {"브랜드", "브랜드명", "brand", "brandname"}:
            rename_map[col] = "브랜드"
        elif compact in {"재고수량", "현재재고"}:
            rename_map[col] = "재고수량"
        elif compact in {"Hold수량", "홀드수량"}:
            rename_map[col] = "Hold수량"
        elif compact in {"가용수량", "가용재고"}:
            rename_map[col] = "가용수량"
        elif compact.startswith("평균단가") or compact in {"EU입고단가", "입고단가"}:
            rename_map[col] = "EU 입고단가"
            unit_price_source_col = unit_price_source_col or col
        elif compact in {"판매수량(3개월내PA+CA)", "최근3개월판매수량"}:
            rename_map[col] = "최근 3개월 판매수량"
    if unit_price_source_col is not None:
        out["EU 입고단가 원본컬럼"] = str(unit_price_source_col)
        label_currency = kpi_mod.unit_price_currency_from_label(unit_price_source_col)
        if label_currency:
            out["EU 입고단가 통화"] = label_currency
    out = out.rename(columns=rename_map)

    for col in ["재고수량", "Hold수량", "가용수량", "최근 3개월 판매수량"]:
        if col in out.columns:
            out[col] = kpi_mod.to_number_series(out[col])
    if "EU 입고단가" in out.columns:
        if key == "eu_stock":
            out["EU 입고단가"] = kpi_mod.to_unit_price_number_series(out["EU 입고단가"])
            out["EU 입고단가 통화"] = EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY
        else:
            out["EU 입고단가"] = kpi_mod.to_number_series(out["EU 입고단가"])
    return out


def init_state(context: SessionContext | None = None) -> SessionContext:
    return ensure_session_context(context)


def go_to_tab(tab_name: str, context: SessionContext | None = None) -> SessionContext:
    context = ensure_session_context(context)
    context.active_tab = tab_name
    return context


def get_data_or_sample(key: str, sample_func, context: SessionContext | None = None) -> pd.DataFrame:
    """업로드 파일이 있으면 업로드 데이터를, 없으면 샘플 데이터를 반환한다.

    단, 하나라도 실제 업로드가 시작된 세션에서는 누락 파일을 샘플로 대체하지 않는다.
    샘플과 실데이터가 한 엑셀에 섞이면 모든 시트가 정상 추출처럼 보이는 위험이 있기 때문이다.
    """
    uploaded_data = ensure_session_context(context).uploaded_data
    if key in uploaded_data:
        return uploaded_data[key].copy()
    if any(df is not None for df in uploaded_data.values()):
        return pd.DataFrame()
    return sample_func().copy()


def get_order_review_data_or_empty(key: str, sample_func, context: SessionContext | None = None) -> pd.DataFrame:
    """발주 검토에서는 실제 업로드가 시작되면 누락 파일을 샘플 대신 빈 데이터로 처리한다."""
    uploaded_data = ensure_session_context(context).uploaded_data
    if any(df is not None for df in uploaded_data.values()):
        return uploaded_data.get(key, pd.DataFrame()).copy()
    return sample_func().copy()


def uploaded_data_signature(context: SessionContext | None = None) -> tuple:
    context = ensure_session_context(context)
    uploaded_data = context.uploaded_data
    uploaded_files = context.uploaded_files
    return tuple(
        sorted(
            (
                key,
                uploaded_files.get(key, ""),
                id(df),
                getattr(df, "shape", None),
            )
            for key, df in uploaded_data.items()
        )
    )


def order_review_settings_signature(settings: dict, excluded_only: bool = False, context: SessionContext | None = None) -> tuple:
    return (
        _ORDER_REVIEW_LOGIC_VERSION,
        bool(excluded_only),
        settings.get("base_date"),
        settings.get("safety_months"),
        tuple(settings.get("modes", [])),
        settings.get("include_inbound_po_in_coverage"),
        settings.get("include_hq_eu_in_order_coverage"),
        settings.get("entity_code"),
        tuple(sorted((settings.get("lead_times") or {}).items())),
        tuple(sorted((settings.get("lead_times_by_code") or {}).items())),
        tuple(sorted((settings.get("lead_time_overrides") or {}).items())),
        settings.get("lead_time_effective_date"),
        settings.get("min_monthly_sales_for_order_review"),
        settings.get("stock_adjustment_factor"),
        settings.get("eur_krw_rate"),
        settings.get("pa_ca_sales_column_override"),
        uploaded_data_signature(context),
    )


def cached_order_review_df(
    settings: dict,
    safety_months: float | None = None,
    excluded_only: bool = False,
    context: SessionContext | None = None,
) -> pd.DataFrame:
    context = ensure_session_context(context)
    cache = context.order_review_cache
    key = order_review_settings_signature(settings, excluded_only, context)
    if key not in cache:
        cache[key] = order_review_mod.order_review_df(settings, safety_months=safety_months, excluded_only=excluded_only, context=context)
    return cache[key].copy()


def sample_eu_stock() -> pd.DataFrame:
    # 재고금액은 sample_kpi_values()의 eu_stock_amount(11490M 원)와 일치하도록 설정
    return pd.DataFrame(
        [
            ["PURITO", "PURITO_CENTELLA_SERUM_60ML", "880900001001", "센텔라 세럼 60ml", 5200, 200, 4800, 8900, "해운", 3_400_000_000],
            ["ANUA", "ANUA_HEARTLEAF_TONER_250ML", "880900001002", "어성초 토너 250ml", 1600, 400, 3900, 4000, "해운", 600_000_000],
            ["COSRX", "COSRX_SNAIL_MUCIN_ESSENCE_100ML", "880900001003", "스네일 에센스 100ml", 2300, 200, 3200, 3000, "항공", 850_000_000],
            ["MEDICUBE", "MEDICUBE_AGE_R_AMP_30ML", "880900001004", "에이지알 앰플 30ml", 2100, 300, 3300, 3000, "해운", 810_000_000],
            ["BEAUTY OF JOSEON", "BOJ_GINSENG_SERUM_30ML", "880900001005", "진생 세럼 30ml", 3900, 300, 2900, 2400, "철송", 1_300_000_000],
            ["ANUA", "ANUA_HEARTLEAF_SUNCREAM_50ML", "880900001006", "어성초 선크림 50ml", 900, 150, 3500, 3300, "항공", 370_000_000],
            ["COSRX", "COSRX_VITAMIN_C_SERUM_23", "880900001007", "비타민 C 세럼 23", 1800, 250, 4100, 2600, "항공", 860_000_000],
            ["MEDICUBE", "MEDICUBE_COLLAGEN_MASK", "880900001008", "콜라겐 마스크", 2800, 100, 1800, 2100, "철송", 580_000_000],
            ["PURITO", "PURITO_OAT_IN_GEL_CREAM", "880900001009", "오트 인 젤 크림", 7200, 0, 2600, 500, "트럭", 2_180_000_000],
            ["BEAUTY OF JOSEON", "BOJ_RELIEF_SUN_50ML", "880900001010", "릴리프 선 50ml", 1500, 200, 3000, 3600, "해운", 540_000_000],
        ],
        columns=["브랜드", "상품코드", "바코드", "상품명", "재고수량", "Hold수량", "EU 입고단가", "최근 3개월 판매수량", "검토 운송수단", "재고금액"],
    )


def sample_hq_eu_stock() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["PURITO", "PURITO_CENTELLA_SERUM_60ML", "880900001001", "센텔라 세럼 60ml", 3200, 400, 4800],
            ["ANUA", "ANUA_HEARTLEAF_TONER_250ML", "880900001002", "어성초 토너 250ml", 4200, 600, 3900],
            ["COSRX", "COSRX_SNAIL_MUCIN_ESSENCE_100ML", "880900001003", "스네일 에센스 100ml", 1500, 300, 3200],
            ["MEDICUBE", "MEDICUBE_AGE_R_AMP_30ML", "880900001004", "에이지알 앰플 30ml", 1200, 300, 3300],
            ["BEAUTY OF JOSEON", "BOJ_GINSENG_SERUM_30ML", "880900001005", "진생 세럼 30ml", 900, 500, 2900],
            ["ANUA", "ANUA_HEARTLEAF_SUNCREAM_50ML", "880900001006", "어성초 선크림 50ml", 2500, 200, 3500],
            ["COSRX", "COSRX_VITAMIN_C_SERUM_23", "880900001007", "비타민 C 세럼 23", 1600, 100, 4100],
            ["MEDICUBE", "MEDICUBE_COLLAGEN_MASK", "880900001008", "콜라겐 마스크", 2000, 150, 1800],
            ["PURITO", "PURITO_OAT_IN_GEL_CREAM", "880900001009", "오트 인 젤 크림", 1500, 0, 2600],
            ["BEAUTY OF JOSEON", "BOJ_RELIEF_SUN_50ML", "880900001010", "릴리프 선 50ml", 2500, 300, 3000],
        ],
        columns=["브랜드", "상품코드", "바코드", "상품명", "재고수량", "Hold수량", "EU 입고단가"],
    )


def sample_sales_detail() -> pd.DataFrame:
    inv = sample_eu_stock()
    rows = []
    for _, row in inv.iterrows():
        base = int(row["최근 3개월 판매수량"])
        recent_factor = {
            "ANUA_HEARTLEAF_TONER_250ML": 1.85,
            "PURITO_OAT_IN_GEL_CREAM": 0.2,
            "COSRX_VITAMIN_C_SERUM_23": 0.45,
            "ANUA_HEARTLEAF_SUNCREAM_50ML": 1.6,
        }.get(row["상품코드"], 1.0)
        rows.append(
            [
                row["브랜드"],
                row["상품코드"],
                row["상품명"],
                base,
                max(int(base / 3 * recent_factor), 0),
                int(base * row["EU 입고단가"]),
            ]
        )
    return pd.DataFrame(rows, columns=["브랜드", "SKU", "상품명", "판매 기준기간 판매량", "최근 판매량", "매출"])


def sample_hq_to_eu_sales_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["PURITO", "PURITO_CENTELLA_SERUM_60ML", "센텔라 세럼 60ml", "2026-05-12", 840_000],
            ["ANUA", "ANUA_HEARTLEAF_TONER_250ML", "어성초 토너 250ml", "2026-05-12", 1_055_000],
            ["COSRX", "COSRX_SNAIL_MUCIN_ESSENCE_100ML", "스네일 에센스 100ml", "2026-05-12", 545_000],
            ["MEDICUBE", "MEDICUBE_AGE_R_AMP_30ML", "에이지알 앰플 30ml", "2026-05-12", 359_000],
            ["BEAUTY OF JOSEON", "BOJ_RELIEF_SUN_50ML", "릴리프 선 50ml", "2026-05-12", 245_000],
        ],
        columns=["브랜드", "SKU", "상품명", "출고일", "환산금액"],
    )


def sample_open_po() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["ANUA_HEARTLEAF_TONER_250ML", 1500],
            ["COSRX_SNAIL_MUCIN_ESSENCE_100ML", 800],
            ["MEDICUBE_AGE_R_AMP_30ML", 600],
            ["ANUA_HEARTLEAF_SUNCREAM_50ML", 1000],
            ["BOJ_RELIEF_SUN_50ML", 1800],
        ],
        columns=["SKU", "미입고수량"],
    )


def sample_shipping() -> pd.DataFrame:
    # 금액 컬럼은 EUR 기준. 합계 ≈52,259,800 EUR → ×1726.89 ≈ 90,247M KRW (검증 기준값에 근접)
    rows = [
        ["철송", "PURITO_CENTELLA_SERUM_60ML", "PURITO", "센텔라 세럼 60ml", 1200, 1200, "2026-03-22", 40, "2026-05-01", "안정", 200],
        ["항공", "COSRX_SNAIL_MUCIN_ESSENCE_100ML", "COSRX", "스네일 에센스 100ml", 850, 850, "2026-04-21", 14, "2026-05-05", "주의", 100],
        ["해운", "MEDICUBE_AGE_R_AMP_30ML", "MEDICUBE", "에이지알 앰플 30ml", 3200, 3200, "2026-02-05", 90, "2026-05-06", "안정", 200],
        ["철송", "COSRX_LOW_PH_CLEANSER_150ML", "COSRX", "약산성 클렌저 150ml", 900, 900, "2026-03-29", 40, "2026-05-08", "안정", 100],
        ["항공", "ANUA_HEARTLEAF_TONER_250ML", "ANUA", "어성초 토너 250ml", 2100, 2100, "2026-04-28", 14, "2026-05-12", "임박위험", 100],
        ["철송", "BOJ_GINSENG_SERUM_30ML", "BEAUTY OF JOSEON", "진생 세럼 30ml", 1450, 1450, "2026-04-04", 40, "2026-05-14", "안정", 100],
        ["해운", "ANUA_HEARTLEAF_TONER_250ML", "ANUA", "어성초 토너 250ml", 5600, 5600, "2026-02-16", 90, "2026-05-17", "입고 전 품절", 84_000],
        ["해운", "PURITO_CENTELLA_SERUM_60ML", "PURITO", "센텔라 세럼 60ml", 8900, 8900, "2026-02-18", 90, "2026-05-19", "안정", 195_800],
        ["해운", "PURITO_CENTELLA_SERUM_60ML", "PURITO", "센텔라 세럼 60ml", 5000, 4800, "2026-02-20", 90, "2026-05-20", "안정", 75_000],
        ["해운", "ANUA_HEARTLEAF_TONER_250ML", "ANUA", "어성초 토너 250ml", 4000, 3900, "2026-02-20", 90, "2026-05-20", "안정", 60_000],
        ["해운", "MEDICUBE_AGE_R_AMP_30ML", "MEDICUBE", "에이지알 앰플 30ml", 3000, 3300, "2026-02-20", 90, "2026-05-20", "안정", 30_000],
        ["철송", "PURITO_OAT_IN_GEL_CREAM", "PURITO", "오트 인 젤 크림", 1000, 1000, "2026-04-12", 40, "2026-05-22", "안정", 100],
        ["항공", "ANUA_HEARTLEAF_SUNCREAM_50ML", "ANUA", "어성초 선크림 50ml", 2300, 2300, "2026-05-12", 14, "2026-05-26", "주의", 100],
        ["철송", "BOJ_GINSENG_SERUM_30ML", "BEAUTY OF JOSEON", "진생 세럼 30ml", 3200, 3200, "2026-04-18", 40, "2026-05-28", "안정", 200],
        ["해운", "ANUA_HEARTLEAF_TONER_250ML", "ANUA", "어성초 토너 250ml", 185050, 185050, "2026-03-02", 90, "2026-05-31", "입고 전 품절", 51_814_000],
        ["해운", "BOJ_RELIEF_SUN_50ML", "BEAUTY OF JOSEON", "릴리프 선 50ml", 1800, 1800, "2026-03-10", 90, "2026-06-08", "주의", 100],
    ]
    df = pd.DataFrame(rows, columns=["운송수단", "SKU", "브랜드", "상품명", "수량", "입고가(KRW)", "출고일", "리드타임", "ETA", "위험도", "금액"])
    return df


def sample_past_sales() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["PURITO", "PURITO_CENTELLA_SERUM_60ML", "센텔라 세럼 60ml", "7월", "2026-07-01", "2026-04-02", "90일", "여름 진정 케어 수요 증가"],
            ["ANUA", "ANUA_HEARTLEAF_TONER_250ML", "어성초 토너 250ml", "6월", "2026-06-01", "2026-03-03", "90일", "초여름 베스트 SKU"],
            ["COSRX", "COSRX_LOW_PH_CLEANSER_150ML", "약산성 클렌저 150ml", "8월", "2026-08-01", "2026-05-03", "90일", "휴가철 클렌징 수요"],
            ["BEAUTY OF JOSEON", "BOJ_GINSENG_SERUM_30ML", "진생 세럼 30ml", "11월", "2026-11-01", "2026-08-03", "90일", "블랙프라이데이 사전 확보"],
        ],
        columns=["브랜드", "SKU", "상품명", "성수기 월", "시즌 시작 예상일", "추천 발주 마감일", "적용 리드타임", "비고"],
    )


def sample_sales_history() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "출고일",
            "상품코드",
            "상품명",
            "브랜드",
            "국가",
            "수량",
            "환산금액",
            "거래처",
            "Site",
            "창고",
        ]
    )


def sample_prod_list() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "prod_cd",
            "prod_nm",
            "brand_nm",
            "class1_nm",
            "class2_nm",
            "bar_code",
            "prod_gbn",
            "use_yn",
        ]
    )


_SAMPLE_FUNCS = {
    "eu_stock": sample_eu_stock,
    "hq_eu_stock": sample_hq_eu_stock,
    "sales_detail": sample_sales_detail,
    "hq_to_eu_sales_detail": sample_hq_to_eu_sales_detail,
    "open_po": sample_open_po,
    "shipping": sample_shipping,
    "past_sales": sample_past_sales,
    "sales_history": sample_sales_history,
    "prod_list": sample_prod_list,
}

