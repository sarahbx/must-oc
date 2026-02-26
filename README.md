# must-oc

`oc`-like CLI for querying OpenShift must-gather directories offline.

## Setup

Run directly with [uv](https://docs.astral.sh/uv/):

```bash
uv run must-oc -d /path/to/must-gather get pods -n openshift-storage
```

## Examples

List all pods across namespaces:

```bash
uv run must-oc -d /path/to/must-gather get pods -A
```

View logs for a specific container:

```bash
uv run must-oc -d /path/to/must-gather logs my-pod -n my-namespace -c my-container
```

## Links

- [Contributing](CONTRIBUTING.md)
- [License](LICENSE)
