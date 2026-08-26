import logging
import threading
import time
from typing import List

import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32
EMBED_MAX_RETRIES = 2
GEMINI_BATCH_SIZE = 8
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_local_model = None
_local_lock = threading.Lock()


def is_api_key_configured() -> bool:
    return (
        settings.GEMINI_API_KEY is not None
        and (
            settings.GEMINI_API_KEY.startswith("AIzaSy")
            or settings.GEMINI_API_KEY.startswith("AQ")
        )
    )


if is_api_key_configured():
    genai.configure(api_key=settings.GEMINI_API_KEY)


def _provider() -> str:
    return settings.EMBEDDING_PROVIDER.lower()


def _get_local_model():
    global _local_model
    with _local_lock:
        if _local_model is None:
            from fastembed import TextEmbedding

            logger.info("Loading local embedding model BAAI/bge-small-en-v1.5...")
            _local_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            logger.info("Local embedding model ready.")
        return _local_model


def _local_embed_batch(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = _get_local_model()
    return [vec.tolist() for vec in model.embed(texts, batch_size=EMBED_BATCH_SIZE)]


def _gemini_embed_batch(texts: List[str], task_type: str) -> List[List[float]]:
    response = genai.embed_content(
        model="models/gemini-embedding-001",
        content=texts,
        task_type=task_type,
    )
    embeddings = response["embedding"]
    if texts and embeddings and not isinstance(embeddings[0], (list, tuple)):
        return [embeddings]
    return embeddings


_gemini_quota_exhausted = False

def _gemini_embed_with_retry(texts: List[str], task_type: str) -> List[List[float]]:
    global _gemini_quota_exhausted
    if _gemini_quota_exhausted:
        raise RuntimeError("Gemini daily quota exhausted")
    last_error = None
    for attempt in range(EMBED_MAX_RETRIES):
        try:
            return _gemini_embed_batch(texts, task_type)
        except Exception as e:
            last_error = e
            err = str(e)
            if "quota exceeded" in err.lower():
                _gemini_quota_exhausted = True
                logger.warning(f"Gemini daily embedding quota exceeded, marking exhausted: {e}")
                raise RuntimeError(f"Gemini daily quota exceeded: {e}")
            if "429" in err:
                wait = min(30, 2 ** attempt * 4)
                logger.warning(f"Gemini rate limit, retry in {wait}s ({attempt + 1}/{EMBED_MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Gemini embedding failed after retries: {last_error}")


def _embed_with_provider(texts: List[str], task_type: str) -> List[List[float]]:
    provider = _provider()

    if provider == "local":
        return _local_embed_batch(texts)

    if provider == "gemini":
        results: List[List[float]] = []
        for start in range(0, len(texts), GEMINI_BATCH_SIZE):
            chunk = texts[start : start + GEMINI_BATCH_SIZE]
            results.extend(_gemini_embed_with_retry(chunk, task_type))
        return results

    # auto: try Gemini per small chunk, fall back to local on any failure
    if not is_api_key_configured():
        return _local_embed_batch(texts)

    results = []
    for start in range(0, len(texts), GEMINI_BATCH_SIZE):
        chunk = texts[start : start + GEMINI_BATCH_SIZE]
        try:
            results.extend(_gemini_embed_with_retry(chunk, task_type))
        except Exception as e:
            logger.warning(f"Gemini unavailable ({e}), using local embeddings for chunk")
            results.extend(_local_embed_batch(chunk))
    return results


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Document embeddings for ChromaDB indexing."""
    return _embed_with_provider(texts, "retrieval_document")


def get_embedding(text: str) -> List[float]:
    return get_embeddings_batch([text])[0]


_query_cache: dict = {}

def get_query_embedding(text: str) -> List[float]:
    """Query embedding — BGE prefix for local, retrieval_query for Gemini with in-memory caching."""
    if text in _query_cache:
        return _query_cache[text]

    if _provider() == "local" or (_provider() == "auto" and not is_api_key_configured()):
        res = _local_embed_batch([BGE_QUERY_PREFIX + text])[0]
        _query_cache[text] = res
        return res

    if _provider() == "gemini":
        res = _embed_with_provider([text], "retrieval_query")[0]
        _query_cache[text] = res
        return res

    # auto with Gemini key: try Gemini query embed, fall back to BGE
    try:
        res = _gemini_embed_with_retry([text], "retrieval_query")[0]
        _query_cache[text] = res
        return res
    except Exception as e:
        logger.warning(f"Gemini query embed failed ({e}), using local model")
        res = _local_embed_batch([BGE_QUERY_PREFIX + text])[0]
        _query_cache[text] = res
        return res
