from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pandas as pd

from .config import CANONICAL_FIELDS, SETTINGS
from .domain import ProcessedRecord, ProcessingResult
from .ingestion import read_csv
from .matching import find_duplicate_candidates
from .normalization import normalize_row
from .profiling import profile_dataframe
from .quality import calculate_quality
from .schema_mapping import apply_auto_mappings, map_columns
from .validation import validate_mapped_frame, validate_normalized_row


class CatalogProcessor(ABC):
    @abstractmethod
    def process(
        self,
        payload: bytes,
        merchant_aliases: dict[str, str] | None = None,
        default_currency: str | None = None,
    ) -> ProcessingResult:
        raise NotImplementedError


class PandasCatalogProcessor(CatalogProcessor):
    def process(
        self,
        payload: bytes,
        merchant_aliases: dict[str, str] | None = None,
        default_currency: str | None = None,
    ) -> ProcessingResult:
        started_at = datetime.now(timezone.utc)
        frame = read_csv(payload)
        profiles = profile_dataframe(frame)
        mappings = map_columns(list(frame.columns), merchant_aliases)
        rename_map = apply_auto_mappings(list(frame.columns), mappings)
        mapped = frame.rename(columns=rename_map).copy()
        for field in CANONICAL_FIELDS:
            if field not in mapped.columns:
                mapped[field] = None
        validate_mapped_frame(mapped)

        normalized: list[dict[str, object]] = []
        traces = []
        validations = []
        raw_rows = []
        for position, (_, row) in enumerate(mapped.iterrows()):
            mapped_raw = {str(key): (None if pd.isna(value) else value) for key, value in row.items()}
            source_row = frame.iloc[position]
            raw = {str(key): (None if pd.isna(value) else value) for key, value in source_row.items()}
            values, row_traces = normalize_row(mapped_raw, default_currency)
            raw_rows.append(raw)
            normalized.append(values)
            traces.append(row_traces)
            validations.append(validate_normalized_row(values, row_traces))

        duplicates = {candidate.row_index: candidate for candidate in find_duplicate_candidates(normalized)}
        records: list[ProcessedRecord] = []
        for index, values in enumerate(normalized):
            duplicate = duplicates.get(index)
            entity_certainty = 0.0 if duplicate and duplicate.exact else 1.0 - duplicate.confidence if duplicate else 1.0
            quality = calculate_quality(values, mappings, traces[index], validations[index], entity_certainty)
            needs_review = bool(validations[index] or duplicate or quality.overall < SETTINGS.publishable_score_threshold)
            records.append(
                ProcessedRecord(
                    row_index=index,
                    raw_values=raw_rows[index],
                    canonical_values=values,
                    traces=traces[index],
                    validation_errors=validations[index],
                    quality=quality,
                    duplicate=duplicate,
                    route="human_review" if needs_review else "publishable",
                )
            )
        source_columns = set(frame.columns)
        exact_canonical = set(CANONICAL_FIELDS) & source_columns
        return ProcessingResult(
            profiles=profiles,
            mappings=mappings,
            records=records,
            missing_columns=[field for field in CANONICAL_FIELDS if field not in exact_canonical and field not in rename_map.values()],
            unexpected_columns=[column for column in frame.columns if column not in CANONICAL_FIELDS],
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            default_currency=default_currency.upper() if default_currency else None,
        )
