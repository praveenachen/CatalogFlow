# Databricks notebook source
"""Databricks notebook-task entry point for the CatalogFlow medallion pipeline.

Install the CatalogFlow backend package on the job cluster. Configure this file as
the job's notebook/source task and pass the parameters submitted by
DatabricksCatalogProcessor. The task deliberately imports the same deterministic
processor and projection contract used by local execution so business rules do
not silently diverge.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from app.pipeline_contract import gold_rows, result_metrics, silver_rows
from app.processing import PandasCatalogProcessor


PARAMETERS = ("batch_id", "merchant_id", "raw_uri", "processed_uri", "curated_uri", "default_currency")


def _parameter(name: str) -> str:
    dbutils.widgets.text(name, "")  # type: ignore[name-defined]  # provided by Databricks
    return dbutils.widgets.get(name)  # type: ignore[name-defined]


def _json_text(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, sort_keys=True)


def _delta_frame(rows: list[dict], schema_name: str):
    schemas = {
        "silver": "batch_id long, merchant_id long, source_row_id long, raw_values string, "
                  "canonical_values string, normalization_trace string, validation_issues array<string>, "
                  "quality_components string, automation_confidence double, automation_status string, "
                  "review_status string, duplicate string",
        "gold": "batch_id long, merchant_id long, source_row_id long, sku string, product_name string, "
                "description string, category string, price decimal(38,18), currency string, inventory long, "
                "tags array<string>, automation_confidence double, automation_status string, review_status string",
    }

    if schema_name not in schemas:
        raise ValueError(f"Unsupported Delta schema: {schema_name}")

    if not rows:
        # Keep an explicit schema even for empty outputs so an empty Gold dataset
        # cannot be mistaken for a missing/partially written result.
        return spark.createDataFrame([], schemas[schema_name])  # type: ignore[name-defined]

    if schema_name == "silver":
        normalized_rows = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "raw_values": _json_text(row.get("raw_values")),
                    "canonical_values": _json_text(row.get("canonical_values")),
                    "normalization_trace": _json_text(row.get("normalization_trace")),
                    "validation_issues": [str(issue) for issue in (row.get("validation_issues") or [])],
                    "quality_components": _json_text(row.get("quality_components")),
                    "duplicate": _json_text(row.get("duplicate")),
                }
            )
    else:
        # Gold rows are already canonical scalar/list values. Preserve Decimal and
        # integer types and only normalize tags so Spark can apply the explicit schema.
        normalized_rows = []
        for row in rows:
            normalized_rows.append(
                {
                    **row,
                    "tags": [str(tag) for tag in (row.get("tags") or [])],
                }
            )

    return spark.createDataFrame(normalized_rows, schemas[schema_name])  # type: ignore[name-defined]

def run() -> dict:
    values = {name: _parameter(name) for name in PARAMETERS}
    batch_id = int(values["batch_id"])
    merchant_id = None if values["merchant_id"] in {"", "default"} else int(values["merchant_id"])

    # Binary ingestion preserves the exact uploaded bytes. The raw S3 object is
    # immutable; Bronze adds replay metadata without rewriting the source object.
    binary = spark.read.format("binaryFile").load(values["raw_uri"]).first()  # type: ignore[name-defined]
    payload = bytes(binary.content)
    ingested_at = datetime.now(timezone.utc).isoformat()
    bronze_uri = values["processed_uri"].rsplit("/", 1)[0] + "/bronze.delta"
    bronze = spark.createDataFrame(  # type: ignore[name-defined]
        [(batch_id, merchant_id, values["raw_uri"], ingested_at, payload)],
        "batch_id long, merchant_id long, raw_uri string, ingested_at string, source_bytes binary",
    )
    bronze.write.format("delta").mode("overwrite").save(bronze_uri)

    result = PandasCatalogProcessor().process(payload, default_currency=values["default_currency"] or None)
    silver = silver_rows(result, batch_id, merchant_id)
    gold = gold_rows(result, batch_id, merchant_id)
    _delta_frame(silver, "silver").write.format("delta").mode("overwrite").save(values["processed_uri"])

    metrics = result_metrics(result)
    metrics.update(
        {
            "batch_id": batch_id,
            "merchant_id": merchant_id,
            "bronze_uri": bronze_uri,
            "processed_uri": values["processed_uri"],
            "curated_uri": values["curated_uri"],
        }
    )
    metrics_uri = values["curated_uri"].rsplit("/", 1)[0] + "/batch_quality_metrics.delta"
    spark.createDataFrame([(batch_id, json.dumps(metrics, sort_keys=True))], "batch_id long, metrics_json string").write.format(  # type: ignore[name-defined]
        "delta"
    ).mode("overwrite").save(metrics_uri)
    # Gold is deliberately the final data write. API workflow state only treats it
    # as successful after the Databricks run itself reaches terminal SUCCESS.
    _delta_frame(gold, "gold").write.format("delta").mode("overwrite").save(values["curated_uri"])
    return {"quality_metrics": metrics, "metrics_uri": metrics_uri}


if __name__ == "__main__":
    output = run()
    dbutils.notebook.exit(json.dumps(output, sort_keys=True))  # type: ignore[name-defined]
