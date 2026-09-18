from __future__ import annotations

import json
import os
from opsscript_gate.models import DistroStatus, RunReport, SingleResult


def format_terminal_table(report: RunReport) -> str:
    """Format the report as a clean, aligned ASCII terminal table."""
    headers = ["Distro", "Status", "Exit Code", "Duration", "Details"]

    rows: list[list[str]] = []
    for r in report.results:
        exit_code_str = str(r.exit_code) if r.exit_code is not None else "-"
        duration_str = f"{r.duration:.2f}s"

        if r.status == DistroStatus.PASS:
            detail = "OK"
        elif r.error_message:
            detail = r.error_message
        else:
            detail = "-"

        rows.append([
            r.distro,
            r.status.value,
            exit_code_str,
            duration_str,
            detail,
        ])

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            if len(val) > col_widths[i]:
                col_widths[i] = len(val)

    # Upper bound for detail column to keep terminal tidy
    max_detail_width = 50
    if col_widths[4] > max_detail_width:
        col_widths[4] = max_detail_width

    def format_row(values: list[str]) -> str:
        formatted_vals = []
        for i, v in enumerate(values):
            w = col_widths[i]
            if len(v) > w:
                truncated = v[: w - 3] + "..."
                formatted_vals.append(truncated.ljust(w))
            else:
                formatted_vals.append(v.ljust(w))
        return "| " + " | ".join(formatted_vals) + " |"

    sep_line = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"

    lines = [
        sep_line,
        format_row(headers),
        sep_line,
    ]
    for row in rows:
        lines.append(format_row(row))
    lines.append(sep_line)

    status_str = "PASSED" if report.all_passed else "FAILED"
    lines.append(
        f"Total duration: {report.total_duration:.2f}s | Result: {status_str}"
    )

    # Append output snippets for failing/timed out distros
    failed_results = [r for r in report.results if r.status != DistroStatus.PASS and r.output_snippet]
    if failed_results:
        lines.append("\n" + "=" * 60)
        lines.append("Failed Distributions - Output Snippets (last 15 lines):")
        lines.append("=" * 60)
        for r in failed_results:
            lines.append(f"\n--- [{r.distro}] ({r.status.value}) ---")
            lines.append(r.output_snippet)

    return "\n".join(lines)


def format_github_summary(report: RunReport) -> str:
    """Format the report as GitHub-flavored Markdown for Actions Step Summary."""
    overall_badge = "✅ **ALL PASSED**" if report.all_passed else "❌ **CHECKS FAILED**"

    lines = [
        "## 🛡️ OpsScript Gate Compatibility Report",
        "",
        f"**Overall Status**: {overall_badge}  ",
        f"**Total Duration**: `{report.total_duration:.2f}s`  ",
        f"**Total Tested**: `{len(report.results)}`",
        "",
        "| Distro | Status | Exit Code | Duration | Message |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]

    for r in report.results:
        if r.status == DistroStatus.PASS:
            status_icon = "✅ PASS"
        elif r.status == DistroStatus.FAIL:
            status_icon = "❌ FAIL"
        elif r.status == DistroStatus.TIMED_OUT:
            status_icon = "⏱️ TIMED_OUT"
        else:
            status_icon = "⚠️ ERROR"

        exit_code_str = f"`{r.exit_code}`" if r.exit_code is not None else "`N/A`"
        duration_str = f"`{r.duration:.2f}s`"
        msg = r.error_message or "-"
        msg_escaped = msg.replace("|", "\\|")

        lines.append(
            f"| `{r.distro}` | {status_icon} | {exit_code_str} | {duration_str} | {msg_escaped} |"
        )

    lines.append("")

    # Expandable details for any failures or timeouts
    failures = [r for r in report.results if r.status != DistroStatus.PASS]
    if failures:
        lines.append("### 🔍 Failure Diagnostic Logs")
        for r in failures:
            lines.append(f"<details><summary><b>[{r.status.value}] {r.distro}</b></summary>")
            lines.append("")
            if r.error_message:
                lines.append(f"> **Error:** {r.error_message}")
                lines.append("")
            if r.output_snippet:
                lines.append("```text")
                lines.append(r.output_snippet)
                lines.append("```")
            else:
                lines.append("*No output captured.*")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


def format_json(report: RunReport) -> str:
    """Format the report as structured JSON."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def write_github_step_summary(report: RunReport) -> bool:
    """Write markdown report to $GITHUB_STEP_SUMMARY if present in environment."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return False

    try:
        markdown_content = format_github_summary(report)
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n" + markdown_content + "\n")
        return True
    except Exception:
        return False
