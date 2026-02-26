# must_oc/oc/describe.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from utilities.format import format_describe
from utilities.paths import discover_roots, find_resource_files
from utilities.types import resolve_resource_type
from utilities.yaml_parser import load_resource


def run_describe(args: argparse.Namespace) -> None:
    """Orchestrate the 'describe' command.

    Finds a specific resource by name, loads its YAML, applies redaction
    for sensitive fields, formats the output in describe style, and prints it.
    """
    # Require a resource name.
    if not args.name:
        print("Error: resource name is required for describe.", file=sys.stderr)
        sys.exit(1)

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

    # Step 3: Find resource files matching the specific name.
    files = find_resource_files(
        roots=roots,
        namespace=args.namespace,
        all_namespaces=args.all_namespaces,
        api_group=api_group,
        plural=plural,
        name=args.name,
    )

    # Step 4: Check if any file was found.
    if not files:
        namespace_msg = f" in namespace {args.namespace}" if args.namespace else ""
        print(
            f"Error: {args.resource_type} {args.name} not found{namespace_msg}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 5: Load the first matching resource file.
    file_path = files[0]
    resource = load_resource(path=file_path)

    # Step 6: Format and print with redaction applied via format_describe.
    # [SEC V-003] format_describe calls redact_sensitive_fields internally.
    output = format_describe(resource=resource, show_secrets=args.show_secrets)
    print(output)
