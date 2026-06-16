"""Encounter analysis for /analyze-encounter.

Pipeline (the split discussed in design):
1. Supersession -> pick the governing guideline for the billed code.
2. LLM classifies the free-text documentation into MDM tiers, grounded by the
   actual AMA 2021 criteria text (the only fuzzy step).
3. The hardcoded rules engine turns those tiers into a deterministic verdict.
4. Time-based check, documentation gaps, and a denial-risk heuristic.

The DECISION is always deterministic code; the LLM only reads and labels the
messy notes.
"""

from __future__ import annotations

from .. import gemini_client, prompts, retrieval
from ..config import get_settings
from ..rules import em_rules
from ..schemas import (
    Citation,
    EncounterAnalysisResponse,
    EncounterRequest,
    MdmBreakdown,
    clamp_sentences,
)

_settings = get_settings()
_VALID_TIERS = set(em_rules.LEVEL_ORDER)


def _classify(req: EncounterRequest) -> dict:
    doc = req.documentation
    user = prompts.CLASSIFY_USER.format(
        visit_type=req.visit_type,
        chief_complaint=req.chief_complaint or "(none)",
        diagnoses=", ".join(req.diagnoses) or "(none)",
        procedures=", ".join(req.procedures) or "(none)",
        hpi=doc.HPI or "(none)",
        exam=doc.exam or "(none)",
        assessment=doc.assessment or "(none)",
        problems_criteria="\n".join(f"- {k}: {v}" for k, v in em_rules.PROBLEMS_CRITERIA.items()),
        data_criteria="\n".join(f"- {k}: {v}" for k, v in em_rules.DATA_CRITERIA.items()),
        risk_criteria="\n".join(f"- {k}: {v}" for k, v in em_rules.RISK_CRITERIA.items()),
    )
    return gemini_client.generate_json(prompts.CLASSIFY_SYSTEM, user)


def _tier(value, default="straightforward") -> str:
    t = (value or {}).get("tier", default) if isinstance(value, dict) else default
    return t if t in _VALID_TIERS else default


def analyze(req: EncounterRequest) -> EncounterAnalysisResponse:
    code = req.billed_code.strip()
    gov = em_rules.governing_guideline(code)
    gov_label = f'{gov.guideline_set} ({gov.location})'

    # Codes outside the office/outpatient family: the AMA 2021 MDM grid does not
    # apply, so we do not invent a leveling verdict (Rule 6).
    if not em_rules.is_office_outpatient(code):
        return EncounterAnalysisResponse(
            billed_code=code,
            governing_guideline=gov_label,
            supports_billed_code="indeterminate",
            code_assessment=(
                f"{code} is not an office/outpatient E/M code (99202-99215), so the "
                "AMA 2021 MDM leveling used here does not apply. This assistant cannot "
                "determine support for it from the provided guidelines."
            ),
            documentation_gaps=[],
            denial_risk="medium",
            denial_risk_rationale=(
                "Without an applicable leveling rule, denial risk cannot be assessed "
                "from the documents; refer to the HAAD Coding Manual for this code family."
            ),
            citations=[Citation(**gov.as_dict())],
            insufficient_evidence=True,
        )

    cls = _classify(req)
    problems = _tier(cls.get("problems"))
    data = _tier(cls.get("data"))
    risk = _tier(cls.get("risk"))
    llm_gaps = [g for g in (cls.get("documentation_gaps") or []) if isinstance(g, str)]

    mdm = em_rules.assess_mdm(code, problems, data, risk)

    # Optional time-based corroboration when the encounter time is documented.
    time_note = ""
    minutes = req.documentation.time_minutes
    if minutes is not None:
        if em_rules.time_supports_code(code, minutes):
            time_note = f" Documented time ({minutes} min) is within the {code} range, which independently supports the code."
        else:
            best = em_rules.code_for_time(minutes, established=code.startswith("9921"))
            time_note = f" Documented time ({minutes} min) does not fall in the {code} range" + (f" (it matches {best})." if best else ".")

    # Deterministic documentation gaps in addition to the LLM's.
    gaps = list(llm_gaps)
    if not req.documentation.assessment:
        gaps.append("No assessment / clinical impression documented (required for each encounter).")
    if not req.documentation.HPI:
        gaps.append("No history of present illness (HPI) documented.")

    # Verdict + denial-risk heuristic.
    if mdm.verdict == "overcoded":
        supports, risk_level = "not_supported", "high"
    elif gaps:
        supports, risk_level = "supported", "medium"
    else:
        supports, risk_level = "supported", "low"

    code_assessment = clamp_sentences(
        f"Documentation supports {mdm.achieved_level} MDM, while {code} requires "
        f"{mdm.required_level} MDM, so the billed code is {'supported' if supports == 'supported' else 'not supported (over-coded)'}."
        + (f" The documentation could justify a higher level." if mdm.verdict == "undercoded" else "")
        + time_note,
        _settings.max_answer_sentences,
    )

    # Pull one cited passage on medical necessity for the rationale.
    nec_rows = retrieval.hybrid_search(
        f"medical necessity documentation requirements {code} {' '.join(req.diagnoses)}",
        2, _settings.candidate_k,
    )
    citations = [Citation(**em_rules.CITATION_MDM)]
    if minutes is not None:
        citations.append(Citation(**em_rules.CITATION_TIME))
    citations += [Citation(**retrieval.to_citation(r)) for r in nec_rows]

    rationale = clamp_sentences(
        {
            "high": f"The billed level exceeds what the notes support, which JAWDA scores as a billing accuracy error and payers deny for lack of medical necessity. Strengthen the {mdm.required_level}-level elements before submitting.",
            "medium": "The code is supported, but documentation gaps could be challenged on medical-necessity review; closing the listed gaps reduces denial risk.",
            "low": "The documentation supports the billed code with no major gaps, so denial risk on medical-necessity grounds is low.",
        }[risk_level],
        _settings.max_answer_sentences,
    )

    return EncounterAnalysisResponse(
        billed_code=code,
        governing_guideline=gov_label,
        supports_billed_code=supports,
        code_assessment=code_assessment,
        documentation_gaps=gaps,
        denial_risk=risk_level,
        denial_risk_rationale=rationale,
        mdm_breakdown=MdmBreakdown(
            problems=problems, data=data, risk=risk,
            achieved_level=mdm.achieved_level, required_level=mdm.required_level,
        ),
        citations=citations,
        insufficient_evidence=bool(cls.get("insufficient_evidence", False)),
    )
