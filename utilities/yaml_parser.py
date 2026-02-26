# utilities/yaml_parser.py
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# [SEC V-001] Maximum file size for YAML parsing: 100MB
MAX_YAML_SIZE: int = 100 * 1024 * 1024


def check_file_size(path: Path) -> None:
    """[SEC V-001] Raise ValueError if file exceeds MAX_YAML_SIZE.

    Called before every YAML load to prevent memory exhaustion from
    excessively large files.
    """
    file_size = path.stat().st_size
    if file_size > MAX_YAML_SIZE:
        raise ValueError(
            f"File {path} is {file_size} bytes, exceeding the maximum allowed size of {MAX_YAML_SIZE} bytes (100MB)"
        )


def load_resource(path: Path) -> dict[str, Any]:
    """Load a single YAML resource from a file.

    [SEC V-001] Checks file size before reading.
    [SEC V-006] Uses yaml.safe_load() exclusively -- never yaml.load().

    Handles files that begin with the YAML document separator '---'.
    """
    check_file_size(path=path)
    content = path.read_text(encoding="utf-8")
    resource = yaml.safe_load(content)
    if resource is None:
        return {}
    if not isinstance(resource, dict):
        raise ValueError(
            f"Expected a YAML mapping in {path}, got {type(resource).__name__}"
        )
    return resource


def load_resource_list(path: Path) -> list[dict[str, Any]]:
    """Load a YAML file and return a list of resources.

    [SEC V-001] Checks file size before reading.
    [SEC V-006] Uses yaml.safe_load() exclusively.

    If the file contains a *List kind (e.g. PodList, DeploymentList),
    return the items from that list. Otherwise return the single resource
    wrapped in a list.
    """
    check_file_size(path=path)
    content = path.read_text(encoding="utf-8")
    resource = yaml.safe_load(content)
    if resource is None:
        return []
    if not isinstance(resource, dict):
        raise ValueError(
            f"Expected a YAML mapping in {path}, got {type(resource).__name__}"
        )
    kind = resource.get("kind", "")
    if isinstance(kind, str) and kind.endswith("List"):
        items = resource.get("items")
        if items is None:
            return []
        if not isinstance(items, list):
            raise ValueError(
                f"Expected 'items' to be a list in {path}, got {type(items).__name__}"
            )
        return items
    return [resource]


def extract_metadata(resource: dict[str, Any]) -> dict[str, Any]:
    """Extract common metadata fields from a Kubernetes resource dict.

    Returns a dict with keys: name, namespace, labels, creationTimestamp,
    kind, apiVersion. Missing fields default to empty string or empty dict
    (for labels).
    """
    metadata = resource.get("metadata", {}) or {}
    return {
        "name": metadata.get("name", ""),
        "namespace": metadata.get("namespace", ""),
        "labels": metadata.get("labels") or {},
        "creationTimestamp": metadata.get("creationTimestamp", ""),
        "kind": resource.get("kind", ""),
        "apiVersion": resource.get("apiVersion", ""),
    }
