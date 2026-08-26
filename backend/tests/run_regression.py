import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_service import sql_service
from app.services.sql_example_retrieval_service import sql_example_retrieval_service

schema_context = """
CREATE TABLE "orders" (
    "order_id" INTEGER PRIMARY KEY,
    "customer_id" INTEGER,
    "amount" NUMERIC
);

CREATE TABLE "customers" (
    "customer_id" INTEGER PRIMARY KEY,
    "name" VARCHAR,
    "city" VARCHAR
);
"""

queries = [
    "How many orders are there in total?",
    "How many orders have been placed?",
    "What is the average amount of all orders?",
    "What is the total amount of all orders?",
    "What is the minimum order amount?",
    "What is the maximum order amount?",
    "For each customer, show their total spending.",
    "Find customers whose total spending is greater than the average customer spending."
]

async def run_regression():
    print("==================== REGRESSION TEST SUITE ====================")
    for idx, q in enumerate(queries, 1):
        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=5)
        res = await sql_service.generate_sql(schema_context, q, examples)
        elapsed = time.perf_counter() - t0
        
        mode = res.get("rag_mode", "unknown")
        llm_invoked = mode in ("deepseek_llm", "llm_adapt")
        sql = res.get("sql", "").strip()
        confidence = res.get("confidence")
        
        path_str = "Direct RAG (LLM Bypassed)" if not llm_invoked else f"LLM Invoked ({mode})"
        
        print(f"Test {idx}: \"{q}\"")
        print(f"  Generated SQL: {sql}")
        print(f"  Execution Path: {path_str}")
        print(f"  LLM Invoked: {llm_invoked}")
        print(f"  Confidence: {confidence}")
        print(f"  Latency: {elapsed*1000:.1f}ms")
        if examples:
            top_ex = examples[0]
            print(f"  Top RAG Example: \"{top_ex.get('question')}\" (Similarity: {top_ex.get('similarity')})")
        print("---------------------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(run_regression())
