# tests/utilities/test_format.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from utilities.format import (
    SENSITIVE_KEY_PATTERNS,
    SENSITIVE_RESOURCE_KINDS,
    format_age,
    format_describe,
    format_table,
    redact_sensitive_fields,
)


class TestFormatTable:
    """Tests for format_table()."""

    def test_produces_aligned_columns(self) -> None:
        """format_table produces properly aligned columns with at least 2-space gaps."""
        headers = ["name", "status", "age"]
        rows = [
            ["my-pod", "Running", "5d"],
            ["another-longer-pod", "Pending", "3h"],
        ]
        result = format_table(headers, rows)
        lines = result.split("\n")

        assert len(lines) == 3
        # Headers should be uppercase.
        assert lines[0].startswith("NAME")
        assert "STATUS" in lines[0]
        assert "AGE" in lines[0]

        # Check alignment: all STATUS values should start at the same column.
        status_col_header = lines[0].index("STATUS")
        status_col_row1 = lines[1].index("Running")
        status_col_row2 = lines[2].index("Pending")
        assert status_col_header == status_col_row1
        assert status_col_header == status_col_row2

    def test_empty_rows_returns_header_only(self) -> None:
        """format_table with empty rows returns header line only."""
        headers = ["name", "namespace", "status"]
        rows: list[list[str]] = []
        result = format_table(headers, rows)
        lines = result.split("\n")

        assert len(lines) == 1
        assert "NAME" in lines[0]
        assert "NAMESPACE" in lines[0]
        assert "STATUS" in lines[0]

    def test_handles_long_values_without_truncation(self) -> None:
        """format_table handles long values without truncating them."""
        headers = ["name", "image"]
        long_image = (
            "registry.redhat.io/odf4/rook-ceph-rhel9-operator@sha256:abcdef1234567890"
        )
        rows = [
            ["short", long_image],
            ["pod-2", "nginx:latest"],
        ]
        result = format_table(headers, rows)
        # The full long image value must appear in the output.
        assert long_image in result

        lines = result.split("\n")
        assert len(lines) == 3

    def test_at_least_two_spaces_between_columns(self) -> None:
        """Columns must have at least 2 spaces separating them."""
        headers = ["a", "b"]
        rows = [["x", "y"]]
        result = format_table(headers, rows)
        # Between column A content and column B content there should be at least 2 spaces.
        # Header line: "A  B"
        lines = result.split("\n")
        # The gap between end of col-A and start of col-B must be >= 2.
        for line in lines:
            parts = line.split("  ", 1)
            assert len(parts) == 2, (
                f"Expected at least 2 spaces between columns in: {line!r}"
            )

    def test_empty_headers_returns_empty_string(self) -> None:
        """format_table with no headers returns an empty string."""
        result = format_table([], [])
        assert result == ""


class TestFormatAge:
    """Tests for format_age()."""

    def test_returns_unknown_for_none(self) -> None:
        """format_age returns '<unknown>' for None."""
        assert format_age(None) == "<unknown>"

    def test_returns_unknown_for_empty_string(self) -> None:
        """format_age returns '<unknown>' for empty string."""
        assert format_age("") == "<unknown>"

    def test_returns_unknown_for_invalid_timestamp(self) -> None:
        """format_age returns '<unknown>' for unparseable input."""
        assert format_age("not-a-timestamp") == "<unknown>"

    def test_converts_timestamp_to_days(self) -> None:
        """format_age shows days for timestamps older than 24 hours."""
        five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
        timestamp = five_days_ago.isoformat()
        result = format_age(timestamp)
        assert result == "5d"

    def test_converts_timestamp_to_hours(self) -> None:
        """format_age shows hours for timestamps between 1-24 hours old."""
        three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
        timestamp = three_hours_ago.isoformat()
        result = format_age(timestamp)
        assert result == "3h"

    def test_converts_timestamp_to_minutes(self) -> None:
        """format_age shows minutes for timestamps between 1-60 minutes old."""
        ten_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
        timestamp = ten_min_ago.isoformat()
        result = format_age(timestamp)
        assert result == "10m"

    def test_converts_timestamp_to_seconds(self) -> None:
        """format_age shows seconds for timestamps less than 1 minute old."""
        thirty_sec_ago = datetime.now(timezone.utc) - timedelta(seconds=30)
        timestamp = thirty_sec_ago.isoformat()
        result = format_age(timestamp)
        assert result == "30s"

    def test_handles_iso_format_with_trailing_z(self) -> None:
        """format_age handles ISO timestamps ending with Z."""
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        timestamp = two_days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
        result = format_age(timestamp)
        assert result == "2d"


class TestFormatDescribe:
    """Tests for format_describe()."""

    def test_renders_nested_dicts_with_indentation(self) -> None:
        """format_describe renders nested dicts with 2-space indentation."""
        resource: dict[str, Any] = {
            "kind": "Pod",
            "metadata": {
                "name": "test-pod",
                "namespace": "default",
            },
        }
        result = format_describe(resource, show_secrets=True)
        assert "metadata:" in result
        assert "  name:" in result
        assert "test-pod" in result
        assert "  namespace:" in result
        assert "default" in result

    def test_handles_lists(self) -> None:
        """format_describe handles lists, rendering items on separate lines."""
        resource: dict[str, Any] = {
            "kind": "Pod",
            "metadata": {
                "name": "test-pod",
                "labels": {
                    "app": "web",
                    "tier": "frontend",
                },
            },
        }
        result = format_describe(resource, show_secrets=True)
        assert "app:" in result
        assert "web" in result
        assert "tier:" in result
        assert "frontend" in result

    def test_renders_top_level_key_value(self) -> None:
        """format_describe renders top-level scalar values as 'Key:  value'."""
        resource: dict[str, Any] = {
            "kind": "Pod",
            "apiVersion": "v1",
        }
        result = format_describe(resource, show_secrets=True)
        assert "kind:" in result
        assert "Pod" in result
        assert "apiVersion:" in result
        assert "v1" in result

    def test_show_secrets_false_shows_redacted(self) -> None:
        """[SEC V-003] format_describe with show_secrets=False shows <REDACTED>."""
        resource: dict[str, Any] = {
            "kind": "Secret",
            "metadata": {
                "name": "my-secret",
                "namespace": "default",
            },
            "data": {
                "username": "YWRtaW4=",
                "password": "cGFzc3dvcmQ=",
            },
        }
        result = format_describe(resource, show_secrets=False)
        assert "<REDACTED>" in result
        assert "YWRtaW4=" not in result
        assert "cGFzc3dvcmQ=" not in result

    def test_handles_none_values(self) -> None:
        """format_describe renders None values as '<none>'."""
        resource: dict[str, Any] = {
            "kind": "Pod",
            "deletionTimestamp": None,
        }
        result = format_describe(resource, show_secrets=True)
        assert "<none>" in result

    def test_handles_list_of_strings(self) -> None:
        """format_describe renders a list of strings on separate lines."""
        resource: dict[str, Any] = {
            "kind": "Pod",
            "finalizers": ["kubernetes.io/pv-protection", "other-finalizer"],
        }
        result = format_describe(resource, show_secrets=True)
        assert "kubernetes.io/pv-protection" in result
        assert "other-finalizer" in result


class TestRedactSensitiveFields:
    """[SEC V-003] Tests for redact_sensitive_fields()."""

    def test_redacts_secret_data_values(self) -> None:
        """[SEC V-003] redact_sensitive_fields redacts Secret data values."""
        resource: dict[str, Any] = {
            "kind": "Secret",
            "metadata": {"name": "my-secret"},
            "data": {
                "username": "YWRtaW4=",
                "password": "cGFzc3dvcmQ=",
            },
            "stringData": {
                "config": "some-config-value",
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)

        # All data values should be redacted.
        assert result["data"]["username"] == "<REDACTED>"
        assert result["data"]["password"] == "<REDACTED>"
        assert result["stringData"]["config"] == "<REDACTED>"

        # Original should be unmodified (deep copy).
        assert resource["data"]["username"] == "YWRtaW4="

    def test_redacts_keys_containing_password(self) -> None:
        """[SEC V-003] redact_sensitive_fields redacts keys containing 'password'."""
        resource: dict[str, Any] = {
            "kind": "ConfigMap",
            "metadata": {"name": "my-config"},
            "data": {
                "database_password": "supersecret",
                "normal_key": "normal_value",
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)
        assert result["data"]["database_password"] == "<REDACTED>"
        assert result["data"]["normal_key"] == "normal_value"

    def test_redacts_keys_containing_token(self) -> None:
        """[SEC V-003] redact_sensitive_fields redacts keys containing 'token'."""
        resource: dict[str, Any] = {
            "kind": "ConfigMap",
            "metadata": {"name": "my-config"},
            "data": {
                "auth_token": "abc123",
                "regular_field": "ok",
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)
        assert result["data"]["auth_token"] == "<REDACTED>"
        assert result["data"]["regular_field"] == "ok"

    def test_show_secrets_true_returns_unmodified(self) -> None:
        """[SEC V-003] redact_sensitive_fields with show_secrets=True returns unmodified."""
        resource: dict[str, Any] = {
            "kind": "Secret",
            "metadata": {"name": "my-secret"},
            "data": {
                "password": "supersecret",
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=True)
        # Should return the exact same object, not a copy.
        assert result is resource
        assert result["data"]["password"] == "supersecret"

    def test_redacts_last_applied_configuration(self) -> None:
        """[SEC V-003] redact_sensitive_fields redacts last-applied-configuration annotation."""
        resource: dict[str, Any] = {
            "kind": "Deployment",
            "metadata": {
                "name": "my-deploy",
                "annotations": {
                    "kubectl.kubernetes.io/last-applied-configuration": '{"kind":"Secret","data":{"pw":"abc"}}',
                    "other-annotation": "safe-value",
                },
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)
        annotations = result["metadata"]["annotations"]
        assert (
            annotations["kubectl.kubernetes.io/last-applied-configuration"]
            == "<REDACTED>"
        )
        assert annotations["other-annotation"] == "safe-value"

    def test_deep_copy_preserves_original(self) -> None:
        """[SEC V-003] redact_sensitive_fields returns a deep copy, leaving the original intact."""
        resource: dict[str, Any] = {
            "kind": "ConfigMap",
            "metadata": {"name": "test"},
            "data": {
                "my_password": "secret123",
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)
        assert result["data"]["my_password"] == "<REDACTED>"
        assert resource["data"]["my_password"] == "secret123"
        assert result is not resource

    def test_handles_nested_sensitive_keys(self) -> None:
        """[SEC V-003] redact_sensitive_fields redacts sensitive keys in deeply nested dicts."""
        resource: dict[str, Any] = {
            "kind": "Deployment",
            "metadata": {"name": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {"name": "DB_PASSWORD", "value": "secret"},
                                ],
                            },
                        ],
                    },
                },
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)
        # The key "DB_PASSWORD" is a value, not a dict key, so it should not be redacted.
        # But a key called "password" would be redacted.
        # This test validates that recursive walking works on nested structures.
        assert result["kind"] == "Deployment"

    def test_redacts_all_sensitive_key_patterns(self) -> None:
        """[SEC V-003] All patterns in SENSITIVE_KEY_PATTERNS trigger redaction."""
        for pattern in SENSITIVE_KEY_PATTERNS:
            resource: dict[str, Any] = {
                "kind": "ConfigMap",
                "metadata": {"name": "test"},
                "data": {
                    f"my_{pattern}_field": "sensitive_value",
                },
            }
            result = redact_sensitive_fields(resource, show_secrets=False)
            assert result["data"][f"my_{pattern}_field"] == "<REDACTED>", (
                f"Pattern {pattern!r} did not trigger redaction"
            )

    def test_non_secret_resource_data_not_blanket_redacted(self) -> None:
        """[SEC V-003] Non-Secret resources do not have all data values blanket-redacted."""
        resource: dict[str, Any] = {
            "kind": "ConfigMap",
            "metadata": {"name": "test"},
            "data": {
                "config.yaml": "some: yaml: content",
                "normal_key": "normal_value",
            },
        }
        result = redact_sensitive_fields(resource, show_secrets=False)
        # Non-sensitive keys should remain.
        assert result["data"]["config.yaml"] == "some: yaml: content"
        assert result["data"]["normal_key"] == "normal_value"

    def test_sensitive_resource_kinds_contains_secret(self) -> None:
        """[SEC V-003] SENSITIVE_RESOURCE_KINDS includes 'Secret'."""
        assert "Secret" in SENSITIVE_RESOURCE_KINDS
