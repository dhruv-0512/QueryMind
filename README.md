# QueryMind - Natural Language to SQL Platform

QueryMind lets you upload CSV, Excel, or JSON data, ask questions in plain English, and receive generated SQL plus query results.

## Architecture

```text
Frontend (React + Vite + Tailwind)
        |
        v
Backend (FastAPI)
        |
        +--> PostgreSQL temporary schemas for uploaded data
        +--> Redis for cache, refresh tokens, and rate limiting
        +--> ChromaDB for schema and SQL-example retrieval
        +--> Kafka for audit and query events
        +--> Gemini 2.5 Flash for SQL generation when GEMINI_API_KEY is configured
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | React 18 + JavaScript JSX + Vite + Tailwind CSS 3 |
| Backend | 8000 | FastAPI natural-language-to-SQL API |
| PostgreSQL | 5432 | Uploaded data, metadata, query history, audit records |
| Redis | 6379 | Query cache, refresh tokens, rate limiting |
| Kafka | 9092 | Event streaming for audit, auth, query, and schema events |
| ChromaDB | 8001 | Vector storage for schema and SQL example retrieval |
| Audit Consumer | internal | Kafka consumer that persists audit events |

## Quick Start

1. Copy environment values:

```bash
cp .env.example .env
```

2. Set your Gemini API key in `.env`:

```env
GEMINI_API_KEY=your-key-here
```

3. Start the full stack:

```bash
docker compose up -d --build
```

4. Open the app:

```text
http://localhost:3000
```

Register an account, upload a data file, select the uploaded database, and ask a question.

## Upload Formats

| Format | Extension |
|--------|-----------|
| CSV | `.csv` |
| Excel | `.xlsx`, `.xls` |
| JSON | `.json` |

On upload, QueryMind:

1. Parses the file with pandas.
2. Creates a PostgreSQL schema named `user_{user_id}_{db_id}`.
3. Loads rows into PostgreSQL using asyncpg COPY.
4. Extracts table DDL and indexes schema context in ChromaDB.
5. Uses schema retrieval and curated SQL examples to guide SQL generation.

## Query Flow

1. The user asks a natural-language question.
2. The backend retrieves relevant schema context from ChromaDB.
3. The backend retrieves similar question-to-SQL examples.
4. SQL generation uses one of these paths:
   - RAG-direct: high-similarity examples are adapted to the uploaded schema.
   - LLM-adapt: Gemini 2.5 Flash adapts the retrieved SQL pattern to the uploaded schema.
   - Mock fallback: local testing path when no Gemini key is configured.
5. Generated SQL is validated as read-only SQL.
6. PostgreSQL executes the query against the uploaded data schema.
7. Results are cached in Redis and streamed to Kafka for audit history.

## Query Features

- SQL viewer with copy support and confidence score.
- Results table with pagination and type-aware formatting.
- Chart view powered by Recharts.
- Query history tracking.
- Admin views for users, query history, and system stats.

## Query Safety

- Only `SELECT` and `WITH` queries are allowed.
- Dangerous keywords such as `DROP`, `DELETE`, `ALTER`, `INSERT`, and `UPDATE` are blocked.
- Results are capped at 1,000 rows.
- Query execution timeout is 30 seconds.
- JWT authentication protects API routes.
- Redis-backed rate limiting applies per user.

## Development

Frontend only:

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Backend only:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The frontend is JavaScript/JSX, not TypeScript. Main frontend files live under `frontend/src` as `.jsx` files.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini API key for SQL generation |
| `EMBEDDING_PROVIDER` | `local`, `gemini`, or `auto` |
| `JWT_SECRET_KEY` | Secret used to sign JWTs |
| `JWT_ALGORITHM` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address |
| `CHROMADB_HOST` / `CHROMADB_PORT` | ChromaDB connection |

## Tech Stack

- Frontend: React 18, JavaScript JSX, Vite 5, Tailwind CSS 3, Recharts, Lucide Icons
- Backend: FastAPI, SQLAlchemy 2 async, asyncpg, pandas, Alembic
- Infrastructure: PostgreSQL 16, Redis 7, Kafka 7.6, ChromaDB, Docker Compose
- AI/RAG: Gemini 2.5 Flash, ChromaDB retrieval, local BGE embeddings fallback via fastembed