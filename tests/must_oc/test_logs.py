# tests/must_oc/test_logs.py
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pytest

from must_oc.oc.logs import MAX_LOG_SIZE, run_logs, stream_log
from tests.constants import (
    IMAGE_HASH,
    POD_1_NAME,
    POD_1_NS,
    POD_2_NAME,
    POD_2_NS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_log_args(
    must_gather_dir: str,
    pod_name: str,
    namespace: str,
    container: str | None = None,
    previous: bool = False,
) -> argparse.Namespace:
    """Build an argparse.Namespace mimicking CLI args for ``logs``."""
    return argparse.Namespace(
        must_gather_dir=[must_gather_dir],
        pod_name=pod_name,
        namespace=namespace,
        container=container,
        previous=previous,
        show_secrets=False,
    )


def _add_bare_pod_logs(
    root: Path,
    namespace: str,
    pod_name: str,
    containers: list[str],
    log_content: dict[str, str] | None = None,
    previous_content: dict[str, str] | None = None,
) -> None:
    """Create log files under the bare ``pods/`` path that ``find_log_files`` expects.

    ``find_log_files`` looks at ``namespaces/<NS>/pods/<POD>/<CTR>/<CTR>/logs/current.log``.
    The ``fake_must_gather`` fixture only writes logs under ``core/pods/``, so we
    need to add them under the bare ``pods/`` path for the logs tests.
    """
    image_dir = root / IMAGE_HASH
    for ctr_name in containers:
        log_dir = (
            image_dir
            / "namespaces"
            / namespace
            / "pods"
            / pod_name
            / ctr_name
            / ctr_name
            / "logs"
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        content = "log line 1\nlog line 2\n"
        if log_content and ctr_name in log_content:
            content = log_content[ctr_name]
        (log_dir / "current.log").write_text(content, encoding="utf-8")
        if previous_content and ctr_name in previous_content:
            (log_dir / "previous.log").write_text(
                previous_content[ctr_name], encoding="utf-8"
            )


# ---------------------------------------------------------------------------
# Test: single container pod prints logs
# ---------------------------------------------------------------------------


class TestLogsSingleContainer:
    """Tests for ``logs`` with a single-container pod."""

    def test_logs_single_container_prints_output(
        self,
        fake_must_gather: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logs pod -n NS with single container prints logs (test-pod-1, container-a)."""
        _add_bare_pod_logs(
            fake_must_gather,
            POD_1_NS,
            POD_1_NAME,
            ["container-a"],
            log_content={"container-a": "log line 1\nlog line 2\n"},
        )
        args = _make_log_args(str(fake_must_gather), POD_1_NAME, POD_1_NS)
        run_logs(args)
        captured = capsys.readouterr()
        assert "log line 1" in captured.out
        assert "log line 2" in captured.out


# ---------------------------------------------------------------------------
# Test: specific container flag
# ---------------------------------------------------------------------------


class TestLogsSpecificContainer:
    """Tests for ``logs`` with ``-c container``."""

    def test_logs_specific_container(
        self,
        fake_must_gather: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logs pod -n NS -c container prints specific container logs."""
        _add_bare_pod_logs(
            fake_must_gather,
            POD_1_NS,
            POD_1_NAME,
            ["container-a"],
            log_content={"container-a": "specific container log\n"},
        )
        args = _make_log_args(
            str(fake_must_gather), POD_1_NAME, POD_1_NS, container="container-a"
        )
        run_logs(args)
        captured = capsys.readouterr()
        assert "specific container log" in captured.out


# ---------------------------------------------------------------------------
# Test: multiple containers error
# ---------------------------------------------------------------------------


class TestLogsMultipleContainers:
    """Tests for ``logs`` with pods that have multiple containers."""

    def test_logs_multiple_containers_errors_with_list(
        self,
        fake_must_gather: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logs pod -n NS with multiple containers errors with list (test-pod-2)."""
        _add_bare_pod_logs(
            fake_must_gather,
            POD_2_NS,
            POD_2_NAME,
            ["container-x", "container-y"],
            log_content={
                "container-x": "container-x log line 1\n",
                "container-y": "container-y log line 1\n",
            },
        )
        args = _make_log_args(str(fake_must_gather), POD_2_NAME, POD_2_NS)
        with pytest.raises(SystemExit, match="1"):
            run_logs(args)
        captured = capsys.readouterr()
        assert "multiple containers" in captured.err
        assert "container-x" in captured.err
        assert "container-y" in captured.err
        assert "-c" in captured.err


# ---------------------------------------------------------------------------
# Test: pod not found
# ---------------------------------------------------------------------------


class TestLogsPodNotFound:
    """Tests for ``logs`` with a nonexistent pod."""

    def test_logs_nonexistent_pod(
        self,
        fake_must_gather: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logs nonexistent -n NS prints 'pod not found'."""
        args = _make_log_args(str(fake_must_gather), "nonexistent-pod", POD_1_NS)
        with pytest.raises(SystemExit, match="1"):
            run_logs(args)
        captured = capsys.readouterr()
        assert 'pod "nonexistent-pod" not found' in captured.err
        assert f'namespace "{POD_1_NS}"' in captured.err


# ---------------------------------------------------------------------------
# Test: container not found
# ---------------------------------------------------------------------------


class TestLogsContainerNotFound:
    """Tests for ``logs`` with a nonexistent container."""

    def test_logs_nonexistent_container(
        self,
        fake_must_gather: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logs pod -n NS -c nonexistent prints 'container not found'."""
        # Ensure the pod directory exists under bare pods/ path.
        _add_bare_pod_logs(
            fake_must_gather,
            POD_1_NS,
            POD_1_NAME,
            ["container-a"],
        )
        args = _make_log_args(
            str(fake_must_gather), POD_1_NAME, POD_1_NS, container="nonexistent"
        )
        with pytest.raises(SystemExit, match="1"):
            run_logs(args)
        captured = capsys.readouterr()
        assert 'container "nonexistent" not found' in captured.err
        assert f'pod "{POD_1_NAME}"' in captured.err


# ---------------------------------------------------------------------------
# Test: --previous flag
# ---------------------------------------------------------------------------


class TestLogsPrevious:
    """Tests for ``logs`` with ``--previous``."""

    def test_logs_previous_reads_previous_log(
        self,
        fake_must_gather: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logs pod -n NS --previous reads previous.log."""
        _add_bare_pod_logs(
            fake_must_gather,
            POD_1_NS,
            POD_1_NAME,
            ["container-a"],
            log_content={"container-a": "current log content\n"},
            previous_content={"container-a": "previous log content\n"},
        )
        args = _make_log_args(
            str(fake_must_gather),
            POD_1_NAME,
            POD_1_NS,
            previous=True,
        )
        run_logs(args)
        captured = capsys.readouterr()
        assert "previous log content" in captured.out
        assert "current log content" not in captured.out


# ---------------------------------------------------------------------------
# Test: [SEC V-005] stream_log truncation
# ---------------------------------------------------------------------------


class TestStreamLogTruncation:
    """[SEC V-005] Tests for stream_log truncation at MAX_LOG_SIZE."""

    def test_stream_log_truncates_at_max_bytes(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """[SEC V-005] stream_log truncates output at MAX_LOG_SIZE with notice."""
        log_file = tmp_path / "large.log"
        # Create a log file with content exceeding the limit.
        # Use a small max_bytes for testing.
        max_bytes = 50
        line = "A" * 20 + "\n"  # 21 bytes per line
        # Write enough lines to exceed max_bytes.
        log_file.write_text(line * 10, encoding="utf-8")

        stream_log(log_file, max_bytes=max_bytes)
        captured = capsys.readouterr()

        # Should have printed some lines but then truncated.
        assert "[Truncated:" in captured.out
        assert f"{max_bytes} bytes" in captured.out
        assert "--tail" in captured.out

    def test_stream_log_small_file_no_truncation(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """stream_log does not truncate files under max_bytes."""
        log_file = tmp_path / "small.log"
        log_file.write_text("short line\n", encoding="utf-8")
        stream_log(log_file, max_bytes=MAX_LOG_SIZE)
        captured = capsys.readouterr()
        assert "short line" in captured.out
        assert "[Truncated:" not in captured.out


# ---------------------------------------------------------------------------
# Test: [SEC V-002] symlink path escape
# ---------------------------------------------------------------------------


class TestLogsPathEscape:
    """[SEC V-002] Tests for run_logs rejecting paths that escape must-gather root."""

    def test_run_logs_rejects_symlink_escape(
        self,
        fake_must_gather_with_symlink: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """[SEC V-002] run_logs rejects log path that escapes must-gather root."""
        root = fake_must_gather_with_symlink
        image_dir = root / IMAGE_HASH

        # Create a malicious log symlink pointing outside the root.
        pod_dir = image_dir / "namespaces" / POD_1_NS / "pods" / "evil-pod"
        log_dir = pod_dir / "evil-ctr" / "evil-ctr" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        malicious_log = log_dir / "current.log"
        # Point outside the must-gather root.
        os.symlink("/etc/hostname", malicious_log)

        args = _make_log_args(str(root), "evil-pod", POD_1_NS, container="evil-ctr")
        with pytest.raises(SystemExit, match="1"):
            run_logs(args)
        captured = capsys.readouterr()
        # The path validation should reject it either in find_log_files
        # (which calls validate_path) or in our own validation.
        # Either "not found" or "escapes" is acceptable since
        # validate_path in find_log_files will skip the symlink.
        assert "Error:" in captured.err or "not found" in captured.err
