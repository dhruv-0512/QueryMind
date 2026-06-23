import json
import logging
from typing import Dict, Any, List
import chromadb
from app.config import settings
from app.utils.embeddings import get_embedding, get_embeddings_batch, get_query_embedding

logger = logging.getLogger(__name__)

class RagService:
    def __init__(self) -> None:
        """Setup lazy initialization handles."""
        self.client = None
        self.collection = None

    def _ensure_connected(self) -> None:
        """Ensure connection to ChromaDB is active; connects if not currently initialized."""
        if self.collection is not None:
            return
        try:
            logger.info(f"Establishing lazy connection to ChromaDB at {settings.CHROMADB_HOST}:{settings.CHROMADB_PORT}...")
            self.client = chromadb.HttpClient(
                host=settings.CHROMADB_HOST,
                port=settings.CHROMADB_PORT
            )
            self.collection = self.client.get_or_create_collection(
                name="database_schemas"
            )
            logger.info("ChromaDB lazy connection successful.")
        except Exception as e:
            logger.error(f"Failed to establish connection to ChromaDB: {e}")
            raise RuntimeError(f"ChromaDB connection failure: {e}")

    async def index_schema(self, db_id: str, table_chunks: List[Dict[str, Any]]) -> None:
        """
        Generates embeddings for each table DDL chunk and index them into ChromaDB.
        Each table chunk format: { 'table_name': str, 'chunk_text': str, 'columns': List[str] }
        """
        self._ensure_connected()

        ids = []
        embeddings = []
        metadatas = []
        documents = []

        # Prepare batch vectors
        texts = [chunk["chunk_text"] for chunk in table_chunks]
        try:
            # Generate embeddings in batch (or sequentially if needed, but batch is faster)
            logger.info(f"Generating embeddings for {len(texts)} tables in database {db_id}...")
            raw_embeddings = get_embeddings_batch(texts)
        except Exception as e:
            logger.error(f"Failed to generate embeddings during indexing: {e}")
            raise e

        for idx, chunk in enumerate(table_chunks):
            table_name = chunk["table_name"]
            ids.append(f"{db_id}:{table_name}")
            embeddings.append(raw_embeddings[idx])
            metadatas.append({
                "db_id": db_id,
                "table_name": table_name,
                "columns": json.dumps(chunk["columns"])
            })
            documents.append(chunk["chunk_text"])

        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            logger.info(f"Successfully indexed {len(table_chunks)} tables for database {db_id} in ChromaDB.")
        except Exception as e:
            logger.error(f"Failed to write schemas to ChromaDB: {e}")
            raise e

    async def delete_schema(self, db_id: str) -> None:
        """Delete all indexed schema chunks for a specific database ID."""
        self._ensure_connected()

        try:
            self.collection.delete(
                where={"db_id": db_id}
            )
            logger.info(f"Successfully deleted ChromaDB schema entries for database {db_id}")
        except Exception as e:
            logger.error(f"Failed to delete schemas from ChromaDB for database {db_id}: {e}")
            raise e

    async def retrieve_schema_context(self, db_id: str, query: str, limit: int = 5) -> str:
        """
        Embed the user query, search ChromaDB for top relevant tables,
        and combine them into a single string context.
        """
        self._ensure_connected()

        try:
            query_vector = get_query_embedding(query)
            
            results = self.collection.query(
                query_embeddings=[query_vector],
                where={"db_id": db_id},
                n_results=limit
            )

            retrieved_chunks = []
            if results and "documents" in results and results["documents"]:
                # results['documents'] is a list of lists of strings
                for docs in results["documents"]:
                    for doc in docs:
                        retrieved_chunks.append(doc)

            context_string = "\n\n".join(retrieved_chunks)
            return context_string
        except Exception as e:
            logger.error(f"Failed to query ChromaDB for context: {e}")
            raise e

rag_service = RagService()
