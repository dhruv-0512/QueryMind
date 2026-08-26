import asyncio
import time
import sys
import os
import sqlite3
import json
import statistics
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_service import sql_service
from app.services.sql_example_retrieval_service import sql_example_retrieval_service
from evaluation.benchmark_harness import BENCHMARK_CASES, SCHEMA_CONTEXT, setup_benchmark_db, results_match

# ── New Specific Regression Test Sets ──────────────────────────────
NEW_RANKING_TESTS = [
    {"q": "Find the 5 lowest amount orders.", "ref": "SELECT * FROM orders ORDER BY amount ASC LIMIT 5;", "expected_path": "LLM"},
    {"q": "Show the 3 highest order amounts.", "ref": "SELECT * FROM orders ORDER BY amount DESC LIMIT 3;", "expected_path": "LLM"},
    {"q": "Find the 2 cheapest products.", "ref": "SELECT * FROM products ORDER BY price ASC LIMIT 2;", "expected_path": "LLM"},
    {"q": "What is the maximum order amount?", "ref": "SELECT MAX(amount) FROM orders;", "expected_path": "Direct RAG"},
    {"q": "What is the minimum order amount?", "ref": "SELECT MIN(amount) FROM orders;", "expected_path": "Direct RAG"},
    {"q": "Show the highest order.", "ref": "SELECT * FROM orders ORDER BY amount DESC LIMIT 1;", "expected_path": "LLM"},
]

NEW_DOMAIN_LITERAL_TESTS = [
    {"q": "Show all completed deliveries.", "ref": "SELECT * FROM orders WHERE status = 'delivered';", "expected_path": "LLM"},
    {"q": "What is the total revenue from finished orders?", "ref": "SELECT SUM(amount) FROM orders WHERE status = 'delivered';", "expected_path": "LLM"},
    {"q": "Find all shipped orders.", "ref": "SELECT * FROM orders WHERE status = 'shipped';", "expected_path": "LLM"},
    {"q": "List orders that are still processing.", "ref": "SELECT * FROM orders WHERE status = 'processing';", "expected_path": "LLM"},
]

NEW_COMPLEX_SUBQUERY_TESTS = [
    {"q": "Find customers whose total spending is above the average customer spending.", "ref": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id HAVING SUM(amount) > (SELECT AVG(cust_total) FROM (SELECT SUM(amount) AS cust_total FROM orders GROUP BY customer_id) AS sub);", "expected_path": "LLM"},
    {"q": "Find orders that have an amount greater than the average of all delivered orders.", "ref": "SELECT * FROM orders WHERE amount > (SELECT AVG(amount) FROM orders WHERE status = 'delivered');", "expected_path": "LLM"},
    {"q": "Show products that have a price higher than the average product price.", "ref": "SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products);", "expected_path": "LLM"},
    {"q": "Find customers who have never placed any orders.", "ref": "SELECT * FROM customers WHERE customer_id NOT IN (SELECT DISTINCT customer_id FROM orders);", "expected_path": "LLM"},
    {"q": "For each customer, show the percentage of their spending relative to total company revenue.", "ref": "SELECT customer_id, SUM(amount) * 100.0 / (SELECT SUM(amount) FROM orders) FROM orders GROUP BY customer_id;", "expected_path": "LLM"},
]

async def run_full_validation():
    db_conn = setup_benchmark_db()
    cursor = db_conn.cursor()

    print("======================================================================")
    print("STEP 1: RUNNING 64-QUERY BENCHMARK HARNESS")
    print("======================================================================")

    results = []
    for item in BENCHMARK_CASES:
        qid = item["id"]
        cat = item["category"]
        question = item["question"]
        ref_sql = item["ref_sql"]
        
        cursor.execute(ref_sql)
        expected_rows = cursor.fetchall()

        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(question, limit=5)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, question, examples)
        latency = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        llm_invoked = mode in ("deepseek_llm", "llm_adapt")
        path_name = "Direct RAG" if not llm_invoked else "LLM"
        gen_sql = res.get("sql", "").strip().rstrip(";")
        
        sql_valid = True
        actual_rows = None
        failure_reason = ""
        try:
            cursor.execute(gen_sql)
            actual_rows = cursor.fetchall()
        except Exception as e:
            sql_valid = False
            failure_reason = f"Execution Error: {e}"

        correct = False
        if sql_valid:
            if results_match(actual_rows, expected_rows):
                correct = True
            else:
                failure_reason = f"Mismatch: Actual={actual_rows[:2]} vs Exp={expected_rows[:2]}"

        results.append({
            "id": qid,
            "category": cat,
            "question": question,
            "ref_sql": ref_sql,
            "generated_sql": gen_sql,
            "path": path_name,
            "llm_invoked": llm_invoked,
            "sql_valid": sql_valid,
            "correct": correct,
            "latency_ms": latency,
            "failure_reason": failure_reason,
        })
        status_tag = "[PASS]" if correct else "[FAIL]"
        print(f"[{qid:02d}/64] {status_tag} [{cat}] {path_name:10s} ({latency:6.1f}ms) | Q: {question}")

    # ── Summary Calculations ─────────────────────────────────────────
    total_q = len(results)
    correct_q = sum(1 for r in results if r["correct"])
    valid_q = sum(1 for r in results if r["sql_valid"])
    rag_q = [r for r in results if not r["llm_invoked"]]
    llm_q = [r for r in results if r["llm_invoked"]]
    rag_correct = sum(1 for r in rag_q if r["correct"])
    llm_correct = sum(1 for r in llm_q if r["correct"])
    latencies = [r["latency_ms"] for r in results]

    print("\n" + "="*70)
    print("64-QUERY BENCHMARK RESULTS:")
    print(f"Overall Accuracy    : {correct_q / total_q * 100:.1f}% ({correct_q}/{total_q})")
    print(f"SQL Validity Rate   : {valid_q / total_q * 100:.1f}%")
    print(f"Direct RAG Accuracy : {rag_correct / max(len(rag_q), 1) * 100:.1f}% ({rag_correct}/{len(rag_q)})")
    print(f"LLM Accuracy        : {llm_correct / max(len(llm_q), 1) * 100:.1f}% ({llm_correct}/{len(llm_q)})")
    print(f"Direct RAG Count    : {len(rag_q)} ({len(rag_q)/total_q*100:.1f}%)")
    print(f"LLM Invocation Count: {len(llm_q)} ({len(llm_q)/total_q*100:.1f}%)")
    print(f"Latency Mean/Med/P95: {statistics.mean(latencies):.1f}ms / {statistics.median(latencies):.1f}ms / {statistics.quantiles(latencies, n=20)[18]:.1f}ms")
    print("="*70)

    # ── STEP 2: NEW RANKING TESTS ───────────────────────────────────
    print("\n======================================================================")
    print("STEP 2: NEW RANKING TESTS (Ensuring N-lowest / N-highest route correctly)")
    print("======================================================================")
    ranking_passed = 0
    for idx, item in enumerate(NEW_RANKING_TESTS, 1):
        q, ref, exp_path = item["q"], item["ref"], item["expected_path"]
        cursor.execute(ref)
        expected = cursor.fetchall()

        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=5)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, q, examples)
        lat = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        path = "Direct RAG" if mode not in ("deepseek_llm", "llm_adapt") else "LLM"
        gen_sql = res.get("sql", "").strip().rstrip(";")

        cursor.execute(gen_sql)
        act = cursor.fetchall()
        is_match = results_match(act, expected)
        has_ranking_semantics = "ORDER BY" in gen_sql.upper() and ("LIMIT" in gen_sql.upper() or "MIN(" in gen_sql.upper() or "MAX(" in gen_sql.upper())
        path_ok = is_match and has_ranking_semantics
        if is_match and path_ok:
            ranking_passed += 1
            print(f"[PASS] Ranking #{idx}: \"{q}\" -> {path} | SQL: {gen_sql}")
        else:
            print(f"[FAIL] Ranking #{idx}: \"{q}\" -> {path} (Exp: {exp_path}) | Match: {is_match} | SQL: {gen_sql}")

    print(f"Ranking Tests Passed: {ranking_passed}/{len(NEW_RANKING_TESTS)}")

    # ── STEP 3: NEW DOMAIN LITERAL TESTS ─────────────────────────────
    print("\n======================================================================")
    print("STEP 3: NEW DOMAIN LITERAL & SYNONYM TESTS")
    print("======================================================================")
    literal_passed = 0
    for idx, item in enumerate(NEW_DOMAIN_LITERAL_TESTS, 1):
        q, ref, exp_path = item["q"], item["ref"], item["expected_path"]
        cursor.execute(ref)
        expected = cursor.fetchall()

        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=5)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, q, examples)
        lat = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        path = "Direct RAG" if mode not in ("deepseek_llm", "llm_adapt") else "LLM"
        gen_sql = res.get("sql", "").strip().rstrip(";")

        cursor.execute(gen_sql)
        act = cursor.fetchall()
        is_match = results_match(act, expected)
        if is_match:
            literal_passed += 1
            print(f"[PASS] Domain Literal #{idx}: \"{q}\" -> SQL: {gen_sql}")
        else:
            print(f"[FAIL] Domain Literal #{idx}: \"{q}\" -> SQL: {gen_sql} | Act: {act[:1]} vs Exp: {expected[:1]}")

    print(f"Domain Literal Tests Passed: {literal_passed}/{len(NEW_DOMAIN_LITERAL_TESTS)}")

    # ── STEP 4: COMPLEX SUBQUERY TESTS ──────────────────────────────
    print("\n======================================================================")
    print("STEP 4: COMPLEX SUBQUERY & REASONING TESTS")
    print("======================================================================")
    complex_passed = 0
    for idx, item in enumerate(NEW_COMPLEX_SUBQUERY_TESTS, 1):
        q, ref, exp_path = item["q"], item["ref"], item["expected_path"]
        cursor.execute(ref)
        expected = cursor.fetchall()

        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=5)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, q, examples)
        lat = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        path = "Direct RAG" if mode not in ("deepseek_llm", "llm_adapt") else "LLM"
        gen_sql = res.get("sql", "").strip().rstrip(";")

        cursor.execute(gen_sql)
        act = cursor.fetchall()
        is_match = results_match(act, expected)
        if is_match:
            complex_passed += 1
            print(f"[PASS] Complex #{idx}: \"{q}\" -> SQL: {gen_sql}")
        else:
            print(f"[FAIL] Complex #{idx}: \"{q}\" -> SQL: {gen_sql} | Act: {act[:1]} vs Exp: {expected[:1]}")

    print(f"Complex Subquery Tests Passed: {complex_passed}/{len(NEW_COMPLEX_SUBQUERY_TESTS)}")

    # ── Final JSON Export ───────────────────────────────────────────
    cat_summary = {}
    for cat in sorted(list(set(r["category"] for r in results))):
        c_items = [r for r in results if r["category"] == cat]
        cat_summary[cat] = {
            "total": len(c_items),
            "correct": sum(1 for r in c_items if r["correct"]),
            "accuracy_pct": round(sum(1 for r in c_items if r["correct"]) / len(c_items) * 100, 1),
            "avg_latency_ms": round(statistics.mean([r["latency_ms"] for r in c_items]), 1),
        }

    final_report = {
        "overall_accuracy_pct": round(correct_q / total_q * 100, 1),
        "sql_validity_rate_pct": round(valid_q / total_q * 100, 1),
        "direct_rag_accuracy_pct": round(rag_correct / max(len(rag_q), 1) * 100, 1),
        "llm_accuracy_pct": round(llm_correct / max(len(llm_q), 1) * 100, 1),
        "direct_rag_count": len(rag_q),
        "llm_count": len(llm_q),
        "avg_latency_ms": round(statistics.mean(latencies), 1),
        "median_latency_ms": round(statistics.median(latencies), 1),
        "p95_latency_ms": round(statistics.quantiles(latencies, n=20)[18], 1),
        "categories": cat_summary,
        "new_ranking_passed": f"{ranking_passed}/{len(NEW_RANKING_TESTS)}",
        "new_domain_literal_passed": f"{literal_passed}/{len(NEW_DOMAIN_LITERAL_TESTS)}",
        "new_complex_passed": f"{complex_passed}/{len(NEW_COMPLEX_SUBQUERY_TESTS)}",
    }
    with open("evaluation/final_validation_report.json", "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run_full_validation())
