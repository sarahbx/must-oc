# must_oc/oc/logs.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utilities.paths import discover_roots, find_log_files, validate_path

# [SEC V-005] Maximum log file size to read (100MB).
# Larger files are truncated with a warning message.
MAX_LOG_SIZE: int = 100 * 1024 * 1024


def stream_log(log_path: Path, max_bytes: int = MAX_LOG_SIZE) -> None:
    """[SEC V-005] Stream a log file line-by-line to stdout.

    Reads the file in text mode, printing each line to stdout without
    loading the entire file into memory.  Tracks bytes read and stops
    at *max_bytes* with a truncation notice.

    Args:
        log_path: Path to the log file.
        max_bytes: Maximum number of bytes to read before truncating.
    """
    bytes_read = 0
    with open(log_path, encoding="utf-8", errors="replace") as fhandle:
        for line in fhandle:
            line_bytes = len(line.encode("utf-8"))
            if bytes_read + line_bytes > max_bytes:
                print(
                    f"\n[Truncated: log exceeds {max_bytes} bytes. "
                    f"Use --tail or view the file directly.]"
                )
                return
            sys.stdout.write(line)
            bytes_read += line_bytes


def _find_pod_dir(roots: list[Path], namespace: str, pod_name: str) -> Path | None:
    """Locate the pod directory under ``namespaces/<NS>/pods/<POD>`` in any root.

    Returns the first matching directory path, or ``None`` if the pod
    directory does not exist in any root.
    """
    for root in roots:
        pod_dir = root / "namespaces" / namespace / "pods" / pod_name
        if pod_dir.is_dir():
            return pod_dir
    return None


def _list_containers(pod_dir: Path) -> list[str]:
    """Return sorted container names found inside a pod directory.

    Container directories contain a doubled subdirectory with a ``logs/``
    folder inside.  Only directories matching this pattern are returned.
    """
    containers: list[str] = []
    for entry in sorted(pod_dir.iterdir()):
        if not entry.is_dir():
            continue
        inner = entry / entry.name / "logs"
        if inner.is_dir():
            containers.append(entry.name)
    return containers


def run_logs(args: argparse.Namespace) -> None:
    """Execute the ``logs`` subcommand.

    Finds and streams log output for a specific pod/container from the
    must-gather directory.

    Expected attributes on *args*:
        - pod_name (str): Pod name.
        - namespace (str): Kubernetes namespace.
        - container (str | None): Container name, or None for auto-detect.
        - must_gather_dir (list[str]): Must-gather directory paths.
        - previous (bool): If True, read ``previous.log`` instead of ``current.log``.
        - show_secrets (bool): Unused for logs, present for CLI compatibility.
    """
    pod_name: str = args.pod_name
    namespace: str = args.namespace
    container: str | None = args.container
    log_filename = "previous.log" if args.previous else "current.log"

    roots = discover_roots(
        directories=[Path(dir_path) for dir_path in args.must_gather_dir]
    )

    if container is not None:
        # Specific container requested -- use find_log_files directly.
        log_files = find_log_files(
            roots=roots, namespace=namespace, pod_name=pod_name, container=container
        )
        if not log_files:
            # Determine whether the pod or the container is missing.
            pod_dir = _find_pod_dir(roots=roots, namespace=namespace, pod_name=pod_name)
            if pod_dir is None:
                print(
                    f'Error: pod "{pod_name}" not found in namespace "{namespace}"',
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f'Error: container "{container}" not found in pod "{pod_name}"',
                file=sys.stderr,
            )
            sys.exit(1)

        # For --previous, swap current.log -> previous.log in the found path.
        log_path = log_files[0].parent / log_filename

        # [SEC V-002] Validate the resolved log path.
        for root in roots:
            try:
                validate_path(path=log_path, root=root)
                break
            except ValueError:
                continue
        else:
            print(
                f"Error: log path escapes must-gather root: {log_path}", file=sys.stderr
            )
            sys.exit(1)

        if not log_path.is_file():
            print(
                f'Error: {log_filename} not found for container "{container}" in pod "{pod_name}"',
                file=sys.stderr,
            )
            sys.exit(1)

        stream_log(log_path=log_path)
        return

    # No container specified -- auto-detect.
    log_files = find_log_files(
        roots=roots, namespace=namespace, pod_name=pod_name, container=None
    )

    if not log_files:
        # Check if pod exists at all.
        pod_dir = _find_pod_dir(roots=roots, namespace=namespace, pod_name=pod_name)
        if pod_dir is None:
            print(
                f'Error: pod "{pod_name}" not found in namespace "{namespace}"',
                file=sys.stderr,
            )
            sys.exit(1)
        # Pod exists but no logs found -- might have containers but no log files.
        available = _list_containers(pod_dir=pod_dir)
        if not available:
            print(f'Error: no log files found for pod "{pod_name}"', file=sys.stderr)
            sys.exit(1)
        if len(available) > 1:
            container_list = ", ".join(available)
            print(
                f'Error: pod "{pod_name}" has multiple containers. Use -c to specify one of: [{container_list}]',
                file=sys.stderr,
            )
            sys.exit(1)
        print(f'Error: no log files found for pod "{pod_name}"', file=sys.stderr)
        sys.exit(1)

    # Multiple log files means multiple containers.
    if len(log_files) > 1:
        # List available containers from the found log paths.
        # Path pattern: .../pods/<pod>/<container>/<container>/logs/current.log
        # Container name is at parts[-4] (the first of the doubled container dirs).
        available = sorted(
            {log_file.parent.parent.parent.name for log_file in log_files}
        )
        container_list = ", ".join(available)
        print(
            f'Error: pod "{pod_name}" has multiple containers. Use -c to specify one of: [{container_list}]',
            file=sys.stderr,
        )
        sys.exit(1)

    # Single container -- stream the log.
    log_path = log_files[0].parent / log_filename

    # [SEC V-002] Validate the resolved log path.
    for root in roots:
        try:
            validate_path(path=log_path, root=root)
            break
        except ValueError:
            continue
    else:
        print(f"Error: log path escapes must-gather root: {log_path}", file=sys.stderr)
        sys.exit(1)

    if not log_path.is_file():
        print(f'Error: {log_filename} not found for pod "{pod_name}"', file=sys.stderr)
        sys.exit(1)

    stream_log(log_path=log_path)
