from __future__ import annotations

import io

import pandas as pd


class CatalogIngestionError(ValueError):
    pass


def read_csv(payload: bytes) -> pd.DataFrame:
    if not payload:
        raise CatalogIngestionError("The uploaded CSV is empty.")
    try:
        frame = pd.read_csv(io.BytesIO(payload), dtype=object)
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise CatalogIngestionError(f"Unable to parse CSV: {exc}") from exc
    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.columns.duplicated().any():
        raise CatalogIngestionError("CSV contains duplicate column names.")
    if frame.empty:
        raise CatalogIngestionError("The uploaded CSV contains no data rows.")
    return frame
