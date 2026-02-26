# utilities/paths.py
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_path(path: Path, root: Path) -> Path:
    """[SEC V-002] Resolve symlinks and verify the path stays within root.

    Resolves the given path and the root via Path.resolve(), then checks that
    the resolved path is relative to the resolved root.  Raises ValueError if
    the path escapes the must-gather root (e.g. via symlinks or '..' segments).

    Returns the fully resolved path on success.
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"Path escapes must-gather root: {path}")
    return resolved


def _is_gather_root(directory: Path) -> bool:
    """Return True if *directory* looks like a must-gather root.

    A root is a directory that directly contains ``namespaces/`` or
    ``cluster-scoped-resources/``.
    """
    return (directory / "namespaces").is_dir() or (
        directory / "cluster-scoped-resources"
    ).is_dir()


def discover_roots(directories: list[Path]) -> list[Path]:
    """Find all must-gather root directories inside *directories*.

    For each user-supplied directory:
      1. Raise ``FileNotFoundError`` if the directory does not exist.
      2. Iterate over its immediate children (one level deep).
      3. Any child directory that contains ``namespaces/`` or
         ``cluster-scoped-resources/`` is considered a root.
      4. Within each discovered root, check for nested sub-roots
         (e.g. ODF's ``ceph/`` directory that itself has ``namespaces/``).

    All discovered paths are validated via :func:`validate_path`.

    Returns a sorted list of root paths (sorted by directory name for
    deterministic ordering across runs).
    """
    roots: list[Path] = []

    for base_dir in directories:
        if not base_dir.exists():
            raise FileNotFoundError(f"Must-gather directory does not exist: {base_dir}")

        # Check immediate subdirectories (the image-hash level).
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            if _is_gather_root(child):
                validated = validate_path(path=child, root=base_dir)
                roots.append(validated)

                # Check for nested sub-roots (e.g. ceph/ inside the hash dir).
                for nested in sorted(child.iterdir()):
                    if not nested.is_dir():
                        continue
                    if _is_gather_root(nested):
                        validated_nested = validate_path(path=nested, root=base_dir)
                        roots.append(validated_nested)

    return sorted(roots)


def _namespace_dirs_for_root(
    root: Path,
    namespace: str | None,
    all_namespaces: bool,
) -> list[str]:
    """Return a list of namespace names to scan under *root*.

    When *namespace* is given, returns ``[namespace]`` (no filesystem check).
    When *all_namespaces* is True, enumerates the ``namespaces/`` directory
    and returns all namespace subdirectory names (excluding ``all``).
    """
    if namespace is not None:
        return [namespace]

    if all_namespaces:
        ns_base = root / "namespaces"
        if not ns_base.is_dir():
            return []
        return sorted(
            entry.name
            for entry in ns_base.iterdir()
            if entry.is_dir() and entry.name != "all"
        )

    return []


def find_resource_files(
    roots: list[Path],
    namespace: str | None,
    all_namespaces: bool,
    api_group: str,
    plural: str,
    name: str | None,
) -> list[Path]:
    """Return paths to YAML files matching the query.

    Searches the following patterns in order within each root:

    **Namespaced patterns (when namespace is given or all_namespaces):**

    - Pattern A1 (bare, no api_group prefix -- F-002):
      ``namespaces/<NS>/<plural>/<name>/<name>.yaml``

    - Pattern A2 (with api_group):
      ``namespaces/<NS>/<api_group>/<plural>/<name>.yaml``

    - Pattern A3 (list file):
      ``namespaces/<NS>/<api_group>/<plural>.yaml``

    - Pattern B (all-namespaces aggregated):
      ``namespaces/all/namespaces/<NS>/<api_group>/<plural>/<name>.yaml``

    **Cluster-scoped pattern (when namespace is None and not all_namespaces,
    or always as a supplemental scan):**

    - ``cluster-scoped-resources/<api_group>/<plural>/<name>.yaml``

    **Deduplication rules:**
    - Dedup key: resource name (YAML filename stem).
    - Within a single root, Pattern A takes precedence over Pattern B.
    - Across roots, first root wins (roots are sorted).
    - For single-resource queries (explicit *name*), short-circuit on first match.

    All returned paths are validated via :func:`validate_path`.
    """
    seen_names: set[str] = set()
    results: list[Path] = []

    is_namespaced_query = namespace is not None or all_namespaces

    for root in roots:
        if is_namespaced_query:
            ns_names = _namespace_dirs_for_root(
                root=root, namespace=namespace, all_namespaces=all_namespaces
            )
            pattern_a_files = _collect_pattern_a(
                root=root,
                ns_names=ns_names,
                api_group=api_group,
                plural=plural,
                name=name,
            )
            for file_path in pattern_a_files:
                stem = file_path.stem
                if stem in seen_names:
                    continue
                try:
                    validated = validate_path(path=file_path, root=root)
                except ValueError:
                    logger.debug("Skipping path that failed validation: %s", file_path)
                    continue
                seen_names.add(stem)
                results.append(validated)
                if name is not None:
                    return results

            # Pattern B: namespaces/all/namespaces/<NS>/...
            pattern_b_files = _collect_pattern_b(
                root=root,
                ns_names=ns_names,
                api_group=api_group,
                plural=plural,
                name=name,
            )
            for file_path in pattern_b_files:
                stem = file_path.stem
                if stem in seen_names:
                    continue
                try:
                    validated = validate_path(path=file_path, root=root)
                except ValueError:
                    logger.debug("Skipping path that failed validation: %s", file_path)
                    continue
                seen_names.add(stem)
                results.append(validated)
                if name is not None:
                    return results

        # Cluster-scoped resources
        cluster_files = _collect_cluster_scoped(
            root=root, api_group=api_group, plural=plural, name=name
        )
        for file_path in cluster_files:
            stem = file_path.stem
            if stem in seen_names:
                continue
            try:
                validated = validate_path(path=file_path, root=root)
            except ValueError:
                logger.debug("Skipping path that failed validation: %s", file_path)
                continue
            seen_names.add(stem)
            results.append(validated)
            if name is not None:
                return results

    return results


def _collect_pattern_a(
    root: Path,
    ns_names: list[str],
    api_group: str,
    plural: str,
    name: str | None,
) -> list[Path]:
    """Collect files matching Pattern A1 (bare) and Pattern A2 (api_group prefix).

    Pattern A1: namespaces/<NS>/<plural>/<name>/<name>.yaml
    Pattern A2: namespaces/<NS>/<api_group>/<plural>/<name>.yaml
             or namespaces/<NS>/<api_group>/<plural>/<name>/<name>.yaml
    Pattern A3: namespaces/<NS>/<api_group>/<plural>.yaml  (list file, only when name is None)
    """
    found: list[Path] = []
    for ns_name in ns_names:
        # --- Pattern A1: bare (no api_group prefix) ---
        bare_dir = root / "namespaces" / ns_name / plural
        if bare_dir.is_dir():
            if name is not None:
                candidate = bare_dir / name / f"{name}.yaml"
                if candidate.is_file():
                    found.append(candidate)
            else:
                for sub in sorted(bare_dir.iterdir()):
                    if sub.is_dir():
                        yaml_file = sub / f"{sub.name}.yaml"
                        if yaml_file.is_file():
                            found.append(yaml_file)

        # --- Pattern A2: with api_group prefix ---
        api_dir = root / "namespaces" / ns_name / api_group / plural
        if api_dir.is_dir():
            if name is not None:
                # Flat file: <api_group>/<plural>/<name>.yaml
                candidate = api_dir / f"{name}.yaml"
                if candidate.is_file():
                    found.append(candidate)
                else:
                    # Subdirectory: <api_group>/<plural>/<name>/<name>.yaml
                    candidate = api_dir / name / f"{name}.yaml"
                    if candidate.is_file():
                        found.append(candidate)
            else:
                # Flat files directly in the plural directory.
                for yaml_file in sorted(api_dir.glob("*.yaml")):
                    if yaml_file.is_file():
                        found.append(yaml_file)
                # Subdirectory pattern: <plural>/<name>/<name>.yaml
                for sub in sorted(api_dir.iterdir()):
                    if sub.is_dir():
                        yaml_file = sub / f"{sub.name}.yaml"
                        if yaml_file.is_file():
                            found.append(yaml_file)

        # --- Pattern A3: list file (only when listing, not by name) ---
        if name is None:
            list_file = root / "namespaces" / ns_name / api_group / f"{plural}.yaml"
            if list_file.is_file():
                found.append(list_file)

    return found


def _collect_pattern_b(
    root: Path,
    ns_names: list[str],
    api_group: str,
    plural: str,
    name: str | None,
) -> list[Path]:
    """Collect files matching Pattern B.

    Pattern B: namespaces/all/namespaces/<NS>/<api_group>/<plural>/<name>.yaml
    """
    found: list[Path] = []
    for ns_name in ns_names:
        pattern_b_dir = (
            root / "namespaces" / "all" / "namespaces" / ns_name / api_group / plural
        )
        if not pattern_b_dir.is_dir():
            continue
        if name is not None:
            candidate = pattern_b_dir / f"{name}.yaml"
            if candidate.is_file():
                found.append(candidate)
        else:
            for yaml_file in sorted(pattern_b_dir.glob("*.yaml")):
                if yaml_file.is_file():
                    found.append(yaml_file)
    return found


def _collect_cluster_scoped(
    root: Path,
    api_group: str,
    plural: str,
    name: str | None,
) -> list[Path]:
    """Collect files under cluster-scoped-resources/<api_group>/<plural>/.

    Returns individual YAML files matching the query.
    """
    found: list[Path] = []
    csr_dir = root / "cluster-scoped-resources" / api_group / plural
    if not csr_dir.is_dir():
        return found
    if name is not None:
        candidate = csr_dir / f"{name}.yaml"
        if candidate.is_file():
            found.append(candidate)
    else:
        for yaml_file in sorted(csr_dir.glob("*.yaml")):
            if yaml_file.is_file():
                found.append(yaml_file)
    return found


def find_log_files(
    roots: list[Path],
    namespace: str,
    pod_name: str,
    container: str | None,
) -> list[Path]:
    """Return paths to log files for the given pod and optional container.

    Path pattern:
    ``namespaces/<NS>/pods/<POD>/<CONTAINER>/<CONTAINER>/logs/current.log``

    Note the doubled ``<CONTAINER>/<CONTAINER>`` in real must-gather layout.

    When *container* is ``None``, all containers for the pod are returned.
    All returned paths are validated via :func:`validate_path`.
    """
    results: list[Path] = []
    for root in roots:
        pod_dir = root / "namespaces" / namespace / "pods" / pod_name
        if not pod_dir.is_dir():
            continue

        if container is not None:
            log_path = pod_dir / container / container / "logs" / "current.log"
            if log_path.is_file():
                try:
                    validated = validate_path(path=log_path, root=root)
                    results.append(validated)
                except ValueError:
                    logger.debug(
                        "Skipping log path that failed validation: %s", log_path
                    )
        else:
            # Discover all container directories inside the pod directory.
            for container_dir in sorted(pod_dir.iterdir()):
                if not container_dir.is_dir():
                    continue
                # Skip non-container entries (e.g. the pod YAML itself).
                log_path = container_dir / container_dir.name / "logs" / "current.log"
                if log_path.is_file():
                    try:
                        validated = validate_path(path=log_path, root=root)
                        results.append(validated)
                    except ValueError:
                        logger.debug(
                            "Skipping log path that failed validation: %s", log_path
                        )

    return results
