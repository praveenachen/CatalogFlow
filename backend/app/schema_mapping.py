from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from rapidfuzz import fuzz, process

from .config import CANONICAL_FIELDS, SETTINGS
from .domain import MappingCandidate, MappingMethod


KNOWN_ALIASES = {
    "item_name": "product_name",
    "item_title": "product_name",
    "title": "product_name",
    "product_title": "product_name",
    "details": "description",
    "product_description": "description",
    "cost": "price",
    "retail_price": "price",
    "unit_price": "price",
    "stock": "inventory",
    "inventory_count": "inventory",
    "quantity": "inventory",
    "qty": "inventory",
    "product_type": "category",
    "labels": "tags",
    "tag_list": "tags",
    "product_code": "sku",
    "item_id": "sku",
    "currency_code": "currency",
}


def normalize_field_name(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.strip().lower())).strip("_")


def map_columns(
    columns: Sequence[str],
    merchant_aliases: Mapping[str, str] | None = None,
) -> list[MappingCandidate]:
    aliases = {**KNOWN_ALIASES, **{normalize_field_name(k): v for k, v in (merchant_aliases or {}).items()}}
    results: list[MappingCandidate] = []
    assigned: set[str] = set()
    for source in columns:
        key = normalize_field_name(str(source))
        if key in CANONICAL_FIELDS and key not in assigned:
            candidate = MappingCandidate(
                source_field=str(source), canonical_field=key, confidence=1.0,
                method=MappingMethod.exact, auto_applied=True,
            )
        elif key in aliases and aliases[key] not in assigned:
            candidate = MappingCandidate(
                source_field=str(source), canonical_field=aliases[key], confidence=0.96,
                method=MappingMethod.alias, auto_applied=True,
            )
        else:
            match = process.extractOne(key, CANONICAL_FIELDS, scorer=fuzz.ratio)
            confidence = (match[1] / 100.0) if match else 0.0
            field = match[0] if match and confidence >= SETTINGS.mapping_candidate_threshold else None
            candidate = MappingCandidate(
                source_field=str(source),
                canonical_field=field,
                confidence=round(confidence, 4),
                method=MappingMethod.fuzzy if field else MappingMethod.unresolved,
                auto_applied=bool(field and field not in assigned and confidence >= SETTINGS.mapping_auto_apply_threshold),
            )
        if candidate.auto_applied and candidate.canonical_field:
            assigned.add(candidate.canonical_field)
        results.append(candidate)
    return results


def apply_auto_mappings(columns: Sequence[str], mappings: Sequence[MappingCandidate]) -> dict[str, str]:
    return {
        mapping.source_field: mapping.canonical_field
        for mapping in mappings
        if mapping.auto_applied and mapping.canonical_field in CANONICAL_FIELDS
    }
