# QueryMind 🧠
> Natural Language to SQL Platform

Ask questions in plain English and get instant SQL results against your uploaded data.

## 🎯 Built to demonstrate
Backend Engineering · Distributed Systems · RAG Pipelines · Event-Driven Architecture · Production Security

## Architecture
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   Backend    │────▶│  PostgreSQL  │
│  React+Vite  │     │   FastAPI    │     │ temp schemas │
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
| Service        | Port | Purpose                                        |
|----------------|------|------------------------------------------------|
| Frontend       | 3000 | React 19 + Vite + Tailwind CSS                 |
| Backend        | 8000 | FastAPI (Python 3.12), NLP→SQL pipeline        |
| PostgreSQL     | 5432 | User schemas, metadata, audit logs             |
| Redis          | 6379 | Query cache, refresh tokens, rate limiting     |
| Kafka          | 9092 | Event streaming (KRaft mode, no ZooKeeper)     |
| ChromaDB       | 8001 | Vector embeddings for RAG schema retrieval     |
| Audit Consumer | —    | Kafka consumer persisting events to PostgreSQL |

## Quick Start

**1. Clone the repo**
```bash
git clone https://github.com/dhruv-0512/QueryMind
cd querymind
```

**2. Add your Gemini API key**
```bash
cp .env.example .env
# Set GEMINI_API_KEY=AIzaSy...
```

**3. Start everything**
```bash
docker compose up -d --build
```

Open http://localhost:3000 — register and start querying.

## Upload Formats
Drag-and-drop upload supported:

| Format | Extension   |
|--------|-------------|
| CSV    | .csv        |
| Excel  | .xlsx, .xls |
| JSON   | .json       |

On upload, the system:
1. Parses file with pandas (auto-detects columns & types)
2. Creates isolated PostgreSQL schema: `user_{user_id}_{db_id}`
3. Loads data as a proper relational table
4. Extracts DDL and generates vector embeddings in ChromaDB
5. Schema used for RAG-assisted SQL generation

## How It Works
1. Upload a CSV, Excel, or JSON file
2. Ask a question in plain English e.g. "Show top 5 products by revenue in Q3 2024"
3. RAG retrieves relevant schema chunks from ChromaDB
4. Gemini 1.5 Flash generates a PostgreSQL SELECT query
5. Validator enforces read-only safety rules
6. PostgreSQL executes query against your isolated schema
7. Results display as sortable table or interactive chart
8. Results cached in Redis (1hr TTL), events streamed to Kafka

## Query Security
- ✅ Only SELECT and WITH (CTE) queries allowed
- ❌ Blocked: DROP, DELETE, ALTER, INSERT, UPDATE, TRUNCATE
- ⏱️ 30 second query timeout
- 📊 1,000 row result limit
- 🔐 JWT auth with refresh token rotation
- 🚦 Redis sliding window rate limiting (10 req/min per user)
- 📝 Full audit trail via Kafka → PostgreSQL

## Event-Driven Architecture
All major operations publish to Kafka topics:

| Topic        | Events                                     |
|--------------|--------------------------------------------|
| auth-events  | UserRegistered, UserLoggedIn, UserLoggedOut |
| query-events | QueryExecuted, QueryFailed, CacheHit       |
| schema-events| SchemaIndexed, SchemaUpdated               |
| audit-events | Consumed by Audit Service → PostgreSQL     |

## Environment Variables
| Variable                      | Description                          |
|-------------------------------|--------------------------------------|
| GEMINI_API_KEY                | Google Gemini API key                |
| JWT_SECRET_KEY                | Secret for JWT signing               |
| DATABASE_URL                  | PostgreSQL connection string         |
| REDIS_URL                     | Redis connection string              |
| KAFKA_BOOTSTRAP_SERVERS       | Kafka broker address                 |
| CHROMADB_HOST / CHROMADB_PORT | ChromaDB connection                  |
| FERNET_KEY                    | Encryption key for stored credentials|

## Tech Stack
**Frontend:** React 19, TypeScript, Vite, Tailwind CSS, Recharts, Lucide Icons

**Backend:** FastAPI, SQLAlchemy 2.0 async, Pandas, Alembic, aiokafka, passlib

**Infrastructure:** PostgreSQL 16, Redis 7, Kafka 3.7 (KRaft), ChromaDB, Docker Compose

**AI:** Gemini 1.5 Flash (SQL generation) + text-embedding-004 (schema embeddings)

## Development

**Frontend**
```bash
cd frontend && npm install && npm run dev
```

**Backend**
```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload
```
