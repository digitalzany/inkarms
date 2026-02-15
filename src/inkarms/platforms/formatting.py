"""Convert standard Markdown to Telegram-compatible HTML."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

# Telegram supports only these HTML tags
_ALLOWED_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "a", "blockquote", "span", "tg-spoiler", "tg-emoji",
})

_md = MarkdownIt("commonmark", {"html": False, "linkify": False})


def markdown_to_telegram_html(content: str) -> str:
    """Convert standard Markdown to Telegram-supported HTML.

    Uses markdown-it-py to parse Markdown, then post-processes the HTML
    to strip tags that Telegram doesn't support.

    Args:
        content: Standard Markdown text.

    Returns:
        HTML string safe for Telegram's HTML parse mode.
    """
    if not content or not content.strip():
        return content

    # Pre-process GFM tables (not supported by commonmark parser)
    content = _preprocess_tables(content)

    raw_html = _md.render(content)

    # Post-process unsupported tags
    result = _convert_headers(raw_html)
    result = _convert_lists(result)
    result = _convert_paragraphs(result)
    result = _convert_hr(result)
    result = _strip_unsupported_tags(result)

    # Clean up excessive blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _convert_headers(text: str) -> str:
    """Convert h1-h6 to bold text."""
    def _header_repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        return f"<b>{inner}</b>\n"

    return re.sub(r"<h[1-6]>(.*?)</h[1-6]>", _header_repl, text, flags=re.DOTALL)


def _convert_lists(text: str) -> str:
    """Convert <ul>/<ol> lists to plain text with bullets/numbers."""
    def _convert_ol(m: re.Match) -> str:
        items = re.findall(r"<li>(.*?)</li>", m.group(1), flags=re.DOTALL)
        lines = [f"{i + 1}. {item.strip()}" for i, item in enumerate(items)]
        return "\n".join(lines) + "\n"

    def _convert_ul(m: re.Match) -> str:
        items = re.findall(r"<li>(.*?)</li>", m.group(1), flags=re.DOTALL)
        lines = [f"\u2022 {item.strip()}" for item in items]
        return "\n".join(lines) + "\n"

    text = re.sub(r"<ol>(.*?)</ol>", _convert_ol, text, flags=re.DOTALL)
    text = re.sub(r"<ul>(.*?)</ul>", _convert_ul, text, flags=re.DOTALL)
    # Clean any remaining bare <li> tags
    text = re.sub(r"</?li>", "", text)
    return text


def _convert_paragraphs(text: str) -> str:
    """Strip <p> tags and ensure spacing."""
    text = re.sub(r"<p>", "", text)
    text = re.sub(r"</p>", "\n", text)
    return text


def _convert_hr(text: str) -> str:
    """Replace <hr> with visual text separator."""
    return re.sub(r"<hr\s*/?>", "——————————", text)


def _strip_unsupported_tags(text: str) -> str:
    """Remove HTML tags not supported by Telegram, preserving content.

    Keeps allowed tags (with attributes for <a> and <code>/<pre>),
    strips everything else.
    """
    def _tag_repl(m: re.Match) -> str:
        full = m.group(0)
        tag_name = m.group(1).lower().lstrip("/")
        if tag_name in _ALLOWED_TAGS:
            return full
        return ""

    return re.sub(r"<(/?\w[\w-]*)(?:\s[^>]*)?>", _tag_repl, text)


# ---------------------------------------------------------------------------
# GFM table pre-processing
# ---------------------------------------------------------------------------

_TABLE_SEP_RE = re.compile(r"^\|[\s:|\-]+\|$")


def _preprocess_tables(content: str) -> str:
    """Detect GFM tables in markdown and convert to code-fenced blocks.

    Since markdown-it commonmark doesn't parse tables, pipe-delimited tables
    pass through as raw text.  We detect them, parse the cells, align columns,
    and wrap the result in a code fence so it renders as ``<pre><code>`` which
    Telegram displays in monospace.
    """
    lines = content.split("\n")
    result: list[str] = []
    in_code_fence = False
    table_buf: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Track existing code fences — don't touch tables inside them
        if stripped.startswith("```"):
            if table_buf:
                result.extend(_format_table_block(table_buf))
                table_buf = []
            in_code_fence = not in_code_fence
            result.append(line)
            continue

        if in_code_fence:
            result.append(line)
            continue

        is_table_line = (
            len(stripped) >= 3
            and stripped[0] == "|"
            and stripped[-1] == "|"
            and stripped.count("|") >= 3
        )

        if is_table_line:
            table_buf.append(stripped)
        else:
            if table_buf:
                result.extend(_format_table_block(table_buf))
                table_buf = []
            result.append(line)

    if table_buf:
        result.extend(_format_table_block(table_buf))

    return "\n".join(result)


def _format_table_block(table_lines: list[str]) -> list[str]:
    """Convert raw GFM table lines into a code-fenced aligned table."""
    if len(table_lines) < 2:
        return table_lines

    # Parse rows, skipping the separator line (| --- | --- |)
    rows: list[list[str]] = []
    for line in table_lines:
        if _TABLE_SEP_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return table_lines

    # Calculate column widths
    num_cols = max(len(row) for row in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], len(cell))

    # Build aligned output
    output = ["```"]
    for row_idx, row in enumerate(rows):
        cells = []
        for i in range(num_cols):
            cell = row[i] if i < len(row) else ""
            cells.append(cell.ljust(col_widths[i]))
        output.append(" | ".join(cells))
        # Separator after header row
        if row_idx == 0 and len(rows) > 1:
            output.append("-+-".join("-" * w for w in col_widths))
    output.append("```")
    return output
