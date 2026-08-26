# QueryMind — Natural Language to SQL Platform

**Live Demo**: [https://query-mind-brown.vercel.app/](https://query-mind-brown.vercel.app/)

Ask questions in plain English and get validated SQL results against your uploaded datasets.

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
| **Frontend** | 3000 | React 19 + Vite + Tailwind CSS 3 (Multi-datasource Dashboard & Workspace UI) |
| **Backend** | 8000 | FastAPI (Python 3.12), NL→SQL pipeline, Deterministic Relationship Engine |
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

## Key Features & Multi-Table Engine

- **RAG-First Compositional Architecture (Deterministic Fast Path & Facet Assembly)**:
  - **Deterministic Single-Table Fast Path**: Clean single-table aggregate queries (`COUNT(*)`, `SUM`, `AVG`, `MIN`, `MAX`) execute instantly with zero LLM tokens and direct schema validation.
  - **Facet-Based RAG Composition (Levels 1–8)**: Combines structural SQL facets (tables, projections, joins, grounded filters, group-by dimensions, order/limit clauses) from indexed schema and benchmark examples to assemble clean SQL deterministically with sub-10ms response times.
  - **AST Semantic Constraint Validator (`sqlglot`)**: Hard validation gate that extracts the AST representation of composed SQL and verifies it against the natural-language query's expected semantic constraints. Any missing filters, dropped join conditions, altered categorical values, or unmapped projections trigger an immediate fallback to DeepSeek LLM reasoning.
- **Live Categorical Literal Grounding**: Schema discovery automatically samples bounded distinct values for text/categorical columns (`status`, `category`, `city`, etc.) and attaches them to the grounding context. Natural-language synonyms (e.g. *"completed deliveries"*, *"finished orders"*) map directly to actual database literals (`status = 'delivered'`) without hardcoding.
- **Deterministic Foreign-Key Candidate Detection**: Identifies relationships between uploaded datasets using conventional foreign-key patterns (`*_id`, `*_key`, `*_uuid`), entity/table-name matching, target-key detection, datatype compatibility, and value containment. Detected relationships are confirmed by the user before cross-table execution.
- **Quantity-Qualified Ranking & Entity-Level LEFT JOIN Reasoning**:
  - Differentiates scalar extrema from limit-based rankings (`"5 lowest"`, `"top 3"`, `"cheapest"`) to generate `ORDER BY ... LIMIT N`.
  - When querying entity aggregates across tables, uses `LEFT JOIN` and `COALESCE(SUM(...), 0)` so entities with zero related records remain represented.
- **Attribute Column Filtering**: Excludes descriptive columns (e.g. `created_at`, `contact_emails`, `full_name`) from foreign-key candidate detection to eliminate false relationships.
- **Relationship Graph & BFS Traversal**: Builds a graph from known database foreign keys and confirmed relationships, traversing connected tables to supply schema context for multi-table queries.
- **Multi-Schema Execution**: Queries spanning multiple uploaded datasources are qualified with per-table schema identifiers (`"user_schema_1"."table_a" JOIN "user_schema_2"."table_b"`) and executed safely within PostgreSQL.
- **Curated Spider & WikiSQL ChromaDB Seeding & Offline Embedding Resilience**: Vector database seeds canonical benchmark templates covering multi-table joins, nested subqueries, CTEs, and correlated aggregations, backed by query embedding caching and resilient fallback mechanisms.

> **Note on CSV Relationships**: CSV files do not inherently contain database foreign-key constraints. QueryMind treats relationships detected from uploaded data as candidate relationships and requires user confirmation before using them for cross-dataset querying.

## Upload Formats

Supported drag-and-drop formats:

| Format | Extension |
|--------|-----------|
| CSV | `.csv` |
| Excel | `.xlsx`, `.xls` |
| JSON | `.json` |

On upload:
1. Parses file with **Pandas** (auto-detects column names & types, normalizes special characters & numeric column titles)
2. Loads data into **PostgreSQL schema** (`user_{user_id}_{db_id}`) using asyncpg COPY protocol
3. Extracts DDL and indexes embeddings in **ChromaDB** with sampled categorical values

## Evaluation & Test Harness

QueryMind includes a comprehensive evaluation harness and automated test suite under `evaluation/` and `backend/tests/`.

The evaluation harness covers:
- Simple unconditional aggregates (COUNT, SUM, AVG, MIN, MAX)
- Categorical, numeric, date, and multi-condition filtering
- Grouping, HAVING, and per-entity aggregation
- Multi-table relationships, foreign-key joins, and LEFT JOIN preservation
- Quantity-qualified rankings (top N, N-lowest, N-highest)
- Complex reasoning (scalar subqueries, nested aggregations, percentage calculations)
- Ambiguity resolution (implicit tables and columns)
- Paraphrased linguistic variations and synonym grounding

### Benchmark Results (RAG-First Pipeline)

| Benchmark | Result |
|---|---|
| **50-query RAG-First accuracy** | **96.0% (48/50)** |
| **64-query benchmark** | **98.4% (63/64)** |
| **Safety regression (10q)** | **100.0% (10/10)** |
| **Ranking regression (6q)** | **100.0% (6/6)** |
| **Domain literal regression (4q)** | **100.0% (4/4)** |
| **Complex subquery regression (5q)** | **100.0% (5/5)** |
| **Aggregate expansion regression (10q)** | **100.0% (10/10)** |
| **Case C (RAG accepted wrong SQL)** | **0 / 50 (0.0%)** |
| **RAG-only precision** | **100.0% (32/32)** |
| **Total RAG handled rate** | **64.0% (32/50)** |
| **SQL validity** | **100.0%** |

The **semantic constraint validator** enforces strict bidirectional invariants before any RAG-composed SQL is executed:
- Expected NL constraints ⊆ actual SQL constraints
- Actual SQL constraints ⊆ expected NL constraints (no spurious clauses)
- Column-level projection verification with entity-query `SELECT *` defaulting
- Temporal constraint safety gate routing unsupported date ranges to LLM fallback
- Deterministic table alias parity between `SELECT` and `GROUP BY` clauses for PostgreSQL compatibility
- Datatype safety: `SUM/AVG/MIN/MAX` on VARCHAR columns is rejected
- Zero-constraint guard: bare `SELECT *` with no extractable NL constraints falls back to LLM

### Test Suite

```bash
python -m pytest backend/tests/test_constraint_extraction_and_validation.py -v
# 44 tests: 6 original + 11 Case C regressions + 14 adversarial safety tests + 5 Phase 1 tests + 7 targeted safety tests + 1 PostgreSQL alias parity test
```

Evaluation scripts:

```bash
python backend/evaluation/benchmark_harness.py
python backend/evaluation/rag_first_benchmark.py
```

## How It Works: Multi-File Upload & Cross-Table PostgreSQL Engine

```text
Upload CSVs
     ↓
Schema profiling & distinct value sampling
     ↓
Deterministic FK candidate detection
     ↓
Candidate relationships shown
     ↓
User confirmation
     ↓
Relationship graph & BFS expansion
     ↓
Semantic routing (Fast Path vs RAG Composition vs LLM)
     ↓
RAG facet composition & AST constraint validation
     ↓
PostgreSQL execution (or DeepSeek fallback on validation failure)
```

1. Users upload one or more supported datasets.
2. QueryMind profiles the uploaded schemas, samples distinct values for categorical columns, and loads data into isolated PostgreSQL schemas.
3. When multiple datasets are selected, the deterministic FK candidate detector searches for conventional foreign-key patterns.
4. Candidate relationships are verified using key-pattern matching, datatype compatibility, and value containment.
5. Detected candidates are shown to the user for confirmation.
6. Confirmed relationships are added to the relationship graph.
7. BFS traversal expands relevant connected table context.
8. Semantic routing determines whether the query can be handled by the deterministic fast path, RAG composition, or LLM fallback.
9. ChromaDB retrieves relevant schema and SQL examples.
10. RAG composition extracts and combines reusable SQL facets using live schema and confirmed FK/relationship graph context.
11. sqlglot parses the composed SQL and the semantic constraint validator verifies that the SQL preserves the natural-language query's constraints.
12. If validation succeeds, the composed SQL executes directly in PostgreSQL; if RAG cannot safely satisfy the constraints, the query falls back to DeepSeek/Gemini generation followed by SQL validation.

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
