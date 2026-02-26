# utilities/format.py
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any


# [SEC V-003] Resource kinds whose data field is redacted by default.
SENSITIVE_RESOURCE_KINDS: set[str] = {"Secret"}

# [SEC V-003] Key patterns that indicate sensitive values.
SENSITIVE_KEY_PATTERNS: set[str] = {
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "ssh_key",
    "certificate",
    "credentials",
}

# Annotation key that may contain inline secrets.
_LAST_APPLIED_CONFIG_KEY = "kubectl.kubernetes.io/last-applied-configuration"


def _key_is_sensitive(key: str) -> bool:
    """Return True if the lowercased key contains any sensitive pattern."""
    lowered = key.lower()
    return any(pattern in lowered for pattern in SENSITIVE_KEY_PATTERNS)


def _redact_dict(obj: dict[str, Any]) -> None:
    """Recursively walk a dict, redacting values for sensitive keys in place."""
    for key in list(obj.keys()):
        value = obj[key]
        if _key_is_sensitive(key):
            obj[key] = "<REDACTED>"
        elif isinstance(value, dict):
            _redact_dict(value)
        elif isinstance(value, list):
            _redact_list(value)


def _redact_list(items: list[Any]) -> None:
    """Recursively walk a list, redacting sensitive keys in any nested dicts."""
    for item in items:
        if isinstance(item, dict):
            _redact_dict(obj=item)
        elif isinstance(item, list):
            _redact_list(item)


def redact_sensitive_fields(
    resource: dict[str, Any], show_secrets: bool
) -> dict[str, Any]:
    """[SEC V-003] Redact sensitive fields from a Kubernetes resource dict.

    If show_secrets is True, returns the resource unmodified (no copy).
    Otherwise returns a deep copy with sensitive values replaced by "<REDACTED>".

    Redaction rules:
    1. If the resource kind is in SENSITIVE_RESOURCE_KINDS (e.g. "Secret"),
       all values in "data" and "stringData" top-level fields are replaced.
    2. For any resource, all nested dict keys whose lowercased name contains
       a string from SENSITIVE_KEY_PATTERNS have their values replaced.
    3. The annotation "kubectl.kubernetes.io/last-applied-configuration" is
       redacted as it may contain inline secrets.
    """
    if show_secrets:
        return resource

    result = copy.deepcopy(resource)

    # Rule 1: Redact Secret data/stringData values.
    kind = result.get("kind", "")
    if kind in SENSITIVE_RESOURCE_KINDS:
        for field_name in ("data", "stringData"):
            field = result.get(field_name)
            if isinstance(field, dict):
                for key in field:
                    field[key] = "<REDACTED>"

    # Rule 3: Redact last-applied-configuration annotation.
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict) and _LAST_APPLIED_CONFIG_KEY in annotations:
            annotations[_LAST_APPLIED_CONFIG_KEY] = "<REDACTED>"

    # Rule 2: Walk all nested dicts for sensitive key patterns.
    _redact_dict(obj=result)

    return result


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Column-aligned tabular output matching ``oc get`` style.

    Auto-sizes columns based on content width. Left-aligns all columns.
    Headers are rendered in ALL CAPS. At least 2 spaces between columns.
    """
    upper_headers = [hdr.upper() for hdr in headers]

    if not upper_headers:
        return ""

    col_count = len(upper_headers)
    col_widths = [len(hdr) for hdr in upper_headers]

    for row in rows:
        for idx in range(min(len(row), col_count)):
            col_widths[idx] = max(col_widths[idx], len(str(row[idx])))

    separator = "  "
    lines: list[str] = []

    # Header line.
    header_parts: list[str] = []
    for idx, hdr in enumerate(upper_headers):
        if idx < col_count - 1:
            header_parts.append(hdr.ljust(col_widths[idx]))
        else:
            header_parts.append(hdr)
    lines.append(separator.join(header_parts))

    # Data rows.
    for row in rows:
        row_parts: list[str] = []
        for idx in range(col_count):
            cell = str(row[idx]) if idx < len(row) else ""
            if idx < col_count - 1:
                row_parts.append(cell.ljust(col_widths[idx]))
            else:
                row_parts.append(cell)
        lines.append(separator.join(row_parts))

    return "\n".join(lines)


def _format_value(value: Any, indent: int, key_width: int) -> str:
    """Format a single value for describe output, handling nested structures."""
    if value is None:
        return "<none>"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _format_nested_dict(obj=value, indent=indent)
    if isinstance(value, list):
        return _format_list(items=value, indent=indent, key_width=key_width)
    return str(value)


def _format_nested_dict(obj: dict[str, Any], indent: int) -> str:
    """Format a nested dict with indentation for describe output."""
    if not obj:
        return ""

    lines: list[str] = []
    prefix = " " * indent

    for key, value in obj.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            nested = _format_nested_dict(obj=value, indent=indent + 2)
            if nested:
                lines.append(nested)
        elif isinstance(value, list):
            formatted_list = _format_list_items(value, indent, key)
            lines.append(formatted_list)
        else:
            display_val = _format_value(value, indent, len(key))
            lines.append(f"{prefix}{key}:\t{display_val}")

    return "\n".join(lines)


def _format_list_items(items: list[Any], indent: int, key: str) -> str:
    """Format a list of items for describe output, with the key as a prefix."""
    prefix = " " * indent
    # Alignment: subsequent lines align with first value character.
    key_prefix = f"{prefix}{key}:"
    align_indent = len(key_prefix) + 1

    if not items:
        return f"{key_prefix}\t<none>"

    lines: list[str] = []
    for idx, item in enumerate(items):
        if isinstance(item, str):
            if idx == 0:
                lines.append(f"{key_prefix}\t{item}")
            else:
                lines.append(f"{' ' * align_indent}{item}")
        elif isinstance(item, dict):
            if idx == 0:
                # First dict item on same line as key (if simple), or next line.
                nested = _format_nested_dict(item, indent + 2)
                lines.append(f"{key_prefix}")
                if nested:
                    lines.append(nested)
            else:
                nested = _format_nested_dict(item, indent + 2)
                if nested:
                    lines.append(nested)
        else:
            display = str(item) if item is not None else "<none>"
            if idx == 0:
                lines.append(f"{key_prefix}\t{display}")
            else:
                lines.append(f"{' ' * align_indent}{display}")

    return "\n".join(lines)


def _format_list(items: list[Any], indent: int, key_width: int) -> str:
    """Format a list for inline rendering (after a key)."""
    if not items:
        return "<none>"

    # For simple string lists, show first on same line, rest aligned.
    all_simple = all(isinstance(item, (str, int, float, bool)) for item in items)
    if all_simple:
        result_lines = [str(items[0])]
        align = " " * (indent + key_width + 2)  # +2 for ":  " after key
        for item in items[1:]:
            result_lines.append(f"{align}{item}")
        return "\n".join(result_lines)

    # Complex items: render each as nested dict.
    return ""


def format_describe(resource: dict[str, Any], show_secrets: bool) -> str:
    """Key-value output matching ``oc describe`` style.

    Calls redact_sensitive_fields() first. Top-level keys are formatted as
    "Key:  value" (with spacing). Nested dicts are indented with 2 spaces.
    Lists render items on separate lines. Multi-line values are indented
    to align with the first value character.
    """
    redacted = redact_sensitive_fields(resource=resource, show_secrets=show_secrets)
    lines: list[str] = []

    for key, value in redacted.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            nested = _format_nested_dict(obj=value, indent=2)
            if nested:
                lines.append(nested)
        elif isinstance(value, list):
            formatted = _format_list_items(value, 0, key)
            lines.append(formatted)
        else:
            display_val = _format_value(value, 0, len(key))
            # Use tab-based alignment for consistent key-value spacing.
            lines.append(f"{key}:\t{display_val}")

    # Post-process: convert tabs to spaces for alignment.
    # Find the longest key (before the tab) and align all values.
    processed: list[str] = []
    max_key_len = 0
    for line in "\n".join(lines).split("\n"):
        if "\t" in line:
            key_part = line.split("\t", 1)[0]
            max_key_len = max(max_key_len, len(key_part))

    # Align with at least 2 spaces after the longest key.
    align_col = max_key_len + 2
    for line in "\n".join(lines).split("\n"):
        if "\t" in line:
            key_part, val_part = line.split("\t", 1)
            padding = align_col - len(key_part)
            if padding < 2:
                padding = 2
            processed.append(f"{key_part}{' ' * padding}{val_part}")
        else:
            processed.append(line)

    return "\n".join(processed)


def format_age(timestamp_str: str | None) -> str:
    """Convert an ISO timestamp string to a relative age string.

    Format: "5d", "3h", "2m", "10s". Uses the largest applicable unit.
    Returns "<unknown>" for None or empty string.
    """
    if not timestamp_str:
        return "<unknown>"

    try:
        # Parse ISO 8601 timestamp. Handle both with and without trailing Z.
        timestamp_clean = timestamp_str.replace("Z", "+00:00")
        parsed_time = datetime.fromisoformat(timestamp_clean)

        # Ensure timezone-aware. If naive, assume UTC.
        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        delta = now - parsed_time

        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "0s"

        days = total_seconds // 86400
        if days > 0:
            return f"{days}d"

        hours = total_seconds // 3600
        if hours > 0:
            return f"{hours}h"

        minutes = total_seconds // 60
        if minutes > 0:
            return f"{minutes}m"

        return f"{total_seconds}s"

    except (ValueError, TypeError):
        return "<unknown>"
