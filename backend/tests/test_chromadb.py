import pytest
import uuid
from app.services.rag_service import rag_service
from app.services.sql_example_retrieval_service import sql_example_retrieval_service

@pytest.mark.asyncio
async def test_rag_service_indexing_and_retrieval():
    test_db_id = str(uuid.uuid4())
    sample_chunks = [
        {
            "table_name": "users",
            "chunk_text": "CREATE TABLE users (id UUID PRIMARY KEY, email VARCHAR(255), role VARCHAR(50));",
            "columns": ["id", "email", "role"]
        },
        {
            "table_name": "orders",
            "chunk_text": "CREATE TABLE orders (id UUID PRIMARY KEY, user_id UUID, total_amount DECIMAL(10,2));",
            "columns": ["id", "user_id", "total_amount"]
        }
    ]

    # 1. Index schema chunks
    await rag_service.index_schema(test_db_id, sample_chunks)

    # 2. Retrieve schema context
    context = await rag_service.retrieve_schema_context(test_db_id, "find total amount spent by user")
    assert isinstance(context, str)
    assert "orders" in context or "users" in context

    # 3. Clean up / delete schema
    await rag_service.delete_schema(test_db_id)
    cleared_context = await rag_service.retrieve_schema_context(test_db_id, "find total amount spent by user")
    assert cleared_context == ""

@pytest.mark.asyncio
async def test_sql_example_retrieval_service():
    sample_examples = [
        {
            "question": "List all active users",
            "sql": "SELECT * FROM users WHERE active = true;",
            "pattern_type": "filter",
            "complexity": "simple",
            "source": "test"
        }
    ]

    # 1. Upsert examples
    await sql_example_retrieval_service.upsert_examples(sample_examples)

    # 2. Retrieve examples
    results = await sql_example_retrieval_service.retrieve_examples("show me active users", limit=1)
    assert len(results) >= 1
    assert "users" in results[0]["sql"]
