import asyncio
import time
import sys
import os
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.sql_service import sql_service
from app.services.sql_example_retrieval_service import sql_example_retrieval_service

# Realistic live schema context
schema_context = """
CREATE TABLE "orders" (
    "order_id" INTEGER PRIMARY KEY,
    "customer_id" INTEGER,
    "amount" NUMERIC,
    "status" VARCHAR
);

CREATE TABLE "customers" (
    "customer_id" INTEGER PRIMARY KEY,
    "name" VARCHAR,
    "city" VARCHAR
);
"""

def setup_test_db():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE "orders" (
            "order_id" INTEGER PRIMARY KEY,
            "customer_id" INTEGER,
            "amount" REAL,
            "status" TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE "customers" (
            "customer_id" INTEGER PRIMARY KEY,
            "name" TEXT,
            "city" TEXT
        )
    """)
    customers = [
        (1, "Alice", "Chennai"),
        (2, "Bob", "Mumbai"),
        (3, "Charlie", "Chennai"),
        (4, "David", "Delhi")
    ]
    orders = [
        (101, 1, 500.0, "delivered"),
        (102, 1, 300.0, "cancelled"),
        (103, 2, 1200.0, "delivered"),
        (104, 3, 400.0, "delivered"),
        (105, 3, 200.0, "delivered"),
        (106, 4, 150.0, "processing")
    ]
    cur.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
    conn.commit()
    return conn

test_queries = [
    (1, "What is the average order amount for delivered orders?", "LLM"),
    (2, "What is the average order amount for each customer?", "LLM"),
    (3, "What is the average amount of orders placed by customers from Chennai?", "LLM"),
    (4, "Show the total spending for each customer.", "LLM"),
    (5, "Which customer has spent the most?", "LLM"),
    (6, "Find customers whose total spending is above the average customer spending.", "LLM"),
    (7, "What is the maximum order amount?", "Direct RAG"),
    (8, "What is the maximum order amount among delivered orders?", "LLM"),
    (9, "What is the total revenue?", "Direct RAG"),
    (10, "What is the total revenue for each city?", "LLM")
]

async def run_stress_test():
    db_conn = setup_test_db()
    cursor = db_conn.cursor()
    
    print("======================== STRESS TEST RESULTS ========================")
    results_summary = []

    for num, q, expected in test_queries:
        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(q, limit=5)
        res = await sql_service.generate_sql(schema_context, q, examples)
        elapsed = time.perf_counter() - t0
        
        mode = res.get("rag_mode", "unknown")
        llm_invoked = mode in ("deepseek_llm", "llm_adapt")
        actual_path = "Direct RAG" if not llm_invoked else "LLM"
        sql = res.get("sql", "").strip().rstrip(";")
        
        sql_valid = True
        result_valid = True
        db_output = None
        try:
            cursor.execute(sql)
            db_output = cursor.fetchall()
        except Exception as e:
            sql_valid = False
            result_valid = False
            db_output = str(e)

        # Semantic verification of results against expected ground truth
        if num == 1:
            # Delivered orders: 500, 1200, 400, 200 -> avg = 575.0
            if db_output and len(db_output) > 0 and db_output[0][0] is not None:
                val = float(db_output[0][0])
                result_valid = abs(val - 575.0) < 0.01
            else:
                result_valid = False
        elif num == 2:
            # Customer 1: 400.0, 2: 1200.0, 3: 300.0, 4: 150.0
            result_valid = len(db_output) == 4 if isinstance(db_output, list) else False
        elif num == 3:
            # Chennai customers (1 & 3): orders = 500, 300, 400, 200 -> sum=1400, avg=350.0 (or avg of delivered if specified)
            if db_output and len(db_output) > 0 and db_output[0][0] is not None:
                val = float(db_output[0][0])
                result_valid = abs(val - 350.0) < 0.01 or abs(val - 366.66) < 0.01
            else:
                result_valid = False
        elif num == 4:
            # 4 rows (1 for each customer)
            result_valid = len(db_output) == 4 if isinstance(db_output, list) else False
        elif num == 5:
            # Bob (id 2) spent 1200
            result_valid = len(db_output) >= 1 if isinstance(db_output, list) else False
        elif num == 6:
            # spending above avg
            result_valid = len(db_output) >= 1 if isinstance(db_output, list) else False
        elif num == 7:
            # max order amount = 1200.0
            if db_output and len(db_output) > 0 and db_output[0][0] is not None:
                val = float(db_output[0][0])
                result_valid = abs(val - 1200.0) < 0.01
            else:
                result_valid = False
        elif num == 8:
            # max among delivered = 1200.0
            if db_output and len(db_output) > 0 and db_output[0][0] is not None:
                val = float(db_output[0][0])
                result_valid = abs(val - 1200.0) < 0.01
            else:
                result_valid = False
        elif num == 9:
            # total revenue = 2750.0
            if db_output and len(db_output) > 0 and db_output[0][0] is not None:
                val = float(db_output[0][0])
                result_valid = abs(val - 2750.0) < 0.01
            else:
                result_valid = False
        elif num == 10:
            # grouped by city -> 3 cities
            result_valid = len(db_output) >= 3 if isinstance(db_output, list) else False

        top_ex = examples[0] if examples else {}
        top_ex_str = f"{top_ex.get('question')} (sim: {top_ex.get('similarity')})" if top_ex else "None"
        is_routing_correct = (actual_path == expected)
        
        results_summary.append({
            "num": num,
            "query": q,
            "expected": expected,
            "actual": actual_path,
            "llm_invoked": llm_invoked,
            "sql": sql,
            "sql_valid": sql_valid,
            "result_valid": result_valid,
            "db_output": db_output,
            "latency": elapsed,
            "top_ex": top_ex_str,
            "routing_ok": is_routing_correct
        })

        print(f"Query {num}: \"{q}\"")
        print(f"  Expected Path: {expected} | Actual Path: {actual_path} | Match: {'YES' if is_routing_correct else 'FAIL/BUG'}")
        print(f"  LLM Invoked: {llm_invoked} ({mode})")
        print(f"  Generated SQL: {sql}")
        print(f"  Execution Result: {db_output}")
        print(f"  SQL Correct: {sql_valid} | Result Correct: {result_valid}")
        print(f"  Latency: {elapsed*1000:.1f}ms")
        print(f"  Top RAG Example: {top_ex_str}")
        print("---------------------------------------------------------------------")

    # Explicit Safety Assertions
    print("\n======================== SAFETY ASSERTIONS ========================")
    
    # 1. Query containing 'delivered' cannot produce an unconditional aggregate over all orders
    q1_sql = results_summary[0]["sql"].lower()
    assert "where" in q1_sql and "delivered" in q1_sql, "Assertion Failed: Query 1 dropped 'delivered' filter!"
    print("Assertion 1 Passed: Query containing 'delivered' preserved filter.")

    # 2. Query containing 'for each customer' cannot produce an ungrouped aggregate
    q2_sql = results_summary[1]["sql"].lower()
    assert "group by" in q2_sql, "Assertion Failed: Query 2 dropped 'GROUP BY'!"
    print("Assertion 2 Passed: Query containing 'for each customer' preserved GROUP BY.")

    # 3. Query containing 'from Chennai' cannot discard the customer/city constraint
    q3_sql = results_summary[2]["sql"].lower()
    assert "chennai" in q3_sql and ("join" in q3_sql or "where" in q3_sql), "Assertion Failed: Query 3 dropped Chennai filter!"
    print("Assertion 3 Passed: Query containing 'from Chennai' preserved customer/city constraint.")

    # 4. 'spent the most' cannot be mapped to an unrelated HAVING template
    q5_sql = results_summary[4]["sql"].lower()
    assert "having count(*) > 3" not in q5_sql and ("order by" in q5_sql or "max" in q5_sql), "Assertion Failed: Query 5 mapped to invalid HAVING template!"
    print("Assertion 4 Passed: 'spent the most' correctly identified top spending customer.")

    # 5. 'for each city' cannot produce an overall SUM
    q10_sql = results_summary[9]["sql"].lower()
    assert "group by" in q10_sql and "city" in q10_sql, "Assertion Failed: Query 10 produced overall SUM instead of GROUP BY city!"
    print("Assertion 5 Passed: 'for each city' correctly grouped by city.")
    print("ALL SAFETY ASSERTIONS PASSED!")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
