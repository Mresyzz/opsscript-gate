from __future__ import annotations

import argparse
import os
import sys

from opsscript_gate import __version__
from opsscript_gate.reporter import (
    format_github_summary,
    format_json,
    format_terminal_table,
    write_github_step_summary,
)
from opsscript_gate.runner import (
    DEFAULT_MATRIX,
    DEFAULT_TIMEOUT,
    DockerDaemonError,
    run_matrix,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="opsscript-gate",
        description="Lightweight unprivileged container cross-distro compatibility pre-check for Linux ops scripts.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 'run' subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run cross-distro compatibility validation on a shell script",
    )
    run_parser.add_argument(
        "script_path",
        type=str,
        help="Path to the target shell script to validate",
    )
    run_parser.add_argument(
        "--matrix",
        type=str,
        default=None,
        help=(
            "Comma-separated list of container images to test against. "
            f"Defaults to: {','.join(DEFAULT_MATRIX)}"
        ),
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Hard timeout in seconds per container (default: {DEFAULT_TIMEOUT}s)",
    )
    run_parser.add_argument(
        "--format",
        choices=["table", "markdown", "json"],
        default="table",
        help="Output report format: 'table' (default ASCII), 'markdown', or 'json'",
    )

    return parser


def parse_matrix_argument(matrix_raw: str | None) -> list[str]:
    """Parse comma-separated matrix string into a list of image names."""
    if not matrix_raw:
        return DEFAULT_MATRIX
    images = [img.strip() for img in matrix_raw.split(",") if img.strip()]
    return images if images else DEFAULT_MATRIX


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "run":
        script_path = args.script_path
        if not os.path.isfile(script_path):
            sys.stderr.write(f"Error: Script file not found: {script_path}\n")
            return 1

        matrix = parse_matrix_argument(args.matrix)

        try:
            report = run_matrix(
                script_path=script_path,
                matrix=matrix,
                timeout=args.timeout,
            )
        except DockerDaemonError as err:
            sys.stderr.write(f"Docker Error: {err}\n")
            return 1
        except Exception as err:
            sys.stderr.write(f"Unexpected Error: {err}\n")
            return 1

        # Format report output
        if args.format == "json":
            output = format_json(report)
        elif args.format == "markdown":
            output = format_github_summary(report)
        else:
            output = format_terminal_table(report)

        print(output)

        # Automatic GitHub Actions Step Summary injection
        write_github_step_summary(report)

        # Exit code convention: 0 for all pass, 1 for any failure/timeout/error
        return 0 if report.all_passed else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
