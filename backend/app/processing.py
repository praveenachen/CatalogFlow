from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json

import pandas as pd

from .config import CANONICAL_FIELDS, SETTINGS
from .domain import (
    ProcessedRecord,
    ProcessingRequest,
    ProcessingResult,
    ProcessorStatus,
    ProcessorSubmission,
    RunStatus,
)
from .ingestion import read_csv
from .matching import find_duplicate_candidates
from .normalization import normalize_row
from .profiling import profile_dataframe
from .quality import calculate_quality
from .schema_mapping import apply_auto_mappings, map_columns
from .validation import validate_mapped_frame, validate_normalized_row


class CatalogProcessor(ABC):
    processor_type = "base"
    asynchronous = False

    @abstractmethod
    def process(
        self,
        payload: bytes,
        merchant_aliases: dict[str, str] | None = None,
        default_currency: str | None = None,
    ) -> ProcessingResult:
        raise NotImplementedError

    def submit(self, request: ProcessingRequest) -> ProcessorSubmission:
        if request.payload is None:
            raise ValueError("Local processing requires the source payload.")
        result = self.process(request.payload, default_currency=request.default_currency)
        return ProcessorSubmission(status=RunStatus.completed, result=result)

    def refresh(self, external_run_id: str) -> ProcessorStatus:
        raise NotImplementedError("This processor does not expose asynchronous runs.")


class PandasCatalogProcessor(CatalogProcessor):
    processor_type = "local"

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


class DatabricksCatalogProcessor(CatalogProcessor):
    processor_type = "databricks"
    asynchronous = True

    def __init__(
        self,
        job_id: int,
        host: str | None = None,
        token: str | None = None,
        workspace_client=None,
    ) -> None:
        if not job_id:
            raise ValueError("DATABRICKS_JOB_ID is required for Databricks processing.")
        if workspace_client is None:
            from databricks.sdk import WorkspaceClient

            arguments = {key: value for key, value in {"host": host, "token": token}.items() if value}
            workspace_client = WorkspaceClient(**arguments)
        self.job_id = job_id
        self.client = workspace_client

    def process(
        self,
        payload: bytes,
        merchant_aliases: dict[str, str] | None = None,
        default_currency: str | None = None,
    ) -> ProcessingResult:
        raise NotImplementedError("Databricks processing is asynchronous; call submit().")

    def submit(self, request: ProcessingRequest) -> ProcessorSubmission:
        response = self.client.jobs.run_now(
            job_id=self.job_id,
            job_parameters={
                "batch_id": str(request.batch_id),
                "merchant_id": str(request.merchant_id or "default"),
                "raw_uri": request.raw_uri,
                "processed_uri": request.processed_uri,
                "curated_uri": request.curated_uri,
                "default_currency": request.default_currency or "",
            },
        )
        run_id = getattr(response, "run_id", None)
        if run_id is None and getattr(response, "response", None) is not None:
            run_id = getattr(response.response, "run_id", None)
        if run_id is None:
            raise RuntimeError("Databricks submission did not return a run_id.")
        return ProcessorSubmission(status=RunStatus.submitted, external_run_id=str(run_id))

    def refresh(self, external_run_id: str) -> ProcessorStatus:
        run = self.client.jobs.get_run(int(external_run_id))
        state = getattr(run, "state", None)
        lifecycle = _enum_value(getattr(state, "life_cycle_state", None))
        result = _enum_value(getattr(state, "result_state", None))
        message = getattr(state, "state_message", None)
        if lifecycle in {"QUEUED", "PENDING", "BLOCKED", "WAITING_FOR_RETRY"}:
            status = RunStatus.submitted
        elif lifecycle in {"RUNNING", "TERMINATING"}:
            status = RunStatus.running
        elif lifecycle in {"CANCELED", "CANCELLING"} or result == "CANCELED":
            status = RunStatus.cancelled
        elif lifecycle in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            status = RunStatus.completed if result == "SUCCESS" else RunStatus.failed
        else:
            status = RunStatus.submitted
        error_code = result if status == RunStatus.failed else None
        metadata = {"lifecycle_state": lifecycle, "result_state": result}
        if status == RunStatus.completed:
            metadata.update(self._result_metadata(int(external_run_id)))
        return ProcessorStatus(
            status=status,
            error_code=error_code,
            error_message=message if status in {RunStatus.failed, RunStatus.cancelled} else None,
            result_metadata=metadata,
        )

    def _result_metadata(self, run_id: int) -> dict:
        """Read a JSON task result when the configured job publishes one."""
        try:
            output = self.client.jobs.get_run_output(run_id)
        except Exception as exc:
            return {"output_available": False, "output_error": type(exc).__name__}
        notebook = getattr(output, "notebook_output", None)
        raw = getattr(notebook, "result", None) if notebook is not None else None
        if not raw:
            return {"output_available": False}
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {"output_available": True, "output_format": "non_json"}
        return {"output_available": True, **parsed} if isinstance(parsed, dict) else {
            "output_available": True,
            "output": parsed,
        }


def _enum_value(value) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw).upper()
