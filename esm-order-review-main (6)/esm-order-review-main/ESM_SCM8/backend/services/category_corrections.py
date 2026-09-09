"""Read, persist, merge, and apply SKU category corrections."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re

import pandas as pd

from core.common import PROJECT_ROOT

from backend.services.upload_models import SavedUpload


DEFAULT_CATEGORY_CORRECTION_PATH = PROJECT_ROOT / "data" / "category_corrections" / "default_category_corrections_20260612.xlsx"
USER_CATEGORY_CORRECTION_PATH = PROJECT_ROOT / "data" / "category_corrections" / "user_category_corrections.csv"
CORRECTION_COLUMNS = ("상품코드", "기능구분1", "기능구분2", "상품명(참고)", "브랜드(참고)", "수정일시")


def _normalized_column_name(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def read_category_correction_upload(upload: SavedUpload) -> pd.DataFrame:
    source = BytesIO(upload.content) if upload.content is not None else upload.path
    return read_category_correction_excel(pd.ExcelFile(source))


def read_category_correction_excel(excel_file: pd.ExcelFile) -> pd.DataFrame:
    sheet_name = "보정입력" if "보정입력" in excel_file.sheet_names else excel_file.sheet_names[0]
    best_df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str)
    if sheet_name == "보정입력":
        return best_df

    best_score = -1
    for candidate_sheet in excel_file.sheet_names:
        candidate = pd.read_excel(excel_file, sheet_name=candidate_sheet, dtype=str)
        normalized_columns = {_normalized_column_name(column) for column in candidate.columns}
        score = 0
        if any(name in normalized_columns for name in ("상품코드", "sku", "prod_cd")):
            score += 2
        if any(name in normalized_columns for name in ("기능구분1", "class1_nm")):
            score += 2
        if any(name in normalized_columns for name in ("기능구분2", "class2_nm")):
            score += 2
        if score > best_score:
            best_score = score
            best_df = candidate
    return pd.DataFrame(best_df)


def read_default_category_corrections() -> pd.DataFrame:
    if not DEFAULT_CATEGORY_CORRECTION_PATH.exists():
        return pd.DataFrame()
    try:
        return read_category_correction_excel(pd.ExcelFile(DEFAULT_CATEGORY_CORRECTION_PATH))
    except Exception as exc:  # noqa: BLE001
        print(f"[default category correction skipped] {exc}", flush=True)
        return pd.DataFrame()


def read_user_category_corrections() -> pd.DataFrame:
    if not USER_CATEGORY_CORRECTION_PATH.exists():
        return pd.DataFrame(columns=list(CORRECTION_COLUMNS))
    try:
        return pd.read_csv(USER_CATEGORY_CORRECTION_PATH, dtype=str).fillna("")
    except Exception as exc:  # noqa: BLE001
        print(f"[user category correction skipped] {exc}", flush=True)
        return pd.DataFrame(columns=list(CORRECTION_COLUMNS))


def save_user_category_corrections(rows: list[dict[str, object]]) -> pd.DataFrame:
    current = read_user_category_corrections()
    incoming_rows: list[dict[str, str]] = []
    now = datetime.now().isoformat(timespec="seconds")
    for row in rows:
        code = str(row.get("상품코드") or row.get("productCode") or "").strip()
        category1 = str(row.get("기능구분1") or row.get("category1") or "").strip()
        category2 = str(row.get("기능구분2") or row.get("category2") or "").strip()
        if not code or not category1 or not category2:
            continue
        incoming_rows.append(
            {
                "상품코드": code,
                "기능구분1": category1,
                "기능구분2": category2,
                "상품명(참고)": str(row.get("상품명(참고)") or row.get("productName") or "").strip(),
                "브랜드(참고)": str(row.get("브랜드(참고)") or row.get("brand") or "").strip(),
                "수정일시": now,
            }
        )

    incoming = pd.DataFrame(incoming_rows, columns=list(CORRECTION_COLUMNS))
    if incoming.empty:
        return current

    combined = pd.concat([current, incoming], ignore_index=True)
    combined["_sku_key"] = combined["상품코드"].map(normalize_sku_key)
    combined = combined[combined["_sku_key"].astype(str).str.strip() != ""].drop_duplicates(
        "_sku_key", keep="last"
    ).drop(columns=["_sku_key"])
    USER_CATEGORY_CORRECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(USER_CATEGORY_CORRECTION_PATH, index=False, encoding="utf-8-sig")
    return combined


def merge_default_category_corrections(uploaded_corrections: pd.DataFrame) -> pd.DataFrame:
    frames = [
        frame
        for frame in (
            read_default_category_corrections(),
            read_user_category_corrections(),
            pd.DataFrame(uploaded_corrections),
        )
        if not frame.empty
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def append_default_category_correction_products(
    product_df: pd.DataFrame,
    correction_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add explicitly approved CMS category rows before the product join.

    The CMS product endpoint can omit a SKU that is still present in sales
    history.  A complete row in the checked-in default correction workbook is
    an explicit source correction, not a name-based inference, so it can act as
    a virtual product-master row for the season analysis.
    """
    products = pd.DataFrame(product_df).copy()
    corrections = pd.DataFrame(correction_df).copy()
    if corrections.empty:
        return products

    code_col = _column_by_alias(corrections, (CORRECTION_COLUMNS[0], "SKU", "prod_cd"))
    category1_col = _column_by_alias(corrections, (CORRECTION_COLUMNS[1], "class1_nm"))
    category2_col = _column_by_alias(corrections, (CORRECTION_COLUMNS[2], "class2_nm"))
    if code_col is None or category1_col is None or category2_col is None:
        return products

    product_code_col = _column_by_alias(products, ("prod_cd", "SKU", CORRECTION_COLUMNS[0]))
    existing_keys = (
        set(products[product_code_col].map(normalize_sku_key))
        if product_code_col is not None
        else set()
    )
    product_name_col = _column_by_alias(corrections, (CORRECTION_COLUMNS[3], "productName", "prod_nm"))
    brand_col = _column_by_alias(corrections, (CORRECTION_COLUMNS[4], "brand", "brand_nm"))
    virtual_rows: list[dict[str, str]] = []
    for _, row in corrections.iterrows():
        code = normalize_sku_key(row.get(code_col))
        category1 = str(row.get(category1_col) or "").strip()
        category2 = str(row.get(category2_col) or "").strip()
        if not code or not category1 or not category2 or code in existing_keys:
            continue
        virtual_rows.append(
            {
                "prod_cd": code,
                "prod_nm": str(row.get(product_name_col) or "").strip() if product_name_col else "",
                "brand_nm": str(row.get(brand_col) or "").strip() if brand_col else "",
                "class1_nm": category1,
                "class2_nm": category2,
            }
        )
        existing_keys.add(code)

    if not virtual_rows:
        return products
    return pd.concat([products, pd.DataFrame(virtual_rows)], ignore_index=True)


def _column_by_alias(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized = {_normalized_column_name(column): str(column) for column in pd.DataFrame(df).columns}
    for alias in aliases:
        column = normalized.get(_normalized_column_name(alias))
        if column:
            return column
    return None


def normalize_sku_key(value: object) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def apply_category_corrections_to_merged(
    merged_df: pd.DataFrame,
    correction_df: pd.DataFrame,
    product_code_col: str,
    category1_col: str,
    category2_col: str,
) -> pd.DataFrame:
    merged = pd.DataFrame(merged_df).copy()
    corrections = pd.DataFrame(correction_df).copy()
    if merged.empty or corrections.empty or product_code_col not in merged.columns:
        return merged

    code_col = _column_by_alias(corrections, ("상품코드", "SKU", "prod_cd", product_code_col))
    category1_source_col = _column_by_alias(corrections, ("기능구분1", "class1_nm", category1_col))
    category2_source_col = _column_by_alias(corrections, ("기능구분2", "class2_nm", category2_col))
    if code_col is None or (category1_source_col is None and category2_source_col is None):
        return merged

    correction_keys = corrections[code_col].map(normalize_sku_key)
    merged_keys = merged[product_code_col].map(normalize_sku_key)
    for source_column, target_column in (
        (category1_source_col, category1_col),
        (category2_source_col, category2_col),
    ):
        if source_column is None:
            continue
        value_map = (
            corrections.assign(_sku_key=correction_keys)
            .dropna(subset=["_sku_key"])
            .drop_duplicates("_sku_key", keep="last")
            .set_index("_sku_key")[source_column]
            .astype(str)
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
            .dropna()
            .to_dict()
        )
        mapped = merged_keys.map(value_map)
        mask = mapped.notna() & mapped.astype(str).str.strip().ne("")
        merged.loc[mask, target_column] = mapped[mask]

    return merged


__all__ = [
    "apply_category_corrections_to_merged",
    "append_default_category_correction_products",
    "merge_default_category_corrections",
    "normalize_sku_key",
    "read_category_correction_excel",
    "read_category_correction_upload",
    "read_default_category_corrections",
    "read_user_category_corrections",
    "save_user_category_corrections",
]
