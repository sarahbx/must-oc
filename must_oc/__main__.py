# must_oc/__main__.py
from __future__ import annotations

import argparse
import sys

from must_oc.oc.describe import run_describe
from must_oc.oc.get import run_get
from must_oc.oc.logs import run_logs
from must_oc.oc.update_types import run_update_types


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="must-oc",
        description="oc-like CLI for must-gather directories",
    )

    # Global / parent flags shared across all subcommands.
    parser.add_argument(
        "-d",
        "--must-gather-dir",
        action="append",
        default=None,
        help="Path to must-gather directory (repeatable, defaults to current directory)",
    )
    parser.add_argument(
        "--show-secrets",
        action="store_true",
        default=False,
        help="[SEC V-003] Disable sensitive data redaction",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="[SEC I-002] Enable full tracebacks on errors",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # --- get subcommand ---
    get_parser = subparsers.add_parser(name="get", help="Get resources")
    get_parser.add_argument(
        "resource_type", help="Resource type (e.g. pod, deployment)"
    )
    get_parser.add_argument(
        "name", nargs="?", default=None, help="Specific resource name"
    )
    get_parser.add_argument("-n", "--namespace", default=None, help="Namespace")
    get_parser.add_argument(
        "-A", "--all-namespaces", action="store_true", help="All namespaces"
    )
    get_parser.add_argument(
        "-l", "--selector", dest="label_selector", default=None, help="Label selector"
    )
    get_parser.set_defaults(func=run_get)

    # --- describe subcommand ---
    describe_parser = subparsers.add_parser(name="describe", help="Describe a resource")
    describe_parser.add_argument(
        "resource_type", help="Resource type (e.g. pod, deployment)"
    )
    describe_parser.add_argument("name", help="Resource name")
    describe_parser.add_argument("-n", "--namespace", default=None, help="Namespace")
    describe_parser.set_defaults(func=run_describe, all_namespaces=False)

    # --- logs subcommand ---
    logs_parser = subparsers.add_parser(name="logs", help="Get pod logs")
    logs_parser.add_argument("pod_name", help="Pod name")
    logs_parser.add_argument(
        "-n", "--namespace", required=True, help="Namespace (required)"
    )
    logs_parser.add_argument("-c", "--container", default=None, help="Container name")
    logs_parser.add_argument(
        "--previous", action="store_true", help="Show previous container logs"
    )
    logs_parser.set_defaults(func=run_logs)

    # --- update-types subcommand ---
    update_types_parser = subparsers.add_parser(
        name="update-types", help="Scan must-gather and update config"
    )
    update_types_parser.set_defaults(func=run_update_types)

    return parser


def _validate_args(args: argparse.Namespace) -> None:
    """Perform cross-field validation that argparse alone cannot enforce.

    Raises SystemExit with an error message when validation fails.
    """
    command = getattr(args, "command", None)

    if command == "get":
        if not args.all_namespaces and args.namespace is None:
            print("Error: must specify -n <namespace> or -A", file=sys.stderr)
            sys.exit(1)

    if command == "describe":
        if args.namespace is None:
            print("Error: must specify -n <namespace> for describe", file=sys.stderr)
            sys.exit(1)


def _normalise_must_gather_dir(args: argparse.Namespace) -> None:
    """Ensure args.must_gather_dir is always a list.

    When -d is not provided, default to the current directory.
    """
    if args.must_gather_dir is None:
        args.must_gather_dir = ["."]


def main() -> None:
    """CLI entry point for must-oc."""
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    _normalise_must_gather_dir(args=args)
    _validate_args(args=args)

    try:
        args.func(args)
    except Exception as err:
        if getattr(args, "debug", False):
            raise
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
