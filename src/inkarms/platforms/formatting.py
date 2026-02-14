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

    # Escape raw HTML entities in the source so markdown-it treats them as text.
    # We only escape bare & < > that aren't already part of markdown syntax.
    # markdown-it handles this internally, so we just render.
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
    """Replace <hr> with text separator."""
    return re.sub(r"<hr\s*/?>", "---", text)


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
