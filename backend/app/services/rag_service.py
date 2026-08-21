import json
import logging
from typing import Dict, Any, List, Optional
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
            mode = getattr(settings, "CHROMADB_MODE", "persistent").lower()
            host = settings.CHROMADB_HOST
            port = settings.CHROMADB_PORT
            path = getattr(settings, "CHROMADB_PATH", "./chroma_data")

            if mode == "http":
                logger.info(f"Connecting to ChromaDB HTTP server at {host}:{port}...")
                self.client = chromadb.HttpClient(host=host, port=port)
            else:
                # Attempt HttpClient if external host is explicitly provided, otherwise PersistentClient
                if host and host not in ("localhost", "127.0.0.1") and not host.startswith("."):
                    try:
                        logger.info(f"Attempting connection to ChromaDB HTTP server at {host}:{port}...")
                        client = chromadb.HttpClient(host=host, port=port)
                        client.heartbeat()
                        self.client = client
                    except Exception as http_err:
                        logger.info(f"HTTP connection to {host}:{port} failed ({http_err}). Using PersistentClient at '{path}'.")
                        self.client = chromadb.PersistentClient(path=path)
                else:
                    logger.info(f"Initializing ChromaDB PersistentClient at '{path}'...")
                    self.client = chromadb.PersistentClient(path=path)

            self.collection = self.client.get_or_create_collection(
                name="database_schemas"
            )
            logger.info("ChromaDB connection successful.")
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

    async def retrieve_schema_context(self, db_id: str, query: str, limit: int = 5, schema_info: Optional[Dict[str, Any]] = None) -> str:
        """
        Embed the user query, search ChromaDB for top relevant tables,
        and combine them into a single string context.
        When schema_info is provided, also retrieves connected tables via FK graph.
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
            retrieved_table_names = set()
            if results and "documents" in results and results["documents"]:
                for docs in results["documents"]:
                    for doc in docs:
                        retrieved_chunks.append(doc)
                        # Extract table name from chunk
                        import re
                        m = re.search(r'Table:\s*"([^"]+)"', doc)
                        if m:
                            retrieved_table_names.add(m.group(1).lower())

            # Relationship-aware expansion: pull in FK-connected tables
            if schema_info and retrieved_table_names:
                try:
                    from app.services.relationship_service import relationship_service
                    fk_graph = relationship_service.build_fk_graph(schema_info)
                    connected = relationship_service.get_connected_tables(
                        list(retrieved_table_names), fk_graph, max_hops=2
                    )
                    missing = connected - retrieved_table_names
                    if missing:
                        logger.info(f"[RAG EXPANSION] Adding {missing} via FK graph")
                        # Get chunks for missing tables from schema_info directly
                        chunks_by_table = {c["table_name"].lower(): c["chunk_text"] for c in schema_info.get("chunks", [])}
                        for tbl in missing:
                            if tbl in chunks_by_table:
                                retrieved_chunks.append(chunks_by_table[tbl])
                except Exception as expand_err:
                    logger.warning(f"[RAG EXPANSION] Failed: {expand_err}")

            context_string = "\n\n".join(retrieved_chunks)
            return context_string
        except Exception as e:
            logger.error(f"Failed to query ChromaDB for context: {e}")
            raise e

rag_service = RagService()
