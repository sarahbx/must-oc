# tests/utilities/test_labels.py
from __future__ import annotations

import pytest

from utilities.labels import matches_selector, parse_selector, validate_selector


class TestParseSelector:
    """Tests for parse_selector()."""

    def test_parse_single_term(self) -> None:
        result = parse_selector("key=value")
        assert result == [("key", "=", "value")]

    def test_parse_multiple_terms(self) -> None:
        result = parse_selector("k1=v1,k2=v2")
        assert result == [("k1", "=", "v1"), ("k2", "=", "v2")]

    def test_parse_not_equal(self) -> None:
        result = parse_selector("key!=value")
        assert result == [("key", "!=", "value")]

    def test_parse_double_equals(self) -> None:
        """== should be treated as equality, same semantics as =."""
        result = parse_selector("key==value")
        assert result == [("key", "==", "value")]

    def test_empty_selector_returns_empty_list(self) -> None:
        result = parse_selector("")
        assert result == []

    def test_parse_kubernetes_domain_key(self) -> None:
        result = parse_selector("app.kubernetes.io/name=foo")
        assert result == [("app.kubernetes.io/name", "=", "foo")]

    def test_parse_mixed_operators(self) -> None:
        result = parse_selector("app=web,env!=prod,tier==frontend")
        assert result == [
            ("app", "=", "web"),
            ("env", "!=", "prod"),
            ("tier", "==", "frontend"),
        ]


class TestMatchesSelector:
    """Tests for matches_selector()."""

    def test_matching_labels_returns_true(self) -> None:
        labels = {"app": "web", "env": "prod"}
        selector = [("app", "=", "web")]
        assert matches_selector(labels, selector) is True

    def test_non_matching_labels_returns_false(self) -> None:
        labels = {"app": "web", "env": "prod"}
        selector = [("app", "=", "api")]
        assert matches_selector(labels, selector) is False

    def test_empty_labels_with_equality_selector_returns_false(self) -> None:
        labels: dict[str, str] = {}
        selector = [("app", "=", "web")]
        assert matches_selector(labels, selector) is False

    def test_empty_selector_matches_everything(self) -> None:
        labels = {"app": "web", "env": "prod"}
        assert matches_selector(labels, []) is True

    def test_empty_labels_with_empty_selector_matches(self) -> None:
        assert matches_selector({}, []) is True

    def test_not_equal_key_missing_matches(self) -> None:
        """!= matches when the key does not exist."""
        labels: dict[str, str] = {}
        selector = [("app", "!=", "web")]
        assert matches_selector(labels, selector) is True

    def test_not_equal_value_differs_matches(self) -> None:
        """!= matches when the key exists but value differs."""
        labels = {"app": "api"}
        selector = [("app", "!=", "web")]
        assert matches_selector(labels, selector) is True

    def test_not_equal_value_same_does_not_match(self) -> None:
        """!= does not match when key exists and value is the same."""
        labels = {"app": "web"}
        selector = [("app", "!=", "web")]
        assert matches_selector(labels, selector) is False

    def test_double_equals_matches_same_as_single(self) -> None:
        """== should behave identically to = for matching."""
        labels = {"key": "value"}
        assert matches_selector(labels, [("key", "==", "value")]) is True
        assert matches_selector(labels, [("key", "==", "other")]) is False

    def test_all_terms_must_match(self) -> None:
        labels = {"app": "web", "env": "prod"}
        selector = [("app", "=", "web"), ("env", "=", "staging")]
        assert matches_selector(labels, selector) is False

    def test_all_terms_match(self) -> None:
        labels = {"app": "web", "env": "prod"}
        selector = [("app", "=", "web"), ("env", "=", "prod")]
        assert matches_selector(labels, selector) is True


class TestValidateSelector:
    """Tests for validate_selector() -- [SEC V-004]."""

    def test_rejects_command_injection(self) -> None:
        with pytest.raises(ValueError, match="Invalid selector term"):
            validate_selector("$(whoami)")

    def test_rejects_semicolon_injection(self) -> None:
        with pytest.raises(ValueError, match="Invalid selector term"):
            validate_selector(";rm -rf /")

    def test_rejects_pipe_character(self) -> None:
        with pytest.raises(ValueError, match="Invalid selector term"):
            validate_selector("key|value")

    def test_rejects_empty_terms(self) -> None:
        with pytest.raises(ValueError, match="Empty term"):
            validate_selector("key=val,,key2=val2")

    def test_rejects_too_many_terms(self) -> None:
        terms = ",".join(f"k{idx}=v{idx}" for idx in range(21))
        with pytest.raises(ValueError, match="exceeding the maximum of 20"):
            validate_selector(terms)

    def test_accepts_kubernetes_domain_keys(self) -> None:
        """Should not raise for valid Kubernetes domain-prefixed keys."""
        validate_selector("app.kubernetes.io/name=foo")

    def test_accepts_exactly_max_terms(self) -> None:
        """Exactly MAX_SELECTOR_TERMS should be accepted."""
        terms = ",".join(f"k{idx}=v{idx}" for idx in range(20))
        validate_selector(terms)  # Should not raise

    def test_accepts_empty_string(self) -> None:
        """Empty string is valid (matches everything)."""
        validate_selector("")  # Should not raise

    def test_rejects_backtick_injection(self) -> None:
        with pytest.raises(ValueError, match="Invalid selector term"):
            validate_selector("`whoami`=value")

    def test_rejects_ampersand(self) -> None:
        with pytest.raises(ValueError, match="Invalid selector term"):
            validate_selector("key=value&other")

    def test_accepts_underscores_and_dots(self) -> None:
        validate_selector("my_app.v2=stable_release")  # Should not raise

    def test_accepts_empty_value(self) -> None:
        """A selector like 'key=' with empty value is valid."""
        validate_selector("key=")  # Should not raise
