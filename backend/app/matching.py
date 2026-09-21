from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from .config import SETTINGS
from .domain import DuplicateCandidate


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def find_duplicate_candidates(records: list[dict[str, Any]]) -> list[DuplicateCandidate]:
    results: list[DuplicateCandidate] = []
    for index, record in enumerate(records):
        sku = _key(record.get("sku"))
        name = _key(record.get("product_name"))
        category = _key(record.get("category"))
        for previous_index, previous in enumerate(records[:index]):
            previous_sku = _key(previous.get("sku"))
            previous_name = _key(previous.get("product_name"))
            previous_category = _key(previous.get("category"))
            if sku and previous_sku and sku == previous_sku:
                results.append(DuplicateCandidate(row_index=index, matched_row_index=previous_index, method="exact_sku", confidence=1.0, exact=True))
                break
            if name and category and name == previous_name and category == previous_category:
                results.append(DuplicateCandidate(row_index=index, matched_row_index=previous_index, method="exact_name_category", confidence=1.0, exact=True))
                break
            if name and previous_name:
                score = fuzz.token_set_ratio(name, previous_name) / 100.0
                if score >= SETTINGS.fuzzy_duplicate_threshold:
                    results.append(DuplicateCandidate(row_index=index, matched_row_index=previous_index, method="fuzzy_product_name", confidence=round(score, 4), exact=False))
                    break
    return results
