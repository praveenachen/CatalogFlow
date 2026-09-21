from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import pandera.pandas as pa
from pydantic import ValidationError

from .domain import CanonicalProduct, NormalizationTrace


TABULAR_SCHEMA = pa.DataFrameSchema(
    {
        "product_name": pa.Column(object, nullable=True, required=True),
        "price": pa.Column(object, nullable=True, required=True),
        "currency": pa.Column(object, nullable=True, required=True),
    },
    strict=False,
    coerce=False,
)


def validate_mapped_frame(frame: pd.DataFrame) -> list[str]:
    try:
        TABULAR_SCHEMA.validate(frame, lazy=True)
        return []
    except pa.errors.SchemaErrors as exc:
        return sorted(set(str(item) for item in exc.failure_cases["failure_case"].tolist()))
    except pa.errors.SchemaError as exc:
        return [str(exc)]


def validate_canonical_values(values: dict[str, Any]) -> list[str]:
    payload = {**values, "price": values.get("price") if values.get("price") is not None else Decimal("-1")}
    try:
        CanonicalProduct.model_validate(payload)
        return []
    except ValidationError as exc:
        return [".".join(str(part) for part in error["loc"]) + ": " + error["msg"] for error in exc.errors()]


def validate_normalized_row(values: dict[str, Any], traces: list[NormalizationTrace]) -> list[str]:
    errors = validate_canonical_values(values)
    for trace in traces:
        if trace.rule == "invalid_inventory" and trace.original_value not in (None, ""):
            errors.append("inventory: invalid value")
    return list(dict.fromkeys(errors))
