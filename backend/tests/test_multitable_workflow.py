import pytest
from uuid import uuid4
from app.services.relationship_service import relationship_service
from app.services.rag_service import rag_service
from app.services.sql_service import sql_service
from app.utils.sql_validator import validate_sql_query
from app.schemas.query import QueryRequest
from app.routers.query import _qualify_sql_tables


def test_relationship_service_fk_graph():
    schema_info = {
        "tables": {
            "customers": {
                "columns": ["id", "name", "city"],
                "foreign_keys": []
            },
            "orders": {
                "columns": ["id", "customer_id", "total_amount"],
                "foreign_keys": [
                    {"column": "customer_id", "foreign_table": "customers", "foreign_column": "id"}
                ]
            },
            "order_items": {
                "columns": ["id", "order_id", "product_id", "quantity"],
                "foreign_keys": [
                    {"column": "order_id", "foreign_table": "orders", "foreign_column": "id"},
                    {"column": "product_id", "foreign_table": "products", "foreign_column": "id"}
                ]
            },
            "products": {
                "columns": ["id", "name", "price"],
                "foreign_keys": []
            }
        }
    }

    # 1. Build FK graph
    graph = relationship_service.build_fk_graph(schema_info)
    assert "orders" in graph
    assert "order_items" in graph
    assert "customers" in graph

    # Check forward and reverse edges
    orders_to = [e["to_table"] for e in graph["orders"]]
    assert "customers" in orders_to
    assert "order_items" in orders_to

    # 2. Test connected tables via BFS
    connected_from_orders = relationship_service.get_connected_tables(["orders"], graph, max_hops=2)
    assert connected_from_orders == {"orders", "customers", "order_items", "products"}

    # 3. Format relationship map
    rel_map = relationship_service.format_relationship_map(schema_info)
    assert "Relationships" in rel_map
    assert "orders.customer_id -> customers.id" in rel_map
    assert "order_items.order_id -> orders.id" in rel_map
    assert "order_items.product_id -> products.id" in rel_map


def test_infer_csv_relationships():
    # Plain CSV schemas without explicit SQL Foreign Key constraints
    csv_schema = {
        "tables": {
            "hr": {
                "columns": ["id", "employee_name", "department_id", "salary"],
                "foreign_keys": []
            },
            "departments": {
                "columns": ["id", "department_name", "location"],
                "foreign_keys": []
            }
        }
    }

    inferred = relationship_service.infer_csv_relationships(csv_schema)
    assert len(inferred) == 1
    assert inferred[0]["table"] == "hr"
    assert inferred[0]["column"] == "department_id"
    assert inferred[0]["foreign_table"] == "departments"
    assert inferred[0]["foreign_column"] == "id"

    rel_map = relationship_service.format_relationship_map(csv_schema)
    assert "hr.department_id -> departments.id" in rel_map


def test_query_request_schema():
    uid1 = uuid4()
    uid2 = uuid4()

    # Test single db_id backward compatibility
    req1 = QueryRequest(db_id=uid1, question="Total revenue by customer?")
    assert req1.resolved_db_ids == [uid1]

    # Test multi db_ids
    req2 = QueryRequest(db_ids=[uid1, uid2], question="Cross table analytics?")
    assert req2.resolved_db_ids == [uid1, uid2]

    # Test validation error when neither provided
    with pytest.raises(ValueError):
        QueryRequest(question="Invalid request?")


def test_sql_qualification_multitable():
    schema = "user_schema_123"
    valid_tables = {"customers", "orders", "order_items"}
    
    table_schema_map = {
        "customers": "user_schema_123",
        "orders": "user_schema_123",
        "order_items": "user_schema_456" # Multi-datasource table in different schema
    }

    sql = 'SELECT c.name, SUM(o.total_amount) FROM customers c JOIN orders o ON c.id = o.customer_id JOIN order_items oi ON o.id = oi.order_id GROUP BY c.name;'
    
    qualified = _qualify_sql_tables(sql, schema, valid_tables, table_schema_map)

    assert '"user_schema_123"."customers"' in qualified
    assert '"user_schema_123"."orders"' in qualified
    assert '"user_schema_456"."order_items"' in qualified


def test_multitable_sql_validator():
    schema_info = {
        "tables": {
            "customers": {"columns": ["id", "name", "city"]},
            "orders": {"columns": ["id", "customer_id", "total_amount", "order_date"]},
            "order_items": {"columns": ["id", "order_id", "product_id", "quantity"]}
        }
    }

    # Valid INNER JOIN
    sql1 = 'SELECT c.name, o.total_amount FROM customers c INNER JOIN orders o ON c.id = o.customer_id;'
    is_valid, err, invalid_id = validate_sql_query(sql1, schema_info=schema_info)
    assert is_valid, f"Expected valid SQL, got error: {err}"

    # Valid CTE
    sql2 = 'WITH top_customers AS (SELECT customer_id, SUM(total_amount) AS total FROM orders GROUP BY customer_id) SELECT c.name, tc.total FROM customers c JOIN top_customers tc ON c.id = tc.customer_id;'
    is_valid2, err2, invalid_id2 = validate_sql_query(sql2, schema_info=schema_info)
    assert is_valid2, f"Expected valid CTE SQL, got error: {err2}"

    # Invalid table reference in JOIN
    sql3 = 'SELECT c.name, s.shipment_date FROM customers c JOIN shipments s ON c.id = s.customer_id;'
    is_valid3, err3, invalid_id3 = validate_sql_query(sql3, schema_info=schema_info)
    assert not is_valid3
    assert invalid_id3 == "shipments"


def test_rag_prompt_with_relationship_map():
    schema_context = 'Table: "orders"\nColumns: "id", "customer_id"'
    rel_map = "Relationships (Foreign Keys):\n  orders.customer_id -> customers.id"
    
    prompt = sql_service._build_rag_prompt(
        schema_context=schema_context,
        user_question="Show orders with customer names",
        retrieved_examples=[],
        relationship_map=rel_map
    )

    assert "LIVE UPLOADED DATABASE SCHEMA" in prompt
    assert rel_map in prompt
    assert "JOIN Rule: When joining tables, use explicit JOIN ... ON syntax." in prompt
