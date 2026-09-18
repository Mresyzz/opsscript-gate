import json
import os

from .models import DistroStatus, RunReport


def format_ascii_table(report: RunReport) -> str:
    lines = []
    lines.append(f"Run Report for: {report.script_path}")
    lines.append("-" * 75)
    lines.append(f"{'Image':<20} | {'Status':<10} | {'Exit Code':<9} | {'Time (s)':<10}")
    lines.append("-" * 75)

    for r in report.results:
        exit_code_str = str(r.exit_code) if r.exit_code is not None else "-"
        lines.append(f"{r.image:<20} | {r.status.value:<10} | {exit_code_str:<9} | {r.execution_time:<10.2f}")

    lines.append("-" * 75)

    # Optionally include stderr for failures/errors
    for r in report.results:
        if r.status not in (DistroStatus.PASS, DistroStatus.TIMEOUT):
            if r.stderr.strip():
                lines.append(f"\n[STDERR] {r.image}:")
                lines.append(r.stderr.strip())

    return "\n".join(lines)

def format_markdown_summary(report: RunReport) -> str:
    lines = []
    lines.append(f"## `opsscript-gate` Report: `{os.path.basename(report.script_path)}`")
    lines.append("")
    lines.append("| Image | Status | Exit Code | Time (s) |")
    lines.append("|---|---|---|---|")

    for r in report.results:
        exit_code_str = str(r.exit_code) if r.exit_code is not None else "-"
        icon = "✅" if r.status == DistroStatus.PASS else ("⏳" if r.status == DistroStatus.TIMEOUT else "❌")
        lines.append(f"| `{r.image}` | {icon} {r.status.value} | `{exit_code_str}` | {r.execution_time:.2f} |")

    for r in report.results:
        if r.status not in (DistroStatus.PASS, DistroStatus.TIMEOUT):
            if r.stderr.strip():
                lines.append(f"\n**Stderr for {r.image}**:")
                lines.append("```text")
                lines.append(r.stderr.strip())
                lines.append("```")

    return "\n".join(lines)

def to_json(report: RunReport) -> str:
    data = {
        "script_path": report.script_path,
        "all_passed": report.all_passed,
        "results": [
            {
                "image": r.image,
                "status": r.status.value,
                "exit_code": r.exit_code,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "execution_time": r.execution_time,
            }
            for r in report.results
        ]
    }
    return json.dumps(data, indent=2)

def generate_reports(report: RunReport, fmt: str, json_out: str | None, summary_out: str | None):
    # Always print the requested format to stdout
    if fmt == "table":
        print(format_ascii_table(report))
    elif fmt == "markdown":
        print(format_markdown_summary(report))
    elif fmt == "json":
        print(to_json(report))

    # Handle explicit file outputs
    if json_out:
        with open(json_out, "w") as f:
            f.write(to_json(report))

    if summary_out:
        with open(summary_out, "w") as f:
            f.write(format_markdown_summary(report))

    # Auto-append to GITHUB_STEP_SUMMARY if present
    github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_step_summary:
        try:
            with open(github_step_summary, "a") as f:
                f.write("\n")
                f.write(format_markdown_summary(report))
                f.write("\n")
        except Exception as e:
            print(f"Warning: Failed to write to GITHUB_STEP_SUMMARY: {e}")
