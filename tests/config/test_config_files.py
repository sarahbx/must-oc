# tests/config/test_config_files.py
from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


class TestResourceMapConfig:
    """Tests for config/resource_map.yaml validity."""

    def test_resource_map_loads(self) -> None:
        """resource_map.yaml loads as a valid YAML dict."""
        path = CONFIG_DIR / "resource_map.yaml"
        assert path.exists(), f"Missing {path}"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_resource_map_entries_have_required_keys(self) -> None:
        """Each resource_map.yaml entry has api_group and aliases keys."""
        with open(CONFIG_DIR / "resource_map.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for plural_name, entry in data.items():
            assert isinstance(entry, dict), f"{plural_name}: entry is not a dict"
            assert "api_group" in entry, f"{plural_name}: missing api_group"
            assert "aliases" in entry, f"{plural_name}: missing aliases"
            assert isinstance(entry["aliases"], list), (
                f"{plural_name}: aliases not a list"
            )

    def test_resource_map_contains_core_types(self) -> None:
        """resource_map.yaml includes essential resource types."""
        with open(CONFIG_DIR / "resource_map.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        core_types = ["pods", "services", "configmaps", "secrets", "deployments"]
        for rtype in core_types:
            assert rtype in data, f"Missing core type: {rtype}"

    def test_resource_map_aliases_are_strings(self) -> None:
        """All aliases in resource_map.yaml are strings."""
        with open(CONFIG_DIR / "resource_map.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for plural_name, entry in data.items():
            for alias in entry.get("aliases", []):
                assert isinstance(alias, str), (
                    f"{plural_name}: alias {alias!r} is not a string"
                )


class TestClusterScopedConfig:
    """Tests for config/cluster_scoped.yaml validity."""

    def test_cluster_scoped_loads(self) -> None:
        """cluster_scoped.yaml loads as a valid YAML list."""
        path = CONFIG_DIR / "cluster_scoped.yaml"
        assert path.exists(), f"Missing {path}"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_cluster_scoped_entries_are_strings(self) -> None:
        """All entries in cluster_scoped.yaml are strings."""
        with open(CONFIG_DIR / "cluster_scoped.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for entry in data:
            assert isinstance(entry, str), f"Entry {entry!r} is not a string"

    def test_cluster_scoped_contains_nodes(self) -> None:
        """cluster_scoped.yaml includes 'nodes' as a cluster-scoped type."""
        with open(CONFIG_DIR / "cluster_scoped.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "nodes" in data
