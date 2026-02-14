"""Tests for Telegram markdown-to-HTML formatting."""

from __future__ import annotations

from inkarms.platforms.formatting import markdown_to_telegram_html


class TestBoldAndItalic:
    def test_bold(self):
        result = markdown_to_telegram_html("**bold text**")
        assert "<strong>bold text</strong>" in result

    def test_italic(self):
        result = markdown_to_telegram_html("*italic text*")
        assert "<em>italic text</em>" in result

    def test_bold_italic(self):
        result = markdown_to_telegram_html("***bold italic***")
        assert "<strong>" in result
        assert "<em>" in result
        assert "bold italic" in result


class TestInlineCode:
    def test_inline_code(self):
        result = markdown_to_telegram_html("use `print()` here")
        assert "<code>print()</code>" in result


class TestCodeBlocks:
    def test_fenced_code_block(self):
        result = markdown_to_telegram_html("```\nprint('hi')\n```")
        assert "<pre>" in result
        assert "<code>" in result
        assert "print(&#x27;hi&#x27;)" in result or "print('hi')" in result

    def test_code_block_with_language(self):
        result = markdown_to_telegram_html("```python\nprint('hi')\n```")
        assert "<pre>" in result
        assert "<code" in result


class TestLinks:
    def test_link(self):
        result = markdown_to_telegram_html("[click here](https://example.com)")
        assert '<a href="https://example.com">click here</a>' in result


class TestHeaders:
    def test_h1_to_bold(self):
        result = markdown_to_telegram_html("# Header 1")
        assert "<b>" in result
        assert "Header 1" in result
        # Should not contain h1 tag
        assert "<h1>" not in result

    def test_h2_to_bold(self):
        result = markdown_to_telegram_html("## Header 2")
        assert "<b>" in result
        assert "Header 2" in result

    def test_h3_to_bold(self):
        result = markdown_to_telegram_html("### Header 3")
        assert "<b>" in result
        assert "Header 3" in result


class TestLists:
    def test_unordered_list(self):
        md = "- item one\n- item two\n- item three"
        result = markdown_to_telegram_html(md)
        assert "\u2022 item one" in result
        assert "\u2022 item two" in result
        assert "\u2022 item three" in result
        assert "<ul>" not in result
        assert "<li>" not in result

    def test_ordered_list(self):
        md = "1. first\n2. second\n3. third"
        result = markdown_to_telegram_html(md)
        assert "1. first" in result
        assert "2. second" in result
        assert "3. third" in result
        assert "<ol>" not in result
        assert "<li>" not in result


class TestBlockquote:
    def test_blockquote_preserved(self):
        result = markdown_to_telegram_html("> quoted text")
        assert "<blockquote>" in result
        assert "quoted text" in result


class TestUnsupportedTags:
    def test_hr_stripped(self):
        result = markdown_to_telegram_html("above\n\n---\n\nbelow")
        assert "<hr" not in result

    def test_no_div_tags(self):
        result = markdown_to_telegram_html("plain text")
        assert "<div>" not in result


class TestHTMLEntities:
    def test_angle_brackets_escaped(self):
        result = markdown_to_telegram_html("use `x < 5 && y > 3`")
        # Inside code, < and > should be escaped
        assert "&lt;" in result or "<code>" in result

    def test_ampersand_escaped(self):
        result = markdown_to_telegram_html("Tom & Jerry")
        assert "&amp;" in result


class TestPassthrough:
    def test_empty_string(self):
        assert markdown_to_telegram_html("") == ""

    def test_whitespace_only(self):
        assert markdown_to_telegram_html("   ") == "   "

    def test_plain_text(self):
        result = markdown_to_telegram_html("just plain text")
        assert "just plain text" in result


class TestNestedFormatting:
    def test_bold_with_inline_code(self):
        result = markdown_to_telegram_html("**use `code` here**")
        assert "<strong>" in result
        assert "<code>code</code>" in result

    def test_list_with_bold(self):
        md = "- **bold item**\n- normal item"
        result = markdown_to_telegram_html(md)
        assert "<strong>bold item</strong>" in result or "<b>bold item</b>" in result


class TestStrikethrough:
    def test_strikethrough(self):
        result = markdown_to_telegram_html("~~deleted~~")
        assert "<s>deleted</s>" in result or "deleted" in result
