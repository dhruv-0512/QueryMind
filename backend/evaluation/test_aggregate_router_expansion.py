import asyncio
import time
import sys
import os
import sqlite3
import json
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_service import sql_service
from app.services.sql_example_retrieval_service import sql_example_retrieval_service
from evaluation.benchmark_harness import BENCHMARK_CASES, SCHEMA_CONTEXT, setup_benchmark_db, results_match

# ── 10 Specific Test Queries from User Request ───────────────────────
TARGET_NOVEL_QUERIES = [
    # 1-5: Clean single-table aggregates -> Expected: Direct RAG (LLM Bypassed)
    {
        "id": 1,
        "question": "Total monetary value of every order.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
        "expected_path": "Direct RAG",
        "expected_llm": False,
    },
    {
        "id": 2,
        "question": "Calculate the grand total of order amounts.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
        "expected_path": "Direct RAG",
        "expected_llm": False,
    },
    {
        "id": 3,
        "question": "What is the overall value of all orders?",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
        "expected_path": "Direct RAG",
        "expected_llm": False,
    },
    {
        "id": 4,
        "question": "Give me the sum of all order costs.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
        "expected_path": "Direct RAG",
        "expected_llm": False,
    },
    {
        "id": 5,
        "question": "Determine the total sales value across all orders.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
        "expected_path": "Direct RAG",
        "expected_llm": False,
    },
    # 6-10: Complex/grouped/filtered queries -> Expected: LLM
    {
        "id": 6,
        "question": "What is the total revenue for each city?",
        "ref_sql": "SELECT c.city, SUM(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.city;",
        "expected_path": "LLM",
        "expected_llm": True,
    },
    {
        "id": 7,
        "question": "What is the total revenue from delivered orders?",
        "ref_sql": "SELECT SUM(amount) FROM orders WHERE status = 'delivered';",
        "expected_path": "LLM",
        "expected_llm": True,
    },
    {
        "id": 8,
        "question": "What is the total amount spent by each customer?",
        "ref_sql": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id;",
        "expected_path": "LLM",
        "expected_llm": True,
    },
    {
        "id": 9,
        "question": "What is the total revenue after January 1, 2026?",
        "ref_sql": "SELECT SUM(amount) FROM orders WHERE order_date > '2026-01-01';",
        "expected_path": "LLM",
        "expected_llm": True,
    },
    {
        "id": 10,
        "question": "Determine the grand total monetary value without breaking it down by customer.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
        "expected_path": "LLM",
        "expected_llm": True,
    },
]

async def run_novel_evaluation():
    db_conn = setup_benchmark_db()
    cursor = db_conn.cursor()

    print("======================================================================")
    print("TESTING 10 SPECIFIC USER EVALUATION QUERIES:")
    print("======================================================================")
    
    results = []
    for item in TARGET_NOVEL_QUERIES:
        qid = item["id"]
        q = item["question"]
        ref = item["ref_sql"]
        exp_path = item["expected_path"]
        exp_llm = item["expected_llm"]

        cursor.execute(ref)
        expected_rows = cursor.fetchall()

        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=5)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, q, examples)
        latency = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        llm_invoked = mode in ("deepseek_llm", "llm_adapt")
        actual_path = "Direct RAG" if not llm_invoked else "LLM"
        gen_sql = res.get("sql", "").strip().rstrip(";")

        sql_valid = True
        actual_rows = None
        try:
            cursor.execute(gen_sql)
            actual_rows = cursor.fetchall()
        except Exception as e:
            sql_valid = False
            actual_rows = str(e)

        correct = results_match(actual_rows, expected_rows) if sql_valid else False
        path_correct = (actual_path == exp_path)

        res_obj = {
            "id": qid,
            "question": q,
            "expected_path": exp_path,
            "actual_path": actual_path,
            "llm_invoked": llm_invoked,
            "gen_sql": gen_sql,
            "result": actual_rows,
            "correctness": correct and path_correct,
            "sql_correct": correct,
            "path_correct": path_correct,
            "latency_ms": latency,
        }
        results.append(res_obj)

        status_tag = "[PASS]" if (correct and path_correct) else "[FAIL]"
        print(f"[{qid:02d}/10] {status_tag} Q: \"{q}\"")
        print(f"       Path: {actual_path} (Exp: {exp_path}) | LLM Invoked: {llm_invoked} | Latency: {latency:.1f}ms")
        print(f"       Generated SQL: {gen_sql}")
        print(f"       Result: {actual_rows}")
        print("----------------------------------------------------------------------")

    passed_count = sum(1 for r in results if r["correctness"])
    print(f"\nTarget Queries Result: {passed_count}/10 Passed.")

if __name__ == "__main__":
    asyncio.run(run_novel_evaluation())
