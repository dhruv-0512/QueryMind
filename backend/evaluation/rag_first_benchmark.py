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
from evaluation.benchmark_harness import SCHEMA_CONTEXT, setup_benchmark_db, results_match

RAG_FIRST_50_CASES = [
    # ── Category 1: Aggregates (5 queries) ───────────────────────────
    {
        "id": 1, "category": "1. Aggregates",
        "question": "Calculate the grand total of order amounts.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
    },
    {
        "id": 2, "category": "1. Aggregates",
        "question": "What is the overall average product price?",
        "ref_sql": "SELECT AVG(price) FROM products;",
    },
    {
        "id": 3, "category": "1. Aggregates",
        "question": "Count the total number of customers.",
        "ref_sql": "SELECT COUNT(*) FROM customers;",
    },
    {
        "id": 4, "category": "1. Aggregates",
        "question": "What is the minimum amount among all orders?",
        "ref_sql": "SELECT MIN(amount) FROM orders;",
    },
    {
        "id": 5, "category": "1. Aggregates",
        "question": "Determine the highest price among products.",
        "ref_sql": "SELECT MAX(price) FROM products;",
    },

    # ── Category 2: Filters (5 queries) ──────────────────────────────
    {
        "id": 6, "category": "2. Filters",
        "question": "List all customers who live in Bangalore.",
        "ref_sql": "SELECT * FROM customers WHERE city = 'Bangalore';",
    },
    {
        "id": 7, "category": "2. Filters",
        "question": "Find products with a price greater than 500.",
        "ref_sql": "SELECT * FROM products WHERE price > 500;",
    },
    {
        "id": 8, "category": "2. Filters",
        "question": "Show all completed deliveries.",
        "ref_sql": "SELECT * FROM orders WHERE status = 'delivered';",
    },
    {
        "id": 9, "category": "2. Filters",
        "question": "List all orders that were cancelled.",
        "ref_sql": "SELECT * FROM orders WHERE status = 'cancelled';",
    },
    {
        "id": 10, "category": "2. Filters",
        "question": "Find products in the Electronics category.",
        "ref_sql": "SELECT * FROM products WHERE category = 'Electronics';",
    },

    # ── Category 3: JOINs (5 queries) ────────────────────────────────
    {
        "id": 11, "category": "3. JOINs",
        "question": "Show customer names and their order amounts.",
        "ref_sql": "SELECT c.name, o.amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id;",
    },
    {
        "id": 12, "category": "3. JOINs",
        "question": "List order IDs and the product names ordered.",
        "ref_sql": "SELECT oi.order_id, p.product_name FROM order_items oi JOIN products p ON oi.product_id = p.product_id;",
    },
    {
        "id": 13, "category": "3. JOINs",
        "question": "Show customer names with the statuses of their orders.",
        "ref_sql": "SELECT c.name, o.status FROM customers c JOIN orders o ON c.customer_id = o.customer_id;",
    },
    {
        "id": 14, "category": "3. JOINs",
        "question": "List product categories and the quantities ordered.",
        "ref_sql": "SELECT p.category, oi.quantity FROM products p JOIN order_items oi ON p.product_id = oi.product_id;",
    },
    {
        "id": 15, "category": "3. JOINs",
        "question": "Show customer cities and the order amounts placed.",
        "ref_sql": "SELECT c.city, o.amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id;",
    },

    # ── Category 4: JOIN + Filters (5 queries) ───────────────────────
    {
        "id": 16, "category": "4. JOIN + Filters",
        "question": "Show all orders placed by customers from Chennai.",
        "ref_sql": "SELECT o.* FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.city = 'Chennai';",
    },
    {
        "id": 17, "category": "4. JOIN + Filters",
        "question": "List order items for products in Electronics.",
        "ref_sql": "SELECT oi.* FROM order_items oi JOIN products p ON oi.product_id = p.product_id WHERE p.category = 'Electronics';",
    },
    {
        "id": 18, "category": "4. JOIN + Filters",
        "question": "Show orders placed by Alice.",
        "ref_sql": "SELECT o.* FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.name = 'Alice';",
    },
    {
        "id": 19, "category": "4. JOIN + Filters",
        "question": "Find delivered orders for customers in Mumbai.",
        "ref_sql": "SELECT o.* FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE o.status = 'delivered' AND c.city = 'Mumbai';",
    },
    {
        "id": 20, "category": "4. JOIN + Filters",
        "question": "List customer names who ordered items with quantity greater than 2.",
        "ref_sql": "SELECT DISTINCT c.name FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id WHERE oi.quantity > 2;",
    },

    # ── Category 5: GROUP BY (5 queries) ─────────────────────────────
    {
        "id": 21, "category": "5. GROUP BY",
        "question": "What is the average order amount for each customer ID?",
        "ref_sql": "SELECT customer_id, AVG(amount) FROM orders GROUP BY customer_id;",
    },
    {
        "id": 22, "category": "5. GROUP BY",
        "question": "Count the number of customers in each city.",
        "ref_sql": "SELECT city, COUNT(*) FROM customers GROUP BY city;",
    },
    {
        "id": 23, "category": "5. GROUP BY",
        "question": "What is the total order amount for each status?",
        "ref_sql": "SELECT status, SUM(amount) FROM orders GROUP BY status;",
    },
    {
        "id": 24, "category": "5. GROUP BY",
        "question": "Count how many products exist in each category.",
        "ref_sql": "SELECT category, COUNT(*) FROM products GROUP BY category;",
    },
    {
        "id": 25, "category": "5. GROUP BY",
        "question": "Find customer IDs who placed more than 1 order.",
        "ref_sql": "SELECT customer_id FROM orders GROUP BY customer_id HAVING COUNT(*) > 1;",
    },

    # ── Category 6: JOIN + GROUP BY (5 queries) ──────────────────────
    {
        "id": 26, "category": "6. JOIN + GROUP BY",
        "question": "What is the total revenue for each city?",
        "ref_sql": "SELECT c.city, SUM(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.city;",
    },
    {
        "id": 27, "category": "6. JOIN + GROUP BY",
        "question": "Show customer names and their total spending.",
        "ref_sql": "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name;",
    },
    {
        "id": 28, "category": "6. JOIN + GROUP BY",
        "question": "What is the total quantity sold for each product name?",
        "ref_sql": "SELECT p.product_name, SUM(oi.quantity) FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_name;",
    },
    {
        "id": 29, "category": "6. JOIN + GROUP BY",
        "question": "Find the average order amount for customers in each city.",
        "ref_sql": "SELECT c.city, AVG(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.city;",
    },
    {
        "id": 30, "category": "6. JOIN + GROUP BY",
        "question": "Count the number of orders for each customer name.",
        "ref_sql": "SELECT c.name, COUNT(o.order_id) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name;",
    },

    # ── Category 7: Ranking (5 queries) ──────────────────────────────
    {
        "id": 31, "category": "7. Ranking",
        "question": "Find the 5 lowest amount orders.",
        "ref_sql": "SELECT * FROM orders ORDER BY amount ASC LIMIT 5;",
    },
    {
        "id": 32, "category": "7. Ranking",
        "question": "Show the top 3 most expensive products.",
        "ref_sql": "SELECT * FROM products ORDER BY price DESC LIMIT 3;",
    },
    {
        "id": 33, "category": "7. Ranking",
        "question": "What is the most recent order?",
        "ref_sql": "SELECT * FROM orders ORDER BY order_date DESC LIMIT 1;",
    },
    {
        "id": 34, "category": "7. Ranking",
        "question": "Find the 2 cheapest products.",
        "ref_sql": "SELECT * FROM products ORDER BY price ASC LIMIT 2;",
    },
    {
        "id": 35, "category": "7. Ranking",
        "question": "Show the top 3 customers by total spending.",
        "ref_sql": "SELECT c.customer_id, c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.name ORDER BY total DESC LIMIT 3;",
    },

    # ── Category 8: Multi-Hop Relationships (5 queries) ──────────────
    {
        "id": 36, "category": "8. Multi-Hop Relationships",
        "question": "Show customer names, order IDs, and product names ordered.",
        "ref_sql": "SELECT c.name, o.order_id, p.product_name FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id;",
    },
    {
        "id": 37, "category": "8. Multi-Hop Relationships",
        "question": "What products have been purchased by customers from Bangalore?",
        "ref_sql": "SELECT DISTINCT p.product_name FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id JOIN customers c ON o.customer_id = c.customer_id WHERE c.city = 'Bangalore';",
    },
    {
        "id": 38, "category": "8. Multi-Hop Relationships",
        "question": "Find total quantity ordered per customer name across all products.",
        "ref_sql": "SELECT c.name, SUM(oi.quantity) FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id GROUP BY c.name;",
    },
    {
        "id": 39, "category": "8. Multi-Hop Relationships",
        "question": "Show customer cities and the categories of products they bought.",
        "ref_sql": "SELECT DISTINCT c.city, p.category FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id;",
    },
    {
        "id": 40, "category": "8. Multi-Hop Relationships",
        "question": "Calculate total spending by product category.",
        "ref_sql": "SELECT p.category, SUM(oi.quantity * oi.unit_price) FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.category;",
    },

    # ── Category 9: Nested / Complex (5 queries) ─────────────────────
    {
        "id": 41, "category": "9. Nested / Complex",
        "question": "Find customers whose total spending is above the average customer spending.",
        "ref_sql": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id HAVING SUM(amount) > (SELECT AVG(total) FROM (SELECT SUM(amount) AS total FROM orders GROUP BY customer_id));",
    },
    {
        "id": 42, "category": "9. Nested / Complex",
        "question": "Show products that have a price higher than the average product price.",
        "ref_sql": "SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products);",
    },
    {
        "id": 43, "category": "9. Nested / Complex",
        "question": "Find orders with an amount greater than the average of all delivered orders.",
        "ref_sql": "SELECT * FROM orders WHERE amount > (SELECT AVG(amount) FROM orders WHERE status = 'delivered');",
    },
    {
        "id": 44, "category": "9. Nested / Complex",
        "question": "Find customers who have never placed any orders.",
        "ref_sql": "SELECT * FROM customers WHERE customer_id NOT IN (SELECT customer_id FROM orders);",
    },
    {
        "id": 45, "category": "9. Nested / Complex",
        "question": "List products that have never been ordered.",
        "ref_sql": "SELECT * FROM products WHERE product_id NOT IN (SELECT product_id FROM order_items);",
    },

    # ── Category 10: Paraphrases (5 queries) ─────────────────────────
    {
        "id": 46, "category": "10. Paraphrases",
        "question": "Give me the mean ticket size for completed deliveries.",
        "ref_sql": "SELECT AVG(amount) FROM orders WHERE status = 'delivered';",
    },
    {
        "id": 47, "category": "10. Paraphrases",
        "question": "Retrieve all customers residing in Chennai.",
        "ref_sql": "SELECT * FROM customers WHERE city = 'Chennai';",
    },
    {
        "id": 48, "category": "10. Paraphrases",
        "question": "Compute the mean price across all products.",
        "ref_sql": "SELECT AVG(price) FROM products;",
    },
    {
        "id": 49, "category": "10. Paraphrases",
        "question": "Display the aggregated expenditure for every customer.",
        "ref_sql": "SELECT c.customer_id, c.name, COALESCE(SUM(o.amount), 0) FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.name;",
    },
    {
        "id": 50, "category": "10. Paraphrases",
        "question": "Who is the top spender overall?",
        "ref_sql": "SELECT c.customer_id, c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.name ORDER BY total DESC LIMIT 1;",
    },
]

async def run_rag_first_benchmark():
    db_conn = setup_benchmark_db()
    cursor = db_conn.cursor()

    print("======================================================================")
    print("RUNNING 50-QUERY RAG-FIRST COMPOSITIONAL BENCHMARK")
    print("======================================================================")

    results = []
    category_stats: Dict[str, Dict[str, int]] = {}

    for case in RAG_FIRST_50_CASES:
        qid = case["id"]
        cat = case["category"]
        q = case["question"]
        ref_sql = case["ref_sql"]

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "correct": 0, "rag": 0, "llm": 0}
        category_stats[cat]["total"] += 1

        cursor.execute(ref_sql)
        expected_rows = cursor.fetchall()

        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=8)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, q, examples)
        latency = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        llm_invoked = mode in ("deepseek_llm", "llm_adapt")
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

        if correct:
            category_stats[cat]["correct"] += 1
        if not llm_invoked:
            category_stats[cat]["rag"] += 1
        else:
            category_stats[cat]["llm"] += 1

        res_item = {
            "id": qid,
            "category": cat,
            "question": q,
            "rag_mode": mode,
            "llm_invoked": llm_invoked,
            "gen_sql": gen_sql,
            "sql_valid": sql_valid,
            "correct": correct,
            "latency_ms": latency,
        }
        results.append(res_item)

        status_tag = "[PASS]" if correct else "[FAIL]"
        route_tag = "Direct RAG" if mode == "direct" else ("RAG Comp" if mode == "rag_composition" else "LLM")
        print(f"[{qid:02d}/50] {status_tag} [{cat:22s}] {route_tag:10s} ({latency:6.1f}ms) | Q: {q}")

    total_correct = sum(1 for r in results if r["correct"])
    total_valid = sum(1 for r in results if r["sql_valid"])
    total_rag = sum(1 for r in results if not r["llm_invoked"])
    total_llm = sum(1 for r in results if r["llm_invoked"])
    latencies = [r["latency_ms"] for r in results]

    print("\n" + "="*70)
    print("50-QUERY RAG-FIRST BENCHMARK RESULTS:")
    print(f"Overall Accuracy    : {total_correct/len(results)*100:.1f}% ({total_correct}/{len(results)})")
    print(f"SQL Validity Rate   : {total_valid/len(results)*100:.1f}%")
    print(f"RAG Bypass Rate     : {total_rag/len(results)*100:.1f}% ({total_rag}/{len(results)})")
    print(f"LLM Invocation Count: {total_llm} ({total_llm/len(results)*100:.1f}%)")
    print(f"Latency Mean/Med/P95: {sum(latencies)/len(latencies):.1f}ms / {sorted(latencies)[len(latencies)//2]:.1f}ms / {sorted(latencies)[int(len(latencies)*0.95)]:.1f}ms")
    print("="*70)

    print("\nCATEGORY BREAKDOWN:")
    for cat, st in category_stats.items():
        acc = st["correct"] / st["total"] * 100
        rag_pct = st["rag"] / st["total"] * 100
        print(f"  • {cat:25s}: Accuracy = {acc:5.1f}% ({st['correct']}/{st['total']}) | RAG Bypass = {rag_pct:5.1f}% ({st['rag']}/{st['total']})")

    # Save benchmark report to file
    out_path = os.path.join(os.path.dirname(__file__), "rag_first_benchmark_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "overall_accuracy": total_correct / len(results),
            "sql_validity": total_valid / len(results),
            "rag_bypass_pct": total_rag / len(results),
            "total_queries": len(results),
            "category_breakdown": category_stats,
            "detailed_results": results
        }, f, indent=2)
    print(f"\nReport written to: {out_path}")

if __name__ == "__main__":
    asyncio.run(run_rag_first_benchmark())
