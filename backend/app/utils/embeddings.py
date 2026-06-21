import logging
import hashlib
import random
from typing import List
import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)

def is_api_key_configured() -> bool:
    """Check if a valid, standard Gemini API key (starting with AIzaSy) is configured."""
    return (
        settings.GEMINI_API_KEY is not None and 
        settings.GEMINI_API_KEY.startswith("AIzaSy")
    )

if is_api_key_configured():
    genai.configure(api_key=settings.GEMINI_API_KEY)
    logger.info("Gemini Embedding API client configured successfully.")
else:
    logger.warning("GEMINI_API_KEY is not configured or is a placeholder. Using mock embeddings fallback.")

def get_embedding(text: str) -> List[float]:
    """
    Generate embedding vector. Falls back to deterministic mock vector 
    if no Gemini API key is configured.
    """
    if not is_api_key_configured():
        # Generate a deterministic mock 768-dimension vector using text hash
        hash_val = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
        rnd = random.Random(hash_val)
        return [rnd.uniform(-1.0, 1.0) for _ in range(768)]

    try:
        response = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return response["embedding"]
    except Exception as e:
        logger.error(f"Error generating embedding from Gemini API: {e}")
        raise e

def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embedding vectors for a batch of texts.
    """
    if not is_api_key_configured():
        return [get_embedding(text) for text in texts]

    try:
        response = genai.embed_content(
            model="models/embedding-001",
            content=texts,
            task_type="retrieval_document"
        )
        return response["embedding"]
    except Exception as e:
        logger.error(f"Error generating batch embeddings from Gemini API: {e}")
        raise e
