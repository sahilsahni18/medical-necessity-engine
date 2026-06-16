"""Thin wrapper over Gemini for the two language jobs: embeddings (search) and
JSON generation (answers / classification).

Default: Gemini does both (one key, reliable deploy, no local model to fit in
memory). Documented fallback: set EMBEDDING_PROVIDER=local to run a small
sentence-transformers model for embeddings instead (no quota, uses RAM).

The free embedding tier allows ~100 requests/minute, so embedding is rate-limited
here to stay safely under that, and 429s are retried with the server-suggested
delay. This makes the one-time ingest slow but reliable on the free tier.
"""

from __future__ import annotations

import collections
import json
import time

from .config import get_settings

_settings = get_settings()

# Lazily-initialised singletons.
_genai_client = None
_local_model = None

# --- simple client-side rate limiter for the free embedding tier -------------
_EMBED_MAX_PER_MIN = 90              # stay safely under the ~100/min free limit
_recent_embeds: "collections.deque[float]" = collections.deque()


def _throttle_embeddings(n: int) -> None:
    """Block until embedding `n` more items keeps us under the per-minute cap."""
    now = time.time()
    while _recent_embeds and now - _recent_embeds[0] > 60:
        _recent_embeds.popleft()
    if len(_recent_embeds) + n > _EMBED_MAX_PER_MIN and _recent_embeds:
        sleep_for = 60 - (now - _recent_embeds[0]) + 0.5
        if sleep_for > 0:
            time.sleep(sleep_for)
        now = time.time()
        while _recent_embeds and now - _recent_embeds[0] > 60:
            _recent_embeds.popleft()
    for _ in range(n):
        _recent_embeds.append(time.time())


def _client():
    global _genai_client
    if _genai_client is None:
        from google import genai  # imported lazily so tests don't need the SDK
        if not _settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env (local) or the "
                "hosting platform's environment (deployed)."
            )
        _genai_client = genai.Client(api_key=_settings.gemini_api_key)
    return _genai_client


# --- Embeddings ---------------------------------------------------------------
def _gemini_embed(texts: list[str], task_type: str) -> list[list[float]]:
    from google.genai import types
    client = _client()
    out: list[list[float]] = []
    # Small batches + throttling keep us inside the free-tier rate limit.
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        _throttle_embeddings(len(batch))
        resp = _retry(
            lambda b=batch: client.models.embed_content(
                model=_settings.embedding_model,
                contents=b,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    # Pin the output size so it matches EMBEDDING_DIM / the vector
                    # column. gemini-embedding-001 supports 768 / 1536 / 3072.
                    output_dimensionality=_settings.embedding_dim,
                ),
            )
        )
        out.extend([e.values for e in resp.embeddings])
    return out


def _local_embed(texts: list[str]) -> list[list[float]]:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer(_settings.local_embedding_model)
    return [v.tolist() for v in _local_model.encode(texts, normalize_embeddings=True)]


def embed_documents(texts: list[str]) -> list[list[float]]:
    if _settings.embedding_provider == "local":
        return _local_embed(texts)
    return _gemini_embed(texts, task_type="RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    if _settings.embedding_provider == "local":
        return _local_embed([text])[0]
    return _gemini_embed([text], task_type="RETRIEVAL_QUERY")[0]


# --- Generation ---------------------------------------------------------------
def generate_json(system_instruction: str, user_prompt: str) -> dict:
    """Generate a JSON object. Low temperature for determinism; JSON MIME type."""
    from google.genai import types
    client = _client()
    resp = _retry(
        lambda: client.models.generate_content(
            model=_settings.generation_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
    )
    text = (resp.text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = text.strip("`").replace("json", "", 1).strip()
        return json.loads(cleaned)


def _retry(fn, attempts: int = 6):
    """Backoff for transient errors. On a 429 rate-limit, wait longer (the free
    tier resets per minute) before retrying."""
    delay = 2.0
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - surface the final error
            last = exc
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                time.sleep(35)          # free-tier per-minute window
            else:
                time.sleep(delay)
                delay *= 2
    raise last