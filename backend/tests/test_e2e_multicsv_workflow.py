import pytest
import sqlite3
from app.services.relationship_inference_service import relationship_inference_service
from app.services.relationship_service import relationship_service
from app.services.sql_service import sql_service
from app.utils.sql_validator import validate_sql_query
from app.routers.query import _qualify_sql_tables


@pytest.fixture
def multicsv_database():
    """Setup SQLite database simulating 5 uploaded CSV tables."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE categories (
        category_id INTEGER PRIMARY KEY,
        category_name TEXT NOT NULL
    );

    CREATE TABLE products (
        id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        price REAL NOT NULL
    );

    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        city TEXT NOT NULL
    );

    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        total_amount REAL NOT NULL
    );

    CREATE TABLE order_items (
        item_id INTEGER PRIMARY KEY,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL
    );
    """)

    cursor.executemany("INSERT INTO categories VALUES (?, ?)", [
        (1, "Electronics"), (2, "Apparel"), (3, "Home & Garden")
    ])
    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", [
        (101, 1, "Laptop Pro", 1200.0),
        (102, 1, "Wireless Mouse", 25.0),
        (103, 2, "Cotton T-Shirt", 18.0),
        (104, 3, "Garden Shears", 35.0)
    ])
    cursor.executemany("INSERT INTO customers VALUES (?, ?, ?)", [
        (1, "Alice Smith", "New York"),
        (2, "Bob Jones", "Boston"),
        (3, "Charlie Brown", "San Francisco")
    ])
    cursor.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", [
        (5001, 1, "2024-01-10", 1225.0),
        (5002, 2, "2024-01-12", 35.0),
        (5003, 1, "2024-02-01", 18.0)
    ])
    cursor.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", [
        (1, 5001, 101, 1, 1200.0),
        (2, 5001, 102, 1, 25.0),
        (3, 5002, 104, 1, 35.0),
        (4, 5003, 103, 1, 18.0)
    ])
    conn.commit()
    return conn


def test_e2e_multi_csv_relationship_detection_and_query_workflow(multicsv_database):
    # 1. Profile schemas & sample data
    schema_info = {
        "tables": {
            "categories": {"columns": ["category_id", "category_name"], "column_types": {"category_id": "integer", "category_name": "varchar"}},
            "products": {"columns": ["id", "category_id", "product_name", "price"], "column_types": {"id": "integer", "category_id": "integer", "product_name": "varchar", "price": "float"}},
            "customers": {"columns": ["id", "name", "city"], "column_types": {"id": "integer", "name": "varchar", "city": "varchar"}},
            "orders": {"columns": ["order_id", "customer_id", "order_date", "total_amount"], "column_types": {"order_id": "integer", "customer_id": "integer", "order_date": "varchar", "total_amount": "float"}},
            "order_items": {"columns": ["item_id", "order_id", "product_id", "quantity", "unit_price"], "column_types": {"item_id": "integer", "order_id": "integer", "product_id": "integer", "quantity": "integer", "unit_price": "float"}}
        }
    }

    sample_data = {
        "categories": {"category_id": [1, 2, 3], "category_name": ["Electronics", "Apparel", "Home & Garden"]},
        "products": {"id": [101, 102, 103, 104], "category_id": [1, 1, 2, 3], "product_name": ["Laptop Pro", "Wireless Mouse", "Cotton T-Shirt", "Garden Shears"], "price": [1200.0, 25.0, 18.0, 35.0]},
        "customers": {"id": [1, 2, 3], "name": ["Alice Smith", "Bob Jones", "Charlie Brown"], "city": ["New York", "Boston", "San Francisco"]},
        "orders": {"order_id": [5001, 5002, 5003], "customer_id": [1, 2, 1], "order_date": ["2024-01-10", "2024-01-12", "2024-02-01"], "total_amount": [1225.0, 35.0, 18.0]},
        "order_items": {"item_id": [1, 2, 3, 4], "order_id": [5001, 5001, 5002, 5003], "product_id": [101, 102, 104, 103], "quantity": [1, 1, 1, 1], "unit_price": [1200.0, 25.0, 35.0, 18.0]}
    }

    # 2. Detect candidate relationships deterministically
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info, sample_data)
    strong = [c for c in candidates if c["confidence_level"] == "strong"]

    assert len(strong) >= 4

    # 3. Confirm relationships & build relationship graph
    confirmed_links = [
        {"source_table": "orders", "source_column": "customer_id", "target_table": "customers", "target_column": "id"},
        {"source_table": "order_items", "source_column": "order_id", "target_table": "orders", "target_column": "order_id"},
        {"source_table": "order_items", "source_column": "product_id", "target_table": "products", "target_column": "id"},
        {"source_table": "products", "source_column": "category_id", "target_table": "categories", "target_column": "category_id"},
    ]

    graph = relationship_service.build_fk_graph(schema_info, confirmed_relationships=confirmed_links, sample_data=sample_data)
    rel_map = relationship_service.format_relationship_map(schema_info, confirmed_relationships=confirmed_links, sample_data=sample_data)

    assert "orders.customer_id -> customers.id" in rel_map
    assert "order_items.order_id -> orders.order_id" in rel_map

    # 4. Test 2-Table JOIN Query
    sql_2table = "SELECT c.name, SUM(o.total_amount) AS total FROM customers c INNER JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name;"
    is_valid2, err2, _ = validate_sql_query(sql_2table, schema_info=schema_info)
    assert is_valid2, f"Validation error: {err2}"

    cursor = multicsv_database.cursor()
    cursor.execute(sql_2table)
    rows2 = cursor.fetchall()
    assert len(rows2) == 2  # Alice and Bob

    # 5. Test 3-Table JOIN Query
    sql_3table = "SELECT c.name, p.product_name, oi.quantity FROM customers c INNER JOIN orders o ON c.id = o.customer_id INNER JOIN order_items oi ON o.order_id = oi.order_id INNER JOIN products p ON oi.product_id = p.id ORDER BY oi.item_id;"
    is_valid3, err3, _ = validate_sql_query(sql_3table, schema_info=schema_info)
    assert is_valid3, f"Validation error: {err3}"

    cursor.execute(sql_3table)
    rows3 = cursor.fetchall()
    assert len(rows3) == 4

    # 6. Test 4-Table JOIN Query
    sql_4table = "SELECT cat.category_name, SUM(oi.quantity * oi.unit_price) AS category_revenue FROM order_items oi INNER JOIN products p ON oi.product_id = p.id INNER JOIN categories cat ON p.category_id = cat.category_id INNER JOIN orders o ON oi.order_id = o.order_id GROUP BY cat.category_id, cat.category_name ORDER BY category_revenue DESC;"
    is_valid4, err4, _ = validate_sql_query(sql_4table, schema_info=schema_info)
    assert is_valid4, f"Validation error: {err4}"

    cursor.execute(sql_4table)
    rows4 = cursor.fetchall()
    assert len(rows4) == 3
    assert rows4[0][0] == "Electronics"  # Highest revenue category
