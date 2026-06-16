"""Ingestion pipeline (offline, run once).

Turns the guideline documents into searchable, citable chunks:
parse -> structure-aware chunk (with page metadata) -> embed -> store.

Run via `python -m scripts.ingest`. The heavy embedding work happens here, once;
the resulting vectors live in Postgres so the live API does almost no AI work
per request.
"""

from __future__ import annotations

import os

from pypdf import PdfReader

from . import db, gemini_client
from .config import get_settings

_settings = get_settings()

# Map each shipped file to its machine-readable guideline_set tag. These tags
# drive both citations and the supersession routing in retrieval.py.
GUIDELINE_SETS = {
    "AMA_Guidelines.pdf": "AMA_2021",
    "97_Doc_guidelines.pdf": "CMS_1997",
    "JAWDA_Data_Certification_for_Healthcare_Providers_2026-Part_IX.pdf": "JAWDA",
    "clinical_coding_process_review.pdf": "JAWDA",
    "HAAD_CodingManual_V7.txt": "HAAD",
}


def _chunk(text: str) -> list[str]:
    """Character-based chunking with overlap. Paragraph-aware: we accumulate
    paragraphs until the size budget, so we rarely cut mid-sentence."""
    size, overlap = _settings.chunk_chars, _settings.chunk_overlap
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            # start new buffer carrying a tail of the previous one for context
            tail = buf[-overlap:] if buf else ""
            buf = f"{tail}\n{p}".strip() if tail else p
    if buf:
        chunks.append(buf)
    return [c for c in chunks if len(c) > 40]


def _load_file(path: str, filename: str) -> list[tuple[str, str]]:
    """Return list of (location_label, text) units for a file."""
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(path)
        units = []
        for i, page in enumerate(reader.pages, start=1):
            txt = page.extract_text() or ""
            if txt.strip():
                units.append((f"page {i}", txt))
        return units
    # plain text (e.g. the converted HAAD manual): one logical unit
    with open(path, encoding="utf-8", errors="ignore") as f:
        return [("full document", f.read())]


def run_ingestion() -> dict:
    db.init_schema()
    db.clear_chunks()

    base = _settings.guidelines_dir
    total = 0
    per_doc: dict[str, int] = {}

    for filename in sorted(os.listdir(base)):
        if filename not in GUIDELINE_SETS:
            continue
        gset = GUIDELINE_SETS[filename]
        path = os.path.join(base, filename)
        units = _load_file(path, filename)

        texts: list[str] = []
        meta: list[dict] = []
        for location, text in units:
            for ci, chunk in enumerate(_chunk(text)):
                texts.append(chunk)
                meta.append(
                    {
                        "guideline_set": gset,
                        "source_document": filename,
                        "location": location,
                        "chunk_index": ci,
                        "content": chunk,
                    }
                )

        # Embed in the pipeline (once), store with metadata.
        embeddings = gemini_client.embed_documents(texts)
        for m, e in zip(meta, embeddings):
            m["embedding"] = e
        db.insert_chunks(meta)

        per_doc[filename] = len(meta)
        total += len(meta)

    return {"total_chunks": total, "per_document": per_doc}
