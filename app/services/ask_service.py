"""Q&A service for /ask: retrieve tightly, answer only from context, cite."""

from __future__ import annotations

import re

from .. import gemini_client, prompts, retrieval
from ..config import get_settings
from ..rules import em_rules, jawda_rules
from ..schemas import AskResponse, Citation, clamp_sentences

_settings = get_settings()

# Detect questions that ask what an office/outpatient E/M code *requires*, so we
# can answer from the deterministic rules engine instead of relying on retrieval
# (whose AMA-table chunks extract poorly and make the model abstain at random).
_CODE_RE = re.compile(r"\b(992\d{2})\b")
_REQUIREMENT_INTENT_RE = re.compile(
    r"\b(require|requires|required|requirement|requirements|qualif\w*|need|needs|"
    r"needed|criteri\w*|select|selected|what\s+level|mdm|medical\s+decision|"
    r"time\s+range|how\s+long|how\s+many)\b",
    re.I,
)

# Questions about which guideline VERSION governs a code (the core of Rule 5).
# These have no requirement word ("which version is in effect for 99212?"), so
# without this they fall to RAG and may hedge on the supersession conflict.
_GOVERNANCE_INTENT_RE = re.compile(
    r"\b(which|what)\s+(version|guideline|guidelines|rule|rules|ruleset)\b"
    r"|\b(in\s+effect|governs?|governing|supersed\w*|applies?\s+to|effective)\b"
    r"|\b(1997|1995)\b",
    re.I,
)

# Questions about JAWDA scoring/penalties. Gated so that a question merely
# *mentioning* a form ("is a consent form required?") is not answered with a
# point deduction -- only questions about the score/penalty itself are.
_PENALTY_INTENT_RE = re.compile(
    r"\b(score|scores|scoring|deduct\w*|points?|penalt\w*|lose|lost|losing|"
    r"error|jawda|audit)\b",
    re.I,
)


def _deterministic_code_answer(question: str) -> AskResponse | None:
    """Answer "what does code X require?" from the hardcoded engine when the
    question is clearly about office/outpatient leveling. Returns None otherwise
    (e.g. a reimbursement question that merely mentions a code), so the caller
    falls back to the retrieval path."""
    codes = [c for c in _CODE_RE.findall(question) if em_rules.is_office_outpatient(c)]
    if not codes or not _REQUIREMENT_INTENT_RE.search(question):
        return None
    summary = em_rules.requirement_summary(codes[0])
    if not summary:
        return None
    return AskResponse(
        answer=clamp_sentences(summary["answer"], _settings.max_answer_sentences),
        citations=[Citation(**c) for c in summary["citations"]],
        governing_guideline="AMA_2021",
        insufficient_evidence=False,
    )


def _deterministic_governance_answer(question: str) -> AskResponse | None:
    """Answer "which guideline version governs / is in effect for code X?"
    decisively from the supersession rule (AMA 2021 for 99202-99215). Returns
    None otherwise, so non-outpatient codes fall through to retrieval."""
    codes = [c for c in _CODE_RE.findall(question) if em_rules.is_office_outpatient(c)]
    if not codes or not _GOVERNANCE_INTENT_RE.search(question):
        return None
    summary = em_rules.governance_summary(codes[0])
    if not summary:
        return None
    return AskResponse(
        answer=clamp_sentences(summary["answer"], _settings.max_answer_sentences),
        citations=[Citation(**c) for c in summary["citations"]],
        governing_guideline="AMA_2021",
        insufficient_evidence=False,
    )


def _deterministic_jawda_answer(question: str) -> AskResponse | None:
    """Answer "what score is deducted if X?" from the hardcoded JAWDA penalty
    table when the question is clearly about scoring. Returns None otherwise."""
    if not _PENALTY_INTENT_RE.search(question):
        return None
    penalty = jawda_rules.match_penalty(question)
    if penalty is None:
        return None
    summary = jawda_rules.penalty_answer(penalty)
    return AskResponse(
        answer=clamp_sentences(summary["answer"], _settings.max_answer_sentences),
        citations=[Citation(**c) for c in summary["citations"]],
        governing_guideline="JAWDA",
        insufficient_evidence=False,
    )


def answer_question(question: str) -> AskResponse:
    # Deterministic fast paths: code-requirement and JAWDA-penalty questions are
    # answered from the rules engines (always correct, always cited, never a coin
    # flip). Anything else falls through to grounded retrieval below.
    for handler in (
        _deterministic_code_answer,
        _deterministic_governance_answer,
        _deterministic_jawda_answer,
    ):
        deterministic = handler(question)
        if deterministic is not None:
            return deterministic

    rows = retrieval.hybrid_search(question, _settings.top_k, _settings.candidate_k)

    if not rows:
        return AskResponse(
            answer="The provided guideline documents do not contain information to answer this.",
            citations=[],
            insufficient_evidence=True,
        )

    # Build a numbered context block so the model can cite by id.
    context_lines = []
    by_id: dict[int, dict] = {}
    for r in rows:
        by_id[r["id"]] = r
        context_lines.append(
            f'[id={r["id"]}] ({r["guideline_set"]} - {r["source_document"]}, {r["location"]})\n'
            f'{r["content"]}'
        )
    context = "\n\n".join(context_lines)

    result = gemini_client.generate_json(
        prompts.ASK_SYSTEM,
        prompts.ASK_USER.format(question=question, context=context),
    )

    insufficient = bool(result.get("insufficient_evidence", False))
    answer = clamp_sentences(result.get("answer", ""), _settings.max_answer_sentences)

    used_ids = result.get("used_ids") or []
    cited_rows = [by_id[i] for i in used_ids if i in by_id]
    if not cited_rows and not insufficient:
        cited_rows = rows[:1]  # fall back to the top hit so we never omit a citation

    citations = [Citation(**retrieval.to_citation(r)) for r in cited_rows]
    governing = cited_rows[0]["guideline_set"] if cited_rows else None

    return AskResponse(
        answer=answer or "The documents do not contain enough information to answer this.",
        citations=citations,
        governing_guideline=governing,
        insufficient_evidence=insufficient,
    )