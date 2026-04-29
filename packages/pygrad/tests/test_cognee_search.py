"""Tests for Cognee search result normalization."""

from types import SimpleNamespace

from pygrad.cognee_search import normalize_cognee_search_result


class TestNormalizeCogneeSearchResult:
    """normalize_cognee_search_result handles all cognee.search return shapes."""

    def test_empty_list(self) -> None:
        assert normalize_cognee_search_result([]) == "No results found."

    def test_list_of_dicts_with_search_result(self) -> None:
        raw = [
            {"search_result": ["first hit"]},
            {"search_result": ["second hit"]},
        ]
        assert normalize_cognee_search_result(raw) == "first hit\nsecond hit"

    def test_dict_missing_search_result_uses_default(self) -> None:
        raw = [{"other": 1}]
        assert normalize_cognee_search_result(raw) == "No results found."

    def test_dict_with_empty_search_result(self) -> None:
        raw = [{"search_result": []}]
        assert normalize_cognee_search_result(raw) == "No results found."

    def test_list_of_non_dicts(self) -> None:
        raw = ["plain", 42]
        assert normalize_cognee_search_result(raw) == "plain\n42"

    def test_object_with_result_attribute(self) -> None:
        raw = SimpleNamespace(result="answer text")
        assert normalize_cognee_search_result(raw) == "answer text"

    def test_object_with_falsy_result_falls_through(self) -> None:
        raw = SimpleNamespace(result="")
        assert normalize_cognee_search_result(raw) == "No results found."

    def test_none_and_other_non_list(self) -> None:
        assert normalize_cognee_search_result(None) == "No results found."
        assert normalize_cognee_search_result(0) == "No results found."
