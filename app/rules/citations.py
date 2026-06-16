"""Source registry.

Every hardcoded rule in this package carries a citation back to the exact
document and location it came from. This is what lets the deterministic
rules engine satisfy the assignment's Rule 2 ("always cite the exact source
and location") without ever calling the LLM.

The `guideline_set` tag is the same tag the ingestion pipeline attaches to
retrieved chunks, so citations from code and citations from retrieval are
interchangeable in the API response.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    guideline_set: str          # machine tag, e.g. "AMA_2021"
    document: str               # human-readable file name
    location: str               # section / page reference within the document

    def as_dict(self) -> dict:
        return {
            "guideline_set": self.guideline_set,
            "source_document": self.document,
            "location": self.location,
        }


# --- AMA 2021 (governs office/outpatient E/M codes 99202-99215) ---------------
AMA_MDM_TABLE = Source(
    "AMA_2021",
    "AMA_Guidelines.pdf",
    "Table 2 - Levels of Medical Decision Making (pp. 11-14)",
)
AMA_TIME = Source(
    "AMA_2021",
    "AMA_Guidelines.pdf",
    "Office/Outpatient code descriptors, total time on date of encounter (pp. 15-17)",
)
AMA_DEFINITIONS = Source(
    "AMA_2021",
    "AMA_Guidelines.pdf",
    "Definitions for the elements of MDM (pp. 4-8)",
)
AMA_SUPERSESSION = Source(
    "AMA_2021",
    "AMA_Guidelines.pdf",
    "E/M Guidelines effective Jan 1 2021 for codes 99202-99215 (p. 1)",
)

# --- 1997 CMS (history/exam/MDM bullet counting; non-99202-99215 settings) ----
CMS_1997_GENERAL = Source(
    "CMS_1997",
    "97_Doc_guidelines.pdf",
    "General Principles of Medical Record Documentation (p. 3)",
)

# --- JAWDA Data Certification Part IX -----------------------------------------
JAWDA_PENALTIES = Source(
    "JAWDA",
    "JAWDA_Data_Certification_for_Healthcare_Providers_2026-Part_IX.pdf",
    "Appendix III - Error Scoring Tables (pp. 16-17)",
)
JAWDA_WEIGHTS = Source(
    "JAWDA",
    "JAWDA_Data_Certification_for_Healthcare_Providers_2026-Part_IX.pdf",
    "Appendix II - Scoring Weights (pp. 14-15)",
)
JAWDA_CLAIMS_REVIEW = Source(
    "JAWDA",
    "JAWDA_Data_Certification_for_Healthcare_Providers_2026-Part_IX.pdf",
    "Section 4.2 Claims Review Process (pp. 8-9)",
)

# --- HAAD Coding Manual V7 ----------------------------------------------------
HAAD_MANUAL = Source(
    "HAAD",
    "HAAD_CodingManual_V7.txt",
    "Coding Manual V7 - Coding Guidelines and Conventions",
)
