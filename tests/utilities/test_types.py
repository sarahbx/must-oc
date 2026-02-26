# tests/utilities/test_types.py
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from utilities.types import (
    get_kind_from_plural,
    is_cluster_scoped,
    load_resource_map,
    resolve_resource_type,
)


# ---------------------------------------------------------------------------
# 1. resolve_resource_type("pod") returns ("core", "pods")
# ---------------------------------------------------------------------------
def test_resolve_pod() -> None:
    result = resolve_resource_type("pod")
    assert result == ("core", "pods")


# ---------------------------------------------------------------------------
# 2. resolve_resource_type("deploy") returns ("apps", "deployments")
# ---------------------------------------------------------------------------
def test_resolve_deploy() -> None:
    result = resolve_resource_type("deploy")
    assert result == ("apps", "deployments")


# ---------------------------------------------------------------------------
# 3. resolve_resource_type("nonexistent") raises ValueError
# ---------------------------------------------------------------------------
def test_resolve_nonexistent_raises() -> None:
    with pytest.raises(ValueError, match="Unknown resource type"):
        resolve_resource_type("nonexistent")


# ---------------------------------------------------------------------------
# 4. is_cluster_scoped("nodes") returns True
# ---------------------------------------------------------------------------
def test_nodes_are_cluster_scoped() -> None:
    assert is_cluster_scoped("nodes") is True


# ---------------------------------------------------------------------------
# 5. is_cluster_scoped("pods") returns False
# ---------------------------------------------------------------------------
def test_pods_are_not_cluster_scoped() -> None:
    assert is_cluster_scoped("pods") is False


# ---------------------------------------------------------------------------
# 6. All aliases resolve to correct plural form (parametrized)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("alias", "expected_api_group", "expected_plural"),
    [
        ("pod", "core", "pods"),
        ("po", "core", "pods"),
        ("pods", "core", "pods"),
        ("svc", "core", "services"),
        ("service", "core", "services"),
        ("cm", "core", "configmaps"),
        ("configmap", "core", "configmaps"),
        ("secret", "core", "secrets"),
        ("sa", "core", "serviceaccounts"),
        ("pvc", "core", "persistentvolumeclaims"),
        ("ev", "core", "events"),
        ("no", "core", "nodes"),
        ("ns", "core", "namespaces"),
        ("pv", "core", "persistentvolumes"),
        ("rc", "core", "replicationcontrollers"),
        ("ep", "core", "endpoints"),
        ("deploy", "apps", "deployments"),
        ("deployment", "apps", "deployments"),
        ("rs", "apps", "replicasets"),
        ("sts", "apps", "statefulsets"),
        ("ds", "apps", "daemonsets"),
        ("job", "batch", "jobs"),
        ("cj", "batch", "cronjobs"),
        ("ing", "networking.k8s.io", "ingresses"),
        ("netpol", "networking.k8s.io", "networkpolicies"),
        ("role", "rbac.authorization.k8s.io", "roles"),
        ("clusterrole", "rbac.authorization.k8s.io", "clusterroles"),
        ("route", "route.openshift.io", "routes"),
        ("hpa", "autoscaling", "horizontalpodautoscalers"),
        ("pdb", "policy", "poddisruptionbudgets"),
    ],
)
def test_alias_resolves_to_correct_plural(
    alias: str, expected_api_group: str, expected_plural: str
) -> None:
    api_group, plural = resolve_resource_type(alias)
    assert api_group == expected_api_group
    assert plural == expected_plural


# ---------------------------------------------------------------------------
# 7. Config YAML with missing `aliases` key still loads (tmp_path fixture)
# ---------------------------------------------------------------------------
def test_missing_aliases_key_still_loads(tmp_path: Path) -> None:
    resource_map_path = tmp_path / "resource_map.yaml"
    resource_map_path.write_text(
        yaml.dump({"widgets": {"api_group": "example.test"}}),
        encoding="utf-8",
    )

    # Clear the lru_cache so the custom path is picked up.
    load_resource_map.cache_clear()
    try:
        result = load_resource_map(resource_map_path)
    finally:
        load_resource_map.cache_clear()

    assert "widgets" in result
    assert result["widgets"] == ("example.test", "widgets")


# ---------------------------------------------------------------------------
# 8. Empty resource_map.yaml results in empty map (tmp_path fixture)
# ---------------------------------------------------------------------------
def test_empty_resource_map_returns_empty(tmp_path: Path) -> None:
    resource_map_path = tmp_path / "resource_map.yaml"
    resource_map_path.write_text("", encoding="utf-8")

    load_resource_map.cache_clear()
    try:
        result = load_resource_map(resource_map_path)
    finally:
        load_resource_map.cache_clear()

    assert result == {}


# ---------------------------------------------------------------------------
# Additional: get_kind_from_plural tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("plural", "expected_kind"),
    [
        ("pods", "Pod"),
        ("deployments", "Deployment"),
        ("policies", "Policy"),
        ("ingresses", "Ingress"),
        ("statuses", "Status"),
        ("endpoints", "Endpoints"),
        ("configmaps", "Configmap"),
        ("secrets", "Secret"),
        ("nodes", "Node"),
    ],
)
def test_get_kind_from_plural(plural: str, expected_kind: str) -> None:
    result = get_kind_from_plural(plural)
    assert result == expected_kind
