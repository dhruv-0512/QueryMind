# QueryMind — Natural Language to SQL Platform

**Live Demo**: [https://query-mind-brown.vercel.app/](https://query-mind-brown.vercel.app/)

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

- **Deterministic 5-Step Viva-Ready Relationship Engine**: Automatically infers Foreign Key links (`orders.customer_id` $\rightarrow$ `customers.id`, `order_items.product_id` $\rightarrow$ `products.id`) using a 5-step explainable strategy (`*_id`/`*_key`/`*_uuid` pattern, table stem matching, target key check, datatype compatibility, $\ge 80\%$ value containment).
- **Attribute Column Exclusion**: Explicitly rejects generic attribute columns (`created_at`, `prospect_company`, `contact_emails`, `contact_mobile_phone`, `full_name`) to eliminate false positives.
- **User Relationship Confirmation Modal**: Displays detected relationship candidates with human-readable explanations (`97% of source values match target key`) and check/confirm controls.
- **Dashboard & Workspace Multi-File Selection**: Select multiple database files directly on the home page (`Dashboard.jsx`) or workspace (`QueryWorkspace.jsx`) and click `Query Selected (N)`.
- **Multi-Table & Cross-Table SQL Generation**: Full support for `INNER JOIN`, `LEFT JOIN`, self-joins, junction tables, `HAVING`, and `WITH` (CTE) clauses.
- **FK Graph Relationship Traversal**: Automatically builds bidirectional Foreign Key graphs (`RelationshipService`) and performs BFS traversal to retrieve connected table DDLs.
- **Multi-Schema Execution**: Queries spanning multiple uploaded datasources are qualified with per-table schema identifiers (`"user_schema_1"."table_a" JOIN "user_schema_2"."table_b"`) and executed safely with unified PostgreSQL `search_path` mapping.
- **Curated Example Dataset**: Seeding pipeline ingests 2,500+ diverse question-SQL examples sourced directly from **Spider** and **WikiSQL**.

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
3. Extracts DDL and indexes embeddings in **ChromaDB**

## Benchmark & Evaluation

Evaluation harnesses and benchmark scripts are available under `evaluation/`:

- **Standard Baseline (`evaluation/evaluate.py`)**: Evaluates NL paraphrasing, schema grounding, and SQL injection security.
- **Multi-Table Benchmark (`evaluation/evaluate_multitable.py`)**: Tests 2-table, 3-table, and 4-table JOINs across multi-table schema relationships.

To run evaluation scripts locally:

```bash
# Run baseline evaluation
python evaluation/evaluate.py

# Run multi-table benchmark
python evaluation/evaluate_multitable.py
```

Detailed test outputs, generated reports, and raw benchmark metrics can be found in the [`evaluation/results/`](evaluation/results) folder.

## How It Works: Multi-File Upload & Cross-Table PostgreSQL Engine

```text
Upload CSVs
     ↓
Schema profiling
     ↓
Deterministic 5-Step Relationship Inference (*_id pattern, datatype, ≥80% value containment)
     ↓
Candidate relationships shown in Modal UI
     ↓
User confirmation
     ↓
Relationship Graph & BFS expansion
     ↓
Relationship-aware ChromaDB RAG
     ↓
DeepSeek / Gemini SQL generation
     ↓
sqlglot AST validation
     ↓
Cross-schema PostgreSQL execution (search_path)
```

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
