# tests/utilities/test_yaml_parser.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from utilities.yaml_parser import (
    MAX_YAML_SIZE,
    check_file_size,
    extract_metadata,
    load_resource,
    load_resource_list,
)


STANDARD_POD_YAML = """\
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
  labels:
    app: myapp
    tier: frontend
  creationTimestamp: "2026-01-15T10:30:00Z"
spec:
  containers:
    - name: web
      image: nginx:latest
status:
  phase: Running
"""

POD_LIST_YAML = """\
apiVersion: v1
kind: PodList
metadata:
  resourceVersion: "12345"
items:
  - apiVersion: v1
    kind: Pod
    metadata:
      name: pod-a
      namespace: test-ns
  - apiVersion: v1
    kind: Pod
    metadata:
      name: pod-b
      namespace: test-ns
"""

INVALID_YAML = """\
apiVersion: v1
kind: Pod
metadata:
  name: broken
  labels: [this is not valid: {yaml content
"""


class TestLoadResource:
    """Tests for load_resource function."""

    def test_parses_standard_pod_yaml(self, tmp_path: Path) -> None:
        """load_resource parses a standard pod YAML."""
        yaml_file = tmp_path / "pod.yaml"
        yaml_file.write_text(STANDARD_POD_YAML, encoding="utf-8")
        result = load_resource(yaml_file)
        assert result["apiVersion"] == "v1"
        assert result["kind"] == "Pod"
        assert result["metadata"]["name"] == "test-pod"
        assert result["metadata"]["namespace"] == "default"
        assert result["metadata"]["labels"]["app"] == "myapp"
        assert result["status"]["phase"] == "Running"

    def test_handles_yaml_starting_with_document_separator(
        self, tmp_path: Path
    ) -> None:
        """load_resource handles YAML starting with ---."""
        yaml_content = "---\n" + STANDARD_POD_YAML
        yaml_file = tmp_path / "pod-with-separator.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        result = load_resource(yaml_file)
        assert result["kind"] == "Pod"
        assert result["metadata"]["name"] == "test-pod"

    def test_invalid_yaml_raises_exception(self, tmp_path: Path) -> None:
        """load_resource with invalid YAML raises an exception."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text(INVALID_YAML, encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            load_resource(yaml_file)

    def test_rejects_file_exceeding_max_yaml_size(self, tmp_path: Path) -> None:
        """[SEC V-001] load_resource rejects file exceeding MAX_YAML_SIZE."""
        yaml_file = tmp_path / "large.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")
        oversized = MAX_YAML_SIZE + 1
        fake_stat_result = os.stat_result((0o100644, 0, 0, 0, 0, 0, oversized, 0, 0, 0))
        with patch.object(Path, "stat", return_value=fake_stat_result):
            with pytest.raises(ValueError, match="exceeding the maximum allowed size"):
                load_resource(yaml_file)


class TestLoadResourceList:
    """Tests for load_resource_list function."""

    def test_extracts_items_from_pod_list(self, tmp_path: Path) -> None:
        """load_resource_list extracts items from a PodList."""
        yaml_file = tmp_path / "podlist.yaml"
        yaml_file.write_text(POD_LIST_YAML, encoding="utf-8")
        result = load_resource_list(yaml_file)
        assert len(result) == 2
        assert result[0]["metadata"]["name"] == "pod-a"
        assert result[1]["metadata"]["name"] == "pod-b"

    def test_single_resource_returns_list_with_resource(self, tmp_path: Path) -> None:
        """load_resource_list with single resource (non-list) returns [resource]."""
        yaml_file = tmp_path / "single-pod.yaml"
        yaml_file.write_text(STANDARD_POD_YAML, encoding="utf-8")
        result = load_resource_list(yaml_file)
        assert len(result) == 1
        assert result[0]["kind"] == "Pod"
        assert result[0]["metadata"]["name"] == "test-pod"


class TestExtractMetadata:
    """Tests for extract_metadata function."""

    def test_extracts_all_fields(self) -> None:
        """extract_metadata returns all expected fields from a resource."""
        resource: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "test-pod",
                "namespace": "default",
                "labels": {"app": "myapp"},
                "creationTimestamp": "2026-01-15T10:30:00Z",
            },
        }
        result = extract_metadata(resource)
        assert result["name"] == "test-pod"
        assert result["namespace"] == "default"
        assert result["labels"] == {"app": "myapp"}
        assert result["creationTimestamp"] == "2026-01-15T10:30:00Z"
        assert result["kind"] == "Pod"
        assert result["apiVersion"] == "v1"

    def test_handles_missing_labels_gracefully(self) -> None:
        """extract_metadata handles missing labels gracefully."""
        resource: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "no-labels-pod",
                "namespace": "default",
            },
        }
        result = extract_metadata(resource)
        assert result["name"] == "no-labels-pod"
        assert result["labels"] == {}

    def test_handles_missing_metadata(self) -> None:
        """extract_metadata handles a resource with no metadata at all."""
        resource: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
        }
        result = extract_metadata(resource)
        assert result["name"] == ""
        assert result["namespace"] == ""
        assert result["labels"] == {}
        assert result["creationTimestamp"] == ""
        assert result["kind"] == "ConfigMap"
        assert result["apiVersion"] == "v1"


class TestSecurityV006SafeLoad:
    """[SEC V-006] Tests ensuring yaml.safe_load is used exclusively."""

    def test_safe_load_prevents_object_deserialization(self, tmp_path: Path) -> None:
        """[SEC V-006] yaml.safe_load prevents Python object deserialization."""
        malicious_yaml = "exploit: !!python/object/apply:os.system ['echo pwned']\n"
        yaml_file = tmp_path / "malicious.yaml"
        yaml_file.write_text(malicious_yaml, encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            load_resource(yaml_file)

    def test_no_unsafe_yaml_load_in_source(self) -> None:
        """[SEC V-006] Grep all source files: yaml.load( without safe_ MUST NOT exist."""
        project_root = Path(__file__).resolve().parent.parent.parent
        source_dirs = [project_root / "utilities", project_root / "must_oc"]
        violations: list[str] = []
        for source_dir in source_dirs:
            if not source_dir.exists():
                continue
            for python_file in source_dir.rglob("*.py"):
                content = python_file.read_text(encoding="utf-8")
                for line_num, line in enumerate(content.splitlines(), start=1):
                    # Check for yaml.load( but exclude yaml.safe_load(
                    if "yaml.load(" in line and "yaml.safe_load(" not in line:
                        violations.append(f"{python_file}:{line_num}: {line.strip()}")
        assert violations == [], (
            "[SEC V-006] Found unsafe yaml.load() calls:\n" + "\n".join(violations)
        )


class TestSecurityV001FileSize:
    """[SEC V-001] Tests for file size checking."""

    def test_check_file_size_raises_on_101mb(self, tmp_path: Path) -> None:
        """[SEC V-001] check_file_size raises on 101MB file."""
        yaml_file = tmp_path / "huge.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")
        size_101mb = 101 * 1024 * 1024
        fake_stat_result = os.stat_result(
            (0o100644, 0, 0, 0, 0, 0, size_101mb, 0, 0, 0)
        )
        with patch.object(Path, "stat", return_value=fake_stat_result):
            with pytest.raises(ValueError, match="exceeding the maximum allowed size"):
                check_file_size(yaml_file)

    def test_check_file_size_passes_on_99mb(self, tmp_path: Path) -> None:
        """[SEC V-001] check_file_size passes on 99MB file."""
        yaml_file = tmp_path / "ok.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")
        size_99mb = 99 * 1024 * 1024
        fake_stat_result = os.stat_result((0o100644, 0, 0, 0, 0, 0, size_99mb, 0, 0, 0))
        with patch.object(Path, "stat", return_value=fake_stat_result):
            # Should not raise
            check_file_size(yaml_file)

    def test_check_file_size_passes_on_exactly_100mb(self, tmp_path: Path) -> None:
        """[SEC V-001] check_file_size passes on exactly 100MB (boundary)."""
        yaml_file = tmp_path / "boundary.yaml"
        yaml_file.write_text("key: value", encoding="utf-8")
        size_100mb = 100 * 1024 * 1024
        fake_stat_result = os.stat_result(
            (0o100644, 0, 0, 0, 0, 0, size_100mb, 0, 0, 0)
        )
        with patch.object(Path, "stat", return_value=fake_stat_result):
            # Exactly 100MB should pass (limit is > not >=)
            check_file_size(yaml_file)
