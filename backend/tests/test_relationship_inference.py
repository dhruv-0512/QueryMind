import pytest
from app.services.relationship_inference_service import (
    relationship_inference_service,
    RelationshipInferenceService,
)


def test_attribute_column_rejection():
    srv = RelationshipInferenceService()

    # Attribute columns must be identified correctly
    assert srv.is_attribute_column("prospect_full_name")
    assert srv.is_attribute_column("prospect_job_title")
    assert srv.is_attribute_column("prospect_company")
    assert srv.is_attribute_column("prospect_linkedin")
    assert srv.is_attribute_column("contact_emails")
    assert srv.is_attribute_column("contact_mobile_phone")
    assert srv.is_attribute_column("created_at")
    assert srv.is_attribute_column("updated_at")

    # Key columns must NOT be marked as attributes
    assert not srv.is_attribute_column("customer_id")
    assert not srv.is_attribute_column("order_id")
    assert not srv.is_attribute_column("product_id")
    assert not srv.is_attribute_column("id")


def test_key_candidate_identification():
    srv = RelationshipInferenceService()

    assert srv.is_key_candidate("customer_id")
    assert srv.is_key_candidate("order_id")
    assert srv.is_key_candidate("product_id")
    assert srv.is_key_candidate("user_uuid")
    assert srv.is_key_candidate("id")

    assert not srv.is_key_candidate("prospect_full_name")
    assert not srv.is_key_candidate("contact_emails")
    assert not srv.is_key_candidate("created_at")


def test_hard_negative_1_identical_attribute_columns():
    schema_info = {
        "tables": {
            "table_a": {"columns": ["prospect_company", "contact_person"], "column_types": {"prospect_company": "varchar", "contact_person": "varchar"}},
            "table_b": {"columns": ["prospect_company", "address"], "column_types": {"prospect_company": "varchar", "address": "varchar"}}
        }
    }
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info)
    assert len(candidates) == 0


def test_hard_negative_2_identical_timestamps():
    schema_info = {
        "tables": {
            "table_a": {"columns": ["created_at", "updated_at"], "column_types": {"created_at": "timestamp", "updated_at": "timestamp"}},
            "table_b": {"columns": ["created_at", "deleted_at"], "column_types": {"created_at": "timestamp", "deleted_at": "timestamp"}}
        }
    }
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info)
    assert len(candidates) == 0


def test_hard_negative_3_identical_emails():
    schema_info = {
        "tables": {
            "table_a": {"columns": ["contact_email", "work_email"], "column_types": {"contact_email": "varchar", "work_email": "varchar"}},
            "table_b": {"columns": ["contact_email", "personal_email"], "column_types": {"contact_email": "varchar", "personal_email": "varchar"}}
        }
    }
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info)
    assert len(candidates) == 0


def test_hard_negative_4_identical_phone_numbers():
    schema_info = {
        "tables": {
            "table_a": {"columns": ["contact_mobile_phone"], "column_types": {"contact_mobile_phone": "varchar"}},
            "table_b": {"columns": ["contact_mobile_phone"], "column_types": {"contact_mobile_phone": "varchar"}}
        }
    }
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info)
    assert len(candidates) == 0


def test_hard_negative_5_identical_full_names():
    schema_info = {
        "tables": {
            "table_a": {"columns": ["full_name"], "column_types": {"full_name": "varchar"}},
            "table_b": {"columns": ["full_name"], "column_types": {"full_name": "varchar"}}
        }
    }
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info)
    assert len(candidates) == 0


def test_realistic_hr_prospect_contact_dataset_no_false_positives():
    schema_info = {
        "tables": {
            "hr_prospect_data": {
                "columns": [
                    "prospect_full_name", "prospect_job_title", "prospect_linkedin",
                    "prospect_company", "prospect_country", "created_at"
                ],
                "column_types": {
                    "prospect_full_name": "varchar", "prospect_job_title": "varchar",
                    "prospect_linkedin": "varchar", "prospect_company": "varchar",
                    "prospect_country": "varchar", "created_at": "timestamp"
                }
            },
            "hr_contact_data": {
                "columns": [
                    "prospect_full_name", "prospect_company_name", "contact_emails",
                    "contact_mobile_phone", "prospect_company_website", "created_at"
                ],
                "column_types": {
                    "prospect_full_name": "varchar", "prospect_company_name": "varchar",
                    "contact_emails": "varchar", "contact_mobile_phone": "varchar",
                    "prospect_company_website": "varchar", "created_at": "timestamp"
                }
            }
        }
    }

    sample_data = {
        "hr_prospect_data": {
            "prospect_full_name": ["Alice Smith", "Bob Jones"],
            "prospect_job_title": ["Software Engineer", "Product Manager"],
            "prospect_linkedin": ["linkedin.com/in/alice", "linkedin.com/in/bob"],
            "prospect_company": ["Google", "Microsoft"],
            "created_at": ["2024-01-01", "2024-01-02"]
        },
        "hr_contact_data": {
            "prospect_full_name": ["Alice Smith", "Bob Jones"],
            "prospect_company_name": ["Google", "Microsoft"],
            "contact_emails": ["alice@google.com", "bob@msft.com"],
            "contact_mobile_phone": ["+1234567890", "+1987654321"],
            "created_at": ["2024-01-01", "2024-01-02"]
        }
    }

    candidates = relationship_inference_service.detect_candidate_relationships(schema_info, sample_data)
    # Must produce ZERO false positive candidate relationships!
    assert len(candidates) == 0


def test_legitimate_foreign_key_detection():
    schema_info = {
        "tables": {
            "customers": {
                "columns": ["id", "name", "city"],
                "column_types": {"id": "integer", "name": "varchar", "city": "varchar"}
            },
            "orders": {
                "columns": ["order_id", "customer_id", "amount"],
                "column_types": {"order_id": "integer", "customer_id": "integer", "amount": "float"}
            }
        }
    }

    sample_data = {
        "customers": {"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "city": ["NY", "BOS", "SF"]},
        "orders": {"order_id": [101, 102, 103], "customer_id": [1, 2, 1], "amount": [500, 700, 200]}
    }

    candidates = relationship_inference_service.detect_candidate_relationships(schema_info, sample_data)
    assert len(candidates) == 1

    cand = candidates[0]
    assert cand["source_table"] == "orders"
    assert cand["source_column"] == "customer_id"
    assert cand["target_table"] == "customers"
    assert cand["target_column"] == "id"
    assert cand["score"] >= 0.85
    assert cand["confidence_level"] == "strong"
