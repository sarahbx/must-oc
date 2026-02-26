# must_oc/oc/get.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from utilities.format import format_age, format_table
from utilities.labels import matches_selector, parse_selector
from utilities.paths import discover_roots, find_resource_files
from utilities.types import resolve_resource_type
from utilities.yaml_parser import extract_metadata, load_resource, load_resource_list


def _is_list_file(file_path: Path, plural: str) -> bool:
    """Return True if the file is a list file (e.g. pods.yaml matching plural 'pods')."""
    return file_path.stem == plural


def _load_resources_from_file(file_path: Path, plural: str) -> list[dict[str, Any]]:
    """Load resources from a single file, handling both list and individual files."""
    if _is_list_file(file_path, plural):
        return load_resource_list(path=file_path)
    return [load_resource(path=file_path)]


def _dedup_key(resource: dict[str, Any]) -> tuple[str, str, str]:
    """Return a deduplication key of (namespace, kind, name) for a resource."""
    meta = extract_metadata(resource=resource)
    return (meta["namespace"], meta["kind"], meta["name"])


def _extract_pod_ready(resource: dict[str, Any]) -> str:
    """Extract READY column value (ready_count/total_count) from a Pod resource."""
    status = resource.get("status", {}) or {}
    container_statuses = status.get("containerStatuses", []) or []
    total_count = len(container_statuses)
    ready_count = sum(1 for ctr in container_statuses if ctr.get("ready", False))
    return f"{ready_count}/{total_count}"


def _extract_pod_status(resource: dict[str, Any]) -> str:
    """Extract STATUS column value from a Pod resource."""
    status = resource.get("status", {}) or {}
    return str(status.get("phase", "Unknown"))


def _extract_pod_restarts(resource: dict[str, Any]) -> str:
    """Extract RESTARTS column value (sum of restartCounts) from a Pod resource."""
    status = resource.get("status", {}) or {}
    container_statuses = status.get("containerStatuses", []) or []
    total_restarts = sum(int(ctr.get("restartCount", 0)) for ctr in container_statuses)
    return str(total_restarts)


def _build_pod_row(resource: dict[str, Any], all_namespaces: bool) -> list[str]:
    """Build a table row for a Pod resource."""
    meta = extract_metadata(resource=resource)
    row: list[str] = []
    if all_namespaces:
        row.append(meta["namespace"])
    row.append(meta["name"])
    row.append(_extract_pod_ready(resource))
    row.append(_extract_pod_status(resource))
    row.append(_extract_pod_restarts(resource))
    row.append(format_age(meta["creationTimestamp"]))
    return row


def _build_generic_row(resource: dict[str, Any], all_namespaces: bool) -> list[str]:
    """Build a table row for a non-Pod resource."""
    meta = extract_metadata(resource=resource)
    row: list[str] = []
    if all_namespaces:
        row.append(meta["namespace"])
    row.append(meta["name"])
    row.append(format_age(meta["creationTimestamp"]))
    return row


def run_get(args: argparse.Namespace) -> None:
    """Orchestrate the 'get' command.

    Resolves the resource type, discovers must-gather roots, finds matching
    resource files, loads and filters resources, then prints a formatted table.
    """
    # Step 1: Resolve resource type.
    try:
        api_group, plural = resolve_resource_type(user_input=args.resource_type)
    except ValueError as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)

    # Step 2: Discover must-gather roots.
    try:
        roots = discover_roots(
            directories=[Path(dir_path) for dir_path in args.must_gather_dir]
        )
    except FileNotFoundError as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)

    # Step 3: Find resource files.
    files = find_resource_files(
        roots=roots,
        namespace=args.namespace,
        all_namespaces=args.all_namespaces,
        api_group=api_group,
        plural=plural,
        name=args.name,
    )

    # Step 4: Load resources from files.
    resources: list[dict[str, Any]] = []
    for file_path in files:
        loaded = _load_resources_from_file(file_path=file_path, plural=plural)
        resources.extend(loaded)

    # Step 5: Apply label selector filtering.
    if args.label_selector:
        selector = parse_selector(selector_str=args.label_selector)
        filtered: list[dict[str, Any]] = []
        for resource in resources:
            meta = extract_metadata(resource=resource)
            if matches_selector(meta["labels"], selector):
                filtered.append(resource)
        resources = filtered

    # Step 6: Deduplicate resources by (namespace, kind, name).
    seen_keys: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for resource in resources:
        key = _dedup_key(resource=resource)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(resource)
    resources = deduped

    # Step 7 & 8: Build table and print.
    if not resources:
        if args.namespace:
            print(f"No resources found in namespace {args.namespace}.")
        else:
            print("No resources found.")
        return

    is_pod = plural == "pods"

    if is_pod:
        headers = ["NAME", "READY", "STATUS", "RESTARTS", "AGE"]
        if args.all_namespaces:
            headers = ["NAMESPACE"] + headers
        rows = [_build_pod_row(res, args.all_namespaces) for res in resources]
    else:
        headers = ["NAME", "AGE"]
        if args.all_namespaces:
            headers = ["NAMESPACE"] + headers
        rows = [_build_generic_row(res, args.all_namespaces) for res in resources]

    output = format_table(headers=headers, rows=rows)
    print(output)
