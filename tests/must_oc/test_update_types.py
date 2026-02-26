# tests/must_oc/test_update_types.py
from __future__ import annotations

import stat
from pathlib import Path

import pytest

from must_oc.oc.update_types import (
    merge_cluster_scoped,
    merge_resource_map,
    scan_cluster_scoped,
    scan_resource_types,
    write_config_safe,
)
from tests.constants import IMAGE_HASH


class TestScanResourceTypes:
    """Tests for scan_resource_types filesystem scanning."""

    def test_discovers_namespaced_types(self, fake_must_gather: Path) -> None:
        """scan_resource_types finds resource types under namespaces/<NS>/<api_group>/<type>/."""
        roots = [fake_must_gather / IMAGE_HASH]
        result = scan_resource_types(roots)

        assert "pods" in result
        assert result["pods"] == "core"
        assert "deployments" in result
        assert result["deployments"] == "apps"

    def test_discovers_pattern_b_types(self, fake_must_gather: Path) -> None:
        """scan_resource_types finds types under namespaces/all/namespaces/<NS>/<api_group>/<type>/."""
        roots = [fake_must_gather / IMAGE_HASH]
        result = scan_resource_types(roots)

        # Pattern B pods from namespaces/all/namespaces/test-ns/core/pods/
        assert "pods" in result

    def test_empty_root_returns_empty(self, tmp_path: Path) -> None:
        """scan_resource_types returns empty dict when root has no namespaces/ dir."""
        result = scan_resource_types([tmp_path])
        assert result == {}

    def test_multiple_roots_merged(
        self, fake_must_gather_multi: tuple[Path, Path]
    ) -> None:
        """scan_resource_types merges types from multiple roots."""
        ocp_root, odf_root = fake_must_gather_multi
        roots = [ocp_root / IMAGE_HASH, odf_root.parent / odf_root.name]
        result = scan_resource_types(roots)
        assert "pods" in result


class TestScanClusterScoped:
    """Tests for scan_cluster_scoped filesystem scanning."""

    def test_discovers_cluster_scoped_types(self, fake_must_gather: Path) -> None:
        """scan_cluster_scoped finds types under cluster-scoped-resources/."""
        roots = [fake_must_gather / IMAGE_HASH]
        result = scan_cluster_scoped(roots)

        assert "nodes" in result

    def test_empty_root_returns_empty(self, tmp_path: Path) -> None:
        """scan_cluster_scoped returns empty set with no cluster-scoped-resources/ dir."""
        result = scan_cluster_scoped([tmp_path])
        assert result == set()


class TestMergeResourceMap:
    """Tests for merge_resource_map additive merging."""

    def test_adds_new_types(self) -> None:
        """merge_resource_map adds discovered types not in existing map."""
        existing: dict = {}
        discovered = {"pods": "core", "deployments": "apps"}

        updated, count = merge_resource_map(existing, discovered)

        assert count == 2
        assert "pods" in updated
        assert updated["pods"]["api_group"] == "core"
        assert updated["pods"]["aliases"] == []
        assert "deployments" in updated

    def test_preserves_existing_entries(self) -> None:
        """merge_resource_map does not overwrite existing entries."""
        existing = {
            "pods": {"api_group": "core", "aliases": ["po", "pod"]},
        }
        discovered = {"pods": "core", "services": "core"}

        updated, count = merge_resource_map(existing, discovered)

        assert count == 1
        assert updated["pods"]["aliases"] == ["po", "pod"]
        assert "services" in updated

    def test_preserves_aliases(self) -> None:
        """merge_resource_map preserves manually-added aliases in existing entries."""
        existing = {
            "pods": {"api_group": "core", "aliases": ["po", "pod", "custom-alias"]},
        }
        discovered = {"pods": "core"}

        updated, count = merge_resource_map(existing, discovered)

        assert count == 0
        assert "custom-alias" in updated["pods"]["aliases"]

    def test_empty_existing_map(self) -> None:
        """merge_resource_map handles empty existing map."""
        updated, count = merge_resource_map({}, {"pods": "core"})
        assert count == 1
        assert "pods" in updated

    def test_api_group_mismatch_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        """merge_resource_map warns on stderr when api_group differs."""
        existing = {"pods": {"api_group": "core", "aliases": []}}
        discovered = {"pods": "different-group"}

        updated, count = merge_resource_map(existing, discovered)

        assert count == 0
        captured = capsys.readouterr()
        assert "mismatch" in captured.err.lower()
        assert updated["pods"]["api_group"] == "core"


class TestMergeClusterScoped:
    """Tests for merge_cluster_scoped additive merging."""

    def test_adds_new_types(self) -> None:
        """merge_cluster_scoped adds discovered types not in existing list."""
        existing: list[str] = ["nodes"]
        discovered = {"nodes", "persistentvolumes", "clusterroles"}

        updated, count = merge_cluster_scoped(existing, discovered)

        assert count == 2
        assert "nodes" in updated
        assert "persistentvolumes" in updated
        assert "clusterroles" in updated

    def test_no_duplicates(self) -> None:
        """merge_cluster_scoped does not add duplicates."""
        existing = ["nodes", "persistentvolumes"]
        discovered = {"nodes", "persistentvolumes"}

        updated, count = merge_cluster_scoped(existing, discovered)

        assert count == 0
        assert len(updated) == 2

    def test_empty_existing_list(self) -> None:
        """merge_cluster_scoped handles empty existing list."""
        updated, count = merge_cluster_scoped([], {"nodes"})
        assert count == 1
        assert "nodes" in updated


class TestWriteConfigSafe:
    """[SEC V-007] Tests for write_config_safe atomic writes and permissions."""

    def test_writes_content(self, tmp_path: Path) -> None:
        """write_config_safe creates file with correct content."""
        target = tmp_path / "test.yaml"
        write_config_safe(target, "key: value\n")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "key: value\n"

    def test_sets_0644_permissions(self, tmp_path: Path) -> None:
        """[SEC V-007] write_config_safe sets file permissions to 0o644."""
        target = tmp_path / "test.yaml"
        write_config_safe(target, "key: value\n")

        mode = target.stat().st_mode
        assert stat.S_IMODE(mode) == 0o644

    def test_atomic_write_no_tmp_file_left(self, tmp_path: Path) -> None:
        """write_config_safe does not leave .tmp file after completion."""
        target = tmp_path / "test.yaml"
        write_config_safe(target, "key: value\n")

        tmp_file = target.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """write_config_safe overwrites existing file content."""
        target = tmp_path / "test.yaml"
        target.write_text("old content\n", encoding="utf-8")

        write_config_safe(target, "new content\n")
        assert target.read_text(encoding="utf-8") == "new content\n"
