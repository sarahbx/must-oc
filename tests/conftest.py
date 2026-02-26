# tests/conftest.py
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.constants import IMAGE_HASH
from tests.utils import (
    build_deployment_yaml,
    build_pod_yaml,
    build_secret_yaml,
    populate_must_gather,
    populate_must_gather_multi,
)


@pytest.fixture
def fake_pod_yaml() -> Callable[..., str]:
    """Return a factory that produces minimal but realistic Pod YAML strings."""

    def _build(
        name: str,
        namespace: str,
        labels: dict[str, str] | None = None,
        containers: list[dict[str, str]] | None = None,
    ) -> str:
        return build_pod_yaml(name, namespace, labels=labels, containers=containers)

    return _build


@pytest.fixture
def fake_deployment_yaml() -> Callable[..., str]:
    """Return a factory that produces minimal Deployment YAML strings."""

    def _build(name: str, namespace: str) -> str:
        return build_deployment_yaml(name, namespace)

    return _build


@pytest.fixture
def fake_secret_yaml() -> Callable[..., str]:
    """Return a factory that produces Secret YAML strings with base64-encoded data.

    [SEC V-003] Used for redaction testing.
    """

    def _build(
        name: str,
        namespace: str,
        data: dict[str, str] | None = None,
    ) -> str:
        return build_secret_yaml(name, namespace, data=data)

    return _build


@pytest.fixture
def fake_must_gather(tmp_path: Path) -> Path:
    """Build a single fake must-gather directory tree.

    Returns the path to ``<tmp_path>/must-gather.local.test-ocp/``.
    """
    return populate_must_gather(tmp_path)


@pytest.fixture
def fake_must_gather_multi(tmp_path: Path) -> tuple[Path, Path]:
    """Build two fake must-gather directories for multi-directory merge testing.

    Returns a tuple of ``(ocp_root, odf_root)`` paths.
    """
    return populate_must_gather_multi(tmp_path)


@pytest.fixture
def fake_must_gather_with_symlink(tmp_path: Path) -> Path:
    """Build a fake must-gather that includes a malicious symlink.

    [SEC V-002] The symlink ``malicious.yaml`` points to ``/etc/hostname``
    to test path traversal rejection.

    Returns the path to ``<tmp_path>/must-gather.local.test-ocp/``.
    """
    root = populate_must_gather(tmp_path)
    image_dir = root / IMAGE_HASH
    malicious_link = (
        image_dir / "namespaces" / "test-ns" / "core" / "pods" / "malicious.yaml"
    )
    malicious_link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("/etc/hostname", malicious_link)
    return root
