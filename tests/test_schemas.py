"""Schema / contract tests."""

from app.schemas import EncounterRequest, clamp_sentences


def test_clamp_sentences_caps_at_four():
    text = "One. Two. Three. Four. Five. Six."
    out = clamp_sentences(text, 4)
    assert out == "One. Two. Three. Four."
    assert out.count(".") == 4


def test_clamp_handles_short_text():
    assert clamp_sentences("Just one sentence.", 4) == "Just one sentence."
    assert clamp_sentences("", 4) == ""


def test_encounter_request_minimal():
    req = EncounterRequest(billed_code="99214")
    assert req.billed_code == "99214"
    assert req.visit_type == "outpatient"
    assert req.documentation.HPI == ""


def test_encounter_request_full():
    req = EncounterRequest(
        visit_type="outpatient",
        chief_complaint="cough",
        diagnoses=["acute bronchitis"],
        procedures=[],
        documentation={"HPI": "x", "exam": "y", "assessment": "z", "time_minutes": 35},
        billed_code="99214",
    )
    assert req.documentation.time_minutes == 35
    assert req.diagnoses == ["acute bronchitis"]
