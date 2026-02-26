# tests/utilities/test_paths.py
from __future__ import annotations

from pathlib import Path

import pytest

from utilities.paths import (
    discover_roots,
    find_log_files,
    find_resource_files,
    validate_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def must_gather_tree(tmp_path: Path) -> Path:
    """Build a minimal fake must-gather directory tree.

    Layout::

        <tmp_path>/must-gather.test/
          fake-hash-abc123/
            namespaces/
              test-ns/
                pods/                          # bare pods/ dir (Pattern A1 - F-002)
                  test-pod-1/
                    test-pod-1.yaml
                    container-a/
                      container-a/
                        logs/
                          current.log
                core/
                  pods.yaml                   # PodList file
                  pods/
                    test-pod-1.yaml           # Pattern A2 (api_group prefix)
                  configmaps/
                    test-cm.yaml
                apps/
                  deployments/
                    test-deploy.yaml
              test-ns-2/
                core/
                  pods/
                    test-pod-3.yaml
            namespaces/all/namespaces/
              test-ns/
                core/
                  pods/
                    test-pod-1.yaml          # Pattern B (duplicate)
            cluster-scoped-resources/
              core/
                nodes/
                  test-node-1.yaml
    """
    gather_dir = tmp_path / "must-gather.test"
    hash_dir = gather_dir / "fake-hash-abc123"

    # --- Pattern A1: bare pods/ (F-002) ---
    pod1_dir = hash_dir / "namespaces" / "test-ns" / "pods" / "test-pod-1"
    pod1_dir.mkdir(parents=True)
    (pod1_dir / "test-pod-1.yaml").write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod-1\n  namespace: test-ns\n",
        encoding="utf-8",
    )

    # Container log with doubled container directory
    log_dir = pod1_dir / "container-a" / "container-a" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "current.log").write_text("2026-01-15 pod started\n", encoding="utf-8")

    # --- Pattern A2: core/pods/<name>.yaml ---
    core_pods_dir = hash_dir / "namespaces" / "test-ns" / "core" / "pods"
    core_pods_dir.mkdir(parents=True)
    (core_pods_dir / "test-pod-1.yaml").write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod-1\n  namespace: test-ns\n",
        encoding="utf-8",
    )

    # --- Pattern A3: core/pods.yaml (list file) ---
    (hash_dir / "namespaces" / "test-ns" / "core" / "pods.yaml").write_text(
        "apiVersion: v1\nkind: PodList\nmetadata: {}\nitems:\n"
        "  - apiVersion: v1\n    kind: Pod\n    metadata:\n      name: test-pod-1\n",
        encoding="utf-8",
    )

    # --- configmaps ---
    cm_dir = hash_dir / "namespaces" / "test-ns" / "core" / "configmaps"
    cm_dir.mkdir(parents=True)
    (cm_dir / "test-cm.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test-cm\n  namespace: test-ns\n",
        encoding="utf-8",
    )

    # --- deployments ---
    deploy_dir = hash_dir / "namespaces" / "test-ns" / "apps" / "deployments"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "test-deploy.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: test-deploy\n  namespace: test-ns\n",
        encoding="utf-8",
    )

    # --- test-ns-2 ---
    ns2_pods = hash_dir / "namespaces" / "test-ns-2" / "core" / "pods"
    ns2_pods.mkdir(parents=True)
    (ns2_pods / "test-pod-3.yaml").write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod-3\n  namespace: test-ns-2\n",
        encoding="utf-8",
    )

    # --- Pattern B: namespaces/all/namespaces/<NS>/... ---
    pattern_b_dir = (
        hash_dir / "namespaces" / "all" / "namespaces" / "test-ns" / "core" / "pods"
    )
    pattern_b_dir.mkdir(parents=True)
    (pattern_b_dir / "test-pod-1.yaml").write_text(
        "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod-1\n  namespace: test-ns\n",
        encoding="utf-8",
    )

    # --- cluster-scoped-resources ---
    nodes_dir = hash_dir / "cluster-scoped-resources" / "core" / "nodes"
    nodes_dir.mkdir(parents=True)
    (nodes_dir / "test-node-1.yaml").write_text(
        "apiVersion: v1\nkind: Node\nmetadata:\n  name: test-node-1\n",
        encoding="utf-8",
    )

    return gather_dir


# ---------------------------------------------------------------------------
# discover_roots
# ---------------------------------------------------------------------------


class TestDiscoverRoots:
    """Tests for discover_roots()."""

    def test_finds_image_hash_subdirectories(self, must_gather_tree: Path) -> None:
        """discover_roots finds subdirectories containing namespaces/."""
        roots = discover_roots([must_gather_tree])
        assert len(roots) >= 1
        root_names = [rpath.name for rpath in roots]
        assert "fake-hash-abc123" in root_names

    def test_nonexistent_dir_raises_file_not_found(self, tmp_path: Path) -> None:
        """discover_roots raises FileNotFoundError for nonexistent directories."""
        missing = tmp_path / "does-not-exist.test"
        with pytest.raises(FileNotFoundError, match="does not exist"):
            discover_roots([missing])

    def test_handles_nested_sub_roots(self, tmp_path: Path) -> None:
        """discover_roots finds nested sub-roots like ODF's ceph/ directory."""
        gather_dir = tmp_path / "must-gather-odf.test"
        hash_dir = gather_dir / "odf-hash-xyz789"

        # Top-level root
        (hash_dir / "namespaces" / "openshift-storage").mkdir(parents=True)

        # Nested sub-root (ceph/ has its own namespaces/)
        (hash_dir / "ceph" / "namespaces" / "openshift-storage").mkdir(parents=True)

        roots = discover_roots([gather_dir])
        root_names = [rpath.name for rpath in roots]
        assert "odf-hash-xyz789" in root_names
        assert "ceph" in root_names
        assert len(roots) == 2


# ---------------------------------------------------------------------------
# validate_path  [SEC V-002]
# ---------------------------------------------------------------------------


class TestValidatePath:
    """[SEC V-002] Tests for validate_path()."""

    def test_accepts_valid_path_within_root(self, must_gather_tree: Path) -> None:
        """validate_path accepts a path that resolves within root."""
        valid = must_gather_tree / "fake-hash-abc123" / "namespaces" / "test-ns"
        result = validate_path(valid, must_gather_tree)
        assert result.is_relative_to(must_gather_tree.resolve())

    def test_rejects_path_with_dotdot_escaping_root(self, tmp_path: Path) -> None:
        """[SEC V-002] validate_path rejects paths using '..' to escape root."""
        root = tmp_path / "root.test"
        root.mkdir()
        # This path would resolve outside root.
        escaping_path = root / ".." / ".." / "etc" / "hostname"
        with pytest.raises(ValueError, match="Path escapes must-gather root"):
            validate_path(escaping_path, root)

    def test_rejects_symlink_pointing_outside_root(self, tmp_path: Path) -> None:
        """[SEC V-002] validate_path rejects symlinks that resolve outside root."""
        root = tmp_path / "root.test"
        root.mkdir()

        # Create a target file outside root.
        outside = tmp_path / "outside.test"
        outside.mkdir()
        outside_file = outside / "secret.yaml"
        outside_file.write_text("secret: data\n", encoding="utf-8")

        # Create a symlink inside root that points outside.
        symlink = root / "evil-link.yaml"
        symlink.symlink_to(outside_file)

        with pytest.raises(ValueError, match="Path escapes must-gather root"):
            validate_path(symlink, root)


# ---------------------------------------------------------------------------
# find_resource_files
# ---------------------------------------------------------------------------


class TestFindResourceFiles:
    """Tests for find_resource_files()."""

    def test_finds_pods_in_both_pattern_a_and_b(self, must_gather_tree: Path) -> None:
        """find_resource_files finds pods in Pattern A (bare and api_group) and Pattern B.

        Pattern A should take precedence for duplicates, so test-pod-1 should
        appear only once even though it exists in Pattern A1, A2, and B.
        """
        roots = discover_roots([must_gather_tree])
        files = find_resource_files(
            roots=roots,
            namespace="test-ns",
            all_namespaces=False,
            api_group="core",
            plural="pods",
            name=None,
        )
        # test-pod-1 exists in A1, A2, and B -- dedup should keep only first occurrence.
        # pods.yaml (list file) is also found under A3.
        stems = [fpath.stem for fpath in files]
        assert "test-pod-1" in stems
        # Should be deduplicated -- only one entry for test-pod-1.
        assert stems.count("test-pod-1") == 1
        # The list file should also appear.
        assert "pods" in stems

    def test_specific_name_returns_only_that_file(self, must_gather_tree: Path) -> None:
        """find_resource_files with specific name returns only that file."""
        roots = discover_roots([must_gather_tree])
        files = find_resource_files(
            roots=roots,
            namespace="test-ns",
            all_namespaces=False,
            api_group="core",
            plural="pods",
            name="test-pod-1",
        )
        assert len(files) == 1
        assert files[0].stem == "test-pod-1"

    def test_missing_namespace_returns_empty(self, must_gather_tree: Path) -> None:
        """find_resource_files returns empty list for nonexistent namespace."""
        roots = discover_roots([must_gather_tree])
        files = find_resource_files(
            roots=roots,
            namespace="no-such-ns",
            all_namespaces=False,
            api_group="core",
            plural="pods",
            name=None,
        )
        assert files == []

    def test_all_namespaces_finds_pods_across_namespaces(
        self, must_gather_tree: Path
    ) -> None:
        """find_resource_files with all_namespaces finds pods in multiple namespaces."""
        roots = discover_roots([must_gather_tree])
        files = find_resource_files(
            roots=roots,
            namespace=None,
            all_namespaces=True,
            api_group="core",
            plural="pods",
            name=None,
        )
        stems = [fpath.stem for fpath in files]
        assert "test-pod-1" in stems
        assert "test-pod-3" in stems

    def test_finds_cluster_scoped_resources(self, must_gather_tree: Path) -> None:
        """find_resource_files finds cluster-scoped resources (nodes)."""
        roots = discover_roots([must_gather_tree])
        files = find_resource_files(
            roots=roots,
            namespace=None,
            all_namespaces=False,
            api_group="core",
            plural="nodes",
            name=None,
        )
        stems = [fpath.stem for fpath in files]
        assert "test-node-1" in stems

    def test_finds_deployments(self, must_gather_tree: Path) -> None:
        """find_resource_files finds deployments under apps/ api_group."""
        roots = discover_roots([must_gather_tree])
        files = find_resource_files(
            roots=roots,
            namespace="test-ns",
            all_namespaces=False,
            api_group="apps",
            plural="deployments",
            name=None,
        )
        stems = [fpath.stem for fpath in files]
        assert "test-deploy" in stems

    def test_skips_files_that_fail_path_validation(self, tmp_path: Path) -> None:
        """[SEC V-002] find_resource_files skips files that fail path validation.

        Creates a symlink inside the must-gather tree that points to a file
        outside the root.  That symlink-based file must be skipped silently.
        """
        gather_dir = tmp_path / "must-gather-sec.test"
        hash_dir = gather_dir / "sec-hash-001"
        pods_dir = hash_dir / "namespaces" / "evil-ns" / "core" / "pods"
        pods_dir.mkdir(parents=True)

        # Create a real file outside the gather root.
        outside = tmp_path / "outside-sec.test"
        outside.mkdir()
        outside_file = outside / "stolen.yaml"
        outside_file.write_text(
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: stolen\n", encoding="utf-8"
        )

        # Create a symlink inside the pods dir pointing outside root.
        (pods_dir / "stolen.yaml").symlink_to(outside_file)

        # Also create a legitimate file.
        (pods_dir / "legit-pod.yaml").write_text(
            "apiVersion: v1\nkind: Pod\nmetadata:\n  name: legit-pod\n",
            encoding="utf-8",
        )

        roots = discover_roots([gather_dir])
        files = find_resource_files(
            roots=roots,
            namespace="evil-ns",
            all_namespaces=False,
            api_group="core",
            plural="pods",
            name=None,
        )
        stems = [fpath.stem for fpath in files]
        assert "legit-pod" in stems
        assert "stolen" not in stems


# ---------------------------------------------------------------------------
# find_log_files
# ---------------------------------------------------------------------------


class TestFindLogFiles:
    """Tests for find_log_files()."""

    def test_finds_current_log_in_doubled_container_path(
        self, must_gather_tree: Path
    ) -> None:
        """find_log_files finds current.log in the doubled-container path."""
        roots = discover_roots([must_gather_tree])
        log_files = find_log_files(
            roots=roots,
            namespace="test-ns",
            pod_name="test-pod-1",
            container="container-a",
        )
        assert len(log_files) == 1
        assert log_files[0].name == "current.log"
        # Verify doubled container in the path.
        parts = log_files[0].parts
        container_indices = [
            idx for idx, part in enumerate(parts) if part == "container-a"
        ]
        assert len(container_indices) == 2

    def test_nonexistent_container_returns_empty(self, must_gather_tree: Path) -> None:
        """find_log_files returns empty list for a container that doesn't exist."""
        roots = discover_roots([must_gather_tree])
        log_files = find_log_files(
            roots=roots,
            namespace="test-ns",
            pod_name="test-pod-1",
            container="no-such-container",
        )
        assert log_files == []

    def test_finds_all_containers_when_none_specified(
        self, must_gather_tree: Path
    ) -> None:
        """find_log_files discovers all containers when container is None."""
        roots = discover_roots([must_gather_tree])
        log_files = find_log_files(
            roots=roots,
            namespace="test-ns",
            pod_name="test-pod-1",
            container=None,
        )
        assert len(log_files) == 1
        assert log_files[0].name == "current.log"

    def test_nonexistent_pod_returns_empty(self, must_gather_tree: Path) -> None:
        """find_log_files returns empty list for a pod that doesn't exist."""
        roots = discover_roots([must_gather_tree])
        log_files = find_log_files(
            roots=roots,
            namespace="test-ns",
            pod_name="ghost-pod",
            container=None,
        )
        assert log_files == []
