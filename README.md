# QueryMind — Natural Language to SQL Platform

Ask questions in plain English and get instant SQL results against your uploaded data.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   Backend    │────▶│  PostgreSQL  │
│  React+Vite  │     │   FastAPI    │     │  (temp schemas)│
│  Tailwind    │     │              │     └──────────────┘
└──────────────┘     │  ┌────────┐  │     ┌──────────────┐
                     │  │ Gemini │──┼────▶│    Redis     │
                     │  └────────┘  │     │   (cache)    │
                     │  ┌────────┐  │     └──────────────┘
                     │  │ChromaDB│  │     ┌──────────────┐
                     │  └────────┘  │────▶│    Kafka     │
                     └──────────────┘     │   (events)   │
                                          └──────────────┘
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
| **Audit Consumer** | — | Kafka consumer persisting events to Postgres |

## Quick Start

```bash
# 1. Clone and cd into the project
git clone https://github.com/dhruv-0512/QueryMind.git
cd QueryMind

# 2. Set your Gemini API key in .env
# GEMINI_API_KEY=your-key-here

# 3. Start everything
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
1. Parses the file with **pandas** (auto-detects column names & types)
2. Creates a **temporary PostgreSQL schema** named `user_{user_id}_{db_id}`
3. Loads the data using **PostgreSQL COPY protocol** via asyncpg for maximum speed
4. Extracts the **DDL** and generates **vector embeddings** in ChromaDB
5. Tables used for RAG-assisted SQL generation with curated example retrieval

## How It Works

1. **Upload** a CSV/XLSX/JSON file — data is bulk-loaded via PostgreSQL COPY protocol for speed
2. **Ask** a question in natural language (e.g. "Show the top 5 products by revenue in Q3 2024")
3. **RAG Retrieval** runs two searches in parallel against ChromaDB:
   - Retrieves the **table schema** (column names, types) for the target database
   - Retrieves the **top-5 most similar question→SQL pairs** from a curated pool of ~2,000 real-world examples sourced from [Spider](https://yale-lily.github.io/spider) and [WikiSQL](https://github.com/salesforce/WikiSQL) datasets
4. **SQL Generation** takes one of two paths based on similarity:
   - **RAG-Direct** (similarity ≥ 78%): The closest example's SQL is directly adapted — table and column names are automatically remapped to match the user's schema
   - **LLM-Adapt** (similarity < 78%): Schema + top examples are sent to **Gemini 2.5 Flash** with instructions to preserve the retrieved SQL structure while remapping all identifiers to the target schema
5. **SQL Validator** enforces read-only safety (SELECT/WITH only)
6. **PostgreSQL** executes the validated query against the temp schema
7. **Results** render as a formatted table (row numbers, type-aware alignment, number formatting) or an interactive Recharts chart
8. Every query is **cached in Redis** (1 hour TTL) and streamed to **Kafka** for audit

## Query Output Features

- **SQL Viewer** — syntax-highlighted generated SQL with keyword coloring (SELECT, FROM, WHERE, etc.), copy-to-clipboard, and confidence scoring
- **Results Table** — auto-formatted grid with row numbers, snake_case→Title Case headers, right-aligned numbers, NULL styling, alternating row colors, pagination
- **Chart View** — interactive bar/line charts via Recharts with configurable X/Y axes

## Query Security

- Only `SELECT` and `WITH` (CTE) queries are allowed
- Prohibited keywords: `DROP`, `DELETE`, `ALTER`, `INSERT`, `UPDATE`, etc.
- Results capped at **1,000 rows** with **30s timeout**
- JWT authentication with refresh tokens
- Rate limiting per user (Redis sliding window)

## Development

```bash
# Frontend dev (no Docker)
cd frontend && npm install --legacy-peer-deps && npm run dev

# Backend dev (no Docker)
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key for SQL generation + embeddings |
| `JWT_SECRET_KEY` | Secret for JWT signing |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address |
| `CHROMADB_HOST` / `CHROMADB_PORT` | ChromaDB connection |

## Tech Stack

**Frontend:** React 19, TypeScript, Vite, Tailwind CSS 3, Recharts, Lucide Icons
**Backend:** FastAPI, SQLAlchemy 2.0 (async), asyncpg (COPY), Pandas, Alembic
**Infra:** PostgreSQL 16, Redis 7, Kafka 7.6, ChromaDB, Docker Compose
**AI:** Google Gemini (SQL generation + embeddings), BGE-small-en (local embeddings fallback), fastembed
