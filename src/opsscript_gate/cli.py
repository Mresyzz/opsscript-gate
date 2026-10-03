from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from opsscript_gate import __version__
from opsscript_gate.discovery import discover_changed_scripts, discover_scripts
from opsscript_gate.config import DEFAULTS, PRESETS, init_project, load_config, validate_packages
from opsscript_gate.models import MultiScriptReport, RunReport
from opsscript_gate.reporter import (
    emit_github_annotations,
    format_github_summary,
    format_json,
    format_multi_sarif,
    format_multi_github_summary,
    format_multi_terminal_table,
    format_sarif,
    format_terminal_table,
    write_github_step_summary,
)
from opsscript_gate.runner import (
    DEFAULT_MATRIX,
    DEFAULT_TIMEOUT,
    DockerDaemonError,
    get_docker_client,
    run_matrix,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="opsscript-gate",
        allow_abbrev=False,
        description="Lightweight unprivileged container cross-distro compatibility pre-check for Linux ops scripts.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")
    subparsers.add_parser("init", help="Create project configuration and GitHub workflow")
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check the local environment before running containers",
    )
    doctor_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format: 'table' (default) or 'json'",
    )

    # 'run' subcommand
    run_parser = subparsers.add_parser(
        "run",
        allow_abbrev=False,
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
        "--repeat",
        type=int,
        default=1,
        help="Repeat each distribution run to detect flaky runtime behavior (default: 1)",
    )
    run_parser.add_argument(
        "--format",
        choices=["table", "markdown", "json", "sarif"],
        default="table",
        help="Output report format: 'table' (default ASCII), 'markdown', 'json', or 'sarif'",
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
    run_parser.add_argument(
        "--packages",
        action="append",
        default=None,
        help="Optional comma-separated packages to install in each container before running (repeatable; requires network=bridge)",
    )
    run_parser.add_argument(
        "--changed-since",
        help="Only test shell scripts changed between this Git revision and HEAD",
    )

    run_parser.add_argument("--config", help="Project JSON configuration (default: .opsscript-gate.json)")
    run_parser.add_argument("--preset", choices=list(PRESETS), help="Named distribution matrix")
    run_parser.add_argument("--exclude", action="append", default=None, help="Exclude a repository-relative glob (repeatable; replaces config exclusions)")
    run_parser.add_argument("--max-scripts", type=int, default=20, help="Discovery limit; exceeding it fails instead of silently skipping scripts")
    run_parser.add_argument("--dry-run", action="store_true", help="Preview selected scripts and images without Docker")
    run_parser.add_argument("--output", help="Also save the report to this UTF-8 file")
    return parser


def parse_matrix_argument(matrix_raw: str | None) -> list[str]:
    """Parse comma-separated matrix string into a list of image names."""
    if not matrix_raw:
        return DEFAULT_MATRIX
    images = [img.strip() for img in matrix_raw.split(",") if img.strip()]
    return images if images else DEFAULT_MATRIX


def parse_packages_argument(packages_raw: list[str] | None) -> list[str]:
    """Parse repeated comma/newline-separated package arguments."""
    if not packages_raw:
        return []
    packages: list[str] = []
    for raw in packages_raw:
        for package in raw.replace("\r", "\n").replace(",", "\n").split("\n"):
            name = package.strip()
            if name:
                packages.append(name)
    return validate_packages(packages)


def run_checked_matrix(
    args: argparse.Namespace, script_path: str, matrix: list[str]
) -> RunReport | None:
    """Run one script and normalize user-facing Docker/runtime errors."""
    try:
        return run_matrix(
            script_path=script_path,
            matrix=matrix,
            timeout=args.timeout,
            shell_mode=args.shell,
            jobs=args.jobs,
            mem_limit=args.mem_limit,
            pids_limit=args.pids_limit,
            network=args.network,
            packages=args.packages,
            repeat=args.repeat,
        )
    except DockerDaemonError as err:
        sys.stderr.write(f"Docker Error: {err}\n")
    except Exception as err:
        sys.stderr.write(f"Unexpected Error: {err}\n")
    return None


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "init":
        try:
            print("Created:\n" + "\n".join(init_project()))
            print("Review exclusions, then run: opsscript-gate run --dry-run")
            return 0
        except (OSError, ValueError) as err:
            sys.stderr.write(f"Error: {err}\n")
            return 1

    if args.command == "doctor":
        checks = [
            {
                "name": "python",
                "ok": sys.version_info >= (3, 10),
                "detail": f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            }
        ]
        try:
            get_docker_client()
            checks.append({"name": "docker", "ok": True, "detail": "Docker daemon is reachable"})
        except DockerDaemonError as err:
            checks.append({"name": "docker", "ok": False, "detail": str(err)})

        config_path = Path(".opsscript-gate.json")
        checks.append({
            "name": "project",
            "ok": True,
            "detail": f"Found {config_path}" if config_path.is_file() else "No project config (optional)",
        })
        passed = all(check["ok"] for check in checks)
        if args.format == "json":
            print(json.dumps({"status": "PASS" if passed else "FAIL", "checks": checks}, indent=2))
        else:
            print("OpsScript Gate doctor")
            for check in checks:
                marker = "PASS" if check["ok"] else "FAIL"
                print(f"[{marker}] {check['name']}: {check['detail']}")
            if not passed:
                print("Run `opsscript-gate init` after fixing the failed check, then preview with `opsscript-gate run --dry-run`.")
        return 0 if passed else 1

    if args.command == "run":
        try:
            config = load_config(args.config)
            explicit = {token.split("=", 1)[0] for token in argv if token.startswith("--")}
            if any(token.startswith("-j") for token in argv):
                explicit.add("--jobs")
            for key in DEFAULTS:
                if key in config and "--" + key.replace("_", "-") not in explicit:
                    setattr(args, key, config[key])
            if "--matrix" in explicit and "--preset" in explicit:
                raise ValueError("Use either --matrix or --preset, not both")
            if "--matrix" in explicit:
                args.preset = None
            if "--preset" in explicit:
                args.matrix = None
            for key in ("jobs", "timeout", "pids_limit", "max_scripts", "repeat"):
                value = getattr(args, key)
                if value is not None and value < 1:
                    raise ValueError(f"{key.replace('_', '-')} must be positive")
            if args.network not in ("bridge", "none"):
                raise ValueError("network must be bridge or none")
            args.packages = parse_packages_argument(args.packages)
            if args.packages and args.network == "none":
                raise ValueError("packages require network=bridge")
            if args.matrix is not None and not any(x.strip() for x in args.matrix.split(",")):
                raise ValueError("matrix must contain at least one image")
        except ValueError as err:
            sys.stderr.write(f"Error: {err}\n")
            return 1
        # Resolve target script(s)
        if args.script_path and args.changed_since:
            sys.stderr.write("Error: use either a script path or --changed-since, not both\n")
            return 1
        changed_selection = bool(args.changed_since)
        if args.script_path:
            if not os.path.isfile(args.script_path):
                sys.stderr.write(f"Error: Script file not found: {args.script_path}\n")
                return 1
            target_scripts = [args.script_path]
        elif changed_selection:
            try:
                target_scripts = discover_changed_scripts(
                    ".", since=args.changed_since, max_scripts=args.max_scripts, exclude=args.exclude
                )
            except ValueError as err:
                sys.stderr.write(f"Error: {err}\n")
                return 1
        else:
            try:
                target_scripts = discover_scripts(".", max_scripts=args.max_scripts, exclude=args.exclude)
            except ValueError as err:
                sys.stderr.write(f"Error: {err}\n")
                return 1
            if not target_scripts and not changed_selection:
                sys.stderr.write(
                    "No shell scripts discovered in the current directory. "
                    "Please specify a script path explicitly.\n"
                )
                return 1

        matrix = PRESETS[args.preset] if args.preset else parse_matrix_argument(args.matrix)
        if args.output:
            output_path = Path(args.output).resolve()
            protected = [Path(p).resolve() for p in target_scripts]
            protected.append(Path(args.config or ".opsscript-gate.json").resolve())
            if output_path in protected:
                sys.stderr.write("Error: output must not overwrite a target script or configuration\n")
                return 1

        if args.dry_run:
            plan = {"dry_run": True, "scripts": target_scripts, "matrix": matrix,
                    "executions": len(target_scripts) * len(matrix), "shell": args.shell,
                    "network": args.network, "packages": args.packages, "timeout": args.timeout,
                    "repeat": args.repeat}
            if changed_selection:
                plan["changed_since"] = args.changed_since
            output = json.dumps(plan, indent=2) if args.format == "json" else (
                "Execution preview (no scripts executed)\n"
                + "\n".join(f"  {path}" for path in target_scripts)
                + f"\nImages: {', '.join(matrix)}\nContainer executions: {plan['executions']}"
                + (f"\nPackages: {', '.join(args.packages)}" if args.packages else "")
                + f"\nShell: {args.shell} | Network: {args.network} | Timeout: {args.timeout}s | Repeat: {args.repeat}"
            )
            return 0 if publish_output(output, args.output) else 1

        if not target_scripts:
            output = (
                f"No changed shell scripts since {args.changed_since}; skipping compatibility checks."
            )
            return 0 if publish_output(output, args.output) else 1

        if len(target_scripts) == 1:
            script_path = target_scripts[0]
            report = run_checked_matrix(args, script_path, matrix)
            if report is None:
                return 1

            # Format report output
            if args.format == "json":
                output = format_json(report)
            elif args.format == "sarif":
                output = format_sarif(report, script_path=script_path)
            elif args.format == "markdown":
                output = format_github_summary(report, script_path=script_path)
            else:
                output = format_terminal_table(report, script_path=script_path)

            if not publish_output(output, args.output):
                return 1

            # Emit GitHub line annotations if in CI
            emit_github_annotations(report, script_path=script_path)

            # Automatic GitHub Actions Step Summary injection
            write_github_step_summary(report, script_path=script_path)

            return 0 if report.all_passed else 1

        # Multiple scripts discovered
        multi_reports: dict[str, RunReport] = {}
        multi_start = time.perf_counter()

        for script_path in target_scripts:
            report = run_checked_matrix(args, script_path, matrix)
            if report is None:
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
        elif args.format == "sarif":
            output = format_multi_sarif(multi_report)
        elif args.format == "markdown":
            output = format_multi_github_summary(multi_report)
        else:
            output = format_multi_terminal_table(multi_report)

        if not publish_output(output, args.output):
            return 1

        write_github_step_summary(multi_report)

        return 0 if multi_report.all_passed else 1

    return 0


def publish_output(output: str, filename: str | None) -> bool:
    if filename:
        try:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(output + "\n", encoding="utf-8")
        except OSError as err:
            sys.stderr.write(f"Error writing report: {err}\n")
            return False
    print(output)
    return True


if __name__ == "__main__":
    sys.exit(main())
