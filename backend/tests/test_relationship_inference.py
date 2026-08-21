import pytest
from app.services.relationship_inference_service import (
    relationship_inference_service,
    RelationshipInferenceService,
)


def test_signal_a_name_similarity():
    srv = RelationshipInferenceService()

    # Positive matches
    assert srv.calculate_name_similarity("customer_id", "orders", "id", "customers") >= 0.95
    assert srv.calculate_name_similarity("customerId", "orders", "id", "customers") >= 0.95
    assert srv.calculate_name_similarity("customer_id", "orders", "customer_id", "customers") >= 0.95
    assert srv.calculate_name_similarity("product_id", "order_items", "id", "products") >= 0.95

    # Low similarity for unrelated names
    assert srv.calculate_name_similarity("name", "customers", "amount", "orders") < 0.30
    assert srv.calculate_name_similarity("created_at", "users", "price", "products") < 0.30


def test_signal_b_datatype_compatibility():
    srv = RelationshipInferenceService()

    # Exact or same group compatible
    assert srv.calculate_datatype_compatibility("integer", "integer") == 1.0
    assert srv.calculate_datatype_compatibility("integer", "bigint") == 0.90
    assert srv.calculate_datatype_compatibility("varchar", "text") == 0.90
    assert srv.calculate_datatype_compatibility("uuid", "uuid") == 1.0

    # Incompatible
    assert srv.calculate_datatype_compatibility("integer", "date") == 0.0
    assert srv.calculate_datatype_compatibility("varchar", "integer") == 0.0


def test_signal_c_d_e_value_overlap_and_stats():
    srv = RelationshipInferenceService()

    orders_cust_ids = [1, 2, 1, 3, 2, 1, 3]
    customers_ids = [1, 2, 3, 4, 5]

    overlap, uniq_target, card_score, card_type = srv.calculate_value_overlap_and_stats(orders_cust_ids, customers_ids)

    # 100% of orders.customer_id values exist in customers.id
    assert overlap == 1.0
    # customers.id is 100% unique
    assert uniq_target == 1.0
    # Resembles many-to-one
    assert card_type == "many-to-one"
    assert card_score == 1.0


def test_edge_cases_null_and_empty_columns():
    srv = RelationshipInferenceService()

    # Columns with NULLs and empty strings
    vals_a = [1, None, 2, "", 3, None]
    vals_b = [1, 2, 3, 4, 5]

    overlap, uniq_target, card_score, card_type = srv.calculate_value_overlap_and_stats(vals_a, vals_b)
    assert overlap == 1.0
    assert uniq_target == 1.0


def test_edge_case_uuids_and_strings():
    srv = RelationshipInferenceService()

    uuid1 = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    uuid2 = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"
    uuid3 = "c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33"

    src_uuids = [uuid1, uuid2, uuid1]
    tgt_uuids = [uuid1, uuid2, uuid3]

    overlap, uniq_target, _, _ = srv.calculate_value_overlap_and_stats(src_uuids, tgt_uuids)
    assert overlap == 1.0
    assert uniq_target == 1.0


def test_negative_unrelated_coincidental_similarity():
    srv = RelationshipInferenceService()

    schema_info = {
        "tables": {
            "customers": {
                "columns": ["id", "name", "email"],
                "column_types": {"id": "integer", "name": "varchar", "email": "varchar"}
            },
            "products": {
                "columns": ["id", "product_name", "price"],
                "column_types": {"id": "integer", "product_name": "varchar", "price": "float"}
            }
        }
    }

    # Unrelated tables with generic 'id' and 'name' columns should not produce strong candidate relationship
    candidates = srv.detect_candidate_relationships(schema_info)
    strong_candidates = [c for c in candidates if c["confidence_level"] == "strong"]
    assert len(strong_candidates) == 0


def test_positive_multi_table_relationship_detection():
    srv = RelationshipInferenceService()

    schema_info = {
        "tables": {
            "customers": {
                "columns": ["id", "name", "city"],
                "column_types": {"id": "integer", "name": "varchar", "city": "varchar"}
            },
            "orders": {
                "columns": ["order_id", "customer_id", "amount"],
                "column_types": {"order_id": "integer", "customer_id": "integer", "amount": "float"}
            },
            "order_items": {
                "columns": ["item_id", "order_id", "product_id", "quantity"],
                "column_types": {"item_id": "integer", "order_id": "integer", "product_id": "integer", "quantity": "integer"}
            },
            "products": {
                "columns": ["id", "product_name", "price"],
                "column_types": {"id": "integer", "product_name": "varchar", "price": "float"}
            }
        }
    }

    sample_data = {
        "customers": {"id": [1, 2, 3, 4], "name": ["Alice", "Bob", "Charlie", "David"], "city": ["NY", "BOS", "SF", "LA"]},
        "orders": {"order_id": [101, 102, 103], "customer_id": [1, 2, 1], "amount": [500, 700, 200]},
        "order_items": {"item_id": [1, 2, 3], "order_id": [101, 101, 102], "product_id": [50, 51, 50], "quantity": [2, 1, 4]},
        "products": {"id": [50, 51, 52], "product_name": ["Laptop", "Mouse", "Keyboard"], "price": [1000, 25, 75]}
    }

    candidates = srv.detect_candidate_relationships(schema_info, sample_data)
    strong = [c for c in candidates if c["confidence_level"] == "strong"]

    # Verify orders.customer_id -> customers.id
    cust_rel = next((c for c in strong if c["source_table"] == "orders" and c["source_column"] == "customer_id"), None)
    assert cust_rel is not None
    assert cust_rel["target_table"] == "customers"
    assert cust_rel["target_column"] == "id"
    assert cust_rel["score"] >= 0.85

    # Verify order_items.order_id -> orders.order_id
    order_rel = next((c for c in strong if c["source_table"] == "order_items" and c["source_column"] == "order_id"), None)
    assert order_rel is not None
    assert order_rel["target_table"] == "orders"
    assert order_rel["target_column"] == "order_id"
    assert order_rel["score"] >= 0.85

    # Verify order_items.product_id -> products.id
    prod_rel = next((c for c in strong if c["source_table"] == "order_items" and c["source_column"] == "product_id"), None)
    assert prod_rel is not None
    assert prod_rel["target_table"] == "products"
    assert prod_rel["target_column"] == "id"
    assert prod_rel["score"] >= 0.85
