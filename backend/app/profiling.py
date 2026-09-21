from __future__ import annotations

from typing import Any

import pandas as pd

from .domain import ColumnProfile


def _string(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _validity_rate(name: str, series: pd.Series) -> float | None:
    values = series.dropna().map(_string)
    if values.empty:
        return None
    key = name.strip().lower()
    if any(token in key for token in ("price", "cost", "amount")):
        valid = values.str.replace(r"[$,\s]", "", regex=True).str.fullmatch(r"\+?\d+(?:\.\d+)?")
    elif any(token in key for token in ("inventory", "stock", "quantity", "qty")):
        valid = values.str.lower().str.fullmatch(r"\s*\d+(?:\.0+)?\s*(?:units?|pcs?)?\s*")
    elif "currency" in key:
        valid = values.str.fullmatch(r"[A-Za-z]{3}")
    else:
        return None
    return round(float(valid.mean()), 4)


def profile_dataframe(frame: pd.DataFrame, sample_size: int = 5) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    count = len(frame)
    for source_name in frame.columns:
        series = frame[source_name]
        non_null = series.dropna()
        profiles.append(
            ColumnProfile(
                source_name=str(source_name),
                inferred_type=str(series.infer_objects().dtype),
                null_percentage=round(float(series.isna().mean() * 100), 2) if count else 0.0,
                unique_percentage=round(float(non_null.nunique(dropna=True) / max(1, len(non_null)) * 100), 2),
                sample_values=list(dict.fromkeys(_string(value) for value in non_null.head(sample_size))),
                validity_rate=_validity_rate(str(source_name), series),
            )
        )
    return profiles
