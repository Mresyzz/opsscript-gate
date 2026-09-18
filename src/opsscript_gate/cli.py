import argparse
import sys

from .reporter import generate_reports
from .runner import run_script_on_distros


def main():
    parser = argparse.ArgumentParser(description="A lightweight, non-privileged containerized pre-release verification tool for shell scripts.")
    parser.add_argument("script_path", help="Path to the shell script to test.")
    parser.add_argument("--matrix", default="debian:12-slim,ubuntu:22.04,ubuntu:24.04,alpine:3.20", help="Comma-separated image list.")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds per container.")
    parser.add_argument("--format", choices=["table", "markdown", "json"], default="table", help="Format for standard output.")
    parser.add_argument("--json-out", help="Optional path to write JSON report.")
    parser.add_argument("--summary-out", help="Optional path to write Markdown summary report.")

    args = parser.parse_args()

    distros = [d.strip() for d in args.matrix.split(",") if d.strip()]
    if not distros:
        print("Error: No distributions provided in the matrix.", file=sys.stderr)
        sys.exit(1)

    report = run_script_on_distros(args.script_path, distros, args.timeout)

    generate_reports(report, args.format, args.json_out, args.summary_out)

    if not report.all_passed:
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
