"""Supersession routing tests: a 99202-99215 question must exclude the 1997 set,
while general questions keep all guideline sets in scope."""

from app.retrieval import determine_excluded_sets


def test_outpatient_code_excludes_1997():
    assert determine_excluded_sets("Does this visit qualify for a 99214?") == ["CMS_1997"]
    assert determine_excluded_sets("office visit 99213 leveling") == ["CMS_1997"]


def test_general_question_excludes_nothing():
    assert determine_excluded_sets("What documentation proves medical necessity?") == []
    assert determine_excluded_sets("Is hypertension a stable chronic illness?") == []


def test_non_outpatient_code_not_routed_to_ama():
    # An inpatient code mention should not force the AMA-only filter.
    assert determine_excluded_sets("How do I count exam bullets for inpatient care?") == []
