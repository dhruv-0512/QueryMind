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
| **Frontend** | 3000 | React 19 + Vite + Tailwind CSS 3 |
| **Backend** | 8000 | FastAPI (Python 3.12), NL→SQL pipeline |
| **PostgreSQL** | 5432 | Temp schemas `user_{uid}_{db_id}`, metadata, audit |
| **Redis** | 6379 | Query cache, refresh tokens, rate limiting |
| **Kafka** | 9092 | Event streaming (audit, auth, query, schema events) |
| **ChromaDB** | 8001 | Vector embeddings for schema + SQL example RAG |
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
4. Extracts the **DDL** and generates **vector embeddings** in ChromaDB (`BAAI/bge-small-en-v1.5` local fallback or Gemini)
5. Tables are indexed for RAG-assisted SQL generation with curated example retrieval

## How It Works & Resiliency Patterns

1. **Upload** a CSV/XLSX/JSON file — data is bulk-loaded via PostgreSQL COPY protocol for speed.
2. **Ask** a question in natural language (e.g. "Show top 5 sales in 2024").
3. **RAG Retrieval** runs two searches in parallel against ChromaDB:
   - Retrieves the **table schema** (column names, types) for the target database
   - Retrieves the **top-5 most similar question→SQL pairs** from a curated pool of ~2,000 real-world examples sourced from Spider and WikiSQL.
4. **SQL Generation Pathways & The 78% Threshold**:
   - **RAG-Direct (Cosine Similarity ≥ 78%)**: When a user question matches an indexed SQL template with high confidence ($\ge 78\%$), direct Python template remapping is triggered. This executes in **<15ms with $0 API cost**, skipping LLM calls completely while eliminating model hallucination risks for common query patterns.
   - **LLM Adaptation (Cosine Similarity < 78%)**: When similarity is below 78%, structural template remapping is not safe. The schema and top retrieved examples are passed to **DeepSeek AI** (or Gemini) to reason about complex multi-clause query construction.
5. **Circuit Breaker Protection**: Wraps external LLM network calls. If 5 consecutive API errors occur, the circuit opens for 30s, failing fast in `<1ms` to keep backend threads responsive.
6. **SQL Safety & Execution**: Enforces read-only SELECT/WITH statements and runs against the user's isolated PostgreSQL temp schema.
7. **Caching & Idempotent Event Audit**: Caches query results in **Redis** (1 hour TTL) and streams asynchronous events across 4 topics to **Apache Kafka**. A background `audit_consumer` executes **idempotent database writes** (`ON CONFLICT (event_id) DO NOTHING`), preventing duplicate audit entries if consumer offsets are redelivered upon restart.

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
**Backend:** FastAPI, SQLAlchemy 2.0 (async), asyncpg (COPY), Pandas, Alembic, Circuit Breaker  
**Infra:** PostgreSQL 16, Redis 7, Kafka 7.6, ChromaDB, Docker Compose  
**AI / ML:** DeepSeek AI, Google Gemini, BGE-small-en (local fastembed)
