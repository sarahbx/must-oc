# must_oc/oc/update_types.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from utilities.paths import discover_roots
from utilities.types import config_dir


def scan_resource_types(roots: list[Path]) -> dict[str, str]:
    """Walk must-gather roots and discover resource types.

    Scans two directory patterns:

    1. ``<root>/namespaces/<NS>/<api_group>/<type_dir>/``
       (skips the ``all`` namespace directory)
    2. ``<root>/namespaces/all/namespaces/<NS>/<api_group>/<type_dir>/``

    Returns a mapping of ``{plural_name: api_group}`` for all discovered
    resource types.
    """
    discovered: dict[str, str] = {}

    for root in roots:
        ns_base = root / "namespaces"
        if not ns_base.is_dir():
            continue

        # Pattern 1: namespaces/<NS>/<api_group>/<type_dir>/
        for ns_dir in sorted(ns_base.iterdir()):
            if not ns_dir.is_dir() or ns_dir.name == "all":
                continue
            for api_group_dir in sorted(ns_dir.iterdir()):
                if not api_group_dir.is_dir():
                    continue
                api_group = api_group_dir.name
                for type_dir in sorted(api_group_dir.iterdir()):
                    if not type_dir.is_dir():
                        continue
                    plural_name = type_dir.name
                    if plural_name not in discovered:
                        discovered[plural_name] = api_group

        # Pattern 2: namespaces/all/namespaces/<NS>/<api_group>/<type_dir>/
        all_ns_base = ns_base / "all" / "namespaces"
        if all_ns_base.is_dir():
            for ns_dir in sorted(all_ns_base.iterdir()):
                if not ns_dir.is_dir():
                    continue
                for api_group_dir in sorted(ns_dir.iterdir()):
                    if not api_group_dir.is_dir():
                        continue
                    api_group = api_group_dir.name
                    for type_dir in sorted(api_group_dir.iterdir()):
                        if not type_dir.is_dir():
                            continue
                        plural_name = type_dir.name
                        if plural_name not in discovered:
                            discovered[plural_name] = api_group

    return discovered


def scan_cluster_scoped(roots: list[Path]) -> set[str]:
    """Walk ``cluster-scoped-resources/<api_group>/<type_dir>/`` and return plural names.

    Returns a set of plural resource type names found under the
    cluster-scoped-resources directory in any root.
    """
    discovered: set[str] = set()

    for root in roots:
        csr_base = root / "cluster-scoped-resources"
        if not csr_base.is_dir():
            continue
        for api_group_dir in sorted(csr_base.iterdir()):
            if not api_group_dir.is_dir():
                continue
            for type_dir in sorted(api_group_dir.iterdir()):
                if not type_dir.is_dir():
                    continue
                discovered.add(type_dir.name)

    return discovered


def merge_resource_map(
    existing: dict[str, Any],
    discovered: dict[str, str],
) -> tuple[dict[str, Any], int]:
    """Additively merge discovered resource types into an existing resource map.

    For each discovered plural name:
    - If not already in *existing*: add it with the discovered api_group
      and an empty aliases list.
    - If already in *existing*: skip entirely.  If the discovered api_group
      differs from the existing one, emit a warning to stderr.

    Never removes or overwrites existing entries (including manually-added
    aliases).

    Returns a tuple of ``(updated_map, count_of_new_entries)``.
    """
    updated = dict(existing)
    count_new = 0

    for plural_name, api_group in sorted(discovered.items()):
        if plural_name in updated:
            # Check for api_group mismatch.
            existing_group = updated[plural_name].get("api_group", "")
            if existing_group != api_group:
                print(
                    f"Warning: '{plural_name}' API group mismatch. "
                    f"Existing: {existing_group}, Discovered: {api_group}. "
                    f"Keeping existing.",
                    file=sys.stderr,
                )
            continue

        updated[plural_name] = {
            "api_group": api_group,
            "aliases": [],
        }
        count_new += 1

    return updated, count_new


def merge_cluster_scoped(
    existing: list[str],
    discovered: set[str],
) -> tuple[list[str], int]:
    """Additively merge discovered cluster-scoped types into an existing list.

    Appends new types not already present.  Does not duplicate existing
    entries.  Returns a tuple of ``(updated_list, count_of_new_entries)``.
    """
    existing_set = set(existing)
    updated = list(existing)
    count_new = 0

    for plural_name in sorted(discovered):
        if plural_name not in existing_set:
            updated.append(plural_name)
            existing_set.add(plural_name)
            count_new += 1

    return updated, count_new


def write_config_safe(path: Path, content: str) -> None:
    """[SEC V-007] Atomically write *content* to *path* with 0o644 permissions.

    Writes to a temporary file first, sets permissions, then atomically
    renames to the target path.  This prevents partial writes from
    corrupting config files.
    """
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(data=content, encoding="utf-8")
    tmp_path.chmod(mode=0o644)
    tmp_path.rename(target=path)


def _load_existing_resource_map(config_path: Path) -> dict[str, Any]:
    """Load the existing resource_map.yaml as a raw dict.

    Returns an empty dict if the file does not exist or is empty.
    """
    if not config_path.is_file():
        return {}

    with open(config_path, encoding="utf-8") as fhandle:
        raw = yaml.safe_load(fhandle)

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _load_existing_cluster_scoped(config_path: Path) -> list[str]:
    """Load the existing cluster_scoped.yaml as a list of strings.

    Returns an empty list if the file does not exist or is empty.
    """
    if not config_path.is_file():
        return []

    with open(config_path, encoding="utf-8") as fhandle:
        raw = yaml.safe_load(fhandle)

    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def run_update_types(args: argparse.Namespace) -> None:
    """Execute the ``update-types`` subcommand.

    Full workflow:
    1. Discover must-gather roots from the provided directories.
    2. Scan for resource types and cluster-scoped types.
    3. Load existing config files.
    4. Merge discovered types into existing configs (additive only).
    5. Write updated configs back to disk.
    6. Print a summary of changes.

    Expected attributes on *args*:
        - must_gather_dir (list[str]): Must-gather directory paths.
    """
    roots = discover_roots(
        directories=[Path(dir_path) for dir_path in args.must_gather_dir]
    )

    # Scan filesystem for resource types.
    discovered_types = scan_resource_types(roots=roots)
    discovered_cluster = scan_cluster_scoped(roots=roots)

    # Load existing configs.
    cfg_dir = config_dir()
    resource_map_path = cfg_dir / "resource_map.yaml"
    cluster_scoped_path = cfg_dir / "cluster_scoped.yaml"

    existing_map = _load_existing_resource_map(config_path=resource_map_path)
    existing_cluster = _load_existing_cluster_scoped(config_path=cluster_scoped_path)

    # Merge.
    updated_map, map_new_count = merge_resource_map(
        existing=existing_map, discovered=discovered_types
    )
    updated_cluster, cluster_new_count = merge_cluster_scoped(
        existing=existing_cluster, discovered=discovered_cluster
    )

    # Write updated configs.
    resource_map_header = (
        "# resource_map.yaml\n"
        "# Maps resource plural names to API groups and user-facing aliases.\n"
        "# Updated by: must-oc update-types -d <must-gather-dir>\n"
        "# Manual edits are safe -- update-types only adds, never removes.\n\n"
    )
    resource_map_content = resource_map_header + yaml.dump(
        updated_map,
        default_flow_style=False,
        sort_keys=True,
    )
    write_config_safe(path=resource_map_path, content=resource_map_content)

    cluster_scoped_header = (
        "# cluster_scoped.yaml\n"
        "# Resource types found under cluster-scoped-resources/ rather than namespaces/.\n"
        "# Updated by: must-oc update-types -d <must-gather-dir>\n"
        "# Manual edits are safe -- update-types only adds, never removes.\n\n"
    )
    cluster_scoped_content = cluster_scoped_header + yaml.dump(
        updated_cluster,
        default_flow_style=False,
    )
    write_config_safe(path=cluster_scoped_path, content=cluster_scoped_content)

    # Print summary.
    total_new = map_new_count + cluster_new_count
    print(f"Scanned {len(roots)} root(s).")
    print(f"Discovered {len(discovered_types)} namespaced resource type(s).")
    print(f"Discovered {len(discovered_cluster)} cluster-scoped resource type(s).")
    print(f"Added {map_new_count} new resource type(s) to resource_map.yaml.")
    print(
        f"Added {cluster_new_count} new cluster-scoped type(s) to cluster_scoped.yaml."
    )
    if total_new == 0:
        print("No new types discovered -- config files are up to date.")
