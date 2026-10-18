"""Regression tests for the SearchResponse schema contract.

These lock the boundary that used to fail the whole search at its final step:
the breach validator demanded a key that no producer in the pipeline emits, so
any target with a breach hit or a paste exposure returned HTTP 500.

The shapes here are built by calling the real producers rather than hand-writing
dicts — a hand-written fixture would keep passing after a producer changed.
"""

import pytest
from pydantic import ValidationError

from app.schemas import ProfileCreate, SearchResponse
from app.services.breach_service import _normalize_breach

XON_RAW_BREACH = {
    "breach": "LinkedIn",
    "domain": "linkedin.com",
    "xposed_records": 165000000,
    "xposed_data": "Email;Password",
    "xposed_date": 2016,
    "verified": True,
    "password_risk": "easytocrack",
    "details": "LinkedIn breach",
    "logo": "https://logo",
}

# Mirrors the dict built in DarkWebService._search_paste_sites.
PASTE_EXPOSURE = {
    "_type": "paste",
    "Source": "pastebin.com",
    "Id": "https://pastebin.com/abc123",
    "Title": "Paste on pastebin.com",
    "Date": "",
    "EmailCount": 0,
}


def test_search_response_accepts_normalized_breach_shape():
    breach = _normalize_breach(XON_RAW_BREACH, "target@example.com")

    response = SearchResponse(name="Target", ai_response="report", data_breaches=[breach])

    assert response.data_breaches == [breach], "normalized XON breach must survive validation unchanged"


def test_search_response_accepts_paste_exposure_shape():
    response = SearchResponse(name="Target", ai_response="report", data_breaches=[PASTE_EXPOSURE])

    assert response.data_breaches == [PASTE_EXPOSURE], "paste exposures must survive validation unchanged"


def test_search_response_accepts_breaches_and_pastes_together():
    breach = _normalize_breach(XON_RAW_BREACH, "target@example.com")

    response = SearchResponse(name="Target", ai_response="report", data_breaches=[breach, PASTE_EXPOSURE])

    assert len(response.data_breaches) == 2, "both producers feed the same list in post-analysis"


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(["not-a-dict"], id="string_entry"),
        pytest.param([None], id="none_entry"),
        pytest.param([{}], id="empty_dict"),
        pytest.param([{"unrelated": "value"}], id="dict_without_identifier"),
    ],
)
def test_search_response_rejects_unidentifiable_breach_entry(bad_value):
    with pytest.raises(ValidationError):
        SearchResponse(name="Target", ai_response="report", data_breaches=bad_value)


def test_profile_create_accepts_same_breach_shape():
    """The validator lives on the shared mixin, so ProfileCreate must agree."""
    breach = _normalize_breach(XON_RAW_BREACH, "target@example.com")

    profile = ProfileCreate(name="Target", data_breaches=[breach])

    assert profile.data_breaches == [breach]


def test_search_response_validates_on_assignment():
    """Post-analysis enriches the response by assignment; that must be checked here.

    Without validate_assignment the bad value only raises later, inside FastAPI's
    response_model serialization — outside the route's try/except.
    """
    response = SearchResponse(name="Target", ai_response="report")

    with pytest.raises(ValidationError):
        # manipulation_resistance_score is constrained to 1..100
        response.psychological_analysis = {
            "psychological_profile": "x",
            "manipulation_resistance_score": 500,
            "confidence_level": 0.5,
        }


def test_search_response_assignment_accepts_valid_section():
    response = SearchResponse(name="Target", ai_response="report")

    response.subject_confidence = 0.8

    assert response.subject_confidence == 0.8
