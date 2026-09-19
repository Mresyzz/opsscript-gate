import html
import json
import os
import re
import sys
from opsscript_gate.models import DistroStatus, MultiScriptReport, RunReport, SingleResult

# Structure-altering Markdown characters in regular prose:
# \ ` * _ [ ] ( ) # + - ! > ~ |
_MARKDOWN_SPECIAL_RE = re.compile(r"([\\`*_{}\[\]()#+\-.!>~|])")


def escape_inline_code(text: str) -> str:
    """
    Escape text for safe inclusion inside Markdown inline code spans (`...`).
    Replaces backticks with single quotes and strips newlines to prevent code-span breakouts.
    """
    if not text:
        return ""
    cleaned = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return cleaned.replace("`", "'")


def escape_markdown_text(text: str) -> str:
    """
    Escape structure-altering characters in normal Markdown text.
    Prevents headings, blockquotes, raw HTML, links, and formatting injection
    while preserving standard technical terms like 'non-zero' or 'x86_64'.
    """
    if not text:
        return ""
    # Neutralize HTML tags and entities
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Escape brackets, parentheses, pipes, backticks, and backslashes to prevent links/code spans
    text = text.replace("\\", "\\\\")
    text = text.replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")
    text = text.replace("(", "\\(").replace(")", "\\)").replace("|", "\\|")

    # Neutralize line-leading markdown structures (headings, blockquotes, list markers)
    def _neutralize_line_start(m: re.Match) -> str:
        lead, ch = m.group(1), m.group(2)
        if ch in ("#", ">", "-", "+", "*"):
            return f"{lead}\\{ch}"
        return m.group(0)

    return re.sub(r"^(\s*)([#>+\-*])", _neutralize_line_start, text, flags=re.MULTILINE)


def escape_markdown_table_cell(text: str) -> str:
    """
    Escape content for safe inclusion in Markdown table cells.
    Replaces newlines with spaces and escapes pipe characters.
    """
    if not text:
        return ""
    cleaned = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return cleaned.replace("|", "\\|")


def escape_html_text(text: str) -> str:
    """
    Escape text for safe inclusion in HTML tags and attributes (e.g. <summary>).
    """
    if not text:
        return ""
    return html.escape(text, quote=True)


def format_safe_code_fence(content: str, language: str = "text") -> list[str]:
    """
    Safely enclose content in a markdown code block.
    Dynamically adjusts backtick count to prevent premature closing,
    and neutralizes closing HTML tags (e.g. </details>) that could break surrounding containers.
    """
    if not content:
        return [f"```{language}", "```"]

    # Neutralize closing tags if present inside snippet so HTML details/summary container isn't closed
    safe_content = (
        content.replace("</details>", "<\\/details>")
        .replace("</summary>", "<\\/summary>")
        .replace("<details>", "<\\details>")
        .replace("<summary>", "<\\summary>")
    )

    # Calculate max consecutive backticks in content
    max_backticks = 3
    current_run = 0
    for ch in safe_content:
        if ch == "`":
            current_run += 1
            if current_run >= max_backticks:
                max_backticks = current_run + 1
        else:
            current_run = 0

    fence = "`" * max_backticks
    return [f"{fence}{language}", safe_content, fence]


def escape_github_property(value: str) -> str:
    """
    Escape property values for GitHub Actions workflow commands.
    Escapes %, \\r, \\n, :, and ,
    """
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def escape_github_data(value: str) -> str:
    """
    Escape message body content for GitHub Actions workflow commands.
    Escapes %, \\r, and \\n
    """
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def format_github_annotations(report: RunReport, script_path: str = "") -> list[str]:
    """
    Generate GitHub Actions line-level annotation commands for failures.
    Produces ::error file=...,line=...,title=...::... when a line number is known,
    or ::error file=...,title=...::... when line number is unavailable.
    """
    annotations: list[str] = []
    if script_path:
        clean_path = script_path.replace("\\", "/")
        if clean_path.startswith("./"):
            clean_path = clean_path[2:]
        try:
            if os.path.isabs(clean_path):
                clean_path = os.path.relpath(clean_path, ".").replace("\\", "/")
        except Exception:
            pass
        norm_script = clean_path if clean_path else "script.sh"
    else:
        norm_script = "script.sh"
    escaped_file = escape_github_property(norm_script)

    for r in report.results:
        if r.status == DistroStatus.PASS:
            continue

        raw_title = f"OpsScript Gate: [{r.distro}] {r.status.value}"
        if r.diagnostic and r.diagnostic.message:
            raw_title = f"OpsScript Gate: [{r.distro}] {r.diagnostic.message}"

        msg_parts: list[str] = []
        if r.diagnostic:
            msg_parts.append(r.diagnostic.message)
            if r.diagnostic.hint:
                msg_parts.append(r.diagnostic.hint)
        elif r.error_message:
            msg_parts.append(r.error_message)
        else:
            msg_parts.append(f"Execution failed with exit code {r.exit_code}")

        raw_msg = " — ".join(msg_parts)
        escaped_title = escape_github_property(raw_title)
        escaped_msg = escape_github_data(raw_msg)

        line_num = r.diagnostic.line if (r.diagnostic and r.diagnostic.line is not None) else None
        if line_num is not None and line_num > 0:
            annotations.append(
                f"::error file={escaped_file},line={line_num},title={escaped_title}::{escaped_msg}"
            )
        else:
            annotations.append(
                f"::error file={escaped_file},title={escaped_title}::{escaped_msg}"
            )

    return annotations


def emit_github_annotations(report: RunReport, script_path: str = "") -> None:
    """Print annotations to stdout only when running in GitHub Actions."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for ann in format_github_annotations(report, script_path):
            sys.stdout.write(ann + "\n")
        sys.stdout.flush()


def format_terminal_table(report: RunReport, script_path: str = "") -> str:
    """Format the report as a clean, aligned ASCII terminal table with hints."""
    headers = ["Distro", "Status", "Exit Code", "Duration", "Details"]

    rows: list[list[str]] = []
    hints: list[tuple[str, str]] = []

    for r in report.results:
        exit_code_str = str(r.exit_code) if r.exit_code is not None else "-"
        duration_str = f"{r.duration:.2f}s"

        if r.status == DistroStatus.PASS:
            detail = "OK"
        elif r.diagnostic:
            line_suffix = f" (line {r.diagnostic.line})" if r.diagnostic.line else ""
            detail = f"{r.diagnostic.message}{line_suffix}"
            if r.diagnostic.hint:
                hints.append((r.distro, r.diagnostic.hint))
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

    lines: list[str] = []
    if script_path:
        lines.append(f"Target: {script_path}")

    lines.extend([
        sep_line,
        format_row(headers),
        sep_line,
    ])
    for row in rows:
        lines.append(format_row(row))
    lines.append(sep_line)

    status_str = "PASSED" if report.all_passed else "FAILED"
    lines.append(
        f"Total duration: {report.total_duration:.2f}s | Result: {status_str}"
    )

    # Output conservative remediation hints if any
    if hints:
        lines.append("\nRemediation Recommendations:")
        for distro_name, hint_text in hints:
            lines.append(f"  * [{distro_name}] {hint_text}")

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


def format_multi_terminal_table(multi_report: MultiScriptReport) -> str:
    """Format multiple script reports as aligned terminal tables."""
    parts: list[str] = []
    for script_name, report in multi_report.reports.items():
        parts.append(format_terminal_table(report, script_path=script_name))
        parts.append("")
    summary_status = "ALL PASSED" if multi_report.all_passed else "SOME FAILED"
    parts.append(f"Multi-Script Run: {len(multi_report.reports)} scripts tested | Overall: {summary_status}")
    return "\n".join(parts)


def format_markdown_compatibility_card(report: RunReport, script_path: str = "") -> str:
    """
    Format an elegant GitHub-flavored Markdown Compatibility Card.
    Suitable for Step Summary and easily copyable into PR / Issue comments.
    Guarantees strict context-sensitive escaping against Markdown/HTML injection.
    """
    passed_count = sum(1 for r in report.results if r.status == DistroStatus.PASS)
    total_count = len(report.results)
    badge = (
        f"✅ **ALL PASSED ({passed_count}/{total_count})**"
        if report.all_passed
        else f"❌ **CHECKS FAILED ({passed_count}/{total_count} Passed)**"
    )

    lines = [
        "## 🛡️ OpsScript Gate Compatibility Report",
        "",
    ]
    if script_path:
        safe_script_path = escape_inline_code(script_path)
        lines.append(f"**Target Script**: `{safe_script_path}`  ")
    lines.append(f"**Status**: {badge}  ")
    lines.append(f"**Total Duration**: `{report.total_duration:.2f}s`")
    lines.append("")
    lines.append("### 📊 Compatibility Matrix")
    lines.append("")
    lines.append("| Distribution | Status | Exit Code | Time | Diagnostic & Recommendation |")
    lines.append("| :--- | :---: | :---: | :---: | :--- |")

    for r in report.results:
        if r.status == DistroStatus.PASS:
            status_icon = "✅ PASS"
        elif r.status == DistroStatus.FAIL:
            status_icon = "❌ FAIL"
        elif r.status == DistroStatus.TIMED_OUT:
            status_icon = "⏱️ TIMED_OUT"
        else:
            status_icon = "⚠️ ERROR"

        safe_distro = escape_inline_code(r.distro)
        exit_code_str = f"`{r.exit_code}`" if r.exit_code is not None else "`N/A`"
        duration_str = f"`{r.duration:.2f}s`"

        if r.status == DistroStatus.PASS:
            diag_cell = "OK"
        elif r.diagnostic:
            line_str = f" (line {r.diagnostic.line})" if r.diagnostic.line else ""
            clean_cmd = f"`{escape_inline_code(r.diagnostic.command)}`" if r.diagnostic.command else "command"
            diag_cell = f"⚠️ Missing command: {clean_cmd}{line_str}"
            if r.diagnostic.hint:
                safe_hint = escape_markdown_table_cell(r.diagnostic.hint)
                diag_cell += f"<br>💡 *{safe_hint}*"
        elif r.error_message:
            diag_cell = escape_markdown_table_cell(r.error_message)
        elif r.status != DistroStatus.PASS:
            diag_cell = f"Non-zero exit code: {r.exit_code}"
        else:
            diag_cell = "-"

        diag_cell_escaped = escape_markdown_table_cell(diag_cell)
        lines.append(
            f"| `{safe_distro}` | {status_icon} | {exit_code_str} | {duration_str} | {diag_cell_escaped} |"
        )

    lines.append("")

    # Expandable Copy-to-PR block
    lines.append("<details>")
    lines.append("<summary>📋 <b>Copyable Markdown (Click to expand & copy to PR / Issue)</b></summary>")
    lines.append("")
    lines.append("```markdown")
    safe_copy_target = escape_inline_code(script_path or "target")
    lines.append(f"### 🛡️ OpsScript Gate: {passed_count}/{total_count} Passed (`{safe_copy_target}`)")
    lines.append("| Distribution | Status | Time | Details |")
    lines.append("| :--- | :---: | :---: | :--- |")
    for r in report.results:
        icon = "✅" if r.status == DistroStatus.PASS else "❌"
        safe_copy_distro = escape_inline_code(r.distro)
        if r.status == DistroStatus.PASS:
            detail = "OK"
        elif r.diagnostic:
            safe_cmd = escape_inline_code(r.diagnostic.command or "")
            detail = f"Missing `{safe_cmd}`"
            if r.diagnostic.line:
                detail += f" (L{r.diagnostic.line})"
            if r.diagnostic.hint:
                safe_hint = escape_markdown_table_cell(r.diagnostic.hint)
                detail += f" — *{safe_hint}*"
        elif r.error_message:
            detail = escape_markdown_table_cell(r.error_message)
        else:
            detail = "-"
        safe_detail = escape_markdown_table_cell(detail)
        lines.append(f"| `{safe_copy_distro}` | {icon} {r.status.value} | `{r.duration:.2f}s` | {safe_detail} |")
    lines.append("```")
    lines.append("</details>")
    lines.append("")

    # Failure diagnostic details with log snippets
    failures = [r for r in report.results if r.status != DistroStatus.PASS]
    if failures:
        lines.append("### 🔍 Failure Diagnostic Logs")
        for r in failures:
            safe_status = escape_html_text(r.status.value)
            safe_distro = escape_html_text(r.distro)
            lines.append(f"<details><summary><b>[{safe_status}] {safe_distro}</b></summary>")
            lines.append("")
            if r.diagnostic:
                clean_kind = escape_inline_code(r.diagnostic.kind)
                clean_msg = escape_inline_code(r.diagnostic.message)
                line_info = f" (line {r.diagnostic.line})" if r.diagnostic.line else ""
                lines.append(f"> **Diagnostic:** `{clean_kind}` — `{clean_msg}`{line_info}")
                if r.diagnostic.hint:
                    safe_hint = escape_markdown_text(r.diagnostic.hint)
                    lines.append(f"> 💡 **Recommendation:** {safe_hint}")
                lines.append("")
            if r.error_message:
                safe_err = escape_markdown_text(r.error_message)
                lines.append(f"> **Error:** {safe_err}")
                lines.append("")
            if r.output_snippet:
                fence_lines = format_safe_code_fence(r.output_snippet, language="text")
                lines.extend(fence_lines)
            else:
                lines.append("*No output captured.*")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


def format_github_summary(report: RunReport, script_path: str = "") -> str:
    """Format report as GitHub Actions Step Summary markdown."""
    return format_markdown_compatibility_card(report, script_path=script_path)


def format_multi_github_summary(multi_report: MultiScriptReport) -> str:
    """Format multiple script reports into a consolidated GitHub Step Summary."""
    passed_scripts = sum(1 for r in multi_report.reports.values() if r.all_passed)
    total_scripts = len(multi_report.reports)
    badge = f"✅ **{passed_scripts} / {total_scripts} Scripts Passed**" if multi_report.all_passed else f"❌ **{passed_scripts} / {total_scripts} Scripts Passed**"

    lines = [
        "## 🛡️ OpsScript Gate Multi-Script Compatibility Report",
        "",
        f"**Summary**: {badge}  ",
        f"**Total Duration**: `{multi_report.total_duration:.2f}s`",
        "",
    ]

    for script_name, report in multi_report.reports.items():
        card = format_markdown_compatibility_card(report, script_path=script_name)
        lines.append(card)
        lines.append("\n---\n")

    return "\n".join(lines)


def format_json(report: RunReport | MultiScriptReport) -> str:
    """Format the report as structured JSON."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def write_github_step_summary(
    report_or_content: RunReport | MultiScriptReport | str,
    script_path: str = "",
) -> bool:
    """Write markdown report to $GITHUB_STEP_SUMMARY if present in environment."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return False

    try:
        if isinstance(report_or_content, str):
            content = report_or_content
        elif isinstance(report_or_content, MultiScriptReport):
            content = format_multi_github_summary(report_or_content)
        else:
            content = format_github_summary(report_or_content, script_path=script_path)

        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")
        return True
    except Exception:
        return False
