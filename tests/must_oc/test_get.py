# tests/must_oc/test_get.py
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from must_oc.oc.get import run_get


def _make_args(
    resource_type: str,
    must_gather_dir: list[str],
    namespace: str | None = None,
    name: str | None = None,
    all_namespaces: bool = False,
    label_selector: str | None = None,
    show_secrets: bool = False,
) -> argparse.Namespace:
    """Build a mock argparse.Namespace for run_get."""
    return argparse.Namespace(
        resource_type=resource_type,
        name=name,
        namespace=namespace,
        all_namespaces=all_namespaces,
        label_selector=label_selector,
        must_gather_dir=must_gather_dir,
        show_secrets=show_secrets,
    )


class TestGetPodNamespaced:
    """Tests for getting pods in a specific namespace."""

    def test_get_pods_returns_correct_pods(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n test-ns returns table with test-pod-1 and test-pod-2."""
        args = _make_args("pod", [str(fake_must_gather)], namespace="test-ns")
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "NAME" in output
        assert "READY" in output
        assert "STATUS" in output
        assert "RESTARTS" in output
        assert "AGE" in output
        assert "test-pod-1" in output
        assert "test-pod-2" in output
        # Should NOT include pods from other namespaces.
        assert "test-pod-3" not in output
        # Should NOT have NAMESPACE column without -A.
        assert "NAMESPACE" not in output

    def test_get_pod_ready_column(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n test-ns shows correct READY counts."""
        args = _make_args("pod", [str(fake_must_gather)], namespace="test-ns")
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        # test-pod-1 has 1 container (container-a), all ready.
        assert "1/1" in output
        # test-pod-2 has 2 containers (container-x, container-y), all ready.
        assert "2/2" in output

    def test_get_pod_status_column(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n test-ns shows Running status."""
        args = _make_args("pod", [str(fake_must_gather)], namespace="test-ns")
        run_get(args)
        captured = capsys.readouterr()
        assert "Running" in captured.out


class TestGetPodAllNamespaces:
    """Tests for getting pods across all namespaces."""

    def test_get_pods_all_namespaces(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -A returns pods from all namespaces with NAMESPACE column."""
        args = _make_args("pod", [str(fake_must_gather)], all_namespaces=True)
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "NAMESPACE" in output
        assert "test-pod-1" in output
        assert "test-pod-2" in output
        assert "test-pod-3" in output
        assert "test-ns" in output
        assert "test-ns-2" in output


class TestGetPodByName:
    """Tests for getting a specific pod by name."""

    def test_get_single_pod_by_name(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n test-ns test-pod-1 returns only that pod."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name="test-pod-1"
        )
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "test-pod-1" in output
        assert "test-pod-2" not in output


class TestGetPodLabelSelector:
    """Tests for label selector filtering."""

    def test_get_pods_filtered_by_label(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n test-ns -l app=test-app returns only matching pods."""
        args = _make_args(
            "pod",
            [str(fake_must_gather)],
            namespace="test-ns",
            label_selector="app=test-app",
        )
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "test-pod-1" in output
        assert "test-pod-2" not in output

    def test_get_pods_filtered_by_label_no_match(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n test-ns -l app=nonexistent returns no resources found."""
        args = _make_args(
            "pod",
            [str(fake_must_gather)],
            namespace="test-ns",
            label_selector="app=nonexistent",
        )
        run_get(args)
        captured = capsys.readouterr()
        assert "No resources found in namespace test-ns." in captured.out


class TestGetNoResources:
    """Tests for the 'no resources found' case."""

    def test_get_pods_nonexistent_namespace(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod -n nonexistent returns 'No resources found'."""
        args = _make_args("pod", [str(fake_must_gather)], namespace="nonexistent")
        run_get(args)
        captured = capsys.readouterr()
        assert "No resources found in namespace nonexistent." in captured.out

    def test_get_no_namespace_no_resources(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get pod without -n or -A prints generic no resources message."""
        args = _make_args("pod", [str(fake_must_gather)])
        run_get(args)
        captured = capsys.readouterr()
        assert "No resources found." in captured.out


class TestGetDeployment:
    """Tests for getting non-pod resources."""

    def test_get_deployments(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get deployment -n test-ns returns deployments."""
        args = _make_args("deployment", [str(fake_must_gather)], namespace="test-ns")
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "NAME" in output
        assert "AGE" in output
        assert "test-deploy" in output
        # Deployment should NOT have pod-specific columns.
        assert "READY" not in output
        assert "STATUS" not in output
        assert "RESTARTS" not in output


class TestGetMultiGather:
    """Tests for merging multiple must-gather directories."""

    def test_multi_gather_merge(
        self,
        fake_must_gather_multi: tuple[Path, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Multiple must-gather directories are merged, showing pods from both."""
        ocp_root, odf_root = fake_must_gather_multi
        args = _make_args("pod", [str(ocp_root), str(odf_root)], all_namespaces=True)
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        # Should contain pods from OCP gather.
        assert "test-pod-1" in output
        # Should contain pods from ODF gather.
        assert "odf-pod-1" in output


class TestGetSecretSecurity:
    """[SEC V-003] Tests for secret handling in get command."""

    def test_get_secret_no_crash(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """get secret -n test-ns without --show-secrets does not crash.

        The get table for secrets does not directly show data values,
        so this test verifies basic functionality without errors.
        """
        args = _make_args(
            "secret", [str(fake_must_gather)], namespace="test-ns", show_secrets=False
        )
        run_get(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "NAME" in output
        assert "AGE" in output
        assert "test-secret" in output
