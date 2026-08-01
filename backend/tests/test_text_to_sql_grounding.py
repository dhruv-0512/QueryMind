import pytest
from app.utils.sql_validator import validate_sql_query
from app.services.sql_service import sql_service

@pytest.mark.asyncio
async def test_users_table_no_first_name_hallucination():
    # Schema for users table: only id, email, role, created_at, updated_at
    schema_info = {
        "tables": {
            "users": {
                "columns": ["id", "email", "hashed_password", "role", "created_at", "updated_at"]
            }
        }
    }
    schema_context = """
    Table: "users"
    Columns:
      - "id" (UUID, PRIMARY KEY)
      - "email" (VARCHAR(255))
      - "hashed_password" (VARCHAR(255))
      - "role" (VARCHAR(50))
      - "created_at" (TIMESTAMP)
      - "updated_at" (TIMESTAMP)
    """
    
    user_question = "Show users whose email starts with A"
    retrieved_examples = [
        {
            "question": "Show users whose first name starts with A",
            "sql": "SELECT * FROM users WHERE first_name LIKE 'A%';",
            "similarity": 0.90
        }
    ]

    gen_result = await sql_service.generate_sql(schema_context, user_question, retrieved_examples)
    generated_sql = gen_result.get("sql", "")

    # 1. Assert first_name is NOT in generated SQL
    assert "first_name" not in generated_sql.lower(), f"Hallucinated first_name in: {generated_sql}"
    # 2. Assert email IS used
    assert "email" in generated_sql.lower(), f"Expected email in: {generated_sql}"

    # 3. Validate against schema_info
    is_valid, err, _ = validate_sql_query(generated_sql, schema_info=schema_info)
    assert is_valid, f"Validation failed: {err}"

@pytest.mark.asyncio
async def test_products_table_grounding():
    schema_info = {
        "tables": {
            "products": {
                "columns": ["id", "product_name", "price", "stock"]
            }
        }
    }
    schema_context = """
    Table: "products"
    Columns:
      - "id" (INTEGER, PRIMARY KEY)
      - "product_name" (VARCHAR(255))
      - "price" (DECIMAL(10,2))
      - "stock" (INTEGER)
    """

    user_question = "Products above 1000"
    retrieved_examples = [
        {
            "question": "Items with price greater than 500",
            "sql": "SELECT * FROM items WHERE item_price > 500;",
            "similarity": 0.85
        }
    ]

    gen_result = await sql_service.generate_sql(schema_context, user_question, retrieved_examples)
    generated_sql = gen_result.get("sql", "")

    assert "price" in generated_sql.lower(), f"Expected price column in: {generated_sql}"
    assert "1000" in generated_sql, f"Expected 1000 threshold in: {generated_sql}"

    is_valid, err, _ = validate_sql_query(generated_sql, schema_info=schema_info)
    assert is_valid, f"Validation failed: {err}"

@pytest.mark.asyncio
async def test_employees_table_grounding():
    schema_info = {
        "tables": {
            "employees": {
                "columns": ["id", "employee_name", "department", "salary", "hire_date"]
            }
        }
    }
    schema_context = """
    Table: "employees"
    Columns:
      - "id" (INTEGER, PRIMARY KEY)
      - "employee_name" (VARCHAR(255))
      - "department" (VARCHAR(100))
      - "salary" (DECIMAL(10,2))
      - "hire_date" (DATE)
    """

    user_question = "Show employees in Sales department"
    retrieved_examples = [
        {
            "question": "Find workers in Engineering",
            "sql": "SELECT * FROM workers WHERE dept_name = 'Engineering';",
            "similarity": 0.82
        }
    ]

    gen_result = await sql_service.generate_sql(schema_context, user_question, retrieved_examples)
    generated_sql = gen_result.get("sql", "")

    assert "department" in generated_sql.lower(), f"Expected department column in: {generated_sql}"
    assert "sales" in generated_sql.lower(), f"Expected Sales in: {generated_sql}"

    is_valid, err, _ = validate_sql_query(generated_sql, schema_info=schema_info)
    assert is_valid, f"Validation failed: {err}"

def test_validator_detects_hallucinated_column():
    schema_info = {
        "tables": {
            "employees": {
                "columns": ["id", "employee_name", "department", "salary", "hire_date"]
            }
        }
    }
    bad_sql = "SELECT employee_name, gpa FROM employees;"
    is_valid, err, inv_id = validate_sql_query(bad_sql, schema_info=schema_info)
    assert not is_valid
    assert inv_id == "gpa"

def test_validator_detects_nonexistent_table_entries():
    schema_info = {
        "tables": {
            "users": {
                "columns": ["id", "email", "role"]
            }
        }
    }
    bad_sql = "SELECT COUNT(*) FROM entries;"
    is_valid, err, inv_id = validate_sql_query(bad_sql, schema_info=schema_info)
    assert not is_valid
    assert inv_id == "entries"

def test_suggest_schema_matches():
    from app.utils.sql_validator import suggest_schema_matches
    schema_info = {
        "tables": {
            "orders": {"columns": ["id", "order_date", "total_price"]},
            "customers": {"columns": ["id", "customer_name", "email"]},
            "products": {"columns": ["id", "product_name", "price"]}
        }
    }
    
    # 1. Close match on table name ("order" -> "orders")
    best, kind, candidates = suggest_schema_matches("order", schema_info)
    assert best == "orders"
    assert kind == "table"

    # 2. No close match on table name ("entries" vs ["orders", "customers", "products"])
    best_low, kind_low, candidates_low = suggest_schema_matches("entries", schema_info)
    assert best_low is None
    assert "orders" in candidates_low and "customers" in candidates_low and "products" in candidates_low
