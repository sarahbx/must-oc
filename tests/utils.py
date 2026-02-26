# tests/utils.py
from __future__ import annotations

import base64
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from tests.constants import (
    CREATION_TIMESTAMP,
    IMAGE_HASH,
    IMAGE_HASH_ODF,
    MUST_GATHER_DIR_NAME,
    MUST_GATHER_ODF_DIR_NAME,
    NAMESPACE_CREATION_TIMESTAMP,
    NODE_CREATION_TIMESTAMP,
    NODE_READY_TIMESTAMP,
    OCP_VERSION,
    POD_1_CONTAINERS,
    POD_1_LABELS,
    POD_1_NAME,
    POD_1_NS,
    POD_2_CONTAINERS,
    POD_2_NAME,
    POD_2_NS,
    POD_3_CONTAINERS,
    POD_3_NAME,
    POD_3_NS,
)


@contextmanager
def write_file() -> Generator[Path, None, None]:
    """Context manager providing a temporary directory for writing files.

    Uses ``tempfile.TemporaryDirectory`` for automatic cleanup on exit.
    Yields the ``Path`` to the temporary directory root.  Callers should
    use ``emit_file`` to create files within that root.

    Example::

        with write_file() as tmp_root:
            emit_file(tmp_root / "foo.yaml", "key: value")
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def emit_file(path: Path, content: str) -> None:
    """Create parent directories and write *content* to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_pod_yaml(
    name: str,
    namespace: str,
    labels: dict[str, str] | None = None,
    containers: list[dict[str, str]] | None = None,
) -> str:
    """Return a minimal but realistic Pod YAML string.

    Args:
        name: Pod name.
        namespace: Pod namespace.
        labels: Label dict. Defaults to ``{"app": name}``.
        containers: List of container dicts, each with at least a ``name``
            key and optionally an ``image`` key.  Defaults to
            ``[{"name": "main"}]``.
    """
    if labels is None:
        labels = {"app": name}
    if containers is None:
        containers = [{"name": "main"}]

    container_specs: list[dict[str, Any]] = []
    container_statuses: list[dict[str, Any]] = []
    for ctr in containers:
        ctr_name = ctr.get("name", "main")
        ctr_image = ctr.get("image", f"registry.test/{ctr_name}:latest")
        container_specs.append({"name": ctr_name, "image": ctr_image})
        container_statuses.append(
            {
                "name": ctr_name,
                "ready": True,
                "restartCount": 0,
                "state": {"running": {"startedAt": CREATION_TIMESTAMP}},
            }
        )

    pod_dict: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": labels,
            "creationTimestamp": CREATION_TIMESTAMP,
        },
        "spec": {
            "containers": container_specs,
        },
        "status": {
            "phase": "Running",
            "containerStatuses": container_statuses,
        },
    }
    return yaml.dump(pod_dict, default_flow_style=False, sort_keys=False)


def build_deployment_yaml(name: str, namespace: str) -> str:
    """Return a minimal Deployment YAML string."""
    deploy_dict: dict[str, Any] = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {"app": name},
            "creationTimestamp": CREATION_TIMESTAMP,
        },
        "spec": {
            "replicas": 1,
            "selector": {
                "matchLabels": {"app": name},
            },
            "template": {
                "metadata": {
                    "labels": {"app": name},
                },
                "spec": {
                    "containers": [
                        {"name": name, "image": f"registry.test/{name}:latest"},
                    ],
                },
            },
        },
        "status": {
            "readyReplicas": 1,
            "availableReplicas": 1,
        },
    }
    return yaml.dump(deploy_dict, default_flow_style=False, sort_keys=False)


def build_secret_yaml(
    name: str,
    namespace: str,
    data: dict[str, str] | None = None,
) -> str:
    """Return a Secret YAML string with base64-encoded data.

    [SEC V-003] Used for redaction testing.

    Args:
        name: Secret name.
        namespace: Secret namespace.
        data: Plain-text key-value pairs.  Defaults to
            ``{"password": "super-secret"}``.  Values are base64-encoded
            automatically.
    """
    if data is None:
        data = {"password": "super-secret"}

    encoded_data = {
        key: base64.b64encode(val.encode("utf-8")).decode("ascii")
        for key, val in data.items()
    }

    last_applied: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": namespace},
        "data": encoded_data,
    }

    secret_dict: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": yaml.dump(
                    last_applied,
                    default_flow_style=False,
                    sort_keys=False,
                ),
            },
            "creationTimestamp": CREATION_TIMESTAMP,
        },
        "type": "Opaque",
        "data": encoded_data,
    }
    return yaml.dump(secret_dict, default_flow_style=False, sort_keys=False)


def build_namespace_yaml(name: str) -> str:
    """Return a minimal Namespace YAML string."""
    namespace_dict: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": name,
            "labels": {"kubernetes.io/metadata.name": name},
            "creationTimestamp": NAMESPACE_CREATION_TIMESTAMP,
        },
        "status": {
            "phase": "Active",
        },
    }
    return yaml.dump(namespace_dict, default_flow_style=False, sort_keys=False)


def build_configmap_yaml(name: str, namespace: str) -> str:
    """Return a minimal ConfigMap YAML string."""
    configmap_dict: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "creationTimestamp": CREATION_TIMESTAMP,
        },
        "data": {
            "config.yaml": "key: value\n",
        },
    }
    return yaml.dump(configmap_dict, default_flow_style=False, sort_keys=False)


def build_node_yaml(name: str) -> str:
    """Return a minimal Node YAML string."""
    node_dict: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": {
            "name": name,
            "labels": {
                "kubernetes.io/hostname": name,
                "node-role.kubernetes.io/worker": "",
            },
            "creationTimestamp": NODE_CREATION_TIMESTAMP,
        },
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True",
                    "lastTransitionTime": NODE_READY_TIMESTAMP,
                },
            ],
        },
    }
    return yaml.dump(node_dict, default_flow_style=False, sort_keys=False)


def build_pod_list_yaml(pods: list[dict[str, Any]]) -> str:
    """Return a PodList YAML string from a list of pod resource dicts."""
    pod_list_dict: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "PodList",
        "metadata": {
            "resourceVersion": "99999",
        },
        "items": pods,
    }
    return yaml.dump(pod_list_dict, default_flow_style=False, sort_keys=False)


def populate_must_gather(base_path: Path) -> Path:
    """Build a fake must-gather directory tree and return the root path.

    Creates the full directory structure under
    ``<base_path>/must-gather.local.test-ocp/`` including namespaced
    resources, Pattern B duplicates, cluster-scoped resources, logs,
    and a Secret with base64-encoded data for [SEC V-003] testing.
    """
    root = base_path / MUST_GATHER_DIR_NAME
    image_dir = root / IMAGE_HASH

    emit_file(image_dir / "version", OCP_VERSION)

    ns_dir = image_dir / "namespaces" / "test-ns"
    emit_file(ns_dir / "test-ns.yaml", build_namespace_yaml("test-ns"))

    pod1_yaml = build_pod_yaml(
        POD_1_NAME,
        POD_1_NS,
        labels=POD_1_LABELS,
        containers=POD_1_CONTAINERS,
    )
    emit_file(ns_dir / "core" / "pods" / POD_1_NAME / f"{POD_1_NAME}.yaml", pod1_yaml)
    emit_file(ns_dir / "pods" / POD_1_NAME / f"{POD_1_NAME}.yaml", pod1_yaml)
    log_base_1 = (
        ns_dir / "core" / "pods" / POD_1_NAME / "container-a" / "container-a" / "logs"
    )
    emit_file(log_base_1 / "current.log", "log line 1\nlog line 2\n")
    emit_file(log_base_1 / "previous.log", "previous log\n")

    pod2_yaml = build_pod_yaml(POD_2_NAME, POD_2_NS, containers=POD_2_CONTAINERS)
    emit_file(ns_dir / "core" / "pods" / POD_2_NAME / f"{POD_2_NAME}.yaml", pod2_yaml)
    emit_file(ns_dir / "pods" / POD_2_NAME / f"{POD_2_NAME}.yaml", pod2_yaml)
    log_base_2x = (
        ns_dir / "core" / "pods" / POD_2_NAME / "container-x" / "container-x" / "logs"
    )
    emit_file(log_base_2x / "current.log", "container-x log line 1\n")
    log_base_2y = (
        ns_dir / "core" / "pods" / POD_2_NAME / "container-y" / "container-y" / "logs"
    )
    emit_file(log_base_2y / "current.log", "container-y log line 1\n")

    pod1_dict = yaml.safe_load(pod1_yaml)
    pod2_dict = yaml.safe_load(pod2_yaml)
    emit_file(
        ns_dir / "core" / "pods.yaml", build_pod_list_yaml([pod1_dict, pod2_dict])
    )

    emit_file(
        ns_dir / "core" / "secrets" / "test-secret.yaml",
        build_secret_yaml("test-secret", "test-ns"),
    )
    emit_file(
        ns_dir / "core" / "configmaps" / "test-cm.yaml",
        build_configmap_yaml("test-cm", "test-ns"),
    )
    emit_file(
        ns_dir / "apps" / "deployments" / "test-deploy.yaml",
        build_deployment_yaml("test-deploy", "test-ns"),
    )

    ns2_dir = image_dir / "namespaces" / "test-ns-2"
    pod3_yaml = build_pod_yaml(POD_3_NAME, POD_3_NS, containers=POD_3_CONTAINERS)
    emit_file(ns2_dir / "core" / "pods" / POD_3_NAME / f"{POD_3_NAME}.yaml", pod3_yaml)

    pattern_b_dir = (
        image_dir / "namespaces" / "all" / "namespaces" / "test-ns" / "core" / "pods"
    )
    emit_file(pattern_b_dir / f"{POD_1_NAME}.yaml", pod1_yaml)

    cluster_dir = image_dir / "cluster-scoped-resources" / "core" / "nodes"
    emit_file(cluster_dir / "test-node-1.yaml", build_node_yaml("test-node-1"))

    return root


def populate_must_gather_multi(base_path: Path) -> tuple[Path, Path]:
    """Build two fake must-gather directories for multi-directory merge testing.

    Returns a tuple of ``(ocp_root, odf_root)`` paths.
    """
    ocp_root = populate_must_gather(base_path / "gather-ocp")

    odf_root = base_path / "gather-odf" / MUST_GATHER_ODF_DIR_NAME
    odf_image = odf_root / IMAGE_HASH_ODF
    emit_file(odf_image / "version", OCP_VERSION)

    odf_ns = odf_image / "namespaces" / "openshift-storage"
    odf_pod_yaml = build_pod_yaml(
        "odf-pod-1",
        "openshift-storage",
        labels={"app": "odf-operator"},
        containers=[{"name": "odf-main"}],
    )
    emit_file(
        odf_ns / "core" / "pods" / "odf-pod-1" / "odf-pod-1.yaml",
        odf_pod_yaml,
    )
    odf_log_dir = (
        odf_ns / "core" / "pods" / "odf-pod-1" / "odf-main" / "odf-main" / "logs"
    )
    emit_file(odf_log_dir / "current.log", "odf log line 1\n")

    return ocp_root, odf_root
