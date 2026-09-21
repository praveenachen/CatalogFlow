from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from .domain import NormalizationTrace


CATEGORY_ALIASES = {
    "womens shoes": "Footwear",
    "women footwear": "Footwear",
    "ladies shoes": "Footwear",
    "mens tops": "Apparel",
    "shirts": "Apparel",
    "t-shirt": "Apparel",
    "tee": "Apparel",
    "skincare": "Beauty",
    "beauty": "Beauty",
    "cosmetics": "Beauty",
    "laptop accessories": "Electronics",
    "electronics": "Electronics",
    "tech": "Electronics",
    "home goods": "Home",
    "decor": "Home",
    "furniture": "Home",
}


def safe_string(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def normalize_price(value: Any) -> tuple[Decimal | None, NormalizationTrace]:
    raw = safe_string(value)
    cleaned = re.sub(r"[$,\s]", "", raw)
    try:
        result = Decimal(cleaned) if cleaned else None
        if result is not None and result < 0:
            raise InvalidOperation
        certainty = 1.0 if cleaned == raw else 0.98
        rule = "decimal_parse" if cleaned == raw else "strip_currency_and_grouping"
    except (InvalidOperation, ValueError):
        result, certainty, rule = None, 0.0, "invalid_price"
    return result, NormalizationTrace(field="price", original_value=raw, normalized_value=result, rule=rule, certainty=certainty)


def normalize_inventory(value: Any) -> tuple[int | None, NormalizationTrace]:
    raw = safe_string(value)
    match = re.fullmatch(r"\s*(\d+)(?:\.0+)?\s*(?:units?|pcs?)?\s*", raw, re.IGNORECASE)
    result = int(match.group(1)) if match else None
    rule = "integer_parse" if match and match.group(0).strip() == match.group(1) else "strip_inventory_unit" if match else "invalid_inventory"
    certainty = 1.0 if rule == "integer_parse" else 0.98 if match else 0.0
    return result, NormalizationTrace(field="inventory", original_value=raw, normalized_value=result, rule=rule, certainty=certainty)


def normalize_tags(value: Any) -> tuple[list[str], NormalizationTrace]:
    raw = safe_string(value)
    tags = sorted({item.strip().lower().lstrip("#") for item in re.split(r"[,|]", raw) if item.strip().lstrip("#")})
    return tags, NormalizationTrace(field="tags", original_value=raw, normalized_value=tags, rule="split_dedupe_lowercase", certainty=1.0)


def normalize_category(value: Any) -> tuple[str | None, NormalizationTrace]:
    raw = safe_string(value)
    key = re.sub(r"\s+", " ", raw.lower()).strip()
    if not key:
        result, rule, certainty = None, "missing_category", 0.0
    elif key in CATEGORY_ALIASES:
        result, rule, certainty = CATEGORY_ALIASES[key], "known_category_alias", 1.0
    else:
        result, rule, certainty = raw.title(), "title_case_unrecognized_category", 0.65
    return result, NormalizationTrace(field="category", original_value=raw, normalized_value=result, rule=rule, certainty=certainty)


def normalize_currency(value: Any, default_currency: str | None = None) -> tuple[str | None, NormalizationTrace]:
    raw = safe_string(value)
    configured = safe_string(default_currency).upper()
    if raw:
        result, rule, certainty = raw.upper(), "explicit_source_currency", 1.0
    elif configured:
        result, rule, certainty = configured, "configured_default_currency", 0.95
    else:
        result, rule, certainty = None, "missing_currency", 0.0
    return result, NormalizationTrace(
        field="currency", original_value=raw or None, normalized_value=result, rule=rule, certainty=certainty
    )


def normalize_row(
    row: dict[str, Any], default_currency: str | None = None
) -> tuple[dict[str, Any], list[NormalizationTrace]]:
    result = {field: safe_string(row.get(field)) or None for field in ("sku", "description")}
    name = safe_string(row.get("product_name"))
    result["product_name"] = " ".join(word.capitalize() for word in name.split()) if name else None
    currency, currency_trace = normalize_currency(row.get("currency"), default_currency)
    result["currency"] = currency
    price, price_trace = normalize_price(row.get("price"))
    inventory, inventory_trace = normalize_inventory(row.get("inventory"))
    tags, tags_trace = normalize_tags(row.get("tags"))
    category, category_trace = normalize_category(row.get("category"))
    result.update(price=price, inventory=inventory, tags=tags, category=category)
    traces = [
        NormalizationTrace(field="product_name", original_value=name, normalized_value=result["product_name"], rule="trim_title_case", certainty=1.0 if name else 0.0),
        category_trace, price_trace, currency_trace, inventory_trace, tags_trace,
    ]
    return result, traces
