from __future__ import annotations

import argparse
import os
import sys
import time

from opsscript_gate import __version__
from opsscript_gate.discovery import discover_scripts
from opsscript_gate.models import MultiScriptReport, RunReport
from opsscript_gate.reporter import (
    emit_github_annotations,
    format_github_summary,
    format_json,
    format_multi_github_summary,
    format_multi_terminal_table,
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
        help="Run cross-distro compatibility validation on shell scripts",
    )
    run_parser.add_argument(
        "script_path",
        nargs="?",
        default=None,
        type=str,
        help="Path to the target shell script to validate (auto-discovers if omitted)",
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
        "-j", "--jobs",
        type=int,
        default=None,
        help="Number of concurrent container execution jobs (default: min(2, matrix_size))",
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
    run_parser.add_argument(
        "--shell",
        choices=["posix", "shebang", "auto"],
        default="posix",
        help="Shell execution mode: 'posix' (default, /bin/sh), 'shebang' (honors script shebang), or 'auto' (shebang if recognized, else /bin/sh)",
    )
    run_parser.add_argument(
        "--mem-limit",
        type=str,
        default="256m",
        help="Memory limit for containers (default: 256m)",
    )
    run_parser.add_argument(
        "--pids-limit",
        type=int,
        default=128,
        help="Maximum number of processes per container (default: 128)",
    )
    run_parser.add_argument(
        "--network",
        type=str,
        default="bridge",
        help="Network mode for containers: 'bridge' or 'none' (default: bridge)",
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
        # Resolve target script(s)
        if args.script_path:
            if not os.path.isfile(args.script_path):
                sys.stderr.write(f"Error: Script file not found: {args.script_path}\n")
                return 1
            target_scripts = [args.script_path]
        else:
            target_scripts = discover_scripts(".")
            if not target_scripts:
                sys.stderr.write(
                    "No shell scripts discovered in the current directory. "
                    "Please specify a script path explicitly.\n"
                )
                return 1

        matrix = parse_matrix_argument(args.matrix)

        if len(target_scripts) == 1:
            script_path = target_scripts[0]
            try:
                report = run_matrix(
                    script_path=script_path,
                    matrix=matrix,
                    timeout=args.timeout,
                    shell_mode=args.shell,
                    jobs=args.jobs,
                    mem_limit=args.mem_limit,
                    pids_limit=args.pids_limit,
                    network=args.network,
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
                output = format_github_summary(report, script_path=script_path)
            else:
                output = format_terminal_table(report, script_path=script_path)

            print(output)

            # Emit GitHub line annotations if in CI
            emit_github_annotations(report, script_path=script_path)

            # Automatic GitHub Actions Step Summary injection
            write_github_step_summary(report, script_path=script_path)

            return 0 if report.all_passed else 1

        # Multiple scripts discovered
        multi_reports: dict[str, RunReport] = {}
        multi_start = time.perf_counter()

        for script_path in target_scripts:
            try:
                report = run_matrix(
                    script_path=script_path,
                    matrix=matrix,
                    timeout=args.timeout,
                    shell_mode=args.shell,
                    jobs=args.jobs,
                    mem_limit=args.mem_limit,
                    pids_limit=args.pids_limit,
                    network=args.network,
                )
            except DockerDaemonError as err:
                sys.stderr.write(f"Docker Error: {err}\n")
                return 1
            except Exception as err:
                sys.stderr.write(f"Unexpected Error: {err}\n")
                return 1

            multi_reports[script_path] = report
            emit_github_annotations(report, script_path=script_path)

        total_duration = time.perf_counter() - multi_start
        all_passed = all(r.all_passed for r in multi_reports.values())
        multi_report = MultiScriptReport(
            reports=multi_reports,
            total_duration=total_duration,
            all_passed=all_passed,
        )

        if args.format == "json":
            output = format_json(multi_report)
        elif args.format == "markdown":
            output = format_multi_github_summary(multi_report)
        else:
            output = format_multi_terminal_table(multi_report)

        print(output)

        write_github_step_summary(multi_report)

        return 0 if multi_report.all_passed else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
