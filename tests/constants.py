# tests/constants.py
from __future__ import annotations

POD_1_NAME: str = "test-pod-1"
POD_1_NS: str = "test-ns"
POD_1_LABELS: dict[str, str] = {"app": "test-app", "tier": "frontend"}
POD_1_CONTAINERS: list[dict[str, str]] = [{"name": "container-a"}]

POD_2_NAME: str = "test-pod-2"
POD_2_NS: str = "test-ns"
POD_2_LABELS: dict[str, str] = {"app": "test-pod-2"}
POD_2_CONTAINERS: list[dict[str, str]] = [
    {"name": "container-x"},
    {"name": "container-y"},
]

POD_3_NAME: str = "test-pod-3"
POD_3_NS: str = "test-ns-2"
POD_3_LABELS: dict[str, str] = {"app": "test-pod-3"}
POD_3_CONTAINERS: list[dict[str, str]] = [{"name": "container-a"}]

CREATION_TIMESTAMP: str = "2026-01-15T10:30:00Z"
NAMESPACE_CREATION_TIMESTAMP: str = "2026-01-15T10:00:00Z"
NODE_CREATION_TIMESTAMP: str = "2026-01-15T09:00:00Z"
NODE_READY_TIMESTAMP: str = "2026-01-15T09:05:00Z"

IMAGE_HASH: str = "fake-image-hash-abc123"
IMAGE_HASH_ODF: str = "fake-image-hash-def456"

MUST_GATHER_DIR_NAME: str = "must-gather.local.test-ocp"
MUST_GATHER_ODF_DIR_NAME: str = "must-gather.local.test-odf"

OCP_VERSION: str = "4.16.0"
