"""Deterministic E/M leveling engine for office/outpatient codes 99202-99215.

This module hardcodes the *fixed lookup tables* from the AMA 2021 guidelines:
the Medical Decision Making (MDM) grid, the total-time thresholds, and the
supersession rule (AMA 2021 governs these codes, not the 1997 guidelines).

It contains NO language model and NO retrieval. Given the documentation
already classified into tiers, it returns a verdict deterministically, so the
"did we apply the right rule" question is always correct and never invented.

The fuzzy step -- reading free-text notes and deciding which tier they fall
into -- happens in the LLM classifier (services/encounter_service.py). This
engine only consumes the resulting tiers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .citations import AMA_MDM_TABLE, AMA_SUPERSESSION, AMA_TIME, CMS_1997_GENERAL

# Ordered MDM levels. The integer is used for "2 of 3 elements" comparisons.
LEVEL_ORDER = {"straightforward": 1, "low": 2, "moderate": 3, "high": 4}
ORDER_LEVEL = {v: k for k, v in LEVEL_ORDER.items()}

# Office/outpatient codes governed by AMA 2021.
NEW_PATIENT_CODES = {"99202", "99203", "99204", "99205"}
ESTABLISHED_PATIENT_CODES = {"99211", "99212", "99213", "99214", "99215"}
OFFICE_OUTPATIENT_CODES = NEW_PATIENT_CODES | ESTABLISHED_PATIENT_CODES

# Required overall MDM level per code (AMA 2021, Table 2). 99211 has no MDM.
REQUIRED_MDM_BY_CODE = {
    "99202": "straightforward",
    "99203": "low",
    "99204": "moderate",
    "99205": "high",
    "99211": None,
    "99212": "straightforward",
    "99213": "low",
    "99214": "moderate",
    "99215": "high",
}

# Total time on the date of the encounter, in minutes (AMA 2021 descriptors).
# (low, high) inclusive. 99211 is not time-based.
TIME_RANGES_BY_CODE = {
    "99202": (15, 29),
    "99203": (30, 44),
    "99204": (45, 59),
    "99205": (60, 74),
    "99212": (10, 19),
    "99213": (20, 29),
    "99214": (30, 39),
    "99215": (40, 54),
}

# Short, paraphrased criteria for each MDM element, used to *ground* the LLM
# classifier prompt. These are summaries of AMA 2021 Table 2 -- not answers.
PROBLEMS_CRITERIA = {
    "straightforward": "1 self-limited or minor problem.",
    "low": "2+ self-limited/minor problems; or 1 stable chronic illness; or 1 acute uncomplicated illness or injury.",
    "moderate": "1+ chronic illness with exacerbation/progression/side effects; or 2+ stable chronic illnesses; or 1 undiagnosed new problem with uncertain prognosis; or 1 acute illness with systemic symptoms; or 1 acute complicated injury.",
    "high": "1+ chronic illness with severe exacerbation/progression; or 1 acute or chronic illness or injury that poses a threat to life or bodily function.",
}
DATA_CRITERIA = {
    "straightforward": "Minimal or no data reviewed.",
    "low": "Limited data: any combination of 2 of [review of external notes, review of a unique test, ordering a unique test]; or assessment requiring an independent historian.",
    "moderate": "Moderate data: meet 1 of 3 categories (combination of 3 data items; OR independent interpretation of a test; OR discussion of management with an external professional).",
    "high": "Extensive data: meet 2 of the 3 categories above.",
}
RISK_CRITERIA = {
    "straightforward": "Minimal risk from additional diagnostic testing or treatment.",
    "low": "Low risk (e.g. over-the-counter drugs, minor surgery with no risk factors).",
    "moderate": "Moderate risk (e.g. prescription drug management; minor surgery with risk factors; elective major surgery without risk factors; social determinants of health).",
    "high": "High risk (e.g. drug therapy requiring intensive monitoring for toxicity; elective major surgery with risk factors; emergency major surgery; decision regarding hospitalization or de-escalation of care).",
}


@dataclass(frozen=True)
class MdmResult:
    achieved_level: str | None
    required_level: str | None
    supported: bool
    verdict: str          # supported | overcoded | undercoded | not_applicable
    explanation: str


def is_office_outpatient(code: str) -> bool:
    return code.strip() in OFFICE_OUTPATIENT_CODES


def governing_guideline(code: str):
    """Supersession rule (Rule 5): AMA 2021 governs 99202-99215; the 1997
    guidelines still apply to other E/M settings."""
    if is_office_outpatient(code.strip()):
        return AMA_SUPERSESSION
    return CMS_1997_GENERAL


def overall_mdm_level(problems: str, data: str, risk: str) -> str:
    """Two of three elements must meet or exceed a level to qualify for it.

    We find the highest level L for which at least two of the three element
    levels are >= L. Straightforward (1) is always met, so a result is always
    returned.
    """
    levels = [LEVEL_ORDER[problems], LEVEL_ORDER[data], LEVEL_ORDER[risk]]
    achieved = 1
    for target in (4, 3, 2, 1):
        if sum(1 for lv in levels if lv >= target) >= 2:
            achieved = target
            break
    return ORDER_LEVEL[achieved]


def required_level_for_code(code: str) -> str | None:
    return REQUIRED_MDM_BY_CODE.get(code.strip())


def assess_mdm(code: str, problems: str, data: str, risk: str) -> MdmResult:
    """Compare the MDM supported by the documentation against the billed code."""
    code = code.strip()
    if not is_office_outpatient(code):
        return MdmResult(
            None, None, False, "not_applicable",
            f"{code} is not an office/outpatient code (99202-99215); the AMA 2021 "
            "MDM grid does not apply to it.",
        )
    required = required_level_for_code(code)
    if required is None:  # 99211
        return MdmResult(
            None, None, True, "not_applicable",
            "99211 does not require a specific MDM level and is not selected by MDM.",
        )
    achieved = overall_mdm_level(problems, data, risk)
    a, r = LEVEL_ORDER[achieved], LEVEL_ORDER[required]
    if a == r:
        verdict, supported = "supported", True
    elif a < r:
        verdict, supported = "overcoded", False
    else:
        verdict, supported = "undercoded", True
    return MdmResult(
        achieved, required, supported, verdict,
        f"Documentation supports {achieved} MDM; {code} requires {required} MDM.",
    )


def code_for_time(minutes: int, established: bool) -> str | None:
    """Return the office/outpatient code whose time range contains `minutes`."""
    codes = ESTABLISHED_PATIENT_CODES if established else NEW_PATIENT_CODES
    for c in sorted(codes):
        rng = TIME_RANGES_BY_CODE.get(c)
        if rng and rng[0] <= minutes <= rng[1]:
            return c
    return None


def time_supports_code(code: str, minutes: int) -> bool:
    """True if `minutes` falls within the billed code's published time range."""
    rng = TIME_RANGES_BY_CODE.get(code.strip())
    return bool(rng and rng[0] <= minutes <= rng[1])


def requirement_summary(code: str) -> dict | None:
    """Deterministic, cited answer to "what does <code> require / qualify for?"
    for office/outpatient E/M codes 99202-99215 (governed by AMA 2021).

    The leveling thresholds are hardcoded straight from the AMA 2021 tables, so
    this answer is identical on every call and can never be invented or omitted
    by a language model. Returns ``{"answer": str, "citations": [dict, ...]}``,
    or ``None`` if this engine does not govern the code (caller falls back to
    retrieval).
    """
    code = code.strip()
    if not is_office_outpatient(code):
        return None

    patient_kind = "new patient" if code in NEW_PATIENT_CODES else "established patient"
    required = REQUIRED_MDM_BY_CODE.get(code)
    citations = [CITATION_MDM]

    if required is None:  # 99211 is not selected by MDM or time.
        answer = (
            f"Under AMA 2021, {code} is an {patient_kind} office/outpatient visit "
            "for a problem that may not require the presence of a physician or "
            "other qualified health professional; it is not selected by Medical "
            "Decision Making or by total time."
        )
        return {"answer": answer, "citations": citations}

    rng = TIME_RANGES_BY_CODE.get(code)
    if rng:
        time_clause = (
            f" or by {rng[0]}-{rng[1]} minutes of total time on the date of the encounter"
        )
        citations.append(CITATION_TIME)
    else:
        time_clause = ""

    answer = (
        f"Under AMA 2021, code {code} ({patient_kind} office/outpatient visit) is "
        f"selected by either {required}-complexity Medical Decision Making - at least "
        f"2 of the 3 MDM elements (problems, data, and risk) reaching the {required} "
        f"level -{time_clause}. History and examination must be medically appropriate "
        "but are not counted toward selecting the level for codes 99202-99215."
    )
    return {"answer": answer, "citations": citations}


def governance_summary(code: str) -> dict | None:
    """Deterministic, cited answer to "which guideline version governs / is in
    effect for code X?".

    Scoped to office/outpatient codes 99202-99215, where Rule 5 applies: the
    AMA 2021 revisions superseded the 1995/1997 guidelines for these codes. This
    is the decisive supersession answer, so the system never has to hedge on the
    one question the rule is testing. Returns ``None`` for other codes, so the
    caller falls back to retrieval rather than over-asserting AMA 2021.
    """
    code = code.strip()
    if not is_office_outpatient(code):
        return None
    answer = (
        f"AMA 2021 is the governing guideline for office/outpatient code {code}: the "
        "2021 E/M revisions, effective January 1 2021, superseded the 1995/1997 "
        "guidelines for codes 99202-99215, which are now selected by Medical Decision "
        "Making or total time. The 1995/1997 documentation guidelines referenced "
        "elsewhere (including in the HAAD manual) pertain to other E/M documentation "
        "contexts, not to selecting the level for 99202-99215."
    )
    return {"answer": answer, "citations": [AMA_SUPERSESSION.as_dict()]}


# Citations exported for the service layer to attach to responses.
CITATION_MDM = AMA_MDM_TABLE.as_dict()
CITATION_TIME = AMA_TIME.as_dict()