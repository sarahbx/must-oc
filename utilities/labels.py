# utilities/labels.py
from __future__ import annotations

import re


# [SEC V-004] Maximum number of terms in a label selector.
MAX_SELECTOR_TERMS = 20

# [SEC V-004] Strict regex for validating individual selector terms.
# Only allows alphanumeric characters, dots, hyphens, underscores,
# and forward slashes (for Kubernetes label key domains like app.kubernetes.io/name).
SELECTOR_TERM_PATTERN = re.compile(r"^[a-zA-Z0-9_./-]+(=|==|!=)[a-zA-Z0-9_./-]*$")


def validate_selector(selector_str: str) -> None:
    """[SEC V-004] Validate a label selector string.

    Splits on commas, checks each term matches SELECTOR_TERM_PATTERN,
    and enforces MAX_SELECTOR_TERMS. Raises ValueError with a clear
    message on invalid input.
    """
    if not selector_str:
        return

    terms = selector_str.split(",")

    if len(terms) > MAX_SELECTOR_TERMS:
        raise ValueError(
            f"Label selector has {len(terms)} terms, exceeding the maximum of {MAX_SELECTOR_TERMS}"
        )

    for idx, term in enumerate(terms):
        if not term:
            raise ValueError(
                f"Empty term at position {idx} in selector: {selector_str!r}"
            )
        if not SELECTOR_TERM_PATTERN.match(term):
            raise ValueError(f"Invalid selector term at position {idx}: {term!r}")


def parse_selector(selector_str: str) -> list[tuple[str, str, str]]:
    """Parse a label selector string into a list of (key, operator, value) tuples.

    Calls validate_selector() first per [SEC V-004]. Supports =, ==, and != operators.
    An empty selector string returns an empty list (matches everything).
    """
    if not selector_str:
        return []

    validate_selector(selector_str=selector_str)

    result: list[tuple[str, str, str]] = []
    terms = selector_str.split(",")

    for term in terms:
        if "!=" in term:
            key, value = term.split("!=", 1)
            result.append((key, "!=", value))
        elif "==" in term:
            key, value = term.split("==", 1)
            result.append((key, "==", value))
        elif "=" in term:
            key, value = term.split("=", 1)
            result.append((key, "=", value))

    return result


def matches_selector(
    labels: dict[str, str], selector: list[tuple[str, str, str]]
) -> bool:
    """Return True if ALL selector terms match the given labels.

    For = and ==, the label key must exist and its value must equal the selector value.
    For !=, either the key does not exist OR its value differs from the selector value.
    An empty selector list matches everything (returns True).
    """
    for key, operator, value in selector:
        if operator in ("=", "=="):
            if key not in labels or labels[key] != value:
                return False
        elif operator == "!=":
            if key in labels and labels[key] == value:
                return False

    return True
