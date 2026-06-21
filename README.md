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
| **Frontend** | 3000 | React 19 + Vite 8 + Tailwind CSS |
| **Backend** | 8000 | FastAPI (Python 3.12), NLP→SQL pipeline |
| **PostgreSQL** | 5432 | User schemas `user_{uid}_{db_id}`, metadata, audit |
| **Redis** | 6379 | Query cache, refresh tokens, rate limiting |
| **Kafka** | 9092 | Event streaming (audit, auth, query, schema events) |
| **ChromaDB** | 8001 | Vector embeddings for schema RAG retrieval |
| **Audit Consumer** | — | Kafka consumer persisting events to Postgres |

## Quick Start

```bash
# 1. Clone and cd into the project
cd queryai

# 2. Set your Gemini API key in .env
# GEMINI_API_KEY=AIzaSy...

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
3. Loads the data as a proper table
4. Extracts the **DDL** and generates **vector embeddings** in ChromaDB
5. Tables used for RAG-assisted SQL generation

## How It Works

1. **Upload** a CSV/XLSX/JSON file
2. **Ask** a question in natural language (e.g. "Show the top 5 products by revenue in Q3 2024")
3. **RAG** retrieves relevant table schema from ChromaDB
4. **Gemini** generates a PostgreSQL SELECT query
5. **Validator** checks query safety (read-only enforcement)
6. **PostgreSQL** executes the query against your temp schema
7. **Results** display as a sortable table or interactive chart
8. All queries are **cached in Redis** (1 hour TTL) and streamed to **Kafka**

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

**Frontend:** React 19, TypeScript, Vite 8, Tailwind CSS 3, Recharts, Lucide Icons
**Backend:** FastAPI, SQLAlchemy 2.0 (async), Pandas, Alembic
**Infra:** PostgreSQL 16, Redis 7, Kafka 7.6, ChromaDB, Docker Compose
**AI:** Google Gemini 1.5 Pro (SQL generation + text embeddings)
