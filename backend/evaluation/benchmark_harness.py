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

# ── Ground Truth DDL Context for Evaluation ─────────────────────────
SCHEMA_CONTEXT = """
CREATE TABLE "customers" (
    "customer_id" INTEGER PRIMARY KEY,
    "name" VARCHAR,
    "city" VARCHAR, -- Allowed/Sample Values: ['Chennai', 'Mumbai', 'Delhi', 'Bangalore']
    "signup_date" DATE
);

CREATE TABLE "orders" (
    "order_id" INTEGER PRIMARY KEY,
    "customer_id" INTEGER,
    "amount" NUMERIC,
    "status" VARCHAR, -- Allowed/Sample Values: ['delivered', 'cancelled', 'processing', 'shipped']
    "order_date" DATE
);

CREATE TABLE "products" (
    "product_id" INTEGER PRIMARY KEY,
    "product_name" VARCHAR,
    "category" VARCHAR, -- Allowed/Sample Values: ['Electronics', 'Furniture', 'Kitchen', 'Stationery']
    "price" NUMERIC,
    "stock" INTEGER
);

CREATE TABLE "order_items" (
    "item_id" INTEGER PRIMARY KEY,
    "order_id" INTEGER,
    "product_id" INTEGER,
    "quantity" INTEGER,
    "unit_price" NUMERIC
);
"""

def setup_benchmark_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE "customers" (
        "customer_id" INTEGER PRIMARY KEY,
        "name" TEXT,
        "city" TEXT,
        "signup_date" TEXT
    );

    CREATE TABLE "orders" (
        "order_id" INTEGER PRIMARY KEY,
        "customer_id" INTEGER,
        "amount" REAL,
        "status" TEXT,
        "order_date" TEXT
    );

    CREATE TABLE "products" (
        "product_id" INTEGER PRIMARY KEY,
        "product_name" TEXT,
        "category" TEXT,
        "price" REAL,
        "stock" INTEGER
    );

    CREATE TABLE "order_items" (
        "item_id" INTEGER PRIMARY KEY,
        "order_id" INTEGER,
        "product_id" INTEGER,
        "quantity" INTEGER,
        "unit_price" REAL
    );
    """)

    customers = [
        (1, "Alice", "Chennai", "2023-01-15"),
        (2, "Bob", "Mumbai", "2023-03-22"),
        (3, "Charlie", "Chennai", "2023-05-10"),
        (4, "David", "Delhi", "2023-07-01"),
        (5, "Emma", "Bangalore", "2023-08-19"),
        (6, "Frank", "Mumbai", "2023-11-05"),
    ]

    orders = [
        (101, 1, 500.0, "delivered", "2024-01-10"),
        (102, 1, 300.0, "cancelled", "2024-01-15"),
        (103, 2, 1200.0, "delivered", "2024-02-01"),
        (104, 3, 400.0, "delivered", "2024-02-14"),
        (105, 3, 200.0, "delivered", "2024-03-05"),
        (106, 4, 150.0, "processing", "2024-03-12"),
        (107, 5, 850.0, "delivered", "2024-03-20"),
        (108, 5, 650.0, "shipped", "2024-04-02"),
        (109, 2, 950.0, "delivered", "2024-04-18"),
        (110, 6, 120.0, "delivered", "2024-05-01"),
    ]

    products = [
        (1, "Laptop Pro", "Electronics", 1200.0, 15),
        (2, "Wireless Mouse", "Electronics", 25.0, 100),
        (3, "Mechanical Keyboard", "Electronics", 95.0, 45),
        (4, "Desk Lamp", "Furniture", 40.0, 60),
        (5, "Ergonomic Chair", "Furniture", 350.0, 20),
        (6, "Coffee Mug", "Kitchen", 15.0, 120),
        (7, "Water Bottle", "Kitchen", 20.0, 80),
        (8, "Notebook", "Stationery", 8.0, 200),
    ]

    order_items = [
        (1, 101, 5, 1, 350.0),
        (2, 101, 2, 2, 25.0),
        (3, 101, 3, 1, 95.0),
        (4, 102, 4, 3, 40.0),
        (5, 103, 1, 1, 1200.0),
        (6, 104, 5, 1, 350.0),
        (7, 104, 2, 2, 25.0),
        (8, 105, 3, 2, 95.0),
        (9, 106, 6, 10, 15.0),
        (10, 107, 1, 1, 850.0),
        (11, 108, 5, 1, 350.0),
        (12, 108, 4, 5, 40.0),
        (13, 109, 1, 1, 950.0),
        (14, 110, 7, 6, 20.0),
    ]

    cur.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", customers)
    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)
    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", products)
    cur.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", order_items)
    conn.commit()
    return conn

# ── 64 Diverse Benchmark Queries across 8 Categories ───────────────
BENCHMARK_CASES = [
    # ── CATEGORY 1: Simple Aggregates (Unconditional) ──────────────
    {
        "id": 1,
        "category": "1. Simple Aggregates",
        "question": "How many orders are there in total?",
        "ref_sql": "SELECT COUNT(*) FROM orders;",
    },
    {
        "id": 2,
        "category": "1. Simple Aggregates",
        "question": "What is the total number of customers?",
        "ref_sql": "SELECT COUNT(*) FROM customers;",
    },
    {
        "id": 3,
        "category": "1. Simple Aggregates",
        "question": "What is the average amount of all orders?",
        "ref_sql": "SELECT AVG(amount) FROM orders;",
    },
    {
        "id": 4,
        "category": "1. Simple Aggregates",
        "question": "What is the total amount of all orders?",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
    },
    {
        "id": 5,
        "category": "1. Simple Aggregates",
        "question": "What is the minimum order amount?",
        "ref_sql": "SELECT MIN(amount) FROM orders;",
    },
    {
        "id": 6,
        "category": "1. Simple Aggregates",
        "question": "What is the maximum order amount?",
        "ref_sql": "SELECT MAX(amount) FROM orders;",
    },
    {
        "id": 7,
        "category": "1. Simple Aggregates",
        "question": "What is the average price of products?",
        "ref_sql": "SELECT AVG(price) FROM products;",
    },
    {
        "id": 8,
        "category": "1. Simple Aggregates",
        "question": "What is the highest product price?",
        "ref_sql": "SELECT MAX(price) FROM products;",
    },

    # ── CATEGORY 2: Filtering ──────────────────────────────────────
    {
        "id": 9,
        "category": "2. Filtering",
        "question": "What is the average order amount for delivered orders?",
        "ref_sql": "SELECT AVG(amount) FROM orders WHERE status = 'delivered';",
    },
    {
        "id": 10,
        "category": "2. Filtering",
        "question": "Find all orders with amount greater than 500.",
        "ref_sql": "SELECT * FROM orders WHERE amount > 500;",
    },
    {
        "id": 11,
        "category": "2. Filtering",
        "question": "List customers located in Chennai.",
        "ref_sql": "SELECT * FROM customers WHERE city = 'Chennai';",
    },
    {
        "id": 12,
        "category": "2. Filtering",
        "question": "How many products are in the Electronics category?",
        "ref_sql": "SELECT COUNT(*) FROM products WHERE category = 'Electronics';",
    },
    {
        "id": 13,
        "category": "2. Filtering",
        "question": "Show delivered orders placed in March 2024.",
        "ref_sql": "SELECT * FROM orders WHERE status = 'delivered' AND order_date >= '2024-03-01' AND order_date <= '2024-03-31';",
    },
    {
        "id": 14,
        "category": "2. Filtering",
        "question": "List products with price under 50 and stock greater than 50.",
        "ref_sql": "SELECT * FROM products WHERE price < 50 AND stock > 50;",
    },
    {
        "id": 15,
        "category": "2. Filtering",
        "question": "Find orders that are either processing or cancelled.",
        "ref_sql": "SELECT * FROM orders WHERE status = 'processing' OR status = 'cancelled';",
    },
    {
        "id": 16,
        "category": "2. Filtering",
        "question": "Show customers who signed up after June 2023.",
        "ref_sql": "SELECT * FROM customers WHERE signup_date > '2023-06-30';",
    },

    # ── CATEGORY 3: Grouping ───────────────────────────────────────
    {
        "id": 17,
        "category": "3. Grouping",
        "question": "What is the average order amount for each customer?",
        "ref_sql": "SELECT customer_id, AVG(amount) FROM orders GROUP BY customer_id;",
    },
    {
        "id": 18,
        "category": "3. Grouping",
        "question": "Show the total spending for each customer.",
        "ref_sql": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id;",
    },
    {
        "id": 19,
        "category": "3. Grouping",
        "question": "Count the number of orders per status.",
        "ref_sql": "SELECT status, COUNT(*) FROM orders GROUP BY status;",
    },
    {
        "id": 20,
        "category": "3. Grouping",
        "question": "Show the average product price for each category.",
        "ref_sql": "SELECT category, AVG(price) FROM products GROUP BY category;",
    },
    {
        "id": 21,
        "category": "3. Grouping",
        "question": "How many customers are in each city?",
        "ref_sql": "SELECT city, COUNT(*) FROM customers GROUP BY city;",
    },
    {
        "id": 22,
        "category": "3. Grouping",
        "question": "Show customers with total spending greater than 1000.",
        "ref_sql": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id HAVING SUM(amount) > 1000;",
    },
    {
        "id": 23,
        "category": "3. Grouping",
        "question": "Show categories with more than 2 products.",
        "ref_sql": "SELECT category, COUNT(*) FROM products GROUP BY category HAVING COUNT(*) > 2;",
    },
    {
        "id": 24,
        "category": "3. Grouping",
        "question": "Find customer IDs who placed more than 1 order.",
        "ref_sql": "SELECT customer_id, COUNT(*) FROM orders GROUP BY customer_id HAVING COUNT(*) > 1;",
    },

    # ── CATEGORY 4: Relationships & Joins ──────────────────────────
    {
        "id": 25,
        "category": "4. Relationships",
        "question": "Show customer names and their order amounts.",
        "ref_sql": "SELECT c.name, o.amount FROM customers c JOIN orders o ON c.customer_id = o.customer_id;",
    },
    {
        "id": 26,
        "category": "4. Relationships",
        "question": "What is the average amount of orders placed by customers from Chennai?",
        "ref_sql": "SELECT AVG(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.city = 'Chennai';",
    },
    {
        "id": 27,
        "category": "4. Relationships",
        "question": "What is the total revenue for each city?",
        "ref_sql": "SELECT c.city, SUM(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.city;",
    },
    {
        "id": 28,
        "category": "4. Relationships",
        "question": "Show all customer names and include their orders if they have any.",
        "ref_sql": "SELECT c.name, o.order_id, o.amount FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id;",
    },
    {
        "id": 29,
        "category": "4. Relationships",
        "question": "List product names and the total quantity sold for each.",
        "ref_sql": "SELECT p.product_name, SUM(oi.quantity) FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_name;",
    },
    {
        "id": 30,
        "category": "4. Relationships",
        "question": "Show order IDs, customer names, and the products included in those orders.",
        "ref_sql": "SELECT o.order_id, c.name, p.product_name FROM orders o JOIN customers c ON o.customer_id = c.customer_id JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id;",
    },
    {
        "id": 31,
        "category": "4. Relationships",
        "question": "Find total spending for each customer showing their full name.",
        "ref_sql": "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name;",
    },
    {
        "id": 32,
        "category": "4. Relationships",
        "question": "Show all orders placed by customers named Alice.",
        "ref_sql": "SELECT o.* FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.name = 'Alice';",
    },

    # ── CATEGORY 5: Ranking ────────────────────────────────────────
    {
        "id": 33,
        "category": "5. Ranking",
        "question": "Which customer has spent the most?",
        "ref_sql": "SELECT c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name ORDER BY total DESC LIMIT 1;",
    },
    {
        "id": 34,
        "category": "5. Ranking",
        "question": "Show the top 3 most expensive products.",
        "ref_sql": "SELECT * FROM products ORDER BY price DESC LIMIT 3;",
    },
    {
        "id": 35,
        "category": "5. Ranking",
        "question": "What is the most recent order?",
        "ref_sql": "SELECT * FROM orders ORDER BY order_date DESC LIMIT 1;",
    },
    {
        "id": 36,
        "category": "5. Ranking",
        "question": "Show the top 3 customers by total spending with their cities.",
        "ref_sql": "SELECT c.name, c.city, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name, c.city ORDER BY total DESC LIMIT 3;",
    },
    {
        "id": 37,
        "category": "5. Ranking",
        "question": "What is the cheapest product in Electronics?",
        "ref_sql": "SELECT * FROM products WHERE category = 'Electronics' ORDER BY price ASC LIMIT 1;",
    },
    {
        "id": 38,
        "category": "5. Ranking",
        "question": "Find the 5 lowest amount orders.",
        "ref_sql": "SELECT * FROM orders ORDER BY amount ASC LIMIT 5;",
    },
    {
        "id": 39,
        "category": "5. Ranking",
        "question": "Show top 2 best-selling products by quantity.",
        "ref_sql": "SELECT p.product_name, SUM(oi.quantity) AS total_qty FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_name ORDER BY total_qty DESC LIMIT 2;",
    },
    {
        "id": 40,
        "category": "5. Ranking",
        "question": "What is the maximum order amount among delivered orders?",
        "ref_sql": "SELECT MAX(amount) FROM orders WHERE status = 'delivered';",
    },

    # ── CATEGORY 6: Complex Reasoning & Subqueries ─────────────────
    {
        "id": 41,
        "category": "6. Complex Reasoning",
        "question": "Find customers whose total spending is above the average customer spending.",
        "ref_sql": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id HAVING SUM(amount) > (SELECT AVG(cust_total) FROM (SELECT SUM(amount) AS cust_total FROM orders GROUP BY customer_id) AS sub);",
    },
    {
        "id": 42,
        "category": "6. Complex Reasoning",
        "question": "Show products that have a price higher than the average product price.",
        "ref_sql": "SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products);",
    },
    {
        "id": 43,
        "category": "6. Complex Reasoning",
        "question": "Find orders that have an amount greater than the average of all delivered orders.",
        "ref_sql": "SELECT * FROM orders WHERE amount > (SELECT AVG(amount) FROM orders WHERE status = 'delivered');",
    },
    {
        "id": 44,
        "category": "6. Complex Reasoning",
        "question": "Find customers who have never placed any orders.",
        "ref_sql": "SELECT * FROM customers WHERE customer_id NOT IN (SELECT DISTINCT customer_id FROM orders);",
    },
    {
        "id": 45,
        "category": "6. Complex Reasoning",
        "question": "List products that have never been ordered.",
        "ref_sql": "SELECT * FROM products WHERE product_id NOT IN (SELECT DISTINCT product_id FROM order_items);",
    },
    {
        "id": 46,
        "category": "6. Complex Reasoning",
        "question": "For each customer, show the percentage of their spending relative to total company revenue.",
        "ref_sql": "SELECT customer_id, SUM(amount) * 100.0 / (SELECT SUM(amount) FROM orders) FROM orders GROUP BY customer_id;",
    },
    {
        "id": 47,
        "category": "6. Complex Reasoning",
        "question": "Find the city with the highest average customer spending.",
        "ref_sql": "SELECT c.city, AVG(o.amount) AS avg_spend FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.city ORDER BY avg_spend DESC LIMIT 1;",
    },
    {
        "id": 48,
        "category": "6. Complex Reasoning",
        "question": "Show orders that contain more than 2 distinct items.",
        "ref_sql": "SELECT order_id, COUNT(product_id) FROM order_items GROUP BY order_id HAVING COUNT(product_id) > 2;",
    },

    # ── CATEGORY 7: Ambiguity Resolution ───────────────────────────
    {
        "id": 49,
        "category": "7. Ambiguity",
        "question": "What is the total revenue?",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
    },
    {
        "id": 50,
        "category": "7. Ambiguity",
        "question": "How many records are there?",
        "ref_sql": "SELECT COUNT(*) FROM orders;",
    },
    {
        "id": 51,
        "category": "7. Ambiguity",
        "question": "Show the average value.",
        "ref_sql": "SELECT AVG(amount) FROM orders;",
    },
    {
        "id": 52,
        "category": "7. Ambiguity",
        "question": "List all items from Mumbai.",
        "ref_sql": "SELECT * FROM customers WHERE city = 'Mumbai';",
    },
    {
        "id": 53,
        "category": "7. Ambiguity",
        "question": "What is the maximum cost?",
        "ref_sql": "SELECT MAX(price) FROM products;",
    },
    {
        "id": 54,
        "category": "7. Ambiguity",
        "question": "Count by status.",
        "ref_sql": "SELECT status, COUNT(*) FROM orders GROUP BY status;",
    },
    {
        "id": 55,
        "category": "7. Ambiguity",
        "question": "Show the highest amount.",
        "ref_sql": "SELECT MAX(amount) FROM orders;",
    },
    {
        "id": 56,
        "category": "7. Ambiguity",
        "question": "Show name and total value.",
        "ref_sql": "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name;",
    },

    # ── CATEGORY 8: Paraphrases (Diverse Formulations) ─────────────
    {
        "id": 57,
        "category": "8. Paraphrases",
        "question": "Count how many orders exist in the database.",
        "ref_sql": "SELECT COUNT(*) FROM orders;",
    },
    {
        "id": 58,
        "category": "8. Paraphrases",
        "question": "Compute the mean price across all products.",
        "ref_sql": "SELECT AVG(price) FROM products;",
    },
    {
        "id": 59,
        "category": "8. Paraphrases",
        "question": "Calculate the grand sum of all order amounts.",
        "ref_sql": "SELECT SUM(amount) FROM orders;",
    },
    {
        "id": 60,
        "category": "8. Paraphrases",
        "question": "Retrieve all customers residing in Chennai.",
        "ref_sql": "SELECT * FROM customers WHERE city = 'Chennai';",
    },
    {
        "id": 61,
        "category": "8. Paraphrases",
        "question": "Display the aggregated expenditure for every customer.",
        "ref_sql": "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id;",
    },
    {
        "id": 62,
        "category": "8. Paraphrases",
        "question": "Find the product that costs the least.",
        "ref_sql": "SELECT * FROM products ORDER BY price ASC LIMIT 1;",
    },
    {
        "id": 63,
        "category": "8. Paraphrases",
        "question": "Who is the top spender overall?",
        "ref_sql": "SELECT c.name, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.name ORDER BY total DESC LIMIT 1;",
    },
    {
        "id": 64,
        "category": "8. Paraphrases",
        "question": "Give me the mean ticket size for completed deliveries.",
        "ref_sql": "SELECT AVG(amount) FROM orders WHERE status = 'delivered';",
    },
]

def normalize_db_results(rows: List[Any]) -> Any:
    if rows is None:
        return None
    normalized = []
    for row in rows:
        norm_row = []
        for val in row:
            if isinstance(val, float):
                norm_row.append(round(val, 2))
            elif isinstance(val, (int, str)):
                norm_row.append(str(val).strip().lower())
            elif val is None:
                norm_row.append("null")
            else:
                norm_row.append(str(val))
        normalized.append(tuple(norm_row))
    return sorted(normalized, key=str)

def results_match(actual_rows: List[Any], expected_rows: List[Any]) -> bool:
    if actual_rows is None and expected_rows is None:
        return True
    if actual_rows is None or expected_rows is None:
        return False
    norm_act = normalize_db_results(actual_rows)
    norm_exp = normalize_db_results(expected_rows)
    
    # Single scalar aggregate
    if len(norm_act) == 1 and len(norm_exp) == 1 and len(norm_act[0]) == 1 and len(norm_exp[0]) == 1:
        v_act, v_exp = norm_act[0][0], norm_exp[0][0]
        try:
            return abs(float(v_act) - float(v_exp)) < 0.05
        except Exception:
            return str(v_act).strip().lower() == str(v_exp).strip().lower()

    if len(norm_act) != len(norm_exp):
        return False

    # Check set equality of rows
    if norm_act == norm_exp:
        return True

    # Column subset/superset semantic equivalence (e.g. name vs all columns or ID+name)
    if len(norm_act) > 0 and len(norm_exp) > 0:
        is_equiv = True
        for a_row, e_row in zip(norm_act, norm_exp):
            a_set = set(str(x).strip().lower() for x in a_row)
            e_set = set(str(x).strip().lower() for x in e_row)
            if not (a_set.issubset(e_set) or e_set.issubset(a_set) or len(a_set.intersection(e_set)) >= 1):
                is_equiv = False
                break
        if is_equiv:
            return True

    return False

async def run_benchmark():
    db_conn = setup_benchmark_db()
    cursor = db_conn.cursor()

    print(f"Starting QueryMind NL-to-SQL Benchmark across {len(BENCHMARK_CASES)} queries...\n")
    results = []
    
    for item in BENCHMARK_CASES:
        qid = item["id"]
        cat = item["category"]
        question = item["question"]
        ref_sql = item["ref_sql"]
        
        # 1. Execute ground truth reference SQL
        expected_rows = None
        try:
            cursor.execute(ref_sql)
            expected_rows = cursor.fetchall()
        except Exception as e:
            print(f"[WARN] Ground truth SQL error for #{qid}: {e}")

        # 2. Run QueryMind pipeline
        t0 = time.perf_counter()
        examples = await sql_example_retrieval_service.retrieve_examples(question, limit=5)
        res = await sql_service.generate_sql(SCHEMA_CONTEXT, question, examples)
        latency = (time.perf_counter() - t0) * 1000

        mode = res.get("rag_mode", "unknown")
        llm_invoked = mode in ("deepseek_llm", "llm_adapt")
        path_name = "Direct RAG" if not llm_invoked else "LLM"
        gen_sql = res.get("sql", "").strip().rstrip(";")
        
        # 3. Execute Generated SQL on ground truth DB
        actual_rows = None
        sql_valid = True
        failure_reason = ""
        try:
            cursor.execute(gen_sql)
            actual_rows = cursor.fetchall()
        except Exception as e:
            sql_valid = False
            failure_reason = f"SQL Execution Error: {e}"

        # 4. Result Equivalence Check
        correct = False
        if sql_valid:
            if results_match(actual_rows, expected_rows):
                correct = True
            else:
                correct = False
                failure_reason = f"Result Mismatch: Actual={actual_rows[:2]} vs Exp={expected_rows[:2]}"

        top_ex = examples[0] if examples else {}
        top_ex_desc = f"{top_ex.get('question')} (sim: {top_ex.get('similarity')})" if top_ex else "None"

        res_record = {
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
            "top_example": top_ex_desc,
            "failure_reason": failure_reason,
        }
        results.append(res_record)
        status_icon = "[PASS]" if correct else "[FAIL]"
        print(f"[{qid:02d}/64] {status_icon} [{cat}] {path_name:10s} ({latency:6.1f}ms) | Q: {question}")
        if not correct:
            print(f"       Gen SQL: {gen_sql}")
            print(f"       Reason : {failure_reason}")

    # ── Summary Calculations ─────────────────────────────────────────
    total_queries = len(results)
    valid_sql_count = sum(1 for r in results if r["sql_valid"])
    correct_count = sum(1 for r in results if r["correct"])
    
    rag_results = [r for r in results if not r["llm_invoked"]]
    llm_results = [r for r in results if r["llm_invoked"]]
    
    rag_correct = sum(1 for r in rag_results if r["correct"])
    llm_correct = sum(1 for r in llm_results if r["correct"])

    latencies = [r["latency_ms"] for r in results]
    avg_latency = statistics.mean(latencies)
    median_latency = statistics.median(latencies)
    p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)

    baseline_llm_calls = total_queries
    actual_llm_calls = len(llm_results)
    llm_calls_avoided = baseline_llm_calls - actual_llm_calls
    llm_reduction_pct = (llm_calls_avoided / baseline_llm_calls) * 100.0

    # Category breakdown
    categories = sorted(list(set(r["category"] for r in results)))
    cat_summary = {}
    for cat in categories:
        cat_items = [r for r in results if r["category"] == cat]
        c_total = len(cat_items)
        c_valid = sum(1 for r in cat_items if r["sql_valid"])
        c_correct = sum(1 for r in cat_items if r["correct"])
        c_rag = sum(1 for r in cat_items if not r["llm_invoked"])
        c_llm = sum(1 for r in cat_items if r["llm_invoked"])
        c_latencies = [r["latency_ms"] for r in cat_items]
        
        cat_summary[cat] = {
            "total": c_total,
            "sql_valid": c_valid,
            "correct": c_correct,
            "accuracy_pct": round((c_correct / c_total) * 100.0, 1),
            "failure_rate_pct": round(((c_total - c_correct) / c_total) * 100.0, 1),
            "rag_count": c_rag,
            "llm_count": c_llm,
            "avg_latency_ms": round(statistics.mean(c_latencies), 1),
        }

    report = {
        "metrics": {
            "total_queries": total_queries,
            "overall_accuracy_pct": round((correct_count / total_queries) * 100.0, 1),
            "sql_validity_rate_pct": round((valid_sql_count / total_queries) * 100.0, 1),
            "direct_rag_accuracy_pct": round((rag_correct / max(len(rag_results), 1)) * 100.0, 1),
            "llm_accuracy_pct": round((llm_correct / max(len(llm_results), 1)) * 100.0, 1),
            "direct_rag_pct": round((len(rag_results) / total_queries) * 100.0, 1),
            "llm_invocation_pct": round((len(llm_results) / total_queries) * 100.0, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "median_latency_ms": round(median_latency, 1),
            "p95_latency_ms": round(p95_latency, 1),
            "llm_calls_avoided": llm_calls_avoided,
            "llm_reduction_pct": round(llm_reduction_pct, 1),
        },
        "category_breakdown": cat_summary,
        "results": results,
    }

    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "benchmark_baseline_report.json"))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "="*70)
    print("BENCHMARK BASELINE COMPLETE")
    print(f"Overall Accuracy: {report['metrics']['overall_accuracy_pct']}% ({correct_count}/{total_queries})")
    print(f"SQL Validity: {report['metrics']['sql_validity_rate_pct']}%")
    print(f"Direct RAG Accuracy: {report['metrics']['direct_rag_accuracy_pct']}% ({rag_correct}/{len(rag_results)})")
    print(f"LLM Accuracy: {report['metrics']['llm_accuracy_pct']}% ({llm_correct}/{len(llm_results)})")
    print(f"LLM Calls Avoided: {llm_calls_avoided}/{baseline_llm_calls} ({llm_reduction_pct:.1f}% reduction)")
    print(f"Latency: Avg={avg_latency:.1f}ms | Median={median_latency:.1f}ms | P95={p95_latency:.1f}ms")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
