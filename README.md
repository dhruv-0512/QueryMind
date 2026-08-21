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

- **Deterministic Foreign-Key Candidate Detection**: Identifies likely relationships between uploaded datasets using conventional foreign-key patterns (`*_id`, `*_key`, `*_uuid`), entity/table-name matching, target-key detection, datatype compatibility, and ≥80% value containment. Detected relationships are presented to the user for confirmation before being used for cross-table querying.
- **Attribute Column Filtering**: Excludes generic descriptive columns such as `created_at`, `prospect_company`, `contact_emails`, `contact_mobile_phone`, `full_name`, and similar attributes from foreign-key candidate detection to reduce false positives.
- **User Relationship Confirmation Modal**: Displays detected relationship candidates with confidence/validation information and human-readable explanations, allowing users to select and confirm relationships before cross-table querying.
- **Dashboard & Workspace Multi-File Selection**: Select multiple database files directly on the home page (`Dashboard.jsx`) or workspace (`QueryWorkspace.jsx`) and click `Query Selected (N)`.
- **Multi-Table SQL Support**: Supports generated queries involving INNER JOIN, LEFT JOIN, self-joins, junction tables, HAVING, and WITH (CTE) clauses.
- **Relationship Graph & BFS Traversal**: Builds a graph from known database foreign keys and user-confirmed relationships, then traverses connected tables to expand relevant schema context for multi-table querying.
- **Multi-Schema Execution**: Queries spanning multiple uploaded datasources are qualified with per-table schema identifiers (`"user_schema_1"."table_a" JOIN "user_schema_2"."table_b"`) and executed safely with unified PostgreSQL `search_path` mapping.
- **Curated Example Dataset**: Seeding pipeline ingests 2,500+ diverse question-SQL examples sourced directly from **Spider** and **WikiSQL**.

> **Note on CSV Relationships**: CSV files do not inherently contain database foreign-key constraints. QueryMind therefore treats relationships detected from uploaded data as candidate relationships and requires user confirmation before using them for cross-dataset querying.

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

### Evaluation Results

| Evaluation | Result |
|---|---:|
| Standard baseline | 93.88% (46/49) |
| Multi-table benchmark | 100% (43/43) |
| 2-table JOINs | 100% (22/22) |
| 3-table JOINs | 100% (18/18) |
| 4-table JOINs | 100% (3/3) |
| SQL injection blocking | 100% (4/4) |
| Backend test suite | 38/38 |

QueryMind achieved 100% execution accuracy on the 43-query multi-table benchmark. The multi-table benchmark evaluates queries requiring 2-, 3-, and 4-table joins across related relational schemas. The standard baseline evaluates schema grounding, natural-language query handling, and SQL security checks.

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
Deterministic FK candidate detection
     ↓
Candidate relationships shown
     ↓
User confirmation
     ↓
Relationship graph & BFS expansion
     ↓
Relationship-aware ChromaDB RAG
     ↓
DeepSeek / Gemini SQL generation
     ↓
sqlglot AST validation
     ↓
Cross-schema PostgreSQL execution
```

1. Users upload one or more supported datasets.
2. QueryMind profiles the uploaded schemas and loads the data into isolated PostgreSQL schemas.
3. When multiple datasets are selected, the deterministic FK candidate detector searches for conventional foreign-key patterns such as `customer_id → customers.id`.
4. Candidate relationships are verified using key-pattern matching, datatype compatibility, and source-to-target value containment.
5. Detected candidates are shown to the user for confirmation.
6. Confirmed relationships are added to the relationship graph.
7. BFS traversal expands relevant connected table context.
8. ChromaDB RAG retrieves relevant schema and SQL examples.
9. DeepSeek/Gemini generates the SQL query.
10. sqlglot validates the generated SQL AST.
11. PostgreSQL executes the query across the selected schemas.
12. Results are returned to the user.

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
