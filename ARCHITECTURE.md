# must-oc: Technical Design & Work Plan

## Cynefin Classification: Complicated Domain

**Sense-Analyze-Respond.** The problem space is well-bounded (parse known directory structures, render known output formats), but the must-gather layout has non-trivial variations across different gather types (OCP, ODF, CNV), dual namespace paths (`namespaces/all/namespaces/` vs `namespaces/<NS>/`), and API group mapping requires expert analysis. Multiple valid design approaches exist; this document selects the simplest one.

---

## Phase 1: Architecture Visualization

### 1.1 System Context Diagram

```
 +------------------------------------------------------------------+
 |                          USER (CLI)                               |
 |  must-oc get pod -n openshift-storage                             |
 |  must-oc describe pod -n openshift-storage rook-ceph-mon-...      |
 |  must-oc logs rook-ceph-mon-... -n openshift-storage -c mon       |
 |  must-oc update-types -d ./must-gather.local.NNN                  |
 +----------------------------------+-------------------------------+
                                    |
                                    v
 +----------------------------------+-------------------------------+
 |                        CLI Entry Point                            |
 |                     must_oc/__main__.py                           |
 |   argparse: {get, describe, logs, update-types} subcommands      |
 |   flags: -n, -A, -l, -c, --must-gather-dir (repeatable)         |
 +----------+----------+-------------------+----------+-------------+
            |          |                   |          |
            v          v                   v          v
 +----------+--+  +----+-------+  +-------+--+  +----+-----------+
 |  oc/get.py  |  | oc/        |  | oc/       |  | oc/           |
 |  - find     |  | describe.py|  | logs.py   |  | update_types  |
 |  - parse    |  | - find     |  | - find    |  |   .py         |
 |  - tabular  |  | - format   |  | - stream  |  | - scan FS     |
 +------+------+  +-----+------+  +-----+-----+  | - additive    |
        |               |               |         |   merge       |
        +---------------+---------------+         +------+--------+
                        |                                |
                        v                                v
 +----------------------+-----------------------------------+-------+
 |                    utilities/ Package (top-level)                 |
 |                                                                   |
 |  +---------------------+  +-------------------+                  |
 |  | utilities/paths.py  |  | utilities/         |                 |
 |  | - discover roots    |  |  yaml_parser.py   |                  |
 |  | - resolve ns dirs   |  | - load_yaml()     |                  |
 |  | - find resource     |  | - load_yaml_list()|                  |
 |  | - find logs         |  | - safe parsing    |                  |
 |  | - validate_path()   |  | - enforce size    |                  |
 |  |   [SEC: V-002]      |  |   limits [V-001]  |                  |
 |  +---------------------+  +-------------------+                  |
 |  +---------------------+  +---------------------+               |
 |  | utilities/labels.py |  | utilities/format.py |               |
 |  | - match_labels()    |  | - tabular_output()  |               |
 |  | - parse -l selector |  | - describe_output() |               |
 |  | - validate input    |  | - redact_sensitive() |              |
 |  |   [SEC: V-004]      |  |   [SEC: V-003]       |              |
 |  +---------------------+  +---------------------+               |
 |  +---------------------+                                         |
 |  | utilities/types.py  |                                         |
 |  | - load RESOURCE_MAP |                                         |
 |  |   from YAML config  |                                         |
 |  | - load CLUSTER_SCPD |                                         |
 |  |   from YAML config  |                                         |
 |  | - resolve aliases   |                                         |
 |  +----------+----------+                                         |
 +-----------  |  --------------------------------------------------+
               v
 +-------------+----------------------------------------------------+
 |              config/ Directory (top-level, YAML data)             |
 |                                                                   |
 |  config/resource_map.yaml                                        |
 |    pods:                                                          |
 |      api_group: core                                              |
 |      aliases: [pod, pods, po]                                     |
 |    deployments:                                                   |
 |      api_group: apps                                              |
 |      aliases: [deployment, deployments, deploy]                   |
 |    ...                                                            |
 |                                                                   |
 |  config/cluster_scoped.yaml                                      |
 |    - nodes                                                        |
 |    - persistentvolumes                                            |
 |    - clusterroles                                                 |
 |    ...                                                            |
 +------------------------------------------------------------------+
               |
               v
 +------------------------------------------------------------------+
 |                   Must-Gather Directory (FS)                      |
 |                                                                   |
 |  must-gather.local.NNNN-type/                                    |
 |   +-- <image-hash>/                                              |
 |       +-- cluster-scoped-resources/                              |
 |       |    +-- <api-group>/<type>/<name>.yaml                    |
 |       +-- namespaces/                                            |
 |       |    +-- <NS>/                                             |
 |       |    |    +-- <api-group>/<type>.yaml      (list)          |
 |       |    |    +-- <api-group>/<type>/<name>.yaml (individual)  |
 |       |    |    +-- pods/<pod>/<ctr>/<ctr>/logs/*.log             |
 |       |    +-- all/namespaces/<NS>/              (alt path)      |
 |       |         +-- <api-group>/pods/<name>.yaml                 |
 |       +-- version                                                |
 +------------------------------------------------------------------+
```

### 1.2 Data Flow

```
 User Input                  Path Resolution               Output
 ============                ===============                ======

 "get pod -n NS"  ------>  1. Discover gather roots
                           2. For each root:
                              a. Glob: namespaces/NS/core/pods/*.yaml
                              b. Glob: namespaces/all/namespaces/NS/core/pods/*.yaml
                              c. Glob: namespaces/NS/core/pods.yaml (list file)
                           2b. [SEC] Validate all paths within root (V-002)
                           3. [SEC] Check file size < 100MB before parsing (V-001)
                           3b. Parse YAML with yaml.safe_load() (V-006)
                           4. [SEC] Validate label selector input (V-004)
                           4b. Apply label filter (-l)
                           5. [SEC] Redact sensitive fields unless --show-secrets (V-003)
                           5b. Format as table  ------>  NAME  READY  STATUS  RESTARTS  AGE

 "describe pod    ------>  1. Same discovery as get
  -n NS name"             2. Find specific pod by name
                           2b. [SEC] Validate path within root (V-002)
                           3. [SEC] Check file size < 100MB (V-001)
                           3b. Load full YAML with yaml.safe_load() (V-006)
                           4. [SEC] Redact sensitive fields unless --show-secrets (V-003)
                           4b. Format key: value  ------>  Name:    pod-name
                              with nested sections        Namespace: NS
                                                          Labels:  ...

 "logs pod-name   ------>  1. Discover gather roots
  -n NS -c ctr"           2. Glob: namespaces/NS/pods/<name>/<ctr>/<ctr>/logs/current.log
                           2b. [SEC] Validate path within root (V-002)
                           3. [SEC] Stream file line-by-line, not bulk load (V-005)
                           4. Print to stdout  ------>  <raw log text>

 "update-types    ------>  1. Discover gather roots
  -d ./mg-dir"             2. Walk namespaces/*/<api-group>/<type>/ dirs
                           3. Walk cluster-scoped-resources/<api-group>/<type>/ dirs
                           4. Read existing config YAMLs
                           5. Additive merge only (never removes)
                           6. [SEC] Write with explicit 0o644 permissions (V-007)
                           6b. Write updated config YAMLs ------>  "Added 3 new resource types"
```

### 1.3 Impact Radius

This is a greenfield project. No downstream components to break.

---

## Phase 2: Context & Discovery

### 2.1 Affected Files (New Project Layout)

```
config/
  resource_map.yaml        (resource type -> api_group mapping + aliases)
  cluster_scoped.yaml      (list of cluster-scoped resource type names)
must_oc/
  __init__.py              (empty)
  __main__.py              (CLI entry point, argparse setup)
  oc/
    __init__.py            (empty)
    get.py                 (get command implementation)
    describe.py            (describe command implementation)
    logs.py                (logs command implementation)
    update_types.py        (scan must-gather and update config YAMLs)
utilities/
  __init__.py              (empty)
  paths.py                 (must-gather directory discovery and path resolution)
  yaml_parser.py           (YAML loading, list extraction)
  labels.py                (label selector parsing and matching)
  format.py                (tabular and describe output formatting)
  types.py                 (load config YAMLs, resolve aliases)
tests/
  __init__.py              (empty)
  conftest.py              (shared fixtures: fake must-gather trees)
  must_oc/
    __init__.py            (empty)
    test_get.py
    test_describe.py
    test_logs.py
    test_update_types.py
  utilities/
    __init__.py            (empty)
    test_paths.py
    test_yaml_parser.py
    test_labels.py
    test_format.py
    test_types.py
  config/
    __init__.py            (empty)
    test_config_files.py   (validate config YAML structure and content)
pyproject.toml             (project metadata, dependencies, tool config)
```

**Total: 12 source files, 11 test files, 1 conftest, 2 config YAMLs, 1 pyproject.toml = 27 files.**
Every source file targets 100-300 lines (security controls add ~20-50 lines each). Every test file targets 200-400 lines (including security test cases).

### 2.2 Dependencies

| Dependency | Purpose | Type |
|---|---|---|
| `PyYAML` | Parse YAML resource files and config | Runtime |
| `pytest` | Test framework | Dev |
| `pytest-cov` | Coverage reporting | Dev |
| `mypy` | Type checking | Dev |

No other external dependencies. All path operations use `pathlib.Path`. CLI uses `argparse` (stdlib).

### 2.3 Must-Gather Directory Structure (Discovered from Real Data)

**Critical finding:** Must-gather directories have **two distinct namespace patterns**, both must be scanned:

**Pattern A -- Direct namespace path** (used for logs and operator-specific resources):
```
<root>/namespaces/<NS>/pods/<pod>/<container>/<container>/logs/current.log
<root>/namespaces/<NS>/<api-group>/<type>/<name>.yaml
```

**Pattern B -- All-namespaces aggregated path** (used for pod YAMLs across all namespaces):
```
<root>/namespaces/all/namespaces/<NS>/core/pods/<name>.yaml
<root>/namespaces/all/namespaces/<NS>/<api-group>/<type>/<name>.yaml
```

The `<root>` is: `must-gather.local.NNNN-type/<image-hash-subdirectory>/`

Some must-gathers also have nested sub-roots (e.g., ODF has a `ceph/namespaces/` path inside the image hash directory).

### 2.4 Configuration File Formats

#### `config/resource_map.yaml`

```yaml
# resource_map.yaml
# Maps resource plural names to API groups and user-facing aliases.
# Updated by: must-oc update-types -d <must-gather-dir>
# Manual edits are safe -- update-types only adds, never removes.

pods:
  api_group: core
  aliases:
    - pod
    - po

services:
  api_group: core
  aliases:
    - service
    - svc

configmaps:
  api_group: core
  aliases:
    - configmap
    - cm

secrets:
  api_group: core
  aliases:
    - secret

serviceaccounts:
  api_group: core
  aliases:
    - serviceaccount
    - sa

persistentvolumeclaims:
  api_group: core
  aliases:
    - persistentvolumeclaim
    - pvc

events:
  api_group: core
  aliases:
    - event
    - ev

nodes:
  api_group: core
  aliases:
    - node
    - "no"

namespaces:
  api_group: core
  aliases:
    - namespace
    - ns

persistentvolumes:
  api_group: core
  aliases:
    - persistentvolume
    - pv

replicationcontrollers:
  api_group: core
  aliases:
    - replicationcontroller
    - rc

endpoints:
  api_group: core
  aliases:
    - ep

deployments:
  api_group: apps
  aliases:
    - deployment
    - deploy

replicasets:
  api_group: apps
  aliases:
    - replicaset
    - rs

statefulsets:
  api_group: apps
  aliases:
    - statefulset
    - sts

daemonsets:
  api_group: apps
  aliases:
    - daemonset
    - ds

jobs:
  api_group: batch
  aliases:
    - job

cronjobs:
  api_group: batch
  aliases:
    - cronjob
    - cj

ingresses:
  api_group: networking.k8s.io
  aliases:
    - ingress
    - ing

networkpolicies:
  api_group: networking.k8s.io
  aliases:
    - networkpolicy
    - netpol

roles:
  api_group: rbac.authorization.k8s.io
  aliases:
    - role

rolebindings:
  api_group: rbac.authorization.k8s.io
  aliases:
    - rolebinding

clusterroles:
  api_group: rbac.authorization.k8s.io
  aliases:
    - clusterrole

clusterrolebindings:
  api_group: rbac.authorization.k8s.io
  aliases:
    - clusterrolebinding

routes:
  api_group: route.openshift.io
  aliases:
    - route

horizontalpodautoscalers:
  api_group: autoscaling
  aliases:
    - horizontalpodautoscaler
    - hpa

poddisruptionbudgets:
  api_group: policy
  aliases:
    - poddisruptionbudget
    - pdb

endpointslices:
  api_group: discovery.k8s.io
  aliases:
    - endpointslice

servicemonitors:
  api_group: monitoring.coreos.com
  aliases:
    - servicemonitor

prometheusrules:
  api_group: monitoring.coreos.com
  aliases:
    - prometheusrule
```

#### `config/cluster_scoped.yaml`

```yaml
# cluster_scoped.yaml
# Resource types found under cluster-scoped-resources/ rather than namespaces/.
# Updated by: must-oc update-types -d <must-gather-dir>
# Manual edits are safe -- update-types only adds, never removes.

- nodes
- persistentvolumes
- clusterroles
- clusterrolebindings
- namespaces
- securitycontextconstraints
- volumesnapshotcontents
- volumesnapshotclasses
- storageclasses
- customresourcedefinitions
```

### 2.5 Unknowns

1. **Aggregated list files**: Some directories have `<type>.yaml` files containing `*List` kinds (e.g., `DeploymentList`). We should support both individual files and list files.
2. **Previous logs**: Log directories may contain `current.log`, `previous.log`, and `previous.insecure.log`. Start with `current.log` only; add `--previous` flag in a later iteration.
3. **Cluster-scoped resources**: Nodes, PVs, ClusterRoles exist under `cluster-scoped-resources/`. Defer to Phase 2 -- `get` initially targets namespaced resources only, with cluster-scoped as a stretch goal.

---

## Phase 3: Implementation Strategy

### 3.1 Pattern Selection

**Strategy Pattern** for command dispatch -- each subcommand (`get`, `describe`, `logs`, `update-types`) is an independent module with a single entry function. The CLI dispatcher calls the appropriate module.

**No OOP hierarchy needed.** Each command module exports a `run()` function. KISS.

### 3.2 Resource Type to API Group Mapping

The key design challenge is: when the user types `get pod`, how do we know to look in `core/pods/`? And for `get deployment`, look in `apps/deployments/`?

**Strategy: External YAML config files loaded at runtime, updatable via `update-types` command.**

#### How `utilities/types.py` loads the configs:

```python
# utilities/types.py (pseudocode)
def _config_dir() -> Path:
    """Return path to the config/ directory at project root."""
    return Path(__file__).parent.parent / "config"

def load_resource_map() -> dict[str, tuple[str, str]]:
    """Load resource_map.yaml, build alias -> (api_group, plural) lookup."""
    config_path = _config_dir() / "resource_map.yaml"
    raw = yaml.safe_load(config_path.read_text())
    result: dict[str, tuple[str, str]] = {}
    for plural, entry in raw.items():
        api_group = entry["api_group"]
        result[plural] = (api_group, plural)
        for alias in entry.get("aliases", []):
            result[alias] = (api_group, plural)
    return result

def load_cluster_scoped() -> set[str]:
    """Load cluster_scoped.yaml, return set of plural names."""
    config_path = _config_dir() / "cluster_scoped.yaml"
    return set(yaml.safe_load(config_path.read_text()) or [])
```

#### How `update-types` scans and merges:

The `update-types` subcommand walks the must-gather filesystem to discover resource types that are not yet in the config files, then **adds them without removing any existing entries**.

```
Algorithm:
1. Walk: <root>/namespaces/*/  -- skip "all" directory
   For each: namespaces/<NS>/<api_group>/<type_dir>/
     Record: (api_group, type_dir) as namespaced resource
2. Walk: <root>/cluster-scoped-resources/
   For each: cluster-scoped-resources/<api_group>/<type_dir>/
     Record: (api_group, type_dir) as cluster-scoped resource
3. Walk: <root>/namespaces/all/namespaces/*/
   For each: namespaces/all/namespaces/<NS>/<api_group>/<type_dir>/
     Record: (api_group, type_dir) as namespaced resource
4. Load existing resource_map.yaml and cluster_scoped.yaml
5. For each discovered (api_group, type_dir):
   - If type_dir not in resource_map -> add with api_group, empty aliases
   - If type_dir already exists -> do NOT overwrite (existing wins)
6. For each discovered cluster-scoped type_dir:
   - If not in cluster_scoped.yaml -> add to list
7. Write updated files
8. Print summary: "Added N new resource types, M new cluster-scoped types"
```

**Strictly additive**: Never removes entries. Never overwrites `api_group` or `aliases` for existing entries. This lets users hand-edit the config files with custom aliases and never lose them.

### 3.3 Breaking Changes

None. Greenfield project.

### 3.4 Complexity

**Complicated** -- not Complex. The solution space is known; we are mapping filesystem paths to a well-understood `oc` output contract.

---

## Phase 4: Atomic Execution Steps

### Step 1: Project scaffolding and pyproject.toml

Create `pyproject.toml` with project metadata, dependencies, tool config (mypy, pytest, flake8). Create empty `__init__.py` files for `must_oc/`, `must_oc/oc/`, `utilities/`, `tests/`, `tests/must_oc/`, `tests/utilities/`, `tests/config/`. Create `config/` directory.

**Verify:** `uv run python -c "import must_oc"` succeeds.

### Step 2: `config/resource_map.yaml` and `config/cluster_scoped.yaml`

Write the initial configuration files with the known resource types listed in the config format above. These ship as part of the project and are located via `Path(__file__).parent.parent / "config"` from utilities, or project root-relative from anywhere.

**Verify:** Files are valid YAML. `uv run python -c "import yaml; yaml.safe_load(open('config/resource_map.yaml'))"` succeeds.

### Step 3: `utilities/types.py` -- Resource type mapping (loads from YAML)

Implement:
- `load_resource_map() -> dict[str, tuple[str, str]]` -- Loads `config/resource_map.yaml`, builds `alias -> (api_group, plural)` lookup dict.
- `load_cluster_scoped() -> set[str]` -- Loads `config/cluster_scoped.yaml`, returns set of plural names.
- `resolve_resource_type(user_input: str) -> tuple[str, str]` -- Uses loaded map, returns `(api_group, plural_name)` or raises `ValueError`.
- `is_cluster_scoped(plural_name: str) -> bool` -- Checks against loaded set.
- `get_kind_from_plural(plural_name: str) -> str` -- e.g., `"pods"` -> `"Pod"`. Uses a lookup dict for irregular plurals (e.g., `"policies"` -> `"Policy"`, `"ingresses"` -> `"Ingress"`, `"statuses"` -> `"Status"`). Falls back to simple heuristic (strip trailing 's', capitalize) for unknown types.

**Verify:** `uv run pytest tests/utilities/test_types.py -v` -- all pass.

### Step 4: `utilities/paths.py` -- Must-gather directory discovery

Implement:
- `validate_path(path: Path, root: Path) -> Path` -- **[SEC V-002]** Resolves symlinks with `Path.resolve()` and verifies the resolved path is still within the must-gather root directory. Raises `ValueError` if path escapes root. Called on every file path before reading.
- `discover_roots(directories: list[Path]) -> list[Path]` -- Given user-supplied must-gather dirs, find all `<image-hash>/` subdirectories that contain `namespaces/` or `cluster-scoped-resources/`. Also check for nested roots (e.g., ODF `ceph/` sub-root). All discovered paths validated with `validate_path()`.
- `find_namespace_dirs(roots: list[Path], namespace: str | None, all_namespaces: bool) -> list[tuple[Path, str]]` -- Returns `(path_to_ns_dir, namespace_name)` pairs. All paths validated.
- `find_resource_files(roots: list[Path], namespace: str | None, all_namespaces: bool, api_group: str, plural: str, name: str | None) -> list[Path]` -- Returns paths to YAML files matching the query. All returned paths validated with `validate_path()`.
- `find_log_files(roots: list[Path], namespace: str, pod_name: str, container: str | None) -> list[Path]` -- Returns paths to log files. All returned paths validated with `validate_path()`.

**Security constraint [V-002]:** Every file path returned by any function in this module MUST pass through `validate_path()` to prevent symlink-based path traversal attacks. The validation logic:
```python
def validate_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"Path escapes must-gather root: {path}")
    return resolved
```

**Key logic for `find_resource_files`:**
```
For each root:
  # Pattern A: Direct path (scanned FIRST, takes precedence)
  namespaces/<NS>/<api_group>/<plural>/<name>.yaml
  namespaces/<NS>/<api_group>/<plural>.yaml  (list file)

  # Pattern B: All-namespaces aggregated (scanned second, supplements)
  namespaces/all/namespaces/<NS>/<api_group>/<plural>/<name>.yaml

  # Cluster-scoped
  cluster-scoped-resources/<api_group>/<plural>/<name>.yaml
```

**Deduplication and ordering rules (Pre-Flight Review clarification):**
- Deduplication key: `(namespace, kind, name)` tuple.
- Within a single root, Pattern A takes precedence over Pattern B for the same resource.
- Across multiple roots (multiple `-d` directories), first root wins (roots ordered by directory name, deterministic).
- For single-resource queries with an explicit `name` argument, search short-circuits after first match.
- Performance target: sub-second for single-resource queries, <5s for `get -A` on 100-namespace must-gather.

**Verify:** `uv run pytest tests/utilities/test_paths.py -v` -- all pass.

### Step 5: `utilities/yaml_parser.py` -- YAML loading

Implement:
- `MAX_YAML_SIZE = 100 * 1024 * 1024` -- **[SEC V-001]** Constant: 100MB maximum file size for YAML parsing.
- `check_file_size(path: Path) -> None` -- **[SEC V-001]** Raises `ValueError` if file exceeds `MAX_YAML_SIZE`. Called before every YAML load.
- `load_resource(path: Path) -> dict[str, Any]` -- Check file size first, then load a single YAML document using **`yaml.safe_load()` exclusively** (**[SEC V-006]** -- never `yaml.load()`, never `yaml.unsafe_load()`). Handle `---` prefix.
- `load_resource_list(path: Path) -> list[dict[str, Any]]` -- Check file size first. If file contains a `*List` kind, return the `items`. Otherwise return `[resource]`. Uses `yaml.safe_load()`.
- `extract_metadata(resource: dict[str, Any]) -> dict[str, Any]` -- Pull out `name`, `namespace`, `labels`, `creationTimestamp`, `kind`, `apiVersion`.

**Security constraints:**
- **[V-001]** Every `load_resource()` and `load_resource_list()` call MUST check `path.stat().st_size` against `MAX_YAML_SIZE` before reading.
- **[V-006]** The string `yaml.load(` (without `safe_`) MUST NOT appear anywhere in the codebase. Add a test that greps source files to verify.

**Verify:** `uv run pytest tests/utilities/test_yaml_parser.py -v` -- all pass.

### Step 6: `utilities/labels.py` -- Label selector matching

Implement:
- `MAX_SELECTOR_TERMS = 20` -- **[SEC V-004]** Maximum number of terms in a label selector.
- `SELECTOR_TERM_PATTERN = re.compile(r'^[a-zA-Z0-9_./-]+(=|==|!=)[a-zA-Z0-9_./-]*$')` -- **[SEC V-004]** Strict regex for validating individual selector terms. Only allows alphanumeric characters, dots, hyphens, underscores, and forward slashes (for Kubernetes label key domains).
- `validate_selector(selector_str: str) -> None` -- **[SEC V-004]** Validates the entire selector string: splits on commas, checks each term matches `SELECTOR_TERM_PATTERN`, enforces `MAX_SELECTOR_TERMS`. Raises `ValueError` with a clear message on invalid input.
- `parse_selector(selector_str: str) -> list[tuple[str, str, str]]` -- Calls `validate_selector()` first. Parse `key=value,key2=value2` into `[(key, op, value), ...]`. Support `=`, `==`, `!=` operators.
- `matches_selector(labels: dict[str, str], selector: list[tuple[str, str, str]]) -> bool` -- Returns True if all selector terms match.

**Security constraint [V-004]:** `parse_selector()` MUST call `validate_selector()` before parsing. No regex-based parsing on unvalidated input. Empty selectors return an empty list (match everything).

**Verify:** `uv run pytest tests/utilities/test_labels.py -v` -- all pass.

### Step 7: `utilities/format.py` -- Output formatting

Implement:
- `SENSITIVE_RESOURCE_KINDS = {"Secret"}` -- **[SEC V-003]** Resource kinds whose `data` field is redacted by default.
- `SENSITIVE_KEY_PATTERNS = {"password", "token", "secret", "api_key", "apikey", "private_key", "ssh_key", "certificate", "credentials"}` -- **[SEC V-003]** Substrings in field names that trigger redaction.
- `redact_sensitive_fields(resource: dict[str, Any], show_secrets: bool) -> dict[str, Any]` -- **[SEC V-003]** Returns a deep copy of the resource with sensitive fields replaced by `"<REDACTED>"`. If `show_secrets=True`, returns the resource unmodified. Logic:
  - If `resource["kind"] == "Secret"`: redact all values in `resource["data"]` and `resource["stringData"]`.
  - For any resource: walk all nested dicts; if a key (lowercased) contains any string from `SENSITIVE_KEY_PATTERNS`, replace its value with `"<REDACTED>"`.
  - Redact `metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]` as it may contain inline secrets.
- `format_table(headers: list[str], rows: list[list[str]]) -> str` -- Column-aligned tabular output, matching `oc get` style. Auto-size columns based on content width.
- `format_describe(resource: dict[str, Any], show_secrets: bool) -> str` -- Calls `redact_sensitive_fields()` first. Key-value output matching `oc describe` style. Handles nested dicts and lists with indentation.
- `format_age(timestamp_str: str) -> str` -- Convert ISO timestamp to relative age string (`5d`, `3h`, `2m`).

**`get` table output format** (matching real `oc get pod`):
```
NAME                              READY   STATUS    RESTARTS   AGE
rook-ceph-mon-h-864f674875-44wbp  3/3     Running   0          37d
ocs-operator-87bd7899d-7rlrk      1/1     Running   0          37d
```

**`describe` output format** (matching real `oc describe pod`):
```
Name:         rook-ceph-mon-h-864f674875-44wbp
Namespace:    openshift-storage
Priority:     0
Node:         worker-1
Start Time:   Mon, 19 Jan 2026 22:38:37 +0000
Labels:       app=rook-ceph-mon
              mon=h
Annotations:  k8s.ovn.org/pod-networks: ...
Status:       Running
IP:           10.129.0.83
Containers:
  mon:
    Image:    registry.redhat.io/...
    Port:     <none>
    State:    Running
      Started: Mon, 19 Jan 2026 22:39:00 +0000
```

**Verify:** `uv run pytest tests/utilities/test_format.py -v` -- all pass.

### Step 8: `must_oc/oc/get.py` -- Get command

Implement:
- `run_get(args: argparse.Namespace) -> None` -- Orchestrates: resolve type -> find files (V-002 validated) -> check size (V-001) -> parse with safe_load (V-006) -> validate selectors (V-004) -> filter labels -> redact if Secret (V-003) -> format table -> print.
- Extract pod-specific columns (READY, STATUS, RESTARTS) from pod spec/status.
- For non-pod resources, show generic columns: NAME, AGE (and NAMESPACE if `-A`).
- **[SEC V-003]** Pass `args.show_secrets` through to formatting. For `get secret`, data column values show `<REDACTED>` unless `--show-secrets`.

**Verify:** `uv run pytest tests/must_oc/test_get.py -v` -- all pass.

### Step 9: `must_oc/oc/describe.py` -- Describe command

Implement:
- `run_describe(args: argparse.Namespace) -> None` -- Find the specific resource YAML (V-002 validated), check size (V-001), load with safe_load (V-006), call `redact_sensitive_fields()` (V-003), format as describe output, print.
- Requires a resource name argument.
- Shows all YAML fields in human-readable format.
- **[SEC V-003]** Passes `args.show_secrets` to `format_describe()` which calls `redact_sensitive_fields()`. Sensitive fields show `<REDACTED>` by default.

**Verify:** `uv run pytest tests/must_oc/test_describe.py -v` -- all pass.

### Step 10: `must_oc/oc/logs.py` -- Logs command

Implement:
- `MAX_LOG_SIZE = 100 * 1024 * 1024` -- **[SEC V-005]** Maximum log file size to read (100MB). Larger files are truncated with a warning.
- `stream_log(log_path: Path, max_bytes: int = MAX_LOG_SIZE) -> None` -- **[SEC V-005]** Streams the log file line-by-line to stdout without loading the entire file into memory. Tracks bytes read and stops at `max_bytes` with a truncation notice: `\n[Truncated: log exceeds {max_bytes} bytes. Use --tail or view the file directly.]`
- `run_logs(args: argparse.Namespace) -> None` -- Find log files for the given pod/container, call `stream_log()` to output.
- Requires pod name and namespace.
- If `-c container` is given, show only that container's logs. If not given:
  - If pod has exactly one container, show it.
  - If pod has multiple containers, print error and exit with code 1:
    ```
    Error: pod "my-pod" has multiple containers. Use -c to specify one of: [container-a, container-b]
    ```
- Reads `current.log` by default. Reads `previous.log` if `--previous` is given.
- **[SEC V-002]** All log paths validated via `validate_path()` before reading.

**Log path resolution:**
```
namespaces/<NS>/pods/<POD>/<CONTAINER>/<CONTAINER>/logs/current.log
```

Note the doubled `<CONTAINER>/<CONTAINER>` in the real path structure.

**Verify:** `uv run pytest tests/must_oc/test_logs.py -v` -- all pass.

### Step 11: `must_oc/oc/update_types.py` -- Update types command

Implement:
- `run_update_types(args: argparse.Namespace) -> None` -- Scan must-gather directories, discover resource types and API groups from the filesystem, perform strictly additive merge into `config/resource_map.yaml` and `config/cluster_scoped.yaml`.
- `scan_resource_types(roots: list[Path]) -> dict[str, str]` -- Walk the directory tree, return `{plural_name: api_group}` for all discovered types.
- `scan_cluster_scoped(roots: list[Path]) -> set[str]` -- Walk `cluster-scoped-resources/`, return set of plural names.
- `merge_resource_map(existing: dict, discovered: dict[str, str]) -> tuple[dict, int]` -- Additive merge. Returns updated map and count of new entries.
- `merge_cluster_scoped(existing: list[str], discovered: set[str]) -> tuple[list[str], int]` -- Additive merge. Returns updated list and count of new entries.

**Strictly additive rules:**
- New `plural_name` not in existing map: add with discovered `api_group` and empty `aliases` list.
- `plural_name` already in existing map: **skip entirely** -- do not update `api_group` or `aliases`.
  - **Exception:** If discovered `api_group` differs from existing, emit a warning to stderr: `Warning: '{plural}' API group mismatch. Existing: {existing_group}, Discovered: {discovered_group}. Keeping existing.`
- New cluster-scoped type not in existing list: append.
- Existing cluster-scoped type: skip.
- Output: print summary of what was added.

**Security constraint [V-007]:** Config files MUST be written with explicit `0o644` permissions (`rw-r--r--`). Use `path.chmod(0o644)` after writing. Write to a temporary file first, then atomically rename to prevent partial writes:
```python
def write_config_safe(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(content)
    tmp_path.chmod(0o644)
    tmp_path.rename(path)
```

**Verify:** `uv run pytest tests/must_oc/test_update_types.py -v` -- all pass.

### Step 12: `must_oc/__main__.py` -- CLI entry point

Implement:
- argparse with subcommands: `get`, `describe`, `logs`, `update-types`
- Global flags:
  - `--must-gather-dir` / `-d` (repeatable, defaults to scanning current directory)
  - `--show-secrets` -- **[SEC V-003]** Disable sensitive data redaction. Default: False (secrets are redacted).
  - `--debug` -- **[SEC I-002]** Enable full tracebacks on errors. Default: False (sanitized error messages).
- `get` flags: `-n namespace`, `-A` (all namespaces), `-l label-selector`, `resource_type`, `[name]`
- `describe` flags: `-n namespace`, `resource_type`, `name`
- `logs` flags: `-n namespace`, `-c container`, `pod_name`, `--previous`
- `update-types` flags: `-d` (required, repeatable)
- Dispatch to appropriate `run_*` function.
- **[SEC I-002]** Top-level exception handler:
  ```python
  try:
      run_command(args)
  except Exception as err:
      if args.debug:
          raise
      print(f"Error: {err}", file=sys.stderr)
      sys.exit(1)
  ```

**Verify:** `uv run python -m must_oc get pod -n openshift-storage -d ./must-gather.local.5699449927839406698-odf` prints a table.

### Step 13: `tests/conftest.py` -- Shared test fixtures

Create pytest fixtures that build minimal fake must-gather directory trees in `tmp_path`. Fixtures are **programmatic** (built in Python, not static files).

**Fixture directory structure (Pre-Flight Review clarification):**
```
<tmp_path>/must-gather.local.test-ocp/
  fake-image-hash-abc123/
    version                                       # file: "4.16.0"
    namespaces/
      test-ns/
        test-ns.yaml                              # Namespace YAML
        core/
          pods.yaml                               # PodList (aggregated)
          pods/
            test-pod-1/
              test-pod-1.yaml                     # Individual pod YAML
              container-a/
                container-a/
                  logs/
                    current.log                   # Container log
                    previous.log                  # Previous log
            test-pod-2/
              test-pod-2.yaml                     # Multi-container pod
              container-x/
                container-x/
                  logs/
                    current.log
              container-y/
                container-y/
                  logs/
                    current.log
          secrets/
            test-secret.yaml                      # Secret with data (V-003)
          configmaps/
            test-cm.yaml
        apps/
          deployments/
            test-deploy.yaml
      test-ns-2/                                  # Second namespace for -A testing
        core/
          pods/
            test-pod-3/
              test-pod-3.yaml
    namespaces/all/namespaces/                    # Pattern B (duplicate)
      test-ns/
        core/
          pods/
            test-pod-1.yaml                       # Same pod, Pattern B path
    cluster-scoped-resources/
      core/
        nodes/
          test-node-1.yaml
```

**Required fixture variants:**
- `fake_must_gather(tmp_path)` -- Single must-gather with the structure above.
- `fake_must_gather_multi(tmp_path)` -- Two must-gather directories (simulates OCP + ODF).
- `fake_must_gather_with_symlink(tmp_path)` -- **[SEC V-002]** Includes a symlink `malicious.yaml -> /etc/hostname` for path traversal testing.
- `fake_pod_yaml(name, namespace, labels, containers)` -- Returns minimal pod YAML string.
- `fake_deployment_yaml(name, namespace)` -- Returns minimal deployment YAML string.
- `fake_secret_yaml(name, namespace, data)` -- **[SEC V-003]** Returns Secret YAML with base64 data for redaction testing.

### Step 14: `tests/config/test_config_files.py` -- Config validation tests

Validate that the shipped config files:
- Are valid YAML
- Have the correct structure (`api_group` key, `aliases` list)
- All aliases are strings
- `cluster_scoped.yaml` is a list of strings
- No duplicate aliases across different resource types

**Verify:** `uv run pytest tests/config/test_config_files.py -v` -- all pass.

### Step 15: Integration smoke test

Verify end-to-end against the real must-gather directories included in the repo.

**Integration Smoke Test Scenarios (Pre-Flight Review clarification):**

| # | Command | Expected Exit Code | Output Validation |
|---|---------|-------------------|-------------------|
| 1 | `get pod -n openshift-multus -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output contains >=1 pod name, table has NAME/READY/STATUS columns |
| 2 | `get pod -A -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output contains NAMESPACE column, >=5 pods |
| 3 | `get deployment -n openshift-catalogd -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output contains "catalogd-controller-manager" |
| 4 | `describe pod -n openshift-etcd-operator etcd-operator-6b5dfb6c9b-5f928 -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output contains "Name:", "Namespace:", "Labels:" |
| 5 | `logs etcd-operator-6b5dfb6c9b-5f928 -n openshift-etcd-operator -c etcd-operator -d ./must-gather.local.7602412240244067422-ocp` | 0 | Non-empty output (actual log content) |
| 6 | `get pod -A -d ./must-gather.local.5699449927839406698-odf -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output merges pods from both gathers |
| 7 | `get pod -n nonexistent-ns -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output: "No resources found" |
| 8 | `get secret -n openshift-etcd-operator -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output contains `<REDACTED>` (V-003) |
| 9 | `update-types -d ./must-gather.local.7602412240244067422-ocp` | 0 | Output: "Added N new resource type(s)" |

**Coverage:** `uv run pytest --cov=must_oc --cov=utilities --cov-report=term-missing` shows >= 90% coverage.

---

## Phase 5: Verification

### 5.1 Test Scenarios Per Module

#### `tests/utilities/test_types.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `resolve_resource_type("pod")` returns `("core", "pods")` | Success |
| 2 | `resolve_resource_type("deploy")` returns `("apps", "deployments")` | Success |
| 3 | `resolve_resource_type("nonexistent")` raises `ValueError` | Failure |
| 4 | `is_cluster_scoped("nodes")` returns True | Edge |
| 5 | `is_cluster_scoped("pods")` returns False | Edge |
| 6 | All aliases resolve to correct plural form | Success |
| 7 | Config YAML with missing `aliases` key still loads | Edge |
| 8 | Empty `resource_map.yaml` results in empty map | Edge |

#### `tests/utilities/test_paths.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `discover_roots` finds image-hash subdirectories | Success |
| 2 | `discover_roots` with nonexistent dir raises `FileNotFoundError` | Failure |
| 3 | `find_resource_files` finds pods in both Pattern A and Pattern B | Success |
| 4 | `find_resource_files` with specific name returns only that file | Success |
| 5 | `find_resource_files` returns empty list for missing namespace | Edge |
| 6 | `find_log_files` finds `current.log` in doubled-container path | Success |
| 7 | `find_log_files` with nonexistent container returns empty | Failure |
| 8 | `discover_roots` handles nested roots (ODF `ceph/` subdirectory) | Edge |
| 9 | **[SEC V-002]** `validate_path` rejects symlink pointing outside root | Security |
| 10 | **[SEC V-002]** `validate_path` rejects path with `..` that escapes root | Security |
| 11 | **[SEC V-002]** `validate_path` accepts valid path within root | Security |
| 12 | **[SEC V-002]** `find_resource_files` skips files that fail path validation | Security |

#### `tests/utilities/test_yaml_parser.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `load_resource` parses a standard pod YAML | Success |
| 2 | `load_resource` handles YAML starting with `---` | Success |
| 3 | `load_resource_list` extracts items from a `PodList` | Success |
| 4 | `load_resource` with invalid YAML raises exception | Failure |
| 5 | `extract_metadata` handles missing labels gracefully | Edge |
| 6 | `load_resource_list` with single resource (non-list) returns `[resource]` | Edge |
| 7 | **[SEC V-001]** `load_resource` rejects file exceeding `MAX_YAML_SIZE` | Security |
| 8 | **[SEC V-006]** `yaml.safe_load` prevents Python object deserialization (e.g., `!!python/object/apply:os.system`) | Security |
| 9 | **[SEC V-006]** Grep all source files: `yaml.load(` without `safe_` MUST NOT exist | Security |
| 10 | **[SEC V-001]** `check_file_size` raises on 101MB file, passes on 99MB file | Security |

#### `tests/utilities/test_labels.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `parse_selector("key=value")` parses single term | Success |
| 2 | `parse_selector("k1=v1,k2=v2")` parses multiple terms | Success |
| 3 | `matches_selector` with matching labels returns True | Success |
| 4 | `matches_selector` with non-matching labels returns False | Failure |
| 5 | `parse_selector("key!=value")` parses not-equal | Success |
| 6 | `matches_selector` with empty labels dict | Edge |
| 7 | **[SEC V-004]** `validate_selector` rejects special characters (`$(whoami)`, `;`, `\|`) | Security |
| 8 | **[SEC V-004]** `validate_selector` rejects empty terms (`"key=val,,key2=val2"`) | Security |
| 9 | **[SEC V-004]** `validate_selector` rejects >20 terms | Security |
| 10 | **[SEC V-004]** `validate_selector` accepts Kubernetes domain keys (`app.kubernetes.io/name=foo`) | Security |

#### `tests/utilities/test_format.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `format_table` produces aligned columns | Success |
| 2 | `format_table` with empty rows returns header only | Edge |
| 3 | `format_age` converts timestamp to relative age | Success |
| 4 | `format_describe` renders nested dicts with indentation | Success |
| 5 | `format_describe` handles lists (e.g., containers) | Success |
| 6 | `format_table` handles long values without truncation | Edge |
| 7 | **[SEC V-003]** `redact_sensitive_fields` redacts Secret `data` values | Security |
| 8 | **[SEC V-003]** `redact_sensitive_fields` redacts keys containing "password", "token" | Security |
| 9 | **[SEC V-003]** `redact_sensitive_fields` with `show_secrets=True` returns unmodified | Security |
| 10 | **[SEC V-003]** `redact_sensitive_fields` redacts `last-applied-configuration` annotation | Security |
| 11 | **[SEC V-003]** `format_describe` with `show_secrets=False` shows `<REDACTED>` | Security |

#### `tests/must_oc/test_get.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `get pod -n NS` returns table with correct pods | Success |
| 2 | `get pod -A` returns pods from all namespaces with NS column | Success |
| 3 | `get pod -n NS name` returns single matching pod | Success |
| 4 | `get pod -n NS -l key=value` filters by label | Success |
| 5 | `get pod -n nonexistent` returns "No resources found" | Failure |
| 6 | `get deployment -n NS` returns deployments | Success |
| 7 | Multiple must-gather directories are merged | Edge |
| 8 | **[SEC V-003]** `get secret -n NS` without `--show-secrets` shows `<REDACTED>` | Security |
| 9 | **[SEC V-003]** `get secret -n NS --show-secrets` shows actual values | Security |

#### `tests/must_oc/test_describe.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `describe pod -n NS name` prints full description | Success |
| 2 | `describe pod -n NS nonexistent` prints error | Failure |
| 3 | `describe` without name argument errors | Failure |
| 4 | `describe pod -n NS name` from aggregated list file | Edge |
| 5 | **[SEC V-003]** `describe secret` without `--show-secrets` shows `<REDACTED>` for data fields | Security |
| 6 | **[SEC V-003]** `describe pod` redacts env vars with "password" in key name | Security |

#### `tests/must_oc/test_logs.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `logs pod -n NS` with single container prints logs | Success |
| 2 | `logs pod -n NS -c container` prints specific container logs | Success |
| 3 | `logs pod -n NS` with multiple containers errors with list | Failure |
| 4 | `logs nonexistent -n NS` prints "pod not found" | Failure |
| 5 | `logs pod -n NS -c nonexistent` prints "container not found" | Failure |
| 6 | `logs pod -n NS --previous` reads `previous.log` | Edge |
| 7 | **[SEC V-005]** `stream_log` truncates output at `MAX_LOG_SIZE` with notice | Security |
| 8 | **[SEC V-005]** `stream_log` streams line-by-line without loading full file | Security |
| 9 | **[SEC V-002]** `run_logs` rejects log path that escapes must-gather root | Security |

#### `tests/must_oc/test_update_types.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `scan_resource_types` discovers api_groups from filesystem | Success |
| 2 | `merge_resource_map` adds new types without modifying existing | Success |
| 3 | `merge_resource_map` preserves manually-added aliases | Edge |
| 4 | `merge_cluster_scoped` adds new types to list | Success |
| 5 | `merge_cluster_scoped` does not duplicate existing entries | Edge |
| 6 | `scan_resource_types` handles empty must-gather gracefully | Failure |
| 7 | Full `run_update_types` writes valid YAML back to disk | Integration |
| 8 | `merge_resource_map` with empty existing map adds all discovered | Success |
| 9 | **[SEC V-007]** `write_config_safe` sets 0o644 permissions on written files | Security |
| 10 | **[SEC V-007]** `write_config_safe` atomically writes (tmp file + rename) | Security |

#### `tests/config/test_config_files.py`
| # | Scenario | Type |
|---|---|---|
| 1 | `resource_map.yaml` is valid YAML | Success |
| 2 | Every entry has `api_group` string key | Success |
| 3 | Every entry has `aliases` list (may be empty) | Success |
| 4 | No duplicate aliases across resource types | Edge |
| 5 | `cluster_scoped.yaml` is valid YAML list of strings | Success |
| 6 | All cluster-scoped types exist in `resource_map.yaml` | Edge |

### 5.2 Manual Verification

Run against the real must-gather directories in the repo:

```bash
# Get pods in openshift-storage namespace
uv run python -m must_oc get pod -n openshift-storage \
  -d ./must-gather.local.5699449927839406698-odf

# Get all pods across all namespaces
uv run python -m must_oc get pod -A \
  -d ./must-gather.local.5699449927839406698-odf

# Describe a specific pod
uv run python -m must_oc describe pod -n openshift-storage \
  ocs-operator-87bd7899d-7rlrk \
  -d ./must-gather.local.5699449927839406698-odf

# Get logs for a specific container
uv run python -m must_oc logs rook-ceph-mon-h-864f674875-44wbp \
  -n openshift-storage -c mon \
  -d ./must-gather.local.5699449927839406698-odf

# Multiple must-gather directories
uv run python -m must_oc get pod -A \
  -d ./must-gather.local.5699449927839406698-odf \
  -d ./must-gather.local.7602412240244067422-ocp

# Discover and add new resource types from a must-gather
uv run python -m must_oc update-types \
  -d ./must-gather.local.5699449927839406698-odf

# Verify config was updated
cat config/resource_map.yaml
cat config/cluster_scoped.yaml
```

---

## Appendix A: How Multiple Must-Gather Directories Are Merged

When multiple `-d` flags are provided, or multiple must-gather directories exist:

1. **Discovery**: `discover_roots()` scans each provided directory for image-hash subdirectories.
2. **Aggregation**: All roots are passed to `find_resource_files()` which searches across all of them.
3. **Deduplication**: Resources are deduplicated by `(namespace, kind, name)` tuple. If the same resource appears in multiple gathers, the first one found wins (ordering is by directory name, deterministic).
4. **Output**: Merged results are sorted by name and displayed as a single table.

This matches how you would mentally merge multiple must-gathers during incident investigation.

## Appendix B: Handling the "all/namespaces" Path Variant

Some must-gathers store pod YAMLs in a second location:
```
namespaces/all/namespaces/<NS>/core/pods/<name>.yaml
```

This path is used by certain must-gather plugins (including ODF) to store a copy of all pod definitions alongside the direct namespace path. The tool must scan both locations and deduplicate.

**Implementation**: `find_resource_files()` always checks both patterns. Results are deduplicated by resource name before returning.

## Appendix C: `pyproject.toml` Configuration Plan

```toml
[project]
name = "must-oc"
version = "0.1.0"
description = "oc-like CLI for must-gather directories"
requires-python = ">=3.14"
dependencies = ["pyyaml>=6.0,<7.0"]  # [SEC I-001] Pin major version, audit before upgrading

[project.scripts]
must-oc = "must_oc.__main__:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers -v"

[tool.mypy]
python_version = "3.14"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.coverage.run]
source = ["must_oc", "utilities"]

[tool.coverage.report]
fail_under = 90
show_missing = true

[dependency-groups]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "mypy>=1.11"]
```

## Appendix D: File Line Count Budget

Estimates include security controls (V-001 through V-007, I-001, I-002):

| File | Estimated Lines | Budget | Security Controls |
|---|---|---|---|
| `must_oc/__main__.py` | ~150 | 500 | I-002 (error handler), V-003 (`--show-secrets`), `--debug` |
| `must_oc/oc/get.py` | ~210 | 500 | V-003 (redaction pass-through) |
| `must_oc/oc/describe.py` | ~160 | 500 | V-003 (redaction pass-through) |
| `must_oc/oc/logs.py` | ~130 | 500 | V-005 (`stream_log`), V-002 (path validation) |
| `must_oc/oc/update_types.py` | ~200 | 500 | V-007 (`write_config_safe`) |
| `utilities/paths.py` | ~230 | 500 | V-002 (`validate_path`) |
| `utilities/yaml_parser.py` | ~130 | 500 | V-001 (`check_file_size`), V-006 (`safe_load`) |
| `utilities/labels.py` | ~110 | 500 | V-004 (`validate_selector`, regex, limits) |
| `utilities/format.py` | ~300 | 500 | V-003 (`redact_sensitive_fields`, patterns) |
| `utilities/types.py` | ~100 | 500 | -- |
| `config/resource_map.yaml` | ~180 | N/A | -- |
| `config/cluster_scoped.yaml` | ~15 | N/A | -- |
| `tests/conftest.py` | ~150 | 500 | -- |
| `tests/*/test_*.py` (10 files) | ~300 each | 500 each | Security test cases per module |

All files comfortably within the 500-line limit.

## Appendix E: `update-types` Workflow Detail

```
User runs:
  must-oc update-types -d ./must-gather.local.5699449927839406698-odf

Step 1 - Discover roots:
  Finds: ./must-gather.local.5699449927839406698-odf/registry-redhat-io-.../

Step 2 - Walk filesystem for namespaced resources:
  namespaces/openshift-storage/ceph.rook.io/cephclusters/  -> ("ceph.rook.io", "cephclusters")
  namespaces/openshift-storage/core/pods/                  -> ("core", "pods")  [already known]
  namespaces/all/namespaces/openshift-multus/core/pods/    -> ("core", "pods")  [already known]

Step 3 - Walk filesystem for cluster-scoped resources:
  cluster-scoped-resources/security.openshift.io/securitycontextconstraints/
    -> ("security.openshift.io", "securitycontextconstraints")
  cluster-scoped-resources/core/persistentvolumes/
    -> ("core", "persistentvolumes")  [already known]

Step 4 - Load existing configs:
  resource_map.yaml: {pods: {api_group: core, aliases: [pod, po]}, ...}
  cluster_scoped.yaml: [nodes, persistentvolumes, ...]

Step 5 - Additive merge:
  NEW: cephclusters -> {api_group: ceph.rook.io, aliases: []}
  NEW: securitycontextconstraints -> cluster_scoped list
  SKIP: pods (already exists)
  SKIP: persistentvolumes (already exists)

Step 6 - Write updated configs

Step 7 - Print:
  "Added 1 new resource type(s) to resource_map.yaml"
  "  - cephclusters (ceph.rook.io)"
  "Added 1 new cluster-scoped type(s) to cluster_scoped.yaml"
  "  - securitycontextconstraints"
```

---

## Security Architecture Review

**Review Date:** 2026-02-25 | **Overall Risk Level:** LOW | **Critical/High:** 0 | **Medium:** 3 | **Low:** 4 | **Info:** 2

### Threat Model

`must-oc` is a read-only CLI tool that parses must-gather archives on the local filesystem. Primary threat actors:
1. **Malicious Must-Gather Creator:** Attacker crafts a must-gather archive with symlinks, oversized files, or malicious YAML to exploit the tool.
2. **Accidental Sensitive Data Exposure:** User shares terminal output containing credentials from Kubernetes Secrets.

### Findings and Resolutions

All findings below have been incorporated into the architecture design above. Each finding ID (V-NNN) is referenced inline at every point in the design where the mitigation is applied.

#### V-001: YAML Parsing Resource Exhaustion (Medium) -- RESOLVED

**Risk:** A must-gather with multi-GB YAML files could exhaust memory.
**Resolution:** `utilities/yaml_parser.py` now includes `MAX_YAML_SIZE = 100MB` constant and `check_file_size()` function called before every YAML load operation. Both `load_resource()` and `load_resource_list()` reject files exceeding this limit with a clear error message.
**Tests:** test_yaml_parser.py #7, #10.

#### V-002: Path Traversal via Symbolic Links (Medium) -- RESOLVED

**Risk:** Symlinks in must-gather could point to files outside the must-gather root (e.g., `/etc/passwd`).
**Resolution:** `utilities/paths.py` now includes `validate_path(path, root)` function that resolves all symlinks via `Path.resolve()` and verifies the resolved path remains within the must-gather root via `Path.is_relative_to()`. This function is called on every file path before any read operation across all modules: `find_resource_files()`, `find_log_files()`, and `run_logs()`.
**Tests:** test_paths.py #9, #10, #11, #12; test_logs.py #9.

#### V-003: Sensitive Data Exposure in Output (Medium) -- RESOLVED

**Risk:** Kubernetes Secrets, tokens, passwords, and API keys in must-gather YAML printed verbatim to stdout could be inadvertently shared.
**Resolution:** `utilities/format.py` now includes `redact_sensitive_fields()` function and `SENSITIVE_KEY_PATTERNS` set. By default (`--show-secrets` not passed), all Secret resource `data`/`stringData` fields are replaced with `"<REDACTED>"`. Any field whose key (lowercased) contains patterns like "password", "token", "secret", "api_key", "private_key", "ssh_key", "certificate", "credentials" is also redacted. The `last-applied-configuration` annotation is redacted as it may contain inline secrets. The `--show-secrets` global CLI flag must be explicitly passed to disable redaction.
**Tests:** test_format.py #7, #8, #9, #10, #11.

#### V-004: Label Selector Input Validation (Low) -- RESOLVED

**Risk:** Malformed or adversarial `-l` input (special characters, excessive terms) could cause unexpected behavior.
**Resolution:** `utilities/labels.py` now includes `validate_selector()` function with strict regex validation (`SELECTOR_TERM_PATTERN`), maximum term count (`MAX_SELECTOR_TERMS = 20`), and rejection of empty terms. Only alphanumeric, dots, hyphens, underscores, and forward slashes are allowed in keys/values (matching Kubernetes label syntax). `parse_selector()` calls `validate_selector()` before any parsing.
**Tests:** test_labels.py #7, #8, #9, #10.

#### V-005: Log File Size Limits (Low) -- RESOLVED

**Risk:** Multi-GB log files could exhaust memory if loaded entirely.
**Resolution:** `must_oc/oc/logs.py` now uses `stream_log()` function that reads line-by-line and tracks bytes read. At `MAX_LOG_SIZE = 100MB`, output is truncated with a clear notice directing users to view the file directly. Log files are never loaded into memory as a whole.
**Tests:** test_logs.py #7, #8.

#### V-006: YAML Deserialization Safety (Low) -- RESOLVED

**Risk:** Using `yaml.load()` instead of `yaml.safe_load()` could allow arbitrary Python code execution from malicious YAML.
**Resolution:** The architecture mandates `yaml.safe_load()` exclusively in all YAML parsing. The string `yaml.load(` (without `safe_`) is prohibited in the codebase. A test case greps all `.py` source files to enforce this invariant. The `yaml.safe_load()` function rejects Python-specific YAML tags like `!!python/object/apply:os.system`.
**Tests:** test_yaml_parser.py #8, #9.

#### V-007: Config File Write Permissions (Low) -- RESOLVED

**Risk:** Config files written without explicit permissions could be overly permissive.
**Resolution:** `must_oc/oc/update_types.py` uses `write_config_safe()` function that writes to a temporary file, sets `0o644` permissions, then atomically renames to the target path. This prevents partial writes and ensures consistent permissions.
**Tests:** test_update_types.py #9, #10.

#### I-001: PyYAML Version Pinning (Info) -- RESOLVED

**Risk:** Unpinned major version could pull in breaking changes or reintroduce known CVEs.
**Resolution:** `pyproject.toml` pins `pyyaml>=6.0,<7.0`. The `uv.lock` lockfile pins exact versions.

#### I-002: Verbose Error Messages Leaking Paths (Info) -- RESOLVED

**Risk:** Python tracebacks include full filesystem paths which could leak directory structure in shared output.
**Resolution:** `must_oc/__main__.py` wraps all command dispatch in a try/except. By default, only the error message is printed to stderr (no traceback, no full paths). The `--debug` flag enables full tracebacks for development/troubleshooting.

### Security Testing Checklist

All items below are covered by specific test cases referenced above:

- [x] YAML file size limits enforced (V-001: test_yaml_parser #7, #10)
- [x] `yaml.safe_load()` enforcement via source grep (V-006: test_yaml_parser #8, #9)
- [x] Path traversal prevention for symlinks and `..` (V-002: test_paths #9, #10, #11, #12)
- [x] Sensitive data redaction by default (V-003: test_format #7-#11)
- [x] Label selector validation with strict regex (V-004: test_labels #7-#10)
- [x] Log streaming with truncation (V-005: test_logs #7, #8)
- [x] Config file permissions (V-007: test_update_types #9, #10)
- [x] Error message sanitization (I-002: via `--debug` flag in __main__.py)

### Trust Model & Known Limitations

1. `must-oc` provides defense-in-depth but is fundamentally designed for must-gather archives from trusted sources (e.g., your own clusters or Red Hat support bundles).
2. Kubernetes Secrets are only base64-encoded, not encrypted. `--show-secrets` will decode and display them.
3. The tool runs with the invoking user's permissions and can read any file they can access.
