"""Deterministic E/M engine tests. No DB or Gemini needed."""

from app.rules import em_rules as em


def test_overall_mdm_two_of_three():
    assert em.overall_mdm_level("straightforward", "straightforward", "straightforward") == "straightforward"
    assert em.overall_mdm_level("low", "low", "straightforward") == "low"
    assert em.overall_mdm_level("moderate", "moderate", "straightforward") == "moderate"
    assert em.overall_mdm_level("high", "high", "low") == "high"
    # only one element high -> does not reach high (needs 2 of 3)
    assert em.overall_mdm_level("high", "low", "low") == "low"


def test_assess_mdm_supported_overcoded_undercoded():
    supported = em.assess_mdm("99214", "moderate", "low", "moderate")
    assert supported.supported and supported.verdict == "supported"

    over = em.assess_mdm("99214", "low", "low", "low")
    assert not over.supported and over.verdict == "overcoded"

    under = em.assess_mdm("99213", "high", "high", "high")
    assert under.supported and under.verdict == "undercoded"


def test_99211_not_applicable():
    r = em.assess_mdm("99211", "low", "low", "low")
    assert r.verdict == "not_applicable" and r.supported


def test_required_levels():
    assert em.required_level_for_code("99202") == "straightforward"
    assert em.required_level_for_code("99203") == "low"
    assert em.required_level_for_code("99204") == "moderate"
    assert em.required_level_for_code("99205") == "high"


def test_supersession_governing_guideline():
    # AMA 2021 governs office/outpatient codes...
    assert em.governing_guideline("99214").guideline_set == "AMA_2021"
    assert em.is_office_outpatient("99214")
    # ...and a non-office code falls back to 1997.
    assert em.governing_guideline("99223").guideline_set == "CMS_1997"
    assert not em.is_office_outpatient("99223")


def test_time_rules():
    assert em.time_supports_code("99214", 35)
    assert not em.time_supports_code("99214", 45)
    assert em.code_for_time(35, established=True) == "99214"
    assert em.code_for_time(50, established=False) == "99204"
    assert em.code_for_time(50, established=True) == "99215"
