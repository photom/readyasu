#!/usr/bin/env python3
"""Shared text handling for the readyasu checks.

Reads UTF-8 text, splits Markdown into blocks, masks code and URLs, splits
English sentences, and loads word lists. Standard library only; Python 3.9+.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import bisect
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__version__ = "0.1.0"

SKILL_DIR = Path(__file__).resolve().parent.parent
LISTS_DIR = SKILL_DIR / "references" / "lists"
WORDS_DIR_NAME = ".readyasu-words"
STATE_DIR_NAME = ".readyasu"
DOC_TYPES = (
    "pr", "article", "incident", "proposal", "minutes", "manual", "slides",
    "essay", "formal", "promo", "mail", "paper", "script",
)
READERS = ("expert", "informed", "general")
STANCES = ("recommend", "rule", "explain")
MAX_WORD_LINES = 10000
MAX_REPLACEMENT = 80


class InputError(Exception):
    """A usage or input problem; the scripts exit with code 2."""


# ---------------------------------------------------------------- reading


def read_text(name: str, stdin_text: Optional[str] = None) -> str:
    """Read a UTF-8 file (or standard input for "-") and normalize newlines."""
    if name == "-":
        if stdin_text is not None:
            data = stdin_text
        else:
            raw = sys.stdin.buffer.read()
            data = decode(raw, "standard input")
    else:
        path = Path(name)
        if not path.is_file():
            raise InputError(f"Cannot open {name}: not a file.")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise InputError(f"Cannot read {name}: {exc.strerror or exc}.") from exc
        data = decode(raw, name)
    return normalize_newlines(data)


def decode(raw: bytes, label: str) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = raw.count(b"\n", 0, exc.start) + 1
        raise InputError(f"{label} is not valid UTF-8 (line {line}, byte {exc.start}).") from exc


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def canonical(text: str) -> str:
    """The form that is hashed: newlines normalized, leading and trailing blank lines removed, one final newline."""
    return normalize_newlines(text).strip("\n") + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(canonical(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- masking

_TICKS = re.compile(r"`+")
# GitHub autolinks do not end with punctuation or emphasis markers (*, _, ~).
_URL = re.compile(r"(?<![A-Za-z0-9_.-])(?:https?://|ftp://|www\.)[^\s<>()\[\]]+[^\s<>()\[\].,;:!?'\"*_~]")
_AUTOLINK = re.compile(r"<(?:https?://|mailto:)[^>\s]+>")
_LINK_DEST = re.compile(r"\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"]*\")?\)")
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
# The lookbehind keeps the scan linear on long dotted tokens.
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def code_spans(text: str, comments: bool = True) -> list[tuple[int, int, str]]:
    """Inline code ("code") and HTML comments ("html", only if comments is True), in order.

    As in CommonMark, a run of backticks opens a code span that ends at the next run of the same length; a run
    with no such partner is literal text. Whichever starts first wins, so `<!--` in code is code and a backtick
    inside a comment opens nothing. An unclosed comment runs to the end of the text. Linear time.
    """
    runs = [(m.start(), m.end()) for m in _TICKS.finditer(text)] if "`" in text else []
    by_length: dict[int, list[int]] = {}
    for k, (s, e) in enumerate(runs):
        by_length.setdefault(e - s, []).append(k)
    pointer = dict.fromkeys(by_length, 0)
    comments = comments and "<!--" in text
    spans: list[tuple[int, int, str]] = []
    pos = 0
    k = 0
    comment = text.find("<!--") if comments else -1
    while True:
        while k < len(runs) and runs[k][0] < pos:
            k += 1
        if comment >= 0 and comment < pos:
            comment = text.find("<!--", pos)
        if k < len(runs) and (comment < 0 or runs[k][0] < comment):
            s, e = runs[k]
            same = by_length[e - s]
            p = pointer[e - s]
            while p < len(same) and same[p] <= k:
                p += 1
            pointer[e - s] = p
            if p < len(same):
                spans.append((s, runs[same[p]][1], "code"))
                pos = runs[same[p]][1]
            else:
                pos = e
            k += 1
        elif comment >= 0:
            close = text.find("-->", comment + 4)
            end = len(text) if close < 0 else close + 3
            spans.append((comment, end, "html"))
            pos = end
        else:
            return spans


def protected_spans(text: str) -> list[tuple[int, int, str]]:
    """Spans that must not change: inline code, URLs, autolinks, link targets, e-mail, HTML tags and comments."""
    spans = code_spans(text)
    taken = [False] * (len(text) + 1)
    for start, end, _kind in spans:
        for i in range(start, end):
            taken[i] = True

    def add(pattern: re.Pattern[str], kind: str) -> None:
        for m in pattern.finditer(text):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            spans.append((m.start(), m.end(), kind))

    add(_AUTOLINK, "url")
    add(_LINK_DEST, "url")
    add(_URL, "url")
    if "@" in text:
        add(_EMAIL, "url")
    add(_HTML_TAG, "html")
    spans.sort()
    return spans


def _may_protect(text: str) -> bool:
    return "`" in text or "://" in text or "www." in text or "@" in text or "](" in text or "<" in text


def mask(text: str, fill: str = " ") -> str:
    """Replace protected spans with fill characters (spaces by default), keeping offsets."""
    if not _may_protect(text):
        return text
    chars = list(text)
    for start, end, _kind in protected_spans(text):
        for i in range(start, end):
            chars[i] = fill
    return "".join(chars)


SPLIT_FILL = "X"


def split_view(text: str) -> str:
    """The text that sentences are split on: inline code, URLs and e-mail become "X", HTML tags and comments spaces.

    Code or a URL at the start of a sentence then counts as a capitalized word, so the sentence before it ends
    there, and code at either end of a sentence stays in the sentence. Tags and comments stay separators.
    """
    if not _may_protect(text):
        return text
    chars = list(text)
    for start, end, kind in protected_spans(text):
        fill = " " if kind == "html" else SPLIT_FILL
        for i in range(start, end):
            chars[i] = fill
    return "".join(chars)


# ---------------------------------------------------------------- markdown

_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_LIST_FENCE = re.compile(r"^([ \t]{0,12})(`{3,}|~{3,})(.*)$")
_EMOJI_CLASS = "\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u231A\u231B\u23E9-\u23FA\u2139"
_CALLOUT_EMOJI = "(?:[" + _EMOJI_CLASS + "]\uFE0F?\\s*)?"
# A callout starts with [!TYPE] or a label (**Note:**, *Tip:*, Warning:), optionally after an emoji, which may
# also sit inside the emphasis (**⚠️ Warning:**).
_CALLOUT = re.compile(
    r"^\s*" + _CALLOUT_EMOJI +
    r"(?:\[![A-Za-z]+\]|(?:\*\*|__|\*|_)?" + _CALLOUT_EMOJI +
    r"(?:note|warning|tip|important|caution|info|danger|attention)\b[^\n]{0,3}?(?::|\*\*|__|\*|_))", re.IGNORECASE)
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*))?$")
_LIST = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])(?:[ \t]+(?:\[[ xX]\][ \t]+)?|$)")
_QUOTE = re.compile(r"^ {0,3}>")
_QUOTE_PREFIX = re.compile(r"^\s*(?:>\s?)+")
_RULE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
# No two optional whitespace runs touch, so long runs of spaces do not backtrack.
_TABLE_SEP = re.compile(r"^[ \t]*(?:\|[ \t]*)?:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)*(?:\|[ \t]*)?$")
# CommonMark HTML blocks: block-level tags start a block anywhere; any other tag only when it is
# alone on the line and does not continue a paragraph.
_HTML_BLOCK = re.compile(
    r"^ {0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|"
    r"dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|"
    r"iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|pre|script|search|section|"
    r"style|summary|table|tbody|td|textarea|tfoot|th|thead|title|tr|track|ul)(?=[\s/>]|$)", re.IGNORECASE)
_HTML_ALONE = re.compile(r"^ {0,3}(?:<[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>|</[A-Za-z][A-Za-z0-9-]*\s*>)\s*$")


@dataclass
class Line:
    no: int
    raw: str
    kind: str  # blank code fence heading list quote table para html front rule
    content: str = ""
    offset: int = 0  # index in raw where content starts
    masked: str = ""
    continuation: bool = False  # para line that continues a list item
    level: int = 0  # heading level, 1 to 6
    quoted: bool = False  # code or fence line inside a block quote


@dataclass
class Block:
    kind: str  # para heading list table quote callout
    lines: list[Line] = field(default_factory=list)

    @property
    def first_line(self) -> int:
        return self.lines[0].no

    def joined(self, masked: bool = True) -> tuple[str, list[tuple[int, int]]]:
        """Joined text and a map of (start offset, line number)."""
        parts: list[str] = []
        starts: list[tuple[int, int]] = []
        pos = 0
        for line in self.lines:
            content = line.content
            left = len(content) - len(content.lstrip())
            right = len(content.rstrip())
            text = (line.masked if masked else content)[left:right]
            starts.append((pos, line.no))
            parts.append(text)
            pos += len(text) + 1
        return "\n".join(parts), starts


@dataclass
class Sentence:
    text: str  # original text (unmasked)
    masked: str
    line: int
    kind: str  # block kind
    block_index: int
    start: int = 0  # offset in the block's joined text


def _content_indent(raw: str, lm: re.Match[str]) -> int:
    """Column where a list item's content starts (CommonMark: marker plus 1 to 4 spaces)."""
    marker_end = lm.end(2)
    rest = raw[marker_end:]
    spaces = len(rest) - len(rest.lstrip(" \t"))
    width = len(raw[:marker_end].expandtabs(4))
    if not rest.strip() or not 1 <= spaces <= 4:
        return width + 1
    return width + spaces


def _heading_parts(raw: str, hm: re.Match[str]) -> tuple[str, int]:
    """Heading text without the optional closing #s (which need a space before them), and its offset."""
    if hm.group(2) is None:
        return "", len(raw)
    body = hm.group(2).rstrip()
    i = len(body)
    while i > 0 and body[i - 1] == "#":
        i -= 1
    if i < len(body) and (i == 0 or body[i - 1] in " \t"):
        body = body[:i].rstrip()
    return body, (hm.start(2) if body else len(raw))


def _opens_comment(text: str) -> bool:
    """True if text starts an HTML comment that does not close on the same line (outside inline code)."""
    if "<!--" not in text:
        return False
    return any(kind == "html" and text.find("-->", start + 4, end) < 0 for start, end, kind in code_spans(text))


def _closes_fence(text: str, fence: str, indent: int) -> bool:
    m = _LIST_FENCE.match(text)
    return bool(m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence)
                and not m.group(3).strip() and len(m.group(1).expandtabs(4)) <= indent + 3)


_YAML_KEY = re.compile(r"^\s*(?:#|-(?:\s|$)|[^\s:#][^:]*:(?:\s|$))")
_TOML_KEY = re.compile(r"^\s*(?:#|\[|[\w\"'.-]+\s*=)")


def _front_matter_end(raw_lines: list[str]) -> int:
    """Index of the line that closes front matter starting on line 1, or -1.

    Front matter needs a closing line and a second line that is a key, a comment or (YAML) a list item, so a
    document that starts with a thematic break ("---" then a blank line or a paragraph) is not swallowed.
    """
    if len(raw_lines) < 2:
        return -1
    first = raw_lines[0].strip()
    if first not in ("---", "+++"):
        return -1
    key = _YAML_KEY if first == "---" else _TOML_KEY
    if not key.match(raw_lines[1]) and raw_lines[1].strip() != first:
        return -1
    ends = ("---", "...") if first == "---" else ("+++",)
    for index in range(1, len(raw_lines)):
        if raw_lines[index].strip() in ends:
            return index
    return -1


def _indent(raw: str) -> int:
    return len(raw[:len(raw) - len(raw.lstrip())].expandtabs(4))


def _close_items(items: list[int], indent: int) -> None:
    """End the open list items whose content starts to the right of indent."""
    while items and items[-1] > indent:
        items.pop()


def classify(text: str) -> list[Line]:
    """Classify each line of a Markdown document."""
    raw_lines = text.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
    lines: list[Line] = []
    in_fence: Optional[str] = None
    fence_indent = 0
    in_html_comment = False
    front_end = _front_matter_end(raw_lines)
    items: list[int] = []  # content columns of the open list items, outermost first
    quote_fence: Optional[str] = None
    quote_fence_indent = 0
    quote_para = False  # the previous line is paragraph text inside a block quote
    prev_kind = "blank"
    for index, raw in enumerate(raw_lines):
        no = index + 1
        stripped = raw.strip()
        if index <= front_end:
            lines.append(Line(no, raw, "front"))
            continue
        if in_fence is not None:
            lines.append(Line(no, raw, "code"))
            if _closes_fence(raw, in_fence, fence_indent):
                lines[-1].kind = "fence"
                in_fence = None
                prev_kind = "fence"
            continue
        if not in_html_comment and lines and lines[-1].kind in ("para", "list", "heading", "table") \
                and _opens_comment(lines[-1].content):
            in_html_comment = True  # a comment that starts mid-line hides the following lines
        if in_html_comment:
            lines.append(Line(no, raw, "html"))
            if "-->" in raw:
                in_html_comment = False
            quote_para = False
            continue
        indent = _indent(raw)
        # The previous line is paragraph text in a list item, so this line may continue it lazily.
        lazy_item = bool(items) and prev_kind in ("list", "para")
        if _QUOTE.match(raw):
            _close_items(items, indent)
            content = _QUOTE_PREFIX.sub("", raw, count=1)
            prev_kind = "quote"
            if quote_fence is not None:
                closing = _closes_fence(content, quote_fence, quote_fence_indent)
                lines.append(Line(no, raw, "fence" if closing else "code", quoted=True))
                if closing:
                    quote_fence = None
                quote_para = False
                continue
            m = _LIST_FENCE.match(content)
            if m and not ("`" in m.group(3) and m.group(2)[0] == "`"):
                quote_fence = m.group(2)
                quote_fence_indent = len(m.group(1).expandtabs(4))
                lines.append(Line(no, raw, "fence", quoted=True))
                quote_para = False
                continue
            lines.append(Line(no, raw, "quote", content, len(raw) - len(content)))
            quote_para = bool(content.strip()) and not _HEADING.match(content) and not _RULE.match(content)
            continue
        quote_fence = None  # a fence inside a block quote ends with the quote
        lazy_quote = quote_para and prev_kind == "quote"
        quote_para = False
        m = _FENCE.match(raw) or (_LIST_FENCE.match(raw) if items else None)
        if m and items:
            # Inside a list item a fence may be indented at most three columns past the item's content; four or
            # more after a blank line is indented code (checked below), and after text it continues the text.
            inner = next((column for column in reversed(items) if column <= indent), 0)
            if indent - inner > 3:
                m = None
        if m and not ("`" in m.group(3) and m.group(2)[0] == "`"):
            _close_items(items, indent)
            in_fence = m.group(2)
            fence_indent = len(m.group(1).expandtabs(4))
            lines.append(Line(no, raw, "fence"))
            prev_kind = "code"
            continue
        if stripped.startswith("<!--"):
            lines.append(Line(no, raw, "html"))
            if "-->" not in stripped[4:]:
                in_html_comment = True
            continue
        if not stripped:
            lines.append(Line(no, raw, "blank"))
            prev_kind = "blank"
            continue
        if raw.startswith(("    ", "\t")) and prev_kind in ("blank", "code", "fence"):
            # Indented code needs four columns more than the content of the list item it is in.
            _close_items(items, indent)
            if not items or indent >= items[-1] + 4:
                lines.append(Line(no, raw, "code"))
                prev_kind = "code"
                continue
        sm = _SETEXT.match(raw)
        if sm and prev_kind == "para" and lines and not lines[-1].continuation:
            lines[-1].kind = "heading"
            lines[-1].level = 1 if sm.group(1)[0] == "=" else 2
            lines.append(Line(no, raw, "rule"))
            prev_kind = "rule"
            continue
        if _RULE.match(raw):
            _close_items(items, indent)
            lines.append(Line(no, raw, "rule"))
            prev_kind = "rule"
            continue
        hm = _HEADING.match(raw)
        if hm:
            _close_items(items, indent)
            content, offset = _heading_parts(raw, hm)
            lines.append(Line(no, raw, "heading", content, offset, level=len(hm.group(1))))
            prev_kind = "heading"
            continue
        if stripped.startswith("|") or (prev_kind == "table" and "|" in stripped) or \
                (prev_kind == "para" and "|" in raw and _TABLE_SEP.match(raw)):
            _close_items(items, indent)
            if prev_kind == "para" and lines and _TABLE_SEP.match(raw):
                lines[-1].kind = "table"
            lines.append(Line(no, raw, "table", raw.strip()))
            prev_kind = "table"
            continue
        if _HTML_BLOCK.match(raw) or (prev_kind not in ("para", "list") and not lazy_quote
                                      and _HTML_ALONE.match(raw)):
            _close_items(items, indent)
            lines.append(Line(no, raw, "html"))
            prev_kind = "html"
            continue
        lm = _LIST.match(raw)
        if lm and prev_kind == "para" and not items:
            # CommonMark: a list interrupts a paragraph only with a bullet or "1." and some text, so a wrapped line
            # that starts with "1998. It now employs" continues the paragraph.
            marker = lm.group(2)
            if not raw[lm.end():].strip() or (marker[0].isdigit() and int(marker[:-1]) != 1):
                lm = None
        if lm:
            _close_items(items, indent)
            content = raw[lm.end():]
            lines.append(Line(no, raw, "list", content, lm.end()))
            prev_kind = "list"
            items.append(_content_indent(raw, lm))
            continue
        if lazy_quote:
            # CommonMark lazy continuation: an unprefixed line continues the quoted paragraph.
            lines.append(Line(no, raw, "quote", stripped, len(raw) - len(raw.lstrip())))
            prev_kind = "quote"
            quote_para = True
            continue
        # Text in a list item: a lazy continuation line of its paragraph, or a line indented at least as far as
        # the item's content (a later paragraph of the item, after a blank line or a fence).
        if not lazy_item:
            _close_items(items, indent)
        line = Line(no, raw, "para", raw.lstrip(), len(raw) - len(raw.lstrip()))
        line.continuation = bool(items)
        lines.append(line)
        prev_kind = "para"
    for line in lines:
        if line.kind == "table":
            line.content = line.raw.strip()
            line.offset = len(line.raw) - len(line.raw.lstrip())
        line.masked = mask(line.content)
    return lines


def _mask_block(block: Block) -> None:
    """Mask the block's joined text so that inline code spanning a line break is covered."""
    if len(block.lines) < 2:
        return
    plain, starts = block.joined(False)
    masked = mask(plain)
    for (pos, _no), line in zip(starts, block.lines):
        content = line.content
        left = len(content) - len(content.lstrip())
        right = len(content.rstrip())
        line.masked = content[:left] + masked[pos:pos + right - left] + content[right:]


def blocks(lines: list[Line]) -> list[Block]:
    """Group lines into paragraph, heading, list-item, table-row, quote and callout blocks."""
    result: list[Block] = []
    current: Optional[Block] = None
    container: Optional[str] = None  # "quote" or "callout" for the block quote being read
    for line in lines:
        if line.kind != "quote" and not line.quoted:
            container = None
        if line.quoted:
            current = None
            continue
        if line.kind == "para":
            if current is not None and current.kind in ("para", "list") and (
                    current.kind == "para" or line.continuation):
                current.lines.append(line)
                continue
            current = Block("para", [line])
            result.append(current)
            continue
        if line.kind == "list":
            current = Block("list", [line])
            result.append(current)
            continue
        if line.kind == "quote":
            if not line.content.strip():
                current = None
                continue
            if current is not None and current.kind in ("quote", "callout"):
                current.lines.append(line)
                continue
            if container != "callout":
                # A callout label starts a callout that runs to the end of the block quote,
                # across blank ">" lines and fenced code.
                container = "callout" if _CALLOUT.match(line.content) else "quote"
            current = Block(container, [line])
            result.append(current)
            continue
        if line.kind == "heading":
            result.append(Block("heading", [line]))
        elif line.kind == "table":
            if not _TABLE_SEP.match(line.raw):
                result.append(Block("table", [line]))
        current = None
    for block in result:
        _mask_block(block)
    return result


_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "prof", "inc", "ltd", "co", "jr", "sr",
    "st", "approx", "cf", "al", "dept", "u.s", "u.k", "a.m", "p.m", "e.g.,", "corp",
}
# Abbreviations that are also common words or that come before a number ("No. 5", "Fig. 3",
# "Dec. 5"): not a sentence end only when a digit follows.
_NUMBER_ABBREVIATIONS = {
    "no", "nos", "fig", "figs", "eq", "vol", "pp", "p", "ch", "sec", "ref", "min", "max", "est", "ca", "op",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
# Capitalized words that usually start a sentence, so "Plan B. It was cheaper." splits after "B.".
_SENTENCE_STARTERS = {
    "a", "an", "the", "it", "its", "this", "that", "these", "those", "there", "then", "they", "we", "he", "she",
    "i", "you", "our", "my", "his", "her", "their", "your", "in", "on", "at", "for", "but", "and", "so", "or",
    "if", "when", "after", "before", "now", "next", "also", "however", "as", "to", "with", "by", "from", "what",
    "why", "how", "who", "where", "which", "all", "some", "no", "yes", "one", "each", "both", "once", "while",
    "since", "because", "although", "finally", "first", "today", "here", "not", "only", "even", "still", "yet",
    "thus", "instead", "meanwhile", "later", "let", "please", "do", "is", "are", "was", "were", "see", "use",
}
_BOUNDARY = re.compile(r"([.!?]+|\.\.\.|…)([\"'”’)\]*_]*)(\s+|$)")
_OPENERS = re.compile(r"\s*[\"'“‘(\[*_]*")
_NEXT_WORD = re.compile(r"[\"'“‘(\[*_]*([^\W\d_][\w'’-]*)(\.?)")
_NONSPACE = re.compile(r"\S")


def _starts_sentence(text: str, pos: int) -> bool:
    """True if the text at pos (after spaces and opening quotes) starts with a capital, digit, # or `."""
    i = _OPENERS.match(text, pos)
    j = i.end() if i else pos
    if j >= len(text):
        return False
    ch = text[j]
    return ch.isupper() or ch.isdigit() or ch in "#`"


def _word_before(text: str, pos: int, start: int) -> str:
    """The ASCII word (dots allowed, as in "e.g") that ends at pos."""
    i = pos
    while i > start and ((text[i - 1].isascii() and text[i - 1].isalpha()) or text[i - 1] == "."):
        i -= 1
    while i < pos and text[i] == ".":
        i += 1
    return text[i:pos]


def _is_initial(text: str, pos: int) -> bool:
    """After "X.", True if the next word looks like the rest of a name ("John F. Kennedy", "J. R. Smith")."""
    m = _NEXT_WORD.match(text, pos)
    if not m:
        return False
    word = m.group(1)
    if len(word) == 1 and m.group(2):
        return True
    return word[0].isupper() and word.lower() not in _SENTENCE_STARTERS


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of English sentences in text."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        end = m.end(2)
        punct = m.group(1)
        if not _NONSPACE.search(text, start, m.start()):
            continue
        at_end = m.end() >= len(text)
        if not at_end and not _starts_sentence(text, m.end()) and "\n" not in m.group(3):
            continue
        if punct == "." and not at_end:
            word = _word_before(text, m.start(), start)
            following = text[m.end():m.end() + 1]
            if word:
                low = word.lower()
                if low in _ABBREVIATIONS or (low in _NUMBER_ABBREVIATIONS and following.isdigit()):
                    continue
                if len(word) == 1 and word.isupper() and _is_initial(text, m.end()):
                    continue
            if m.start() > 0 and text[m.start() - 1].isdigit() and following.isdigit():
                continue
        if punct in ("...", "…") and not at_end:
            if not text[m.end():m.end() + 1].isupper():
                continue
        spans.append((start, end))
        start = m.end()
    if _NONSPACE.search(text, start):
        spans.append((start, len(text)))
    result: list[tuple[int, int]] = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s < e:
            result.append((s, e))
    return result


@dataclass
class Document:
    text: str
    lines: list[Line]
    blocks: list[Block]
    sentences: list[Sentence]

    def prose_lines(self) -> list[Line]:
        return [ln for ln in self.lines if ln.kind in ("para", "list", "heading", "table")]


def sentence_spans(plain: str) -> list[tuple[int, int]]:
    """Sentence spans of a block's plain joined text, split on split_view (code and URLs count as words)."""
    return split_sentences(split_view(plain))


def parse(text: str) -> Document:
    lines = classify(text)
    blks = blocks(lines)
    sents: list[Sentence] = []
    for bi, block in enumerate(blks):
        masked, starts = block.joined(True)
        plain, _ = block.joined(False)
        positions = [pos for pos, _no in starts]
        if block.kind in ("heading", "table"):
            spans = [(0, len(masked))] if split_view(plain).strip() else []
        else:
            spans = sentence_spans(plain)
        for s, e in spans:
            line_no = starts[max(0, bisect.bisect_right(positions, s) - 1)][1]
            sents.append(Sentence(plain[s:e].replace("\n", " "), masked[s:e].replace("\n", " "),
                                  line_no, block.kind, bi, s))
    return Document(text, lines, blks, sents)


# ---------------------------------------------------------------- word lists


_APOSTROPHE = re.compile(r"\\?['’]")


def phrase_regex(phrase: str) -> str:
    """Turn a list phrase into a regex: spaces match whitespace, a trailing * matches a word suffix."""
    words = phrase.strip().split()
    parts = []
    for word in words:
        star = word.endswith("*")
        core = word[:-1] if star else word
        piece = _APOSTROPHE.sub("['’]", re.escape(core))  # one pass, so ’ and ' both work
        if star:
            piece += r"[\w’'-]*"
        parts.append(piece)
    body = r"\s+".join(parts)
    lead = r"(?<![\w-])" if words and re.match(r"\w", words[0]) else ""
    tail = r"(?![\w-])" if words and re.search(r"[\w]$", words[-1]) else ""
    if words and words[-1].endswith("*"):
        tail = ""
    return lead + body + tail


@dataclass
class ListEntry:
    phrase: str
    note: str
    pattern: re.Pattern[str]


def load_list(name: str) -> list[ListEntry]:
    """Load references/lists/<name>.txt: one phrase per line, optional TAB and note."""
    path = LISTS_DIR / f"{name}.txt"
    entries: list[ListEntry] = []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return entries
    for raw in content.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        phrase, _, note = raw.partition("\t")
        phrase = phrase.strip()
        if not phrase:
            continue
        entries.append(ListEntry(phrase, note.strip(), re.compile(phrase_regex(phrase), re.IGNORECASE)))
    return entries


# ---------------------------------------------------------------- project words


@dataclass
class Words:
    folder: Optional[Path] = None
    allow: list[str] = field(default_factory=list)
    flags: list[tuple[str, str, re.Pattern[str]]] = field(default_factory=list)  # name, replacement, regex
    digest: str = ""
    count: int = 0

    _allow_keys: frozenset[str] = field(default=frozenset(), repr=False, compare=False)
    _allow_size: int = field(default=-1, repr=False, compare=False)

    def allowed(self, text: str) -> bool:
        """True if text equals an allow.txt entry, ignoring case, apostrophe style and line breaks."""
        if not self.allow:
            return False
        if self._allow_size != len(self.allow):
            self._allow_keys = frozenset(normalize_phrase(a) for a in self.allow)
            self._allow_size = len(self.allow)
        return normalize_phrase(text) in self._allow_keys


def normalize_phrase(text: str) -> str:
    """Lower case, ’ as ', and single spaces: the form used to compare phrases."""
    return " ".join(text.replace("’", "'").replace("‘", "'").lower().split())


def git_top(start: Path) -> Optional[Path]:
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def main_checkout(top: Path) -> Optional[Path]:
    """For a linked worktree, the folder of the original checkout."""
    git = top / ".git"
    if not git.is_file():
        return None
    try:
        first = git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not first.startswith("gitdir:"):
        return None
    gitdir = Path(first[len("gitdir:"):].strip())
    if not gitdir.is_absolute():
        gitdir = (top / gitdir).resolve()
    common = gitdir / "commondir"
    try:
        common_dir = Path(common.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    if not common_dir.is_absolute():
        common_dir = (gitdir / common_dir).resolve()
    return common_dir.parent


def find_words_folder(cwd: Optional[Path] = None) -> Optional[Path]:
    base = (cwd or Path.cwd()).resolve()
    top = git_top(base) or base
    candidate = top / WORDS_DIR_NAME
    if candidate.is_dir():
        return candidate
    main = main_checkout(top)
    if main is not None and (main / WORDS_DIR_NAME).is_dir():
        return main / WORDS_DIR_NAME
    return None


def load_words(folder: Optional[str], no_words: bool) -> Words:
    """Load allow.txt, flag.txt and flag-patterns.txt. Raises InputError on bad content."""
    if folder is not None and no_words:
        raise InputError("Use either --words or --no-words, not both.")
    if no_words:
        return Words()
    if folder is not None:
        path = Path(folder)
        if not path.is_dir():
            raise InputError(f"The word-list folder {folder} does not exist.")
    else:
        found = find_words_folder()
        if found is None:
            return Words()
        path = found
    words = Words(folder=path.resolve())
    digest = hashlib.sha256()
    for name in ("allow.txt", "flag.txt", "flag-patterns.txt"):
        file = path / name
        if not file.is_file():
            continue
        try:
            raw = file.read_bytes()
        except OSError as exc:
            raise InputError(f"Cannot read {file}: {exc.strerror or exc}.") from exc
        content = normalize_newlines(decode(raw, str(file)))
        digest.update(name.encode() + b"\0" + content.encode("utf-8") + b"\0")
        rows = content.split("\n")
        if rows and rows[-1] == "":
            rows.pop()
        if len(rows) > MAX_WORD_LINES:
            raise InputError(f"{file} has more than {MAX_WORD_LINES} lines.")
        for number, row in enumerate(rows, 1):
            if not row.strip() or row.lstrip().startswith("#"):
                continue
            if name == "allow.txt":
                words.allow.append(row.strip())
            elif name == "flag.txt":
                if row.startswith("\t"):
                    continue
                cols = row.split("\t")
                if len(cols) > 2:
                    raise InputError(f"{file}:{number}: use at most one TAB (word<TAB>replacement).")
                word = cols[0].strip()
                replacement = cols[1].strip() if len(cols) == 2 else ""
                if len(replacement) > MAX_REPLACEMENT:
                    raise InputError(f"{file}:{number}: the replacement is longer than {MAX_REPLACEMENT} characters.")
                if word:
                    words.flags.append((word, replacement, re.compile(phrase_regex(word), re.IGNORECASE)))
            else:
                cols = row.split("\t")
                if len(cols) != 2 or not cols[0].strip() or not cols[1]:
                    raise InputError(f"{file}:{number}: write name<TAB>regex.")
                try:
                    pattern = re.compile(cols[1])
                except re.error as exc:
                    raise InputError(f"{file}:{number}: invalid regular expression ({exc}).") from exc
                words.flags.append((cols[0].strip(), "", pattern))
    words.count = len(words.allow) + len(words.flags)
    words.digest = digest.hexdigest() if words.count else ""
    return words


# ---------------------------------------------------------------- misc

_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x231A, 0x231B),
    (0x23E9, 0x23FA), (0x2190, 0x21FF), (0x1F1E6, 0x1F1FF),
)
# Symbols common in ordinary documents: arrows, bullets, check marks, ballot boxes and stars.
_EMOJI_EXCLUDE = {0x2022, 0x2605, 0x2606, 0x2610, 0x2611, 0x2612, 0x2713, 0x2717}


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    if cp in _EMOJI_EXCLUDE:
        return False
    if 0x2190 <= cp <= 0x21FF:
        return False
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


# One emoji as the reader sees it: a flag (two regional indicators), a keycap (1️⃣), or a symbol followed by
# variation selectors, skin-tone modifiers and tag characters, and joined to more symbols by ZWJ (👨‍👩‍👧).
_EMOJI_MODS = "\uFE0E\uFE0F\U0001F3FB-\U0001F3FF\U000E0020-\U000E007F"
_EMOJI_SYMBOL = "\u2190-\u2BFF\U0001F000-\U0001FAFF"
_EMOJI_CLUSTER = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}|[#*0-9]\uFE0F?\u20E3|[" + _EMOJI_SYMBOL + "])"
    "[" + _EMOJI_MODS + "]*"
    "(?:\u200D[" + _EMOJI_SYMBOL + "][" + _EMOJI_MODS + "]*)*")


def emoji_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each emoji in text; a flag, keycap, modified or ZWJ-joined emoji is one span."""
    found: list[tuple[int, int]] = []
    for m in _EMOJI_CLUSTER.finditer(text):
        first = m.group(0)[0]
        if first in "#*0123456789" or is_emoji(first):
            found.append((m.start(), m.end()))
    return found


def emoji_in(text: str) -> list[str]:
    """The emoji in text, one item per emoji as the reader sees it (see emoji_spans)."""
    return [text[s:e] for s, e in emoji_spans(text)]


def plural(n: int, word: str, many: str = "") -> str:
    """'1 line', '2 lines'."""
    return f"{n} {word if n == 1 else (many or word + 's')}"


def display_width_cut(text: str, limit: int = 100) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def excerpt(line: str, col: int, length: int = 1, limit: int = 160) -> str:
    """The line cut to about limit characters around the 1-based column col (and length characters after it)."""
    lead = len(line) - len(line.lstrip())
    text = line.strip()
    if len(text) <= limit:
        return text
    start = max(0, col - 1 - lead)
    center = start + min(max(length, 1), limit // 2) // 2
    left = max(0, min(center - limit // 2, len(text) - limit))
    right = left + limit
    shown = text[left:right].strip()
    return ("…" if left > 0 else "") + shown + ("…" if right < len(text) else "")


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
