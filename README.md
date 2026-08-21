# QueryMind — Natural Language to SQL Platform

Ask questions in plain English and get instant SQL results against your uploaded data.

## System Architecture & Workflow

```
                                ┌──────────────────────────┐
                                │       React + Vite       │
                                │   Frontend (Port 3000)   │
                                └────────────┬─────────────┘
                                             │ HTTP (JWT)
                                             ▼
                                ┌──────────────────────────┐
                                │     FastAPI Backend      │
                                │       (Port 8000)        │
                                └──────┬─────┬─────┬───────┘
                                       │     │     │
         ┌────────────────────────────┘     │     └──────────────────────────┐
         │ (Read/Write Cache)               │ (Schema & Query Events)        │ (DDL Vectors & RAG)
         ▼                                  ▼                                ▼
┌─────────────────┐               ┌──────────────────┐             ┌──────────────────┐
│   Redis 7.0     │               │   Apache Kafka   │             │   ChromaDB       │
│  (Port 6379)    │               │   (Port 9092)    │             │   (Port 8001)    │
└─────────────────┘               └─────────┬────────┘             └──────────────────┘
                                            │
                                            ▼
                                ┌──────────────────────────┐
                                │  Kafka Audit Consumer    │
                                │   (Async Background)     │
                                └────────────┬─────────────┘
                                             │ Write Audit Logs & Metadata
                                             ▼
                                ┌──────────────────────────┐
                                │      PostgreSQL 16       │
                                │  (Temp Schemas & Metadata│
                                └──────────────────────────┘
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **Frontend** | 3000 | React 19 + Vite + Tailwind CSS 3 (Multi-datasource selection UI) |
| **Backend** | 8000 | FastAPI (Python 3.12), NL→SQL pipeline, FK Graph Relationship Service |
| **PostgreSQL** | 5432 | Temp schemas `user_{uid}_{db_id}`, metadata, audit, multi-schema search_path |
| **Redis** | 6379 | Query cache, refresh tokens, rate limiting |
| **Kafka** | 9092 | Event streaming (audit, auth, query, schema events) |
| **ChromaDB** | 8001 | Vector embeddings for schema + Spider/WikiSQL multi-table RAG |
| **Audit Consumer** | — | Kafka consumer persisting events asynchronously to Postgres |

## Quick Start

```bash
# 1. Clone and cd into the project
git clone https://github.com/dhruv-0512/QueryMind.git
cd QueryMind

# 2. Set your DeepSeek or Gemini API key in .env
DEEPSEEK_API_KEY=sk-your-key-here
LLM_PROVIDER=deepseek

# 3. Start everything with Docker Compose
docker compose up -d --build
```

Open **http://localhost:3000** — register an account and start querying.

## Key Features & Multi-Table Engine

- **Multi-Table & Cross-Table SQL Generation**: Full support for `INNER JOIN`, `LEFT JOIN`, self-joins, junction tables, `HAVING`, and `WITH` (CTE) clauses.
- **FK Graph Relationship Traversal**: Automatically builds bidirectional Foreign Key graphs (`RelationshipService`) and performs BFS traversal to retrieve all connected table DDLs when generating multi-table queries.
- **Multi-Datasource Selection UI**: Select single or multiple uploaded database files simultaneously in the frontend workspace.
- **Multi-Schema Execution**: Queries spanning multiple uploaded datasources are qualified with per-table schema identifiers (`"user_schema_1"."table_a" JOIN "user_schema_2"."table_b"`) and executed safely with unified PostgreSQL `search_path` mapping.
- **Curated Multi-Table Example Dataset**: Seeding pipeline ingests 2,500+ diverse question-SQL examples sourced directly from **Spider** and **WikiSQL** with 700+ JOIN templates stratified by depth (2-table, 3-table, 4-table/complex joins), `LEFT JOIN`, CTEs, and `HAVING` filters.
- **AST Schema Grounding & Recovery**: Uses `sqlglot` to parse generated SQL ASTs, enforcing valid table and column references, catching schema hallucinations, and recovering automatically via fuzzy matching.

## Upload Formats

Drag-and-drop upload of data files. Supported formats:

| Format | Extension |
|--------|-----------|
| CSV | `.csv` |
| Excel | `.xlsx`, `.xls` |
| JSON | `.json` |

On upload, the system:
1. Parses the file with **Pandas** (auto-detects column names & types, normalizes special characters & numeric column titles)
2. Creates a **temporary PostgreSQL schema** named `user_{user_id}_{db_id}`
3. Loads the data using **PostgreSQL COPY protocol** via asyncpg for maximum speed
4. Extracts the **DDL and Foreign Keys** and generates **vector embeddings** in ChromaDB
5. Tables and relationships are indexed for RAG-assisted SQL generation with curated example retrieval

## Benchmark & Evaluation

QueryMind includes two automated evaluation harnesses built on independent benchmarks:

1. **Standard Unseen Paraphrase Benchmark (`evaluation/evaluate.py`)**: Tests NL paraphrasing, schema grounding, and read-only security.
2. **Multi-Table Benchmark (`evaluation/evaluate_multitable.py`)**: Tests 2-table, 3-table, and 4-table JOINs, `LEFT JOIN`s, `CTE`s, `HAVING` clauses, and aggregations against the 6-table aviation database (`airlines`, `airports`, `aircraft`, `flights`, `passengers`, `bookings`).

### Benchmark Metrics Summary

| Benchmark Suite | Metric | Score | Target Standard | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Standard Baseline** | **Execution Accuracy** | **`93.88%`** | `> 85.0%` | **PASSED** |
| **Standard Baseline** | **Semantic Answer Accuracy** | **`93.88%`** | `> 80.0%` | **PASSED** |
| **Standard Baseline** | **Top-1 / Top-5 Retrieval Recall** | **`100.0%`** | `> 90.0%` | **PASSED** |
| **Standard Baseline** | **SQL Injection Block Rate** | **`100.0%`** | `100.0%` | **SECURE** |
| **Multi-Table Benchmark** | **2-Table JOIN Accuracy** | **`100.0%`** | `> 80.0%` | **PASSED** |
| **Multi-Table Benchmark** | **3-Table JOIN Accuracy** | **`100.0%`** | `> 80.0%` | **PASSED** |
| **Multi-Table Benchmark** | **4-Table / Complex JOIN Accuracy** | **`100.0%`** | `> 75.0%` | **PASSED** |
| **Multi-Table Benchmark** | **LEFT JOIN Accuracy** | **`100.0%`** | `> 80.0%` | **PASSED** |
| **Multi-Table Benchmark** | **CTE (`WITH ...`) Accuracy** | **`100.0%`** | `> 75.0%` | **PASSED** |
| **Multi-Table Benchmark** | **Overall Multi-Table Accuracy** | **`100.0%`** | `> 80.0%` | **PASSED** |

### Visual Evidence & Latency Charts

<p align="center">
  <img src="evaluation/results/accuracy_chart.png" width="45%" alt="Accuracy Chart" />
  <img src="evaluation/results/latency_chart.png" width="45%" alt="Latency Chart" />
</p>

To run the evaluation harnesses locally:

```bash
# Run standard baseline evaluation
python evaluation/evaluate.py

# Run dedicated multi-table evaluation benchmark
python evaluation/evaluate_multitable.py
```

All evaluation artifacts, benchmark markdown reports, and JSON metrics are stored in [`evaluation/results/`](file:///C:/Users/dhruv/Desktop/PROJECTS/New%20folder%20%287%29/evaluation/results).

## How It Works: Multi-File Upload & Cross-Table PostgreSQL Engine

1. **Multi-File Upload & Ingestion**:
   - Upload any number of data files (`.csv`, `.xlsx`, `.json`) — e.g. `customers.csv`, `orders.csv`, `products.json`.
   - Each file is converted into a native PostgreSQL table inside an isolated PostgreSQL schema (`user_{uid}_{db_id}`) using `asyncpg` COPY protocol for sub-second ingestion.
2. **Multi-Datasource Selection**:
   - In the **Query Workspace**, select one or multiple uploaded databases from the Data Sources panel using checkboxes.
3. **Unified Multi-Schema Discovery**:
   - When you click **Run Query**, QueryMind discovers the live PostgreSQL schemas for all selected files in parallel.
   - It constructs a unified multi-table context, extracting column names, data types, and Foreign Key relationships.
4. **Relationship-Aware RAG Retrieval & Prompting**:
   - Searches ChromaDB for relevant tables and uses BFS graph traversal ([`RelationshipService`](file:///C:/Users/dhruv/Desktop/PROJECTS/New%20folder%20(7)/backend/app/services/relationship_service.py)) to pull in transitively connected FK table schemas.
   - Retrieves top matching structural templates from the 2,500+ Spider & WikiSQL corpus.
   - Injects the merged schema, relationship map, and guidelines into DeepSeek AI (or Gemini).
5. **Cross-Schema PostgreSQL Qualification & JOIN Execution**:
   - The LLM generates standard ANSI SQL JOINs across tables (e.g. `FROM customers c JOIN orders o ON c.id = o.customer_id`).
   - QueryMind's AST qualification engine ([`_qualify_sql_tables`](file:///C:/Users/dhruv/Desktop/PROJECTS/New%20folder%20(7)/backend/app/routers/query.py#L30-L61)) maps each table to its respective PostgreSQL schema:
     ```sql
     SELECT c.name, SUM(o.total_amount) AS revenue
     FROM "user_a1b2_db1"."customers" c
     JOIN "user_a1b2_db2"."orders" o ON c.id = o.customer_id
     GROUP BY c.name;
     ```
   - Sets PostgreSQL `search_path` dynamically to include all selected schemas and executes the query directly in PostgreSQL.
6. **AST Validation & Recovery**: Parses the generated SQL with `sqlglot` to prevent schema hallucinations and handles schema recovery automatically.
7. **Caching & Idempotent Audit**: Caches results in Redis (300s TTL) and logs asynchronous audit events to Apache Kafka.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DEEPSEEK_API_KEY` | DeepSeek API key for high-speed SQL generation |
| `DEEPSEEK_MODEL` | DeepSeek model choice (e.g., `deepseek-chat`) |
| `GEMINI_API_KEY` | Google Gemini API key fallback |
| `LLM_PROVIDER` | Preferred LLM provider (`deepseek`, `gemini`, or `mock`) |
| `EMBEDDING_PROVIDER` | Embedding provider (`local`, `gemini`, or `auto`) |
| `JWT_SECRET_KEY` | Secret for JWT signing |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address |
| `CHROMADB_HOST` / `CHROMADB_PORT` | ChromaDB vector database connection |

## Tech Stack

**Frontend:** React 19, JavaScript (ES2023), Vite, Tailwind CSS 3, Recharts, Lucide Icons  
**Backend:** FastAPI, SQLAlchemy 2.0 (async), asyncpg (COPY), Pandas, Alembic, sqlglot, Circuit Breaker  
**Infra:** PostgreSQL 16, Redis 7, Kafka 7.6, ChromaDB, Docker Compose  
**AI / ML:** DeepSeek AI, Google Gemini, BGE-small-en (local fastembed), Spider & WikiSQL corpora  
