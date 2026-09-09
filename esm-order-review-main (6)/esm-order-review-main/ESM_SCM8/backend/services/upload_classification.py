"""Upload role normalization, workbook classification, and parsed-data caching."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re

import pandas as pd

from core.common import DATA_SPECS, PROJECT_ROOT, UPLOAD_COLUMN_GROUPS
from core.loaders import read_uploaded_file, upload_dataframe_score
from core.session import SessionContext

from backend.services.category_corrections import read_category_correction_upload
from backend.services.upload_models import SavedUpload, uploaded_file_adapter


UPLOAD_DATAFRAME_CACHE_LIMIT = 4
PARSED_UPLOAD_DISK_CACHE_LIMIT = 8
PARSED_UPLOAD_DISK_CACHE_KEYS = {"sales_history", "prod_list"}
PARSED_UPLOAD_DISK_CACHE_DIR = PROJECT_ROOT / "backend" / "storage" / "parsed_upload_cache"
_UPLOAD_DATAFRAME_CACHE: OrderedDict[tuple[str, str], pd.DataFrame] = OrderedDict()
UPLOAD_KEYS = (
    "eu_stock",
    "hq_eu_stock",
    "sales_detail",
    "hq_to_eu_sales_detail",
    "open_po",
    "shipping",
    "past_sales",
    "sales_history",
    "prod_list",
    "category_correction",
)

ROLE_TO_UPLOAD_KEY = {
    "eu_stock": "eu_stock",
    "hq_eu_stock": "hq_eu_stock",
    "sales_detail": "sales_detail",
    "hq_to_eu_sales_detail": "hq_to_eu_sales_detail",
    "shipping": "shipping",
    "inbound": "open_po",
    "open_po": "open_po",
    "past_sales": "past_sales",
    "sales_history": "sales_history",
    "prod_list": "prod_list",
    "category_correction": "category_correction",
}
ALLOWED_UPLOAD_ROLES = tuple(sorted(ROLE_TO_UPLOAD_KEY))
UPLOAD_KEY_TO_RESPONSE_ROLE = {
    "eu_stock": "eu_stock",
    "hq_eu_stock": "hq_eu_stock",
    "sales_detail": "sales_detail",
    "hq_to_eu_sales_detail": "hq_to_eu_sales_detail",
    "open_po": "inbound",
    "shipping": "shipping",
    "past_sales": "past_sales",
    "sales_history": "sales_history",
    "prod_list": "prod_list",
    "category_correction": "category_correction",
}
CLASSIFICATION_PREVIEW_KEYS = {
    "eu_stock",
    "hq_eu_stock",
    "sales_detail",
    "hq_to_eu_sales_detail",
    "open_po",
    "shipping",
    "sales_history",
    "prod_list",
}

FILENAME_HINTS = {
    "eu_stock": ("eu_stock", "local_stock", "stock", "inventory", "cms", "eu재고", "현지재고"),
    "hq_eu_stock": ("hq_eu_stock", "hq_stock", "warehouse", "hq", "본사재고", "창고재고"),
    "sales_detail": ("sales_detail", "sales", "b2b", "판매", "매출"),
    "hq_to_eu_sales_detail": ("hq_to_eu", "hq_sales", "sellout", "본사판매", "본사출고"),
    "open_po": ("open_po", "openpo", "po", "purchase_order", "미입고", "발주"),
    "shipping": ("shipping", "shipment", "transport", "eta", "inbound", "운송", "배송", "해상", "입고예정"),
    "past_sales": ("past_sales", "history", "historical", "과거판매"),
    "sales_history": ("sales_history", "saleshistory", "long_sales", "history", "판매이력", "판매내역", "장기판매"),
    "prod_list": ("prod_list", "product_list", "productmaster", "master", "상품목록", "상품마스터", "prod"),
}
PREVIEW_FILENAME_HINTS = {
    "eu_stock": ("eu현지재고", "현지재고", "local_stock", "eu_stock"),
    "hq_eu_stock": ("본사eu창고재고", "본사재고", "창고재고", "hq_stock", "hq_eu_stock"),
    "sales_detail": ("eu현지판매내역상세", "판매내역상세", "판매상세", "sales_detail"),
    "hq_to_eu_sales_detail": ("본사eu출고내역", "본사→eu", "본사->eu", "본사출고", "hq_to_eu"),
    "shipping": ("해상컨테이너상세내역", "컨테이너상세", "해상", "shipping", "shipment"),
    "open_po": ("미입고현황", "미입고", "open_po", "openpo"),
    "sales_history": ("sales_history", "saleshistory", "판매이력", "판매내역", "장기판매"),
    "prod_list": ("prod_list", "product_list", "상품목록", "상품마스터", "prod"),
}

COLUMN_HINTS = {
    "eu_stock": ("재고수량", "hold수량", "가용수량", "입고단가", "바코드"),
    "hq_eu_stock": ("재고수량", "hold수량", "가용수량", "본사"),
    "sales_detail": ("매출", "판매", "b2b"),
    "hq_to_eu_sales_detail": ("출고", "환산금액", "출고금액"),
    "open_po": ("미입고", "po"),
    "shipping": ("운송수단", "eta", "출고일", "입고가"),
    "past_sales": ("과거", "정산"),
    "sales_history": ("출고일", "판매수량", "판매금액", "Site", "창고"),
    "prod_list": ("prod_cd", "class1_nm", "class2_nm", "기능구분"),
}

REQUIRED_COLUMN_ALIASES = {
    "출고일": ["출고일", "출고 일자", "일자", "date", "Date"],
    "상품코드": ["상품코드", "SKU", "품목코드", "itemcode", "prod_cd"],
    "상품명": ["상품명", "품목명", "itemname", "productname", "prod_nm"],
    "브랜드": ["브랜드", "브랜드명", "brand", "brandname", "brand_nm"],
    "판매수량": ["판매수량", "수량", "판매 수량", "qty", "quantity"],
    "판매금액": ["판매금액", "환산금액", "금액", "매출", "amount"],
    "상품명_마스터": ["상품명_마스터", "prod_nm", "상품명", "상품명마스터"],
    "브랜드_마스터": ["브랜드_마스터", "brand_nm", "브랜드", "브랜드마스터"],
    "기능구분1": ["기능구분1", "class1_nm"],
    "기능구분2": ["기능구분2", "class2_nm"],
    "SKU": ["SKU", "상품코드", "품목코드", "itemcode", "Item Code"],
    "상품코드": ["상품코드", "SKU", "품목코드", "itemcode", "Item Code"],
    "재고수량": ["재고수량", "현재고", "현재 재고", "수량", "stock", "qty"],
    "Hold수량": ["Hold수량", "Hold 수량", "홀드수량", "보류수량", "hold"],
    "EU 입고단가": ["EU 입고단가", "입고단가", "평균단가", "단가", "unit price"],
    "판매 기준기간 판매량": ["판매 기준기간 판매량", "최근 3개월 판매수량", "판매수량", "수량", "판매량"],
    "최근 판매량": ["최근 판매량", "최근 3개월 판매수량", "판매수량", "수량", "판매량"],
    "매출": ["매출", "판매금액", "금액", "환산금액", "매출액"],
    "환산금액": ["환산금액", "출고금액", "금액", "매출"],
    "출고일": ["출고일", "출고 일자", "일자", "date"],
    "미입고수량": ["미입고수량", "미입고 수량", "미입고", "잔량", "수량"],
    "운송수단": ["운송수단", "배송수단", "mode", "Invoice 비고", "INVOICE 비고", "Invoice비고"],
}

def filename_hint_score(filename: str, key: str) -> int:
    lowered = filename.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", filename.lower())
    return 50 if any(hint in lowered or hint in normalized for hint in FILENAME_HINTS.get(key, ())) else 0


def normalize_filename_for_preview(filename: str) -> str:
    stem = Path(filename).stem.lower()
    return re.sub(r"[\s._()\\/\-\[\]]+", "", stem)


def preview_filename_score(filename: str, key: str) -> int:
    normalized = normalize_filename_for_preview(filename)
    score = filename_hint_score(filename, key)
    for hint in PREVIEW_FILENAME_HINTS.get(key, ()):
        normalized_hint = normalize_filename_for_preview(hint)
        if normalized_hint and normalized_hint in normalized:
            score += 300
    return score


def required_column_score(df: pd.DataFrame, key: str) -> int:
    required_columns = DATA_SPECS.get(key, {}).get("required_columns", [])
    if not required_columns:
        return 0

    matches = sum(1 for column in required_columns if required_column_matched(df, key, str(column)))
    complete_bonus = 100 if matches == len(required_columns) else 0
    return matches * 25 + complete_bonus


def column_hint_score(df: pd.DataFrame, key: str) -> int:
    columns_text = " ".join(str(column).lower() for column in df.columns)
    return sum(40 for hint in COLUMN_HINTS.get(key, ()) if hint.lower() in columns_text)


def first_existing_column(df: pd.DataFrame | None, names: tuple[str, ...]) -> str | None:
    if df is None:
        return None
    normalized_to_column = {normalized_column_name(column): str(column) for column in pd.DataFrame(df).columns}
    for name in names:
        column = normalized_to_column.get(normalized_column_name(name))
        if column is not None:
            return column
    return None


def dominant_text_value(df: pd.DataFrame | None, column_names: tuple[str, ...]) -> tuple[str, float] | None:
    column = first_existing_column(df, column_names)
    if column is None or df is None:
        return None
    values = pd.DataFrame(df)[column].dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return None
    counts = values.str.upper().value_counts()
    value = str(counts.index[0])
    ratio = float(counts.iloc[0] / len(values))
    return value, ratio


def non_empty_ratio(df: pd.DataFrame | None, column_names: tuple[str, ...]) -> float | None:
    column = first_existing_column(df, column_names)
    if column is None or df is None or len(df) == 0:
        return None
    values = pd.DataFrame(df)[column].fillna("").astype(str).str.strip()
    return float((values != "").mean())


def business_rule_score(df: pd.DataFrame | None, key: str) -> int:
    site = dominant_text_value(df, ("Site",))
    if site is not None:
        dominant_site, ratio = site
        if ratio >= 0.8:
            if key == "sales_detail" and dominant_site == "EU":
                return 500
            if key == "hq_to_eu_sales_detail" and dominant_site == "KR":
                return 500
            if key == "sales_detail" and dominant_site == "KR":
                return -350
            if key == "hq_to_eu_sales_detail" and dominant_site == "EU":
                return -350

    fr_date_ratio = non_empty_ratio(df, ("FR Date",))
    if fr_date_ratio is not None:
        if key == "eu_stock":
            return 450 if fr_date_ratio >= 0.5 else -350
        if key == "hq_eu_stock":
            return 450 if fr_date_ratio < 0.5 else -350

    return 0


def normalize_upload_role(role: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", role.strip().lower()).strip("_")
    if normalized not in ROLE_TO_UPLOAD_KEY:
        allowed = ", ".join(ALLOWED_UPLOAD_ROLES)
        raise ValueError(f"지원하지 않는 파일 role입니다: '{role}'. 허용 role: {allowed}")
    return normalized


def upload_key_for_role(role: str) -> str:
    return ROLE_TO_UPLOAD_KEY[normalize_upload_role(role)]


def cached_uploaded_dataframe(upload: SavedUpload, key: str, context: SessionContext | None = None) -> pd.DataFrame:
    digest = upload.sha256()
    cache_key = (key, digest)
    cached = _UPLOAD_DATAFRAME_CACHE.get(cache_key)
    if cached is not None:
        _UPLOAD_DATAFRAME_CACHE.move_to_end(cache_key)
        return cached.copy(deep=False)

    disk_cache_path = PARSED_UPLOAD_DISK_CACHE_DIR / key / f"{digest}.pkl"
    if key in PARSED_UPLOAD_DISK_CACHE_KEYS and disk_cache_path.exists():
        try:
            df = pd.read_pickle(disk_cache_path)
            _UPLOAD_DATAFRAME_CACHE[cache_key] = df
            _UPLOAD_DATAFRAME_CACHE.move_to_end(cache_key)
            while len(_UPLOAD_DATAFRAME_CACHE) > UPLOAD_DATAFRAME_CACHE_LIMIT:
                _UPLOAD_DATAFRAME_CACHE.popitem(last=False)
            return df.copy(deep=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[upload cache skipped] {disk_cache_path.name}: {exc}", flush=True)

    adapter = uploaded_file_adapter(upload)
    df = pd.DataFrame(read_uploaded_file(adapter, key=key, context=context))
    if key in PARSED_UPLOAD_DISK_CACHE_KEYS and not df.empty:
        try:
            disk_cache_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_pickle(disk_cache_path)
            cache_files = sorted(disk_cache_path.parent.glob("*.pkl"), key=lambda path: path.stat().st_mtime, reverse=True)
            for old_cache_path in cache_files[PARSED_UPLOAD_DISK_CACHE_LIMIT:]:
                old_cache_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[upload cache write skipped] {disk_cache_path.name}: {exc}", flush=True)
    _UPLOAD_DATAFRAME_CACHE[cache_key] = df
    _UPLOAD_DATAFRAME_CACHE.move_to_end(cache_key)
    while len(_UPLOAD_DATAFRAME_CACHE) > UPLOAD_DATAFRAME_CACHE_LIMIT:
        _UPLOAD_DATAFRAME_CACHE.popitem(last=False)
    return df.copy(deep=False)


def response_role_for_upload_key(key: str, explicit_role: str | None = None) -> str:
    if explicit_role:
        return normalize_upload_role(explicit_role)
    return UPLOAD_KEY_TO_RESPONSE_ROLE.get(key, key)


def file_mapping_from_classifications(classifications: list[dict[str, object]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in classifications:
        role = str(item.get("role") or response_role_for_upload_key(str(item["key"])))
        mapping[role] = str(item["original_name"])
    return mapping


def score_upload_candidates(upload: SavedUpload, context: SessionContext | None = None) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []

    for key in UPLOAD_KEYS:
        adapter = uploaded_file_adapter(upload)
        try:
            df = read_uploaded_file(adapter, key=key, context=context)
        except Exception:
            continue

        score = (
            upload_dataframe_score(df, key=key)
            + required_column_score(df, key)
            + column_hint_score(df, key)
            + filename_hint_score(upload.original_name, key)
            + business_rule_score(df, key)
        )
        candidates.append({"key": key, "df": df, "score": score})

    if not candidates:
        raise ValueError(f"Could not classify uploaded file: {upload.original_name}")

    return sorted(candidates, key=lambda item: int(item["score"]), reverse=True)


def score_upload_candidates_for_preview(upload: SavedUpload, context: SessionContext | None = None) -> list[dict[str, object]]:
    try:
        adapter = uploaded_file_adapter(upload)
        df = pd.DataFrame(read_uploaded_file(adapter, key=None, context=context))
    except Exception:
        df = pd.DataFrame()

    candidates = []
    for key in CLASSIFICATION_PREVIEW_KEYS:
        score = (
            upload_dataframe_score(df, key=key)
            + required_column_score(df, key)
            + column_hint_score(df, key)
            + preview_filename_score(upload.original_name, key)
            + business_rule_score(df, key)
        )
        candidates.append({"key": key, "df": df, "score": score})

    return sorted(candidates, key=lambda item: int(item["score"]), reverse=True)


def classify_upload(upload: SavedUpload, context: SessionContext | None = None) -> tuple[str, pd.DataFrame, int]:
    best = score_upload_candidates(upload, context)[0]
    return str(best["key"]), pd.DataFrame(best["df"]), int(best["score"])


def confidence_from_scores(score: int | None, next_score: int | None) -> str:
    if score is None:
        return "low"
    gap = score - next_score if next_score is not None else score
    if score >= 200 and gap >= 80:
        return "high"
    if score >= 120 and gap >= 30:
        return "medium"
    return "low"


def confidence_for_assignment(df: pd.DataFrame | None, key: str, score: int | None, next_lower_score: int | None) -> str:
    if score is None:
        return "low"
    missing = missing_required_columns(df, key)
    if not missing and score >= 200:
        return "high"
    if len(missing) <= 1 and score >= 200:
        return "medium"
    return confidence_from_scores(score, next_lower_score)


def column_names_for_preview(df: pd.DataFrame | None, limit: int = 12) -> list[str]:
    if df is None:
        return []
    return [str(column) for column in pd.DataFrame(df).columns[:limit]]


def normalized_column_name(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def required_columns_for_key(key: str) -> list[str]:
    return [str(column) for column in DATA_SPECS.get(key, {}).get("required_columns", [])]


def aliases_for_required_column(key: str, required_column: str) -> list[str]:
    aliases = [required_column]
    aliases.extend(REQUIRED_COLUMN_ALIASES.get(required_column, []))
    for group in UPLOAD_COLUMN_GROUPS.get(key, []):
        normalized_group = {normalized_column_name(column) for column in group}
        if normalized_column_name(required_column) in normalized_group:
            aliases.extend(str(column) for column in group)
    seen: set[str] = set()
    unique_aliases: list[str] = []
    for alias in aliases:
        normalized = normalized_column_name(alias)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_aliases.append(str(alias))
    return unique_aliases


def required_column_matched(df: pd.DataFrame | None, key: str, required_column: str) -> bool:
    if df is None:
        return False
    columns = {normalized_column_name(column) for column in pd.DataFrame(df).columns}
    return any(normalized_column_name(alias) in columns for alias in aliases_for_required_column(key, required_column))


def matched_required_columns(df: pd.DataFrame | None, key: str) -> list[str]:
    if df is None:
        return []
    return [column for column in required_columns_for_key(key) if required_column_matched(df, key, column)]


def missing_required_columns(df: pd.DataFrame | None, key: str) -> list[str]:
    if df is None:
        return required_columns_for_key(key)
    return [column for column in required_columns_for_key(key) if not required_column_matched(df, key, column)]


def classification_evidence(
    upload: SavedUpload,
    key: str,
    df: pd.DataFrame | None,
    score: int | None,
    next_score: int | None,
) -> list[str]:
    evidence: list[str] = []
    matched = matched_required_columns(df, key)
    missing = missing_required_columns(df, key)
    filename_score = preview_filename_score(upload.original_name, key)
    site = dominant_text_value(df, ("Site",))
    fr_date_ratio = non_empty_ratio(df, ("FR Date",))
    gap = (score - next_score) if score is not None and next_score is not None else None

    if filename_score > 0:
        evidence.append("파일명 힌트가 이 파일 종류와 일치합니다.")
    if key in {"sales_detail", "hq_to_eu_sales_detail"} and site is not None:
        dominant_site, ratio = site
        if dominant_site == "EU":
            evidence.append(f"Site 값이 EU 중심입니다({ratio:.0%}). EU 현지 판매내역으로 판단합니다.")
        elif dominant_site == "KR":
            evidence.append(f"Site 값이 KR 중심입니다({ratio:.0%}). 본사→EU 판매/출고내역으로 판단합니다.")
    if key in {"eu_stock", "hq_eu_stock"} and fr_date_ratio is not None:
        if fr_date_ratio >= 0.5:
            evidence.append(f"FR Date 입력 비율이 {fr_date_ratio:.0%}입니다. EU 현지 재고로 판단합니다.")
        else:
            evidence.append(f"FR Date 입력 비율이 {fr_date_ratio:.0%}입니다. 본사 EU 창고 재고로 판단합니다.")
    if matched:
        evidence.append(f"필수 컬럼 {len(matched)}개 감지: {', '.join(matched[:6])}")
    if missing:
        evidence.append(f"필수 컬럼 미감지: {', '.join(missing[:6])}")
    if gap is not None:
        evidence.append(f"다음 후보와 점수 차이: {gap}")
    elif score is not None:
        evidence.append(f"분류 점수: {score}")

    return evidence


def classification_candidate_preview(candidate: dict[str, object], assigned: bool = False) -> dict[str, object]:
    key = str(candidate["key"])
    df = pd.DataFrame(candidate["df"]) if candidate.get("df") is not None else None
    return {
        "role": response_role_for_upload_key(key),
        "key": key,
        "score": int(candidate["score"]),
        "rows": int(len(df)) if df is not None else 0,
        "columns": int(len(df.columns)) if df is not None else 0,
        "detected_columns": column_names_for_preview(df),
        "matched_required_columns": matched_required_columns(df, key),
        "missing_required_columns": missing_required_columns(df, key),
        "assigned": assigned,
    }


def classify_uploads_for_preview(saved_uploads: list[SavedUpload]) -> list[dict[str, object]]:
    context = SessionContext()
    candidates_by_upload: list[list[dict[str, object]]] = []
    errors: dict[int, str] = {}

    for upload_index, upload in enumerate(saved_uploads):
        try:
            candidates = [
                candidate
                for candidate in score_upload_candidates_for_preview(upload, context)
                if str(candidate["key"]) in CLASSIFICATION_PREVIEW_KEYS
            ]
        except Exception as exc:  # noqa: BLE001
            candidates = []
            errors[upload_index] = str(exc)
        if not candidates and upload_index not in errors:
            errors[upload_index] = f"Could not classify uploaded file: {upload.original_name}"
        candidates_by_upload.append(candidates)

    assigned_uploads: dict[int, dict[str, object]] = {}
    assigned_keys: set[str] = set()
    ranked_candidates: list[dict[str, object]] = []
    for upload_index, candidates in enumerate(candidates_by_upload):
        for candidate in candidates:
            ranked_candidates.append({"upload_index": upload_index, **candidate})

    ranked_candidates.sort(key=lambda item: int(item["score"]), reverse=True)
    for candidate in ranked_candidates:
        upload_index = int(candidate["upload_index"])
        key = str(candidate["key"])
        if upload_index in assigned_uploads or key in assigned_keys:
            continue
        assigned_uploads[upload_index] = candidate
        assigned_keys.add(key)

    previews: list[dict[str, object]] = []
    for upload_index, upload in enumerate(saved_uploads):
        candidates = candidates_by_upload[upload_index]

        assignment = assigned_uploads.get(upload_index)
        if assignment is None and candidates:
            assignment = {"upload_index": upload_index, **candidates[0]}

        score = int(assignment["score"]) if assignment else None
        assigned_key = str(assignment["key"]) if assignment else ""
        assigned_role = response_role_for_upload_key(assigned_key) if assigned_key else ""
        next_lower_score = None
        assigned_candidate = next((candidate for candidate in candidates if str(candidate["key"]) == assigned_key), None)
        ordered_candidates = []
        if assigned_candidate is not None:
            ordered_candidates.append(assigned_candidate)
        ordered_candidates.extend(candidate for candidate in candidates if str(candidate["key"]) != assigned_key)
        for candidate in ordered_candidates:
            if str(candidate["key"]) != assigned_key and score is not None and int(candidate["score"]) <= score:
                next_lower_score = int(candidate["score"])
                break

        assignment_df = pd.DataFrame(assignment["df"]) if assignment and assignment.get("df") is not None else None
        candidate_previews = [
            classification_candidate_preview(candidate, assigned=str(candidate["key"]) == assigned_key)
            for candidate in ordered_candidates
        ]
        previews.append(
            {
                "index": upload_index,
                "original_name": upload.original_name,
                "suggested_role": assigned_role,
                "suggested_key": assigned_key,
                "score": score,
                "confidence": confidence_for_assignment(assignment_df, assigned_key, score, next_lower_score)
                if assigned_key
                else "low",
                "rows": int(len(assignment_df)) if assignment_df is not None else 0,
                "columns": int(len(assignment_df.columns)) if assignment_df is not None else 0,
                "detected_columns": column_names_for_preview(assignment_df),
                "matched_required_columns": matched_required_columns(assignment_df, assigned_key) if assigned_key else [],
                "missing_required_columns": missing_required_columns(assignment_df, assigned_key) if assigned_key else [],
                "evidence": classification_evidence(upload, assigned_key, assignment_df, score, next_lower_score)
                if assigned_key
                else [],
                "candidates": candidate_previews,
                "error": errors.get(upload_index),
            }
        )

    return previews


def prepare_explicit_role_uploaded_data(
    saved_uploads: list[SavedUpload],
    context: SessionContext | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], list[dict[str, object]]]:
    uploaded_data: dict[str, pd.DataFrame] = {}
    uploaded_files: dict[str, str] = {}
    classifications: list[dict[str, object]] = []

    for upload in saved_uploads:
        role = normalize_upload_role(upload.role or "")
        key = upload_key_for_role(role)
        response_role = response_role_for_upload_key(key, role)
        if key in uploaded_data:
            raise ValueError(f"같은 종류의 파일이 중복되었습니다: {response_role}")

        try:
            df = read_category_correction_upload(upload) if key == "category_correction" else cached_uploaded_dataframe(upload, key, context=context)
        except Exception as exc:
            raise ValueError(
                f"'{upload.original_name}' 파일을 '{response_role}' role로 읽을 수 없습니다."
            ) from exc

        uploaded_data[key] = df
        uploaded_files[key] = upload.original_name
        classifications.append(
            {
                "key": key,
                "role": response_role,
                "original_name": upload.original_name,
                "saved_name": upload.saved_name,
                "source": "explicit",
                "score": None,
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "detected_columns": column_names_for_preview(df),
                "matched_required_columns": matched_required_columns(df, key),
                "missing_required_columns": missing_required_columns(df, key),
            }
        )

    return uploaded_data, uploaded_files, classifications


def prepare_uploaded_data(
    saved_uploads: list[SavedUpload],
    context: SessionContext | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], list[dict[str, object]]]:
    has_explicit_roles = any(upload.role for upload in saved_uploads)
    if has_explicit_roles:
        if not all(upload.role for upload in saved_uploads):
            raise ValueError("파일 role은 모든 파일에 지정하거나, 모든 파일을 자동 분류로 처리해야 합니다.")
        return prepare_explicit_role_uploaded_data(saved_uploads, context)

    uploaded_data: dict[str, pd.DataFrame] = {}
    uploaded_files: dict[str, str] = {}
    classifications: list[dict[str, object]] = []

    candidates_by_upload = [score_upload_candidates(upload, context) for upload in saved_uploads]
    assigned_uploads: dict[int, dict[str, object]] = {}
    assigned_keys: set[str] = set()

    ranked_candidates: list[dict[str, object]] = []
    for upload_index, candidates in enumerate(candidates_by_upload):
        for candidate in candidates:
            ranked_candidates.append({"upload_index": upload_index, **candidate})

    ranked_candidates.sort(key=lambda item: int(item["score"]), reverse=True)
    for candidate in ranked_candidates:
        upload_index = int(candidate["upload_index"])
        key = str(candidate["key"])
        if upload_index in assigned_uploads or key in assigned_keys:
            continue
        assigned_uploads[upload_index] = candidate
        assigned_keys.add(key)

    if len(assigned_uploads) != len(saved_uploads):
        raise ValueError("업로드한 모든 파일에 서로 다른 파일 종류를 배정할 수 없습니다.")

    for upload_index, upload in enumerate(saved_uploads):
        assignment = assigned_uploads[upload_index]
        key = str(assignment["key"])
        df = pd.DataFrame(assignment["df"])
        score = int(assignment["score"])

        uploaded_data[key] = df
        uploaded_files[key] = upload.original_name
        classifications.append(
            {
                "key": key,
                "role": response_role_for_upload_key(key),
                "original_name": upload.original_name,
                "saved_name": upload.saved_name,
                "source": "auto",
                "score": score,
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "detected_columns": column_names_for_preview(df),
                "matched_required_columns": matched_required_columns(df, key),
                "missing_required_columns": missing_required_columns(df, key),
            }
        )

    return uploaded_data, uploaded_files, classifications

__all__ = [
    "ALLOWED_UPLOAD_ROLES",
    "UPLOAD_KEY_TO_RESPONSE_ROLE",
    "classify_uploads_for_preview",
    "column_names_for_preview",
    "file_mapping_from_classifications",
    "matched_required_columns",
    "missing_required_columns",
    "normalize_upload_role",
    "prepare_explicit_role_uploaded_data",
    "prepare_uploaded_data",
    "response_role_for_upload_key",
    "upload_key_for_role",
]
