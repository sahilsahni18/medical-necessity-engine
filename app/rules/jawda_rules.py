"""Deterministic JAWDA scoring engine.

Hardcodes the fixed penalty table and domain weights from JAWDA Data
Certification Part IX, Appendices II and III. Used to answer questions like
"what score do we lose if the LAMA form is missing?" without guessing.

Each penalty carries its category, point deduction, a plain description, and a
citation back to the source table.
"""

from __future__ import annotations

from dataclasses import dataclass

from .citations import JAWDA_PENALTIES, JAWDA_WEIGHTS


@dataclass(frozen=True)
class Penalty:
    key: str
    category: str        # Major | Moderate | Minor
    points: int          # deduction
    description: str
    citation: dict


# Appendix III, Table 1 - Error Scoring for all settings (accuracy errors).
_GENERAL = [
    Penalty("patient_signature_mismatch", "Major", 100,
            "Mismatching patient signature or patient details on supporting documents.",
            JAWDA_PENALTIES.as_dict()),
    Penalty("billed_physician_mismatch", "Major", 100,
            "The billed physician differs from the actual service performer.",
            JAWDA_PENALTIES.as_dict()),
    Penalty("incorrect_drg", "Major", 20,
            "Incorrect Diagnosis-Related Group (facility billed a high/low DRG).",
            JAWDA_PENALTIES.as_dict()),
    Penalty("missing_required_form", "Major", 20,
            "Missing a required form (e.g. consent form, or LAMA form signed by patient/relative).",
            JAWDA_PENALTIES.as_dict()),
    Penalty("incorrect_encounter_type", "Moderate", 10,
            "Claim with incorrect encounter start or end type.",
            JAWDA_PENALTIES.as_dict()),
    Penalty("incorrect_quantity", "Moderate", 10,
            "Claim submitted with incorrect quantities (more or less) of any code.",
            JAWDA_PENALTIES.as_dict()),
    Penalty("missing_physician_authentication", "Moderate", 10,
            "Physician authentication missing on the relevant documentation.",
            JAWDA_PENALTIES.as_dict()),
    Penalty("missing_nonsurgical_procedure_code", "Moderate", 10,
            "Documented non-surgical procedure/service (IM, IV, CTG, ECG, anaesthesia, etc.) not coded.",
            JAWDA_PENALTIES.as_dict()),
    Penalty("incorrect_date", "Minor", 5,
            "Claim submitted with an incorrect date (miscellaneous billing error).",
            JAWDA_PENALTIES.as_dict()),
    Penalty("missing_demographic_details", "Minor", 5,
            "Missing demographic details (e.g. Medical Tourism claim missing payment/patient details).",
            JAWDA_PENALTIES.as_dict()),
]

# Appendix III, Table 2 - Dental accuracy errors.
_DENTAL = [
    Penalty("dental_incorrect_consumable", "Major", 20,
            "Incorrect consumable details (dates, ordering vs using physician signatures, etc.).",
            JAWDA_PENALTIES.as_dict()),
    Penalty("dental_invalid_physician_license", "Moderate", 10,
            "Invalid physician license (expired, or no privilege to perform the service).",
            JAWDA_PENALTIES.as_dict()),
    Penalty("dental_unbundled_procedure", "Major", 10,
            "Billed unbundled procedure (endodontic procedure billed with inclusive CPTs).",
            JAWDA_PENALTIES.as_dict()),
    Penalty("dental_billed_em_in_dental", "Major", 10,
            "Incorrectly billed an E/M code in a dental claim.",
            JAWDA_PENALTIES.as_dict()),
]

PENALTIES: dict[str, Penalty] = {p.key: p for p in (_GENERAL + _DENTAL)}

# Appendix II - Final score domain weights.
SCORING_WEIGHTS = {
    "with_kpi": {"claims_review": 40, "clinical_coding_process_review": 10, "kpi_data_validation": 50},
    "without_kpi": {"claims_review": 80, "clinical_coding_process_review": 20},
}


def penalty_for(key: str) -> Penalty | None:
    return PENALTIES.get(key)


def all_penalties() -> list[Penalty]:
    return list(PENALTIES.values())


def weights(has_kpi: bool) -> dict:
    return SCORING_WEIGHTS["with_kpi" if has_kpi else "without_kpi"]


# Trigger phrases mapping a free-text question to a specific penalty. Ordered by
# specificity; the first match wins. These let the /ask path answer JAWDA
# scoring questions ("what score if the LAMA form is missing?") from this fixed
# table instead of relying on retrieval, the same way E/M codes are handled.
_PENALTY_TRIGGERS: list[tuple[str, list[str]]] = [
    ("missing_required_form", ["lama", "consent form", "required form", "missing form"]),
    ("billed_physician_mismatch", ["billed physician", "physician differs", "actual performer",
                                   "service performer", "different physician", "wrong physician"]),
    ("patient_signature_mismatch", ["signature mismatch", "mismatching signature",
                                    "patient signature", "signature on supporting"]),
    ("incorrect_drg", ["drg", "diagnosis-related group", "diagnosis related group"]),
    ("incorrect_encounter_type", ["encounter type", "encounter start", "encounter end"]),
    ("incorrect_quantity", ["quantity", "quantities"]),
    ("missing_physician_authentication", ["physician authentication", "authentication missing",
                                          "missing authentication"]),
    ("missing_nonsurgical_procedure_code", ["non-surgical procedure", "nonsurgical procedure",
                                            "procedure not coded", "service not coded"]),
    ("incorrect_date", ["incorrect date", "wrong date"]),
    ("missing_demographic_details", ["demographic", "medical tourism"]),
    ("dental_incorrect_consumable", ["consumable"]),
    ("dental_invalid_physician_license", ["invalid license", "expired license", "physician license"]),
    ("dental_unbundled_procedure", ["unbundled", "endodontic"]),
    ("dental_billed_em_in_dental", ["e/m code in a dental", "em code in dental", "e/m in dental"]),
]


def match_penalty(question: str) -> Penalty | None:
    """Return the single JAWDA penalty a question is about, or None if no
    specific penalty is clearly referenced (so the caller falls back to RAG)."""
    q = question.lower()
    for key, triggers in _PENALTY_TRIGGERS:
        if any(t in q for t in triggers):
            return PENALTIES[key]
    return None


def _clean(description: str) -> str:
    """Strip punctuation that would create false sentence boundaries downstream."""
    return (
        description.replace("e.g.", "for example")
        .replace("etc.", "and so on")
        .rstrip(".")
    )


def penalty_answer(penalty: Penalty) -> dict:
    """Deterministic, cited answer for a single JAWDA penalty (<= 2 sentences)."""
    answer = (
        f"Under JAWDA Data Certification Part IX (Appendix III error scoring), this is a "
        f"{penalty.category} error carrying a {penalty.points}-point deduction. "
        f"It covers: {_clean(penalty.description)}."
    )
    return {"answer": answer, "citations": [penalty.citation]}