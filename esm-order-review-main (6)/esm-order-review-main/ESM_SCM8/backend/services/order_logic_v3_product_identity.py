"""V3-only product aliases approved on 2026-08-31.

Codes may differ only in case AND source/master names must match literally.
Literal suffixes such as .0 remain part of the code before shared adapters see it.
Never change cached rows, remove transactions, or normalize product names.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


PRODUCT_IDENTITY_POLICY = "V3_CASE_INSENSITIVE_CODE_EXACT_PRODUCT_NAME_PRESERVE_SUFFIX_V3"
PRODUCT_IDENTITY_REASON = "CASE_ONLY_CODE_EXACT_PRODUCT_NAME"
_CODE_FIELDS = ("상품코드", "SKU", "품목코드", "itemcode", "prod_cd", "sku_code", "sku")
_NAME_FIELDS = ("상품명_마스터", "prod_nm", "상품명", "상품명마스터", "product_name")


def _value(row: Mapping[str, object], fields: Sequence[str]) -> object:
    # Same field precedence as the existing product-master adapter.
    return next((row[key] for key in fields if key in row), None)


def _code(row: Mapping[str, object]) -> str:
    value = _value(row, _CODE_FIELDS)
    return str(value).strip() if value is not None else ""


def _name(row: Mapping[str, object]) -> str | None:
    value = _value(row, _NAME_FIELDS)
    if not isinstance(value, str) or not value.strip() or value.lower() in {"nan", "none", "<na>"}:
        return None
    # No trimming, punctuation removal, unit conversion or Unicode normalization.
    return value


@dataclass(frozen=True)
class ProductIdentityResolver:
    aliases: Mapping[str, str]
    rejected: Mapping[str, str]
    observed_codes: frozenset[str] = frozenset()

    @classmethod
    def build(
        cls,
        products: Sequence[Mapping[str, object]],
        sources: Iterable[Sequence[Mapping[str, object]]],
    ) -> "ProductIdentityResolver":
        masters: dict[str, dict[str, set[str | None]]] = defaultdict(lambda: defaultdict(set))
        for row in products:
            code = _code(row)
            if code:
                masters[code.lower()][code].add(_name(row))

        names: dict[str, set[str]] = defaultdict(set)
        for rows in sources:
            for row in rows:
                code = _code(row)
                if code:
                    names[code]
                    name = _name(row)
                    if name is not None:
                        names[code].add(name)

        aliases: dict[str, str] = {}
        rejected: dict[str, str] = {}
        for code, source_names in sorted(names.items()):
            candidates = masters.get(code.lower(), {})
            if not candidates or code in candidates:
                continue  # Preserve existing exact-code joins; never guess a missing master.
            if len(candidates) != 1:
                rejected[code] = "AMBIGUOUS_MASTER_CODE"
                continue
            target, master_names = next(iter(candidates.items()))
            if len(master_names) != 1 or None in master_names:
                rejected[code] = "MISSING_OR_CONFLICTING_MASTER_NAME"
            elif not source_names:
                rejected[code] = "SOURCE_NAME_MISSING"
            elif source_names != master_names:
                rejected[code] = "SOURCE_NAME_MISMATCH_OR_CONFLICT"
            else:
                aliases[code] = target
        return cls(aliases=aliases, rejected=rejected, observed_codes=frozenset(names))

    def rewrite_rows(self, rows: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
        rewritten: list[Mapping[str, object]] = []
        for row in rows:
            code = _code(row)
            target = self.aliases.get(code)
            if target is None:
                rewritten.append(row)
                continue
            rewritten.append({
                **row,
                **{key: target for key in _CODE_FIELDS if key in row},
            })
        return rewritten

    def rewrite_products(self, rows: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
        # Aliases only point to an existing unique master; master rows and their
        # original duplicate precedence must not change.
        return list(rows)

    def rewrite_payload(self, raw: Mapping[str, object]) -> dict[str, object]:
        return {
            key: (self.rewrite_products(value) if key in {"products", "prod_list"} else self.rewrite_rows(value))
            if isinstance(value, list)
            and all(isinstance(row, Mapping) for row in value) else value
            for key, value in raw.items()
        }

    def source_codes_by_target(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for source, target in sorted(self.aliases.items()):
            if source in self.observed_codes:
                groups[target].append(source)
        return {
            target: sorted(set(codes) | ({target} if target in self.observed_codes else set()))
            for target, codes in groups.items()
        }

    def summary(self) -> dict[str, object]:
        return {
            "policy": PRODUCT_IDENTITY_POLICY,
            "matched_alias_count": len(self.aliases.keys() & self.observed_codes),
            "rejected_alias_count": len(self.rejected),
        }

    def audit(self) -> dict[str, object]:
        return {
            **self.summary(),
            "aliases": dict(self.aliases),
            "rejected": dict(self.rejected),
        }


def inventory_identity_sources(raw: Mapping[str, object]) -> list[list[Mapping[str, object]]]:
    return [
        rows for key, rows in raw.items()
        if key not in {"products", "prod_list"} and isinstance(rows, list)
        and all(isinstance(row, Mapping) for row in rows)
    ]
