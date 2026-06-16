"""API contracts (Pydantic v2).

These models enforce the assignment's answer-quality rules structurally:
- Structured response is mandatory (Rule 4) -> every answer is a typed object.
- Max 4 sentences per free-text field (Rule 4) -> `clamp_sentences` helper.
- Citations are first-class (Rule 2).
- An explicit `insufficient_evidence` flag (Rule 6).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def clamp_sentences(text: str, max_sentences: int = 4) -> str:
    text = (text or "").strip()
    if not text:
        return text
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    return " ".join(parts[:max_sentences]).strip()


class Citation(BaseModel):
    guideline_set: str
    source_document: str
    location: str = ""
    snippet: str = ""


# --- /ask ---------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    governing_guideline: str | None = None
    insufficient_evidence: bool = False


# --- /analyze-encounter -------------------------------------------------------
class DocumentationModel(BaseModel):
    HPI: str = ""
    exam: str = ""
    assessment: str = ""
    time_minutes: int | None = None  # optional; enables time-based leveling

    model_config = {"extra": "allow"}


class EncounterRequest(BaseModel):
    visit_type: str = "outpatient"
    chief_complaint: str = ""
    diagnoses: list[str] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)
    documentation: DocumentationModel = Field(default_factory=DocumentationModel)
    billed_code: str


class MdmBreakdown(BaseModel):
    problems: str | None = None
    data: str | None = None
    risk: str | None = None
    achieved_level: str | None = None
    required_level: str | None = None


class EncounterAnalysisResponse(BaseModel):
    billed_code: str
    governing_guideline: str
    supports_billed_code: str          # supported | not_supported | indeterminate
    code_assessment: str               # <= 4 sentences
    documentation_gaps: list[str] = Field(default_factory=list)
    denial_risk: str                   # low | medium | high
    denial_risk_rationale: str         # <= 4 sentences
    mdm_breakdown: MdmBreakdown | None = None
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = False
