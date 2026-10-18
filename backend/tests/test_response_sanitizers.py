"""Tests for the LLM-output sanitizers used when assembling SearchResponse.

The schema validators for these fields are strict, and their input is JSON that
a local model produced. One malformed item used to raise at the final assembly
step and discard a search that had already run for minutes. Each sanitizer must
drop the bad item and keep the rest.
"""

import pytest

from app.schemas import SearchResponse
from app.services.pipeline.utils import (
    sanitize_breach_list,
    sanitize_email_list,
    sanitize_network_connections,
    sanitize_phone_list,
    sanitize_str_list,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param(["A", "B"], ["A", "B"], id="already_clean"),
        pytest.param([{"name": "Other Guy"}], ["Other Guy"], id="dict_gets_flattened"),
        pytest.param([None, "", "  "], [], id="empty_entries_dropped"),
        pytest.param([42, True], ["42", "True"], id="scalars_coerced"),
        pytest.param("not-a-list", [], id="non_list_input"),
        pytest.param(None, [], id="none_input"),
    ],
)
def test_sanitize_str_list(raw, expected):
    assert sanitize_str_list(raw) == expected, f"Expected {expected} from {raw!r}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param(["a@b.com", "nope", 42, None], ["a@b.com"], id="only_addresses_kept"),
        pytest.param([" a@b.com "], ["a@b.com"], id="whitespace_trimmed"),
        pytest.param([], [], id="empty"),
        pytest.param(None, [], id="none_input"),
    ],
)
def test_sanitize_email_list(raw, expected):
    assert sanitize_email_list(raw) == expected, f"Expected {expected} from {raw!r}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param(["+905551112233", "12", None], ["+905551112233"], id="too_short_dropped"),
        pytest.param([123456], [], id="non_string_dropped"),
        pytest.param(None, [], id="none_input"),
    ],
)
def test_sanitize_phone_list(raw, expected):
    assert sanitize_phone_list(raw) == expected, f"Expected {expected} from {raw!r}"


def test_sanitize_network_connections_drops_null_values():
    """LLM JSON commonly emits null values, which dict[str, str] rejects."""
    result = sanitize_network_connections([{"name": "A", "role": None, "relation": "Colleague"}])

    assert result == [{"name": "A", "relation": "Colleague"}]


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param([{"role": "x"}], [], id="missing_name"),
        pytest.param([{"name": ""}], [], id="blank_name"),
        pytest.param(["plain string"], [], id="non_dict_entry"),
        pytest.param([{"name": "A", "count": 3}], [{"name": "A", "count": "3"}], id="values_coerced_to_str"),
        pytest.param(None, [], id="none_input"),
    ],
)
def test_sanitize_network_connections(raw, expected):
    assert sanitize_network_connections(raw) == expected, f"Expected {expected} from {raw!r}"


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param([{"Name": "LinkedIn"}], [{"Name": "LinkedIn"}], id="breach_kept"),
        pytest.param([{"Source": "pastebin.com"}], [{"Source": "pastebin.com"}], id="paste_kept"),
        pytest.param(["junk", None], [], id="non_dicts_dropped"),
        pytest.param([{}, {"unrelated": 1}], [], id="unidentifiable_dropped"),
        pytest.param(None, [], id="none_input"),
    ],
)
def test_sanitize_breach_list(raw, expected):
    assert sanitize_breach_list(raw) == expected, f"Expected {expected} from {raw!r}"


def test_sanitized_output_satisfies_search_response():
    """The contract that matters: sanitizer output must always pass validation."""
    garbage_from_llm = {
        "similar_profiles": [{"name": "Other Guy"}, None, "Plain Name", 42],
        "network_connections": [{"name": "A", "role": None}, {"role": "orphan"}, "str", {"name": ""}],
        "email_addresses": ["a@b.com", "nope", 42, None],
        "phone_numbers": ["+905551112233", "12", None],
        "data_breaches": [{"Name": "LinkedIn"}, "junk", None, {}],
    }

    response = SearchResponse(
        name="Target",
        ai_response="report",
        similar_profiles=sanitize_str_list(garbage_from_llm["similar_profiles"]),
        network_connections=sanitize_network_connections(garbage_from_llm["network_connections"]),
        email_addresses=sanitize_email_list(garbage_from_llm["email_addresses"]),
        phone_numbers=sanitize_phone_list(garbage_from_llm["phone_numbers"]),
        data_breaches=sanitize_breach_list(garbage_from_llm["data_breaches"]),
    )

    assert response.similar_profiles == ["Other Guy", "Plain Name", "42"]
    assert response.network_connections == [{"name": "A"}]
    assert response.email_addresses == ["a@b.com"]
    assert response.phone_numbers == ["+905551112233"]
    assert response.data_breaches == [{"Name": "LinkedIn"}]
