"""Retrieval layer: hybrid (vector + keyword) search with supersession routing.

Rule 5 (AMA 2021 supersedes the 1997 guidelines for office/outpatient codes
99202-99215) is implemented HERE, as a retrieval filter: when a query is about
those codes, the 1997 chunks are excluded so they can never win, and the answer
is grounded in AMA 2021. Routing the supersession at the retrieval boundary is
more robust than hoping the model remembers which rulebook to prefer.
"""

from __future__ import annotations

import re

from . import db, gemini_client
from .rules.em_rules import OFFICE_OUTPATIENT_CODES

_CODE_RE = re.compile(r"\b(992\d{2})\b")
_OUTPATIENT_HINT = re.compile(
    r"office|outpatient|established patient|new patient|e/?m level|992\d\d", re.I
)


def determine_excluded_sets(query: str) -> list[str]:
    """Decide which guideline sets to exclude for this query (supersession)."""
    codes = set(_CODE_RE.findall(query))
    mentions_outpatient_code = bool(codes & OFFICE_OUTPATIENT_CODES)
    looks_outpatient_em = bool(_OUTPATIENT_HINT.search(query))
    if mentions_outpatient_code or (looks_outpatient_em and codes):
        # Office/outpatient E/M leveling -> AMA 2021 governs; drop 1997.
        return ["CMS_1997"]
    return []


def _normalize(rows: list[dict]) -> dict[int, float]:
    if not rows:
        return {}
    scores = [r["score"] for r in rows]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    return {r["id"]: (r["score"] - lo) / span for r in rows}


def hybrid_search(query: str, k: int, candidate_k: int) -> list[dict]:
    excluded = determine_excluded_sets(query)
    emb = gemini_client.embed_query(query)

    vec_rows = db.vector_search(emb, candidate_k, excluded)
    kw_rows = db.keyword_search(query, candidate_k, excluded)

    vec_norm = _normalize(vec_rows)
    kw_norm = _normalize(kw_rows)

    merged: dict[int, dict] = {}
    for r in vec_rows + kw_rows:
        merged.setdefault(r["id"], r)

    # Weighted blend: semantic similarity leads, keyword match boosts exact tokens.
    def combined(cid: int) -> float:
        return 0.7 * vec_norm.get(cid, 0.0) + 0.3 * kw_norm.get(cid, 0.0)

    ranked = sorted(merged.values(), key=lambda r: combined(r["id"]), reverse=True)
    return ranked[:k]


def to_citation(row: dict, max_snippet: int = 200) -> dict:
    snippet = row["content"].strip().replace("\n", " ")
    if len(snippet) > max_snippet:
        snippet = snippet[:max_snippet].rsplit(" ", 1)[0] + "..."
    return {
        "guideline_set": row["guideline_set"],
        "source_document": row["source_document"],
        "location": row["location"],
        "snippet": snippet,
    }
