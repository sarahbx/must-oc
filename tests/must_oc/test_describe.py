# tests/must_oc/test_describe.py
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from must_oc.oc.describe import run_describe


def _make_args(
    resource_type: str,
    must_gather_dir: list[str],
    namespace: str | None = None,
    name: str | None = None,
    all_namespaces: bool = False,
    label_selector: str | None = None,
    show_secrets: bool = False,
) -> argparse.Namespace:
    """Build a mock argparse.Namespace for run_describe."""
    return argparse.Namespace(
        resource_type=resource_type,
        name=name,
        namespace=namespace,
        all_namespaces=all_namespaces,
        label_selector=label_selector,
        must_gather_dir=must_gather_dir,
        show_secrets=show_secrets,
    )


class TestDescribePod:
    """Tests for describing a pod resource."""

    def test_describe_pod_prints_full_description(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe pod -n test-ns test-pod-1 prints full description with key fields."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name="test-pod-1"
        )
        run_describe(args)
        captured = capsys.readouterr()
        output = captured.out

        # Key fields from format_describe output.
        assert "kind" in output or "Kind" in output
        assert "test-pod-1" in output
        assert "test-ns" in output

    def test_describe_pod_shows_labels(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe pod -n test-ns test-pod-1 includes labels in output."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name="test-pod-1"
        )
        run_describe(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "test-app" in output
        assert "frontend" in output

    def test_describe_pod_shows_metadata(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe pod -n test-ns test-pod-1 includes metadata section."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name="test-pod-1"
        )
        run_describe(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "metadata" in output or "Metadata" in output
        assert "name" in output or "Name" in output


class TestDescribeNotFound:
    """Tests for describe when resource is not found."""

    def test_describe_pod_nonexistent(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe pod -n test-ns nonexistent-pod prints error and exits."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name="nonexistent-pod"
        )
        with pytest.raises(SystemExit) as exc_info:
            run_describe(args)
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error" in captured.err
        assert "nonexistent-pod" in captured.err
        assert "not found" in captured.err

    def test_describe_pod_not_found_includes_namespace(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Error message includes the namespace when provided."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name="nonexistent-pod"
        )
        with pytest.raises(SystemExit):
            run_describe(args)

        captured = capsys.readouterr()
        assert "test-ns" in captured.err


class TestDescribeNoName:
    """Tests for describe when name argument is missing."""

    def test_describe_without_name_errors(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe pod -n test-ns without a name argument prints error and exits."""
        args = _make_args(
            "pod", [str(fake_must_gather)], namespace="test-ns", name=None
        )
        with pytest.raises(SystemExit) as exc_info:
            run_describe(args)
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_describe_with_empty_name_errors(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe pod -n test-ns with empty string name prints error and exits."""
        args = _make_args("pod", [str(fake_must_gather)], namespace="test-ns", name="")
        with pytest.raises(SystemExit) as exc_info:
            run_describe(args)
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Error" in captured.err


class TestDescribeSecretRedaction:
    """[SEC V-003] Tests for secret redaction in describe command."""

    def test_describe_secret_without_show_secrets_redacts(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe secret -n test-ns test-secret without --show-secrets shows <REDACTED>."""
        args = _make_args(
            "secret", [str(fake_must_gather)], namespace="test-ns", name="test-secret"
        )
        run_describe(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "test-secret" in output
        assert "<REDACTED>" in output
        # The actual base64-encoded password should not appear.
        assert "super-secret" not in output

    def test_describe_secret_with_show_secrets_shows_data(
        self, fake_must_gather: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """describe secret -n test-ns test-secret with --show-secrets shows actual data."""
        args = _make_args(
            "secret",
            [str(fake_must_gather)],
            namespace="test-ns",
            name="test-secret",
            show_secrets=True,
        )
        run_describe(args)
        captured = capsys.readouterr()
        output = captured.out

        assert "test-secret" in output
        # With show_secrets=True, REDACTED should not appear.
        assert "<REDACTED>" not in output
