# utilities/types.py
from __future__ import annotations

import functools
from pathlib import Path

import yaml


def config_dir() -> Path:
    """Return the path to the config/ directory at the project root."""
    return Path(__file__).parent.parent / "config"


@functools.lru_cache(maxsize=1)
def _load_irregular_plurals(config_path: Path | None = None) -> dict[str, str]:
    """Load config/irregular_plurals.yaml and return a plural -> Kind mapping."""
    if config_path is None:
        config_path = config_dir() / "irregular_plurals.yaml"

    with open(config_path, encoding="utf-8") as fhandle:
        raw = yaml.safe_load(fhandle)

    if raw is None:
        return {}

    return {str(key): str(val) for key, val in raw.items()}


@functools.lru_cache(maxsize=1)
def load_resource_map(config_path: Path | None = None) -> dict[str, tuple[str, str]]:
    """Load config/resource_map.yaml and build an alias -> (api_group, plural) lookup.

    Both the plural name itself AND each alias map to (api_group, plural).
    """
    if config_path is None:
        config_path = config_dir() / "resource_map.yaml"

    with open(config_path, encoding="utf-8") as fhandle:
        raw = yaml.safe_load(fhandle)

    if raw is None:
        return {}

    resource_map: dict[str, tuple[str, str]] = {}

    for plural_name, details in raw.items():
        if not isinstance(details, dict):
            continue
        api_group = details.get("api_group", "")
        entry = (api_group, plural_name)

        # The plural name itself is a valid lookup key.
        resource_map[plural_name] = entry

        # Each alias also maps to the same (api_group, plural) tuple.
        aliases = details.get("aliases", [])
        if aliases is None:
            aliases = []
        for alias in aliases:
            resource_map[str(alias)] = entry

    return resource_map


@functools.lru_cache(maxsize=1)
def load_cluster_scoped(config_path: Path | None = None) -> set[str]:
    """Load config/cluster_scoped.yaml and return a set of plural names."""
    if config_path is None:
        config_path = config_dir() / "cluster_scoped.yaml"

    with open(config_path, encoding="utf-8") as fhandle:
        raw = yaml.safe_load(fhandle)

    if raw is None:
        return set()

    return set(raw)


def resolve_resource_type(
    user_input: str, config_path: Path | None = None
) -> tuple[str, str]:
    """Look up user input in the loaded resource map.

    Returns (api_group, plural_name).
    Raises ValueError if the input does not match any known resource type or alias.
    """
    resource_map = load_resource_map(config_path=config_path)
    lowered = user_input.lower()

    if lowered in resource_map:
        return resource_map[lowered]

    raise ValueError(
        f"Unknown resource type: {user_input!r}. "
        f"Use 'must-oc update-types' to discover resource types from a must-gather directory."
    )


def is_cluster_scoped(plural_name: str, config_path: Path | None = None) -> bool:
    """Check whether a plural resource name is cluster-scoped."""
    cluster_set = load_cluster_scoped(config_path=config_path)
    return plural_name in cluster_set


def get_kind_from_plural(plural_name: str, config_path: Path | None = None) -> str:
    """Convert a plural resource name to its Kubernetes Kind.

    Uses a lookup from config/irregular_plurals.yaml for irregular plurals.
    Falls back to stripping the trailing 's' and capitalizing the first letter
    for unknown types.

    Examples:
        "pods" -> "Pod"
        "deployments" -> "Deployment"
        "policies" -> "Policy"
        "ingresses" -> "Ingress"
        "statuses" -> "Status"
        "endpoints" -> "Endpoints"
    """
    irregular = _load_irregular_plurals(config_path=config_path)

    if plural_name in irregular:
        return irregular[plural_name]

    # Fallback: strip trailing 's', capitalize first letter.
    if plural_name.endswith("s"):
        singular = plural_name[:-1]
    else:
        singular = plural_name

    return singular[0].upper() + singular[1:] if singular else plural_name
