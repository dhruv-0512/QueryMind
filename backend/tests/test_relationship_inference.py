import pytest
from app.services.relationship_inference_service import (
    relationship_inference_service,
    RelationshipInferenceService,
)


def test_should_detect_legitimate_fk():
    schema_info = {
        "tables": {
            "customers": {
                "columns": ["id", "name"],
                "column_types": {"id": "integer", "name": "varchar"}
            },
            "orders": {
                "columns": ["order_id", "customer_id", "amount"],
                "column_types": {"order_id": "integer", "customer_id": "integer", "amount": "float"}
            }
        }
    }

    sample_data = {
        "customers": {"id": [1, 2, 3, 4], "name": ["Alice", "Bob", "Charlie", "David"]},
        "orders": {"order_id": [101, 102, 103], "customer_id": [1, 2, 1], "amount": [500, 700, 200]}
    }

    candidates = relationship_inference_service.detect_candidate_relationships(schema_info, sample_data)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand["source_table"] == "orders"
    assert cand["source_column"] == "customer_id"
    assert cand["target_table"] == "customers"
    assert cand["target_column"] == "id"
    assert cand["overlap"] == 1.0


def test_should_detect_product_order_items_fk():
    schema_info = {
        "tables": {
            "products": {
                "columns": ["id", "product_name"],
                "column_types": {"id": "integer", "product_name": "varchar"}
            },
            "order_items": {
                "columns": ["item_id", "order_id", "product_id", "quantity"],
                "column_types": {"item_id": "integer", "order_id": "integer", "product_id": "integer", "quantity": "integer"}
            }
        }
    }

    sample_data = {
        "products": {"id": [10, 20, 30], "product_name": ["Laptop", "Mouse", "Keyboard"]},
        "order_items": {"item_id": [1, 2], "order_id": [501, 501], "product_id": [10, 20], "quantity": [1, 2]}
    }

    candidates = relationship_inference_service.detect_candidate_relationships(schema_info, sample_data)
    assert len(candidates) == 1
    assert candidates[0]["source_table"] == "order_items"
    assert candidates[0]["source_column"] == "product_id"
    assert candidates[0]["target_table"] == "products"
    assert candidates[0]["target_column"] == "id"


def test_should_detect_camelcase_and_key_suffixes():
    srv = RelationshipInferenceService()

    # camelCase customerId -> customers.id
    schema_camel = {
        "tables": {
            "customers": {"columns": ["id", "name"], "column_types": {"id": "integer", "name": "varchar"}},
            "orders": {"columns": ["orderId", "customerId", "amount"], "column_types": {"orderId": "integer", "customerId": "integer", "amount": "float"}}
        }
    }
    sample_camel = {
        "customers": {"id": [1, 2, 3]},
        "orders": {"customerId": [1, 2, 1]}
    }
    c_camel = srv.detect_candidate_relationships(schema_camel, sample_camel)
    assert len(c_camel) == 1
    assert c_camel[0]["source_column"] == "customerId"

    # key suffix customer_key -> customers.id
    schema_key = {
        "tables": {
            "customers": {"columns": ["id", "name"], "column_types": {"id": "integer", "name": "varchar"}},
            "orders": {"columns": ["order_id", "customer_key", "amount"], "column_types": {"order_id": "integer", "customer_key": "integer", "amount": "float"}}
        }
    }
    sample_key = {
        "customers": {"id": [1, 2, 3]},
        "orders": {"customer_key": [1, 2, 1]}
    }
    c_key = srv.detect_candidate_relationships(schema_key, sample_key)
    assert len(c_key) == 1
    assert c_key[0]["source_column"] == "customer_key"


def test_should_not_detect_attribute_columns():
    srv = RelationshipInferenceService()

    # Name matching
    c1 = srv.detect_candidate_relationships({"tables": {"table_a": {"columns": ["name"]}, "table_b": {"columns": ["name"]}}})
    assert len(c1) == 0

    # Email matching
    c2 = srv.detect_candidate_relationships({"tables": {"table_a": {"columns": ["email"]}, "table_b": {"columns": ["email"]}}})
    assert len(c2) == 0

    # Created at matching
    c3 = srv.detect_candidate_relationships({"tables": {"table_a": {"columns": ["created_at"]}, "table_b": {"columns": ["created_at"]}}})
    assert len(c3) == 0

    # Prospect company matching
    c4 = srv.detect_candidate_relationships({"tables": {"table_a": {"columns": ["prospect_company"]}, "table_b": {"columns": ["prospect_company"]}}})
    assert len(c4) == 0

    # Phone matching
    c5 = srv.detect_candidate_relationships({"tables": {"table_a": {"columns": ["phone"]}, "table_b": {"columns": ["phone"]}}})
    assert len(c5) == 0


def test_value_overlap_threshold_filtering():
    srv = RelationshipInferenceService(min_overlap=0.80)

    schema_info = {
        "tables": {
            "customers": {"columns": ["id"], "column_types": {"id": "integer"}},
            "orders": {"columns": ["customer_id"], "column_types": {"customer_id": "integer"}}
        }
    }

    # Low overlap (< 80%) -> Should be ignored
    low_overlap_sample = {
        "customers": {"id": [10, 20, 30]},
        "orders": {"customer_id": [1, 2, 3, 10]}  # Only 1 of 4 distinct values overlap = 25%
    }
    c_low = srv.detect_candidate_relationships(schema_info, low_overlap_sample)
    assert len(c_low) == 0

    # High overlap (>= 80%) -> Should be detected
    high_overlap_sample = {
        "customers": {"id": [1, 2, 3, 4]},
        "orders": {"customer_id": [1, 2, 3, 1]}  # 3 of 3 distinct values overlap = 100%
    }
    c_high = srv.detect_candidate_relationships(schema_info, high_overlap_sample)
    assert len(c_high) == 1
