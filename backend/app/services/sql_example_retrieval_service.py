import hashlib
import logging
from typing import Dict, Any, List
import chromadb
from app.config import settings
from app.utils.embeddings import get_embeddings_batch, get_query_embedding

logger = logging.getLogger(__name__)


def _stable_id(source: str, question: str, sql: str) -> str:
    content = f"{source}|{question.strip().lower()}|{sql.strip().lower()}"
    return f"ex:{source}:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def _distance_to_similarity(distance: float) -> float:
    """Convert Chroma L2 distance to a 0-1 similarity score."""
    return max(0.0, min(1.0, 1.0 / (1.0 + distance)))


class SqlExampleRetrievalService:
    def __init__(self) -> None:
        self.client = None
        self.collection = None

    def _ensure_connected(self) -> None:
        if self.collection is not None:
            return
        try:
            logger.info(
                f"Connecting to ChromaDB for SQL examples at "
                f"{settings.CHROMADB_HOST}:{settings.CHROMADB_PORT}..."
            )
            self.client = chromadb.HttpClient(
                host=settings.CHROMADB_HOST,
                port=settings.CHROMADB_PORT,
            )
            self.collection = self.client.get_or_create_collection(
                name="sql_examples_collection",
            )
            logger.info("ChromaDB SQL examples collection ready.")
        except Exception as e:
            logger.error(f"ChromaDB connection failure: {e}")
            raise RuntimeError(f"ChromaDB connection failure: {e}")

    def reset_collection(self) -> None:
        self._ensure_connected()
        self.client.delete_collection("sql_examples_collection")
        self.collection = self.client.get_or_create_collection(
            name="sql_examples_collection",
        )

    async def upsert_examples(self, examples: List[Dict[str, Any]]) -> None:
        """Idempotent upsert of question-SQL pairs with stable IDs."""
        self._ensure_connected()
        if not examples:
            return

        texts = [ex["question"] for ex in examples]
        raw_embeddings = get_embeddings_batch(texts)

        ids, embeddings, metadatas, documents = [], [], [], []
        for idx, ex in enumerate(examples):
            example_id = ex.get("id") or _stable_id(ex["source"], ex["question"], ex["sql"])
            ids.append(example_id)
            embeddings.append(raw_embeddings[idx])
            metadatas.append({
                "question": ex["question"],
                "sql": ex["sql"],
                "pattern_type": ex.get("pattern_type", "unknown"),
                "complexity": ex.get("complexity", "unknown"),
                "source": ex["source"],
            })
            documents.append(ex["question"])

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        logger.info(f"Upserted {len(examples)} SQL examples.")

    async def add_examples(self, examples: List[Dict[str, Any]]) -> None:
        """Backward-compatible alias for upsert."""
        await self.upsert_examples(examples)

    async def retrieve_examples(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Return top semantically similar question-SQL pairs with similarity scores."""
        self._ensure_connected()

        query_vector = get_query_embedding(query)
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            include=["metadatas", "distances"],
        )

        retrieved = []
        if results and results.get("metadatas"):
            distances = results.get("distances", [[]])[0]
            for i, meta in enumerate(results["metadatas"][0]):
                distance = distances[i] if i < len(distances) else 1.0
                retrieved.append({
                    "question": meta.get("question"),
                    "sql": meta.get("sql"),
                    "pattern_type": meta.get("pattern_type"),
                    "complexity": meta.get("complexity"),
                    "source": meta.get("source"),
                    "similarity": round(_distance_to_similarity(distance), 4),
                })
        return retrieved

    def count_examples(self) -> int:
        self._ensure_connected()
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Failed to count collection entries: {e}")
            return 0


sql_example_retrieval_service = SqlExampleRetrievalService()
