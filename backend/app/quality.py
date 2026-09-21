from __future__ import annotations

from statistics import mean

from .config import REQUIRED_FIELDS, SETTINGS
from .domain import MappingCandidate, NormalizationTrace, QualityComponent, QualityScore


def calculate_quality(
    values: dict[str, object],
    mappings: list[MappingCandidate],
    traces: list[NormalizationTrace],
    validation_errors: list[str],
    entity_certainty: float = 1.0,
) -> QualityScore:
    applied = [mapping.confidence for mapping in mappings if mapping.auto_applied]
    mapping_score = mean(applied) if applied else 0.0
    present = sum(1 for field in REQUIRED_FIELDS if values.get(field) not in (None, ""))
    completeness = present / len(REQUIRED_FIELDS)
    validity = max(0.0, 1.0 - min(1.0, len(validation_errors) / len(REQUIRED_FIELDS)))
    trace_certainties = [trace.certainty for trace in traces]
    normalization = mean(trace_certainties) if trace_certainties else 1.0

    raw = {
        "schema_mapping": (mapping_score, [] if mapping_score >= 0.9 else ["One or more source fields have uncertain mappings"]),
        "required_completeness": (completeness, [f"{len(REQUIRED_FIELDS) - present} required field(s) missing"] if present < len(REQUIRED_FIELDS) else []),
        "value_validity": (validity, validation_errors),
        "normalization_certainty": (normalization, [trace.rule for trace in traces if trace.certainty < 0.9]),
        "entity_certainty": (entity_certainty, ["Possible duplicate requires review"] if entity_certainty < 1.0 else []),
    }
    components = {
        name: QualityComponent(score=round(score, 4), weight=SETTINGS.quality_weights[name], reasons=reasons)
        for name, (score, reasons) in raw.items()
    }
    overall = sum(component.score * component.weight for component in components.values())
    return QualityScore(overall=round(overall, 4), components=components)
