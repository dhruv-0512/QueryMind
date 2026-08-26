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

- **Hybrid Execution Engine (Deterministic Fast Path & Semantic RAG)**: 
  - **Deterministic Aggregate Fast Path**: Unconditional single-table aggregations (`COUNT(*)`, `SUM`, `AVG`, `MIN`, `MAX`) execute instantly with zero LLM tokens and direct schema type validation.
  - **Semantic Complexity Guarding**: Queries containing filters, joins, groupings, rankings, subqueries, or date constraints are automatically routed to LLM reasoning to ensure no constraints are dropped.
- **Live Categorical Literal Grounding**: Schema discovery automatically samples bounded distinct values for text/categorical columns (`status`, `category`, `city`, etc.) and attaches them to the grounding context. Natural-language synonyms (e.g. *"completed deliveries"*, *"finished orders"*) map directly to actual database literals (`status = 'delivered'`) without hardcoding.
- **Deterministic Foreign-Key Candidate Detection**: Identifies relationships between uploaded datasets using conventional foreign-key patterns (`*_id`, `*_key`, `*_uuid`), entity/table-name matching, target-key detection, datatype compatibility, and value containment. Detected relationships are confirmed by the user before cross-table execution.
- **Quantity-Qualified Ranking & Entity-Level LEFT JOIN Reasoning**:
  - Differentiates scalar extrema from limit-based rankings (`"5 lowest"`, `"top 3"`, `"cheapest"`) to generate `ORDER BY ... LIMIT N`.
  - When querying entity aggregates across tables, uses `LEFT JOIN` and `COALESCE(SUM(...), 0)` so entities with zero related records remain represented.
- **Attribute Column Filtering**: Excludes descriptive columns (e.g. `created_at`, `contact_emails`, `full_name`) from foreign-key candidate detection to eliminate false relationships.
- **Relationship Graph & BFS Traversal**: Builds a graph from known database foreign keys and confirmed relationships, traversing connected tables to supply schema context for multi-table queries.
- **Multi-Schema Execution**: Queries spanning multiple uploaded datasources are qualified with per-table schema identifiers (`"user_schema_1"."table_a" JOIN "user_schema_2"."table_b"`) and executed safely within PostgreSQL.
- **Curated Spider & WikiSQL ChromaDB Seeding**: Vector database seeds canonical benchmark templates covering multi-table joins, nested subqueries, CTEs, and correlated aggregations, auto-seeded idempotently on startup.

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

Evaluation scripts:

```bash
python backend/evaluation/benchmark_harness.py
python backend/evaluation/full_validation_suite.py
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
Semantic complexity routing (Direct RAG vs LLM)
     ↓
DeepSeek / Gemini SQL generation
     ↓
sqlglot AST validation & PostgreSQL execution
```

1. Users upload one or more supported datasets.
2. QueryMind profiles the uploaded schemas, samples distinct values for categorical columns, and loads data into isolated PostgreSQL schemas.
3. When multiple datasets are selected, the deterministic FK candidate detector searches for conventional foreign-key patterns.
4. Candidate relationships are verified using key-pattern matching, datatype compatibility, and value containment.
5. Detected candidates are shown to the user for confirmation.
6. Confirmed relationships are added to the relationship graph.
7. BFS traversal expands relevant connected table context.
8. Complexity routing determines whether to execute via Direct Fast Path or route to LLM.
9. ChromaDB RAG retrieves relevant schema and SQL examples.
10. DeepSeek/Gemini generates the SQL query.
11. sqlglot validates the generated SQL AST.
12. PostgreSQL executes the query across the selected schemas and returns results.

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
