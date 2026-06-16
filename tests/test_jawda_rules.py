"""Deterministic JAWDA scoring tests."""

from app.rules import jawda_rules as j


def test_missing_form_is_major_20():
    p = j.penalty_for("missing_required_form")
    assert p is not None
    assert p.category == "Major" and p.points == 20
    assert "JAWDA" in p.citation["guideline_set"]


def test_signature_mismatch_is_major_100():
    p = j.penalty_for("patient_signature_mismatch")
    assert p.category == "Major" and p.points == 100


def test_incorrect_date_is_minor_5():
    p = j.penalty_for("incorrect_date")
    assert p.category == "Minor" and p.points == 5


def test_weights():
    assert j.weights(True)["claims_review"] == 40
    assert j.weights(True)["kpi_data_validation"] == 50
    assert j.weights(False)["claims_review"] == 80
    assert "kpi_data_validation" not in j.weights(False)


def test_unknown_penalty_returns_none():
    assert j.penalty_for("does_not_exist") is None
