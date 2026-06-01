"""Embeddings via OpenAI (httpx, no SDK — matches the resume_tailor._generate pattern).

Used by discovery (embed jobs at ingest) and matching (embed profiles, vector search).
Degrades gracefully: with no OPENAI_API_KEY or on error, returns empty vectors so the
caller can fall back to lexical (Postgres FTS) retrieval. Model: text-embedding-3-small
(1536 dims) — cheap and batchable.

NOTE (fast-follow): persisting/searching vectors needs pgvector. The current Postgres
image lacks the `vector` extension, so v1 retrieval is FTS-only; wire vector columns +
HNSW once the DB image is swapped to pgvector/pgvector. These helpers are ready for that.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
_MAX_BATCH = 256


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input (empty list on failure,
    so callers can detect and fall back to lexical search)."""
    if not texts:
        return []
    if not settings.OPENAI_API_KEY:
        logger.warning("embeddings: OPENAI_API_KEY unset — returning empty vectors")
        return [[] for _ in texts]

    cleaned = [(t or "").replace("\n", " ").strip()[:8000] or " " for t in texts]
    out: list[list[float]] = []
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(cleaned), _MAX_BATCH):
                chunk = cleaned[i : i + _MAX_BATCH]
                resp = await client.post(
                    _OPENAI_EMBEDDINGS_URL,
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={"model": EMBEDDING_MODEL, "input": chunk},
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                out.extend(item["embedding"] for item in data)
        return out
    except Exception as e:  # noqa: BLE001 — never break the pipeline on embed failure
        logger.error("embeddings: batch failed (%s) — returning empty vectors", repr(e)[:200])
        return [[] for _ in texts]


async def embed_text(text: str) -> list[float]:
    """Embed a single text. Returns [] on failure."""
    result = await embed_texts([text])
    return result[0] if result else []
