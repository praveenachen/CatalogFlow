from decimal import Decimal

import pandas as pd
import pytest
from pydantic import ValidationError

from app.domain import CanonicalProduct
from app.matching import find_duplicate_candidates
from app.normalization import normalize_category, normalize_inventory, normalize_price, normalize_tags
from app.processing import PandasCatalogProcessor
from app.profiling import profile_dataframe
from app.quality import calculate_quality
from app.schema_mapping import map_columns


def test_canonical_contract_validates_values():
    product = CanonicalProduct(product_name="Boot", price=Decimal("19.99"), currency="usd", inventory=2)
    assert product.currency == "USD"
    with pytest.raises(ValidationError):
        CanonicalProduct(product_name="", price=Decimal("-1"), currency="US")


def test_profiling_is_deterministic_and_reports_validity():
    frame = pd.DataFrame({"cost": ["$1.00", None, "bad"], "item": ["A", "A", "B"]})
    profiles = {profile.source_name: profile for profile in profile_dataframe(frame)}
    assert profiles["cost"].null_percentage == 33.33
    assert profiles["cost"].validity_rate == 0.5
    assert profiles["item"].unique_percentage == 66.67


def test_mapping_stages_exact_alias_fuzzy_and_unresolved():
    mappings = {mapping.source_field: mapping for mapping in map_columns(["price", "item_name", "product_nam", "mystery_xyz"])}
    assert mappings["price"].method == "exact"
    assert mappings["item_name"].canonical_field == "product_name"
    assert mappings["item_name"].method == "alias"
    assert mappings["product_nam"].method == "fuzzy"
    assert mappings["mystery_xyz"].method == "unresolved"
    assert not mappings["mystery_xyz"].auto_applied


def test_normalization_is_traceable_and_rejects_invalid_values():
    price, price_trace = normalize_price("$1,299.00")
    inventory, inventory_trace = normalize_inventory("018 units")
    tags, _ = normalize_tags("#SALE | Summer | sale")
    category, _ = normalize_category(" womens shoes ")
    assert price == Decimal("1299.00") and price_trace.original_value == "$1,299.00"
    assert inventory == 18 and inventory_trace.rule == "strip_inventory_unit"
    assert tags == ["sale", "summer"]
    assert category == "Footwear"
    assert normalize_price("free-ish")[0] is None
    assert normalize_inventory("many")[0] is None


def test_exact_and_fuzzy_duplicate_candidates_do_not_merge():
    records = [
        {"sku": "A-1", "product_name": "Trail Shoe", "category": "Footwear"},
        {"sku": "A-1", "product_name": "Different", "category": "Footwear"},
        {"sku": "B-2", "product_name": "Trail Shoes", "category": "Footwear"},
    ]
    candidates = find_duplicate_candidates(records)
    assert candidates[0].method == "exact_sku" and candidates[0].exact
    assert candidates[1].method == "fuzzy_product_name" and not candidates[1].exact
    assert len(records) == 3


def test_component_quality_score_is_weighted_and_explainable():
    mappings = map_columns(["product_name", "price", "currency"])
    result = calculate_quality(
        {"product_name": "Shoe", "price": Decimal("10"), "currency": "USD"},
        mappings,
        [],
        [],
    )
    assert result.overall == 1.0
    assert set(result.components) == {"schema_mapping", "required_completeness", "value_validity", "normalization_certainty", "entity_certainty"}
    assert sum(component.weight for component in result.components.values()) == 1.0


def test_processor_runs_batch_end_to_end():
    payload = b"sku,item_name,product_type,cost,currency,stock,labels\nA1,trail shoe,womens shoes,$12.50,usd,018 units,#SALE|summer\n"
    result = PandasCatalogProcessor().process(payload)
    assert result.records[0].canonical_values["sku"] == "A1"
    assert result.records[0].canonical_values["product_name"] == "Trail Shoe"
    assert result.records[0].canonical_values["category"] == "Footwear"
    assert result.records[0].canonical_values["inventory"] == 18
    assert result.records[0].raw_values["cost"] == "$12.50"


def test_currency_priority_and_provenance():
    explicit = PandasCatalogProcessor().process(
        b"product_name,price,currency\nBoot,10,CAD\n",
        default_currency="USD",
    ).records[0]
    assert explicit.canonical_values["currency"] == "CAD"
    assert next(trace for trace in explicit.traces if trace.field == "currency").rule == "explicit_source_currency"

    configured = PandasCatalogProcessor().process(
        b"product_name,price\nBoot,10\n",
        default_currency="USD",
    ).records[0]
    configured_trace = next(trace for trace in configured.traces if trace.field == "currency")
    assert configured.canonical_values["currency"] == "USD"
    assert configured_trace.original_value is None
    assert configured_trace.rule == "configured_default_currency"

    missing = PandasCatalogProcessor().process(b"product_name,price\nBoot,10\n").records[0]
    assert missing.canonical_values["currency"] is None
    assert any(error.startswith("currency:") for error in missing.validation_errors)
    assert next(trace for trace in missing.traces if trace.field == "currency").rule == "missing_currency"
