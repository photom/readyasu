#!/usr/bin/env python3
"""Shared text handling for the yomiyasu-en checks.

Reads UTF-8 text, splits Markdown into blocks, masks code and URLs, splits
English sentences, and loads word lists. Standard library only; Python 3.9+.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__version__ = "0.1.0"

SKILL_DIR = Path(__file__).resolve().parent.parent
LISTS_DIR = SKILL_DIR / "references" / "lists"
WORDS_DIR_NAME = ".yomiyasu-en-words"
STATE_DIR_NAME = ".yomiyasu-en"
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
        raise InputError(f"{label} is not valid UTF-8 (byte {exc.start}).") from exc


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_newlines(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- masking

_INLINE_CODE = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_URL = re.compile(r"(?:https?://|ftp://|www\.)[^\s<>()\[\]]+[^\s<>()\[\].,;:!?'\"]")
_AUTOLINK = re.compile(r"<(?:https?://|mailto:)[^>\s]+>")
_LINK_DEST = re.compile(r"\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"]*\")?\)")
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def protected_spans(text: str) -> list[tuple[int, int, str]]:
    """Spans that must not change: inline code, URLs, autolinks, link targets, e-mail."""
    spans: list[tuple[int, int, str]] = []
    taken = [False] * (len(text) + 1)

    def add(pattern: re.Pattern[str], kind: str) -> None:
        for m in pattern.finditer(text):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            spans.append((m.start(), m.end(), kind))

    add(_INLINE_CODE, "code")
    add(_AUTOLINK, "url")
    add(_LINK_DEST, "url")
    add(_URL, "url")
    add(_EMAIL, "url")
    add(_HTML_TAG, "html")
    spans.sort()
    return spans


def mask(text: str) -> str:
    """Replace protected spans with spaces, keeping offsets."""
    if "`" not in text and "://" not in text and "www." not in text and "@" not in text \
            and "](" not in text and "<" not in text:
        return text
    chars = list(text)
    for start, end, _kind in protected_spans(text):
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


# ---------------------------------------------------------------- markdown

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])(?:[ \t]+(?:\[[ xX]\][ \t]+)?|$)")
_QUOTE = re.compile(r"^ {0,3}>")
_RULE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")


@dataclass
class Line:
    no: int
    raw: str
    kind: str  # blank code fence heading list quote table para html front rule
    content: str = ""
    offset: int = 0  # index in raw where content starts
    masked: str = ""
    continuation: bool = False  # para line that continues a list item


@dataclass
class Block:
    kind: str  # para heading list table
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
            text = line.masked if masked else line.content
            text = text.strip()
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


def classify(text: str) -> list[Line]:
    """Classify each line of a Markdown document."""
    raw_lines = text.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
    lines: list[Line] = []
    in_fence: Optional[str] = None
    in_html_comment = False
    in_front = False
    in_list = False
    prev_kind = "blank"
    for index, raw in enumerate(raw_lines):
        no = index + 1
        stripped = raw.strip()
        if index == 0 and stripped == "---":
            in_front = True
            lines.append(Line(no, raw, "front"))
            continue
        if in_front:
            lines.append(Line(no, raw, "front"))
            if stripped in ("---", "..."):
                in_front = False
            continue
        if in_fence is not None:
            lines.append(Line(no, raw, "code"))
            m = _FENCE.match(raw)
            if m and m.group(1)[0] == in_fence[0] and len(m.group(1)) >= len(in_fence) \
                    and not m.group(2).strip():
                lines[-1].kind = "fence"
                in_fence = None
            continue
        if in_html_comment:
            lines.append(Line(no, raw, "html"))
            if "-->" in raw:
                in_html_comment = False
            continue
        m = _FENCE.match(raw)
        if m:
            in_fence = m.group(1)
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
        if raw.startswith(("    ", "\t")) and prev_kind in ("blank", "code") and not in_list:
            lines.append(Line(no, raw, "code"))
            prev_kind = "code"
            continue
        sm = _SETEXT.match(raw)
        if sm and prev_kind == "para" and lines and not lines[-1].continuation:
            lines[-1].kind = "heading"
            lines.append(Line(no, raw, "rule"))
            prev_kind = "rule"
            continue
        if _RULE.match(raw):
            lines.append(Line(no, raw, "rule"))
            prev_kind = "rule"
            in_list = False
            continue
        hm = _HEADING.match(raw)
        if hm:
            content = hm.group(2) or ""
            offset = raw.find(content) if content else len(raw)
            lines.append(Line(no, raw, "heading", content, offset))
            prev_kind = "heading"
            in_list = False
            continue
        if _QUOTE.match(raw):
            lines.append(Line(no, raw, "quote", re.sub(r"^\s*(>\s?)+", "", raw)))
            prev_kind = "quote"
            continue
        if stripped.startswith("|") or (prev_kind == "table" and "|" in stripped) or \
                (_TABLE_SEP.match(raw) and prev_kind == "para" and "|" in raw):
            if _TABLE_SEP.match(raw) and prev_kind == "para" and lines:
                lines[-1].kind = "table"
            kind = "table"
            lines.append(Line(no, raw, kind, raw.strip()))
            prev_kind = "table"
            continue
        if stripped.startswith("<") and _HTML_TAG.match(stripped) and stripped.endswith(">"):
            lines.append(Line(no, raw, "html"))
            prev_kind = "html"
            continue
        lm = _LIST.match(raw)
        if lm:
            content = raw[lm.end():]
            lines.append(Line(no, raw, "list", content, lm.end()))
            prev_kind = "list"
            in_list = True
            continue
        cont = in_list and prev_kind in ("list", "para") and (raw.startswith((" ", "\t")) or prev_kind == "list")
        line = Line(no, raw, "para", raw.lstrip(), len(raw) - len(raw.lstrip()))
        line.continuation = cont
        lines.append(line)
        if not cont:
            in_list = False
        prev_kind = "para"
    for line in lines:
        if line.kind == "table":
            line.content = line.raw.strip()
            line.offset = len(line.raw) - len(line.raw.lstrip())
        line.masked = mask(line.content)
    return lines


def blocks(lines: list[Line]) -> list[Block]:
    """Group lines into paragraph, heading, list-item and table-row blocks."""
    result: list[Block] = []
    current: Optional[Block] = None
    for line in lines:
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
        if line.kind == "heading":
            result.append(Block("heading", [line]))
        elif line.kind == "table":
            if not _TABLE_SEP.match(line.raw):
                result.append(Block("table", [line]))
        current = None
    return result


_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "prof", "inc", "ltd", "co", "jr", "sr",
    "st", "no", "fig", "eq", "approx", "cf", "al", "dept", "est", "u.s", "u.k", "a.m", "p.m",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "vol",
    "pp", "ch", "sec", "min", "max", "ref", "e.g.,", "corp",
}
_BOUNDARY = re.compile(r"([.!?]+|\.\.\.|…)([\"'”’)\]*_]*)(\s+|$)")
_NEXT_START = re.compile(r"[\s]*[\"'“‘(\[*_]*[A-Z0-9#`]")


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of English sentences in text."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        end = m.end(2)
        punct = m.group(1)
        before = text[start:m.start()]
        if not before.strip():
            continue
        if m.end() < len(text):
            if not _NEXT_START.match(text, m.end()):
                if "\n" not in m.group(3):
                    continue
        if punct == ".":
            word = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
            if word:
                w = word.group(1).lower()
                if w in _ABBREVIATIONS or (len(w) == 1 and w.isalpha() and word.group(1).isupper()):
                    if m.end() < len(text):
                        continue
            if re.search(r"\d$", before) and m.end() < len(text) and text[m.end():m.end() + 1].isdigit():
                continue
        if punct in ("...", "…") and m.end() < len(text):
            nxt = text[m.end():m.end() + 1]
            if not nxt.isupper():
                continue
        spans.append((start, end))
        start = m.end()
    if text[start:].strip():
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


def parse(text: str) -> Document:
    lines = classify(text)
    blks = blocks(lines)
    sents: list[Sentence] = []
    for bi, block in enumerate(blks):
        masked, starts = block.joined(True)
        plain, _ = block.joined(False)
        if block.kind in ("heading", "table"):
            spans = [(0, len(masked))] if masked.strip() else []
        else:
            spans = split_sentences(masked)
        for s, e in spans:
            line_no = starts[0][1]
            for pos, no in starts:
                if pos <= s:
                    line_no = no
            sents.append(Sentence(plain[s:e].replace("\n", " "), masked[s:e].replace("\n", " "),
                                  line_no, block.kind, bi))
    return Document(text, lines, blks, sents)


# ---------------------------------------------------------------- word lists


def phrase_regex(phrase: str) -> str:
    """Turn a list phrase into a regex: spaces match whitespace, a trailing * matches a word suffix."""
    words = phrase.strip().split()
    parts = []
    for word in words:
        star = word.endswith("*")
        core = word[:-1] if star else word
        piece = re.escape(core).replace("’", "['’]").replace("'", "['’]").replace("\\'", "['’]")
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

    def allowed(self, text: str) -> bool:
        low = text.strip().lower()
        return any(low == a.lower() for a in self.allow)


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
_EMOJI_EXCLUDE = {0x2190, 0x2191, 0x2192, 0x2193, 0x2194, 0x21D2, 0x21D4, 0x2022}


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    if cp in _EMOJI_EXCLUDE:
        return False
    if 0x2190 <= cp <= 0x21FF:
        return False
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def emoji_in(text: str) -> list[str]:
    found: list[str] = []
    for ch in text:
        if is_emoji(ch):
            found.append(ch)
    return found


def display_width_cut(text: str, limit: int = 100) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


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
