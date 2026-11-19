#!/usr/bin/env python3
"""readyasu lint: list English expressions and Markdown formatting worth reviewing.

Findings are places to review, not orders to change and not a quality score.
Standard library only; Python 3.9+.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import bisect
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, NoReturn, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import readyasu_text as tx  # noqa: E402

__version__ = tx.__version__
TOOL = "readyasu-lint"
JSON_FORMAT = 1

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}

RULES: dict[str, tuple[str, str]] = {
    "bold_unrendered": ("error", "bold markup that will not render"),
    "emoji": ("warn", "emoji"),
    "em_dash": ("warn", "dash used to splice or insert a clause"),
    "chat_residue": ("warn", "assistant chat left in the text"),
    "stock_phrase": ("warn", "stock opener, signpost or closer"),
    "hedge_stack": ("warn", "stacked hedges"),
    "heading_colon": ("warn", "heading that ends with a colon"),
    "bold_label_list": ("warn", "two or more items in a row that start with a bold label and colon"),
    "heavy_bold": ("warn", "many bold phrases in one paragraph"),
    "ai_vocabulary": ("info", "word far more frequent in AI text"),
    "wordy_phrase": ("info", "wordy phrase with a shorter form"),
    "metaphor_verb": ("info", "metaphorical verb for an ordinary event"),
    "intensifier": ("info", "intensifier"),
    "jargon": ("info", "corporate jargon"),
    "negative_contrast": ("info", "negative contrast (not X, but Y)"),
    "personification": ("info", "tool or idea given a will or feelings"),
    "self_answered_question": ("info", "self-answered question (The result? ...)"),
    "fragment_run": ("info", "three or more very short sentences in a row"),
    "count_announcement": ("info", "announcement of a count (three key points)"),
    "closing_summary": ("info", "closing summary heading"),
    "excess_list": ("info", "most of the text is bullet points"),
    "exclamation": ("info", "exclamation mark"),
    "sentence_start_repeat": ("info", "three or more sentences in a row start with the same word"),
    "decorative_colon": ("info", "paragraph that ends with a colon and nothing after it"),
    "project_term": ("info", "word from the project's flag list"),
}

EXEMPT: dict[str, tuple[str, ...]] = {
    "pr": ("excess_list",),
    "article": (),
    "incident": ("excess_list",),
    "proposal": (),
    "minutes": ("bold_label_list", "excess_list", "fragment_run"),
    "manual": ("excess_list",),
    "slides": ("bold_label_list", "excess_list", "fragment_run", "self_answered_question",
               "count_announcement", "closing_summary"),
    "essay": ("fragment_run", "exclamation"),
    "formal": (),
    "promo": ("emoji", "exclamation", "fragment_run", "self_answered_question"),
    "mail": ("emoji", "exclamation"),
    "paper": (),
    "script": ("fragment_run", "exclamation", "self_answered_question"),
}

# Word lists: (rule, list name, doc types that exempt findings from this list).
LIST_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("chat_residue", "chat-residue", ()),
    ("chat_residue", "closing-courtesies", ("mail",)),
    ("chat_residue", "chat-interjections", ("essay", "mail", "script")),
    ("stock_phrase", "stock-phrases", ()),
    ("ai_vocabulary", "ai-vocabulary", ()),
    ("wordy_phrase", "wordy-phrases", ()),
    ("metaphor_verb", "metaphor-verbs", ()),
    ("intensifier", "intensifiers", ()),
    ("jargon", "jargon", ()),
)
LIST_LABELS = {"closing-courtesies": "courtesies and offers", "chat-interjections": "interjections"}
# Lists whose matches inside double quotation marks are dialogue, not residue.
QUOTE_EXEMPT_LISTS = ("chat-interjections",)
LIST_RULE_NAMES = frozenset(rule for rule, _name, _types in LIST_RULES) | {"project_term"}

# Doc types that exempt part of a rule (the findings from some word lists).
PARTIAL_EXEMPT: dict[str, tuple[str, ...]] = {
    doc_type: tuple(sorted({rule for rule, _name, types in LIST_RULES if doc_type in types}))
    for doc_type in tx.DOC_TYPES if any(doc_type in types for _rule, _name, types in LIST_RULES)
}

KEPT_WORD_RULES = ("project_term", "ai_vocabulary", "metaphor_verb", "jargon")


def _partial_help() -> str:
    rows = []
    for doc_type in tx.DOC_TYPES:
        by_rule: dict[str, list[str]] = {}
        for rule, name, types in LIST_RULES:
            if doc_type in types:
                by_rule.setdefault(rule, []).append(f"{LIST_LABELS[name]} ({name}.txt)")
        for rule, parts in by_rule.items():
            rows.append(f"  {doc_type} also exempts {rule} for {' and '.join(parts)} only.")
    return "\n".join(rows)


HELP_EPILOG = """Rules exempted by --doc-type:
""" + "\n".join(f"  {k:<9} {', '.join(v) if v else 'none'}" for k, v in EXEMPT.items()) + "\n" + _partial_help() + """
  Interjections inside double quotation marks are not reported in any type.
Exempted findings do not count toward the review findings, --strict or --fail-on.

Exit codes:
  0  finished, and no --fail-on condition matched (findings or not)
  1  a --fail-on (or --strict) condition matched
  2  usage or input error (file cannot be read, not UTF-8, bad word list)"""


@dataclass
class Finding:
    line: int
    col: int
    rule: str
    severity: str
    message: str
    match: str
    text: str
    start: int = field(default=0, repr=False)
    end: int = field(default=0, repr=False)
    exempt_in: tuple[str, ...] = field(default=(), repr=False)  # doc types that exempt this finding
    block: int = field(default=-1, repr=False)


@dataclass
class LintResult:
    findings: list[Finding]
    exempted: list[Finding]
    doc_type: Optional[str]
    reader: Optional[str]
    words: tx.Words


# ---------------------------------------------------------------- helpers


def _line_text(doc: tx.Document, no: int) -> str:
    if 1 <= no <= len(doc.lines):
        return doc.lines[no - 1].raw
    return ""


def _show(text: str) -> str:
    """Text for a message or the match field: one line, single spaces."""
    return " ".join(text.split())


def _make(doc: tx.Document, rule: str, no: int, col: int, message: str, match: str,
          start: int = 0, end: int = 0, block: int = -1, exempt_in: tuple[str, ...] = ()) -> Finding:
    return Finding(no, col, rule, RULES[rule][0], message, _show(match), _line_text(doc, no),
                   start, end, exempt_in, block)


class _Locator:
    """Maps an offset in a block's joined text to (line number, 1-based column in the raw line)."""

    def __init__(self, block: tx.Block, starts: list[tuple[int, int]]) -> None:
        self.positions = [pos for pos, _no in starts]
        self.numbers = [no for _pos, no in starts]
        self.bases = [ln.offset + len(ln.content) - len(ln.content.lstrip()) for ln in block.lines]

    def __call__(self, offset: int) -> tuple[int, int]:
        i = max(0, bisect.bisect_right(self.positions, offset) - 1)
        return self.numbers[i], offset - self.positions[i] + self.bases[i] + 1


_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def _first_key(phrase: str) -> str:
    """The leading letters of a word-list phrase in lower case; every match of the phrase starts with them."""
    words = phrase.split()
    m = re.match(r"[a-z]+", words[0].lower()) if words else None
    return m.group(0) if m else ""


def _scan(pattern: re.Pattern[str], key: str, text: str, low: Optional[str]) -> Iterator[re.Match[str]]:
    """pattern.finditer(text), trying only the places where the phrase's first letters occur.

    low is text.lower() when it has the same length (else None). Scanning hundreds of case-insensitive
    phrase patterns over a long text is otherwise the slowest part of lint.
    """
    if not key or low is None:
        yield from pattern.finditer(text)
        return
    pos = low.find(key)
    while pos >= 0:
        m = pattern.match(text, pos)
        if m:
            yield m
            pos = low.find(key, max(m.end(), pos + 1))
        else:
            pos = low.find(key, pos + 1)


def _in_quotes(text: str, start: int, end: int) -> bool:
    """True if text[start:end] sits between double quotation marks in the same block."""
    before, after = text[:start], text[end:]
    if before.count('"') % 2 == 1 and '"' in after:
        return True
    return before.rfind("“") > before.rfind("”") and "”" in after


# ---------------------------------------------------------------- regex rules

_HEDGE_STACK = re.compile(
    r"\b(?:may|might|could|can|would)\s+(?:potentially|possibly|perhaps|conceivably|maybe)\b"
    r"|\b(?:possibly|perhaps|maybe)\s+(?:may|might|could)\b"
    # "it seems ... may": within one clause, and not ability ("could not").
    r"|\bit\s+(?:seems|appears)\s+(?:that\s+)?"
    r"(?:(?!\b(?:but|and|or|so|yet|because|although|though|while|whereas|if|when|unless)\b)[^.;:,!?\n]){0,40}?"
    r"\b(?:might|may|could(?!\s+not\b))\s+(?:possibly|potentially|perhaps)?"
    r"|\b(?:likely|probably)\s+(?:may|might|could)\b"
    r"|\bmight\s+(?:likely|probably)\b",
    re.IGNORECASE)

_NEG_BE = (r"(?:['’]s\s+not|\s+is\s+not|\s+was\s+not|\s+are\s+not|\s+were\s+not|['’]re\s+not|"
           r"\s+isn['’]t|\s+aren['’]t|\s+wasn['’]t|\s+weren['’]t)")
_NEG_CONTRAST = (
    re.compile(
        r"\b(?:(?:this|that|these|those|the|our|your|its|their|my)\s+[\w-]+(?:\s+[\w-]+)?|"
        r"it|this|that|these|they|which|he|she)" + _NEG_BE + r"\s+"
        r"(?:just\s+|only\s+|merely\s+|simply\s+|about\s+)?[^.;:!?\n]{1,80}?[,;—–]\s*"
        r"(?:it|this|that|they|he|she)(?:['’]s|\s+is|\s+was|\s+are|\s+were|['’]re)\b", re.IGNORECASE),
    re.compile(
        r"(?:^|(?<=[.!?]\s))(?:It|This|That|They|We|I|You|The\s+\w+(?:\s+\w+)?|What\s+\w+\s+\w+)"
        r"(?:\s+(?:isn['’]t|is\s+not|wasn['’]t|was\s+not|aren['’]t|are\s+not|weren['’]t|doesn['’]t|don['’]t|"
        r"didn['’]t)|['’]s\s+not|['’]re\s+not)\b"
        r"[^.!?\n]{0,80}\.\s+(?:It|This|That|They|We|You)(?:['’]s|\s+is|\s+was|\s+are|\s+were|['’]re|\s+needed|\s+need)\b"),
    re.compile(r"\bnot\s+(?:just|only|merely|simply)\b[^.;!?\n]{1,60}?,?\s*\bbut\s+(?:also\s+)?", re.IGNORECASE),
    re.compile(r"\b(?:doesn['’]t|don['’]t|didn['’]t|does\s+not|do\s+not|isn['’]t|aren['’]t)\s+(?:just|only|merely|simply)\s+"
               r"[^.;:!?\n]{1,60}?[,;—–]\s*(?:it|they|this|we|he|she)\b", re.IGNORECASE),
    re.compile(r"\b(?:isn['’]t|is\s+not)\s+(?:just\s+|really\s+)?about\b[^.;!?\n]{1,60}?[.;,—–]\s*"
               r"(?:it['’]s|it\s+is)\s+about\b", re.IGNORECASE),
)

_PERSON_SUBJECT = (r"(?:code|codebase|data|dataset|tool|system|function|method|class|logs?|architecture|design|"
                   r"framework|api|metrics?|numbers|graph|chart|compiler|tests?|errors?|repository|repo|pipeline|"
                   r"model|algorithm|database|schema|spreadsheet|dashboard|platform|app|application|script)")
_PERSON_VERB = (r"(?:tells?(?:\s+a\s+story)?|speaks?(?:\s+volumes)?|whispers?|screams?|sings?|knows?|wants?|loves?|"
                r"hates?|cares?|believes?|remembers?|forgets?|understands?|feels?|thinks?|refuses?|insists?|begs?|"
                r"cries|craves?|longs?|dreams?|deserves?|demands?|breathes?|yearns?|gladly|happily|"
                r"has\s+a\s+(?:story|mind\s+of\s+its\s+own)|is\s+(?:happy|unhappy|angry|eager|reluctant))")
_PERSONIFICATION = re.compile(
    r"\b(?:the|this|that|your|our|its|each|every|my)\s+(?:\w+\s+)?" + _PERSON_SUBJECT +
    r"\s+(?:itself\s+|quietly\s+|silently\s+|now\s+|always\s+|really\s+)?" + _PERSON_VERB + r"\b",
    re.IGNORECASE)

_SELF_Q = re.compile(
    r"^(?:(?:and|so|but)\s+)?(?:the\s+\w+(?:\s+\w+)?|why\s+does\s+(?:this|it|that)\s+matter|why\s+(?:is\s+)?(?:this|that)\s+important|"
    r"what\s+does\s+(?:this|that|it)\s+mean(?:\s+for\s+\w+(?:\s+\w+)?)?|so\s+what|sound\s+familiar|why|how|"
    r"what['’]s\s+the\s+catch|the\s+best\s+part|the\s+kicker)\?$",
    re.IGNORECASE)

_NUMBER_WORD = r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten|twelve)"
_COUNT = (
    re.compile(r"\b(?:here\s+are|there\s+are|these\s+are|below\s+are|we['’]ll\s+cover|we\s+will\s+cover|i['’]ll\s+share|"
               r"let['’]s\s+look\s+at)\s+" + _NUMBER_WORD +
               r"\s+(?:\w+\s+){0,2}(?:reasons|ways|tips|points|things|steps|benefits|takeaways|lessons|factors|"
               r"strategies|insights|questions|principles|mistakes|pillars|areas|ideas|features)\b", re.IGNORECASE),
    re.compile(r"\b" + _NUMBER_WORD + r"\s+(?:key|main|core|essential|critical|important)\s+"
               r"(?:reasons|ways|tips|points|things|steps|benefits|takeaways|lessons|factors|strategies|insights|"
               r"principles|pillars|areas|ideas|features)\b", re.IGNORECASE),
)

_CLOSING = re.compile(
    r"^(?:\d+[.)]?\s*)?(?:conclusion|conclusions|summary|in\s+summary|final\s+thoughts|closing\s+thoughts|"
    r"key\s+takeaways|takeaways|wrapping\s+up|wrap[- ]up|tl;?\s*dr|the\s+bottom\s+line|in\s+conclusion|"
    r"to\s+sum\s+up|parting\s+thoughts)\s*:?$", re.IGNORECASE)

_DASHES = re.compile(r"(?<=\S)\s*—\s*(?=\S)|\s–\s|\s--\s|―")
_RANGE_DASH = re.compile(r"\d\s*[—–]\s*\d")
_DASH_ONLY = "—–―-"
# A time or date at the start of a line, before a dash: "09:12 — Config change rolled out".
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|"
          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)\.?"
_TIME = r"\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?"
_DATE = (r"\d{4}-\d{1,2}-\d{1,2}(?:T\d{1,2}:\d{2}(?::\d{2})?Z?)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
         + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH
         + r"(?:\s+\d{4})?|" + _MONTH + r"\s+\d{4}|" + _WEEKDAY + r"|(?:19|20)\d{2}|q[1-4](?:\s+\d{4})?|"
         r"(?:day|week|sprint|phase)\s+\d+|t\s*[+-]\s*\d+\s*(?:min|m|h|d|s)?")
_ZONE = r"(?:\s*\(?(?:utc|gmt|[a-z]{1,3}[sd]?t)(?:\s*[+-]\s*\d{1,2}(?::?\d{2})?)?\)?)?"
_STAMP = re.compile(r"^[\s*_\[(]*(?:(?:" + _TIME + "|" + _DATE + r")" + _ZONE + r"[\s,]*)+[*_\])]*\s*$", re.IGNORECASE)
# A field label after a dash: "Fix the alert — Owner: Marco Ruiz — Due: Dec 5".
_FIELD_AFTER = re.compile(r"\s*[*_]*[A-Z][\w/&-]*(?:[ \t]+[\w/&-]+){0,2}[*_]*:[*_]*(?:\s|$)")
# A paragraph that is only an image or display math still follows a colon.
_FIGURE_LINE = re.compile(r"^(?:\[?!\[[^\]]*\](?:\([^()]*\)|\[[^\]]*\])(?:\]\([^()]*\))?\s*)+$|^\$\$|^\\\[")
_EMOJI_CANDIDATE = re.compile("[\u2190-\u2BFF\U0001F000-\U0001FAFF]")  # every code point tx.is_emoji accepts

_BOLD_LABEL = re.compile(r"^\s*(?:\*\*|__)([^*_\n]{1,60}?)(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:)(?:\s|$)")
# The text inside cannot contain the delimiter, so an unclosed ** stops at the next one (linear time).
_BOLD_SPAN = re.compile(r"\*\*(?=\S)(?:[^*\n]|\*(?!\*))+?(?<=\S)\*\*|__(?=\S)(?:[^_\n]|_(?!_))+?(?<=\S)__")
_STOP_STARTS = {"the", "a", "an"}


def _after_timestamp(text: str, pos: int) -> bool:
    """True if the text from the start of the line to pos is only a time or date."""
    start = text.rfind("\n", max(0, pos - 41), pos) + 1
    if start == 0 and pos > 40:
        return False
    return bool(_STAMP.match(text, start, pos))


def _empty_cell(text: str, start: int, end: int) -> bool:
    """True if the dash at text[start:end] is the whole table cell ("| — |")."""
    left = text.rfind("|", 0, start) + 1
    right = text.find("|", end)
    cell = text[left:right if right >= 0 else len(text)]
    return not cell.strip().strip(_DASH_ONLY)


# ---------------------------------------------------------------- bold rendering


def _is_punct(ch: str) -> bool:
    return bool(ch) and unicodedata.category(ch).startswith(("P", "S"))


def bold_problems(text: str) -> list[tuple[int, str, str, bool]]:
    """Find ** runs that CommonMark will not pair. Returns (offset, snippet, reason, lone).

    An unpaired ** between two letters or digits (2**3) is shown as text, as intended, and is skipped.
    lone is True when the run is the only other ** in the text (**kwargs, or a forgotten closing **).
    """
    runs: list[tuple[int, bool, bool]] = []
    for m in re.finditer(r"(?<![*\\])\*\*(?!\*)", text):
        i = m.start()
        prev = text[i - 1] if i > 0 else " "
        nxt = text[i + 2] if i + 2 < len(text) else " "
        left = not nxt.isspace() and (not _is_punct(nxt) or prev.isspace() or _is_punct(prev))
        right = not prev.isspace() and (not _is_punct(prev) or nxt.isspace() or _is_punct(nxt))
        runs.append((i, left, right))
    if not runs:
        return []
    stack: list[int] = []
    unmatched: list[int] = []
    for i, left, right in runs:
        if right and stack:
            stack.pop()
        elif left:
            stack.append(i)
        else:
            unmatched.append(i)
    unmatched.extend(stack)

    def intraword(i: int) -> bool:
        return i > 0 and i + 2 < len(text) and text[i - 1].isalnum() and text[i + 2].isalnum()

    index_of = {i: k for k, (i, _l, _r) in enumerate(runs)}
    others = sum(1 for i, _l, _r in runs if not intraword(i))
    closers = [m.start() for m in re.finditer(r"[^\s\w]\*\*\w", text)]
    reported: set[int] = set()
    problems: list[tuple[int, str, str, bool]] = []
    for i in sorted(unmatched):
        k = index_of[i]
        if k > 0 and runs[k - 1][0] in reported:
            continue  # one finding per broken pair
        if intraword(i):
            continue  # 2**3, a**b: CommonMark shows the asterisks, which is what was meant
        reported.add(i)
        snippet = text[max(0, i - 15): i + 17].strip()
        prev = text[i - 1] if i > 0 else " "
        nxt = text[i + 2] if i + 2 < len(text) else " "
        lone = others == 1
        if nxt.isspace() and not prev.isspace():
            reason = "a space before the closing ** (write **text** without inner spaces)"
        elif prev.isspace() and nxt.isspace():
            reason = "** surrounded by spaces"
        elif _is_punct(prev) and nxt.isalnum():
            reason = "punctuation before the closing ** and a letter right after it (add a space after **)"
        elif _is_punct(nxt) and prev.isalnum():
            reason = "a letter right before the opening ** and punctuation after it (add a space before **)"
        elif nxt.isspace():
            reason = "a space after the opening **"
        elif bisect.bisect_left(closers, i + 2) < len(closers):
            reason = "the closing ** has punctuation before it and a letter right after it (add a space after the closing **)"
        elif lone:
            reason = ("a lone ** shows as two asterisks (add the closing ** for bold, or put code such as "
                      "**kwargs in backticks)")
        else:
            reason = "no matching **"
        problems.append((i, snippet, reason, lone))
    return problems


# ---------------------------------------------------------------- lint


def _title_block(doc: tx.Document) -> int:
    """Index of the document title (the first level-1 heading), or -1."""
    for bi, block in enumerate(doc.blocks):
        if block.kind == "heading" and block.lines[0].level == 1:
            return bi
    return -1


def lint(text: str, doc_type: Optional[str] = None, reader: Optional[str] = None,
         words: Optional[tx.Words] = None) -> LintResult:
    words = words or tx.Words()
    doc = tx.parse(text)
    found: list[Finding] = []
    lists = [(rule, name, [(entry, _first_key(entry.phrase)) for entry in tx.load_list(name)], types)
             for rule, name, types in LIST_RULES]
    flags = []
    for name, replacement, pattern in words.flags:
        is_phrase = pattern.pattern == tx.phrase_regex(name)  # flag.txt entry, not a flag-patterns.txt regex
        flags.append((name, replacement, pattern, is_phrase, _first_key(name) if is_phrase else ""))
    title = _title_block(doc)

    for bi, block in enumerate(doc.blocks):
        if block.kind == "quote":
            continue  # quotations are not revised; callouts are checked like paragraphs
        masked, starts = block.joined(True)
        if not masked.strip():
            continue
        plain, _ = block.joined(False)  # same offsets as masked; used for what messages show
        bold_view = tx.mask(plain, "x")
        locate = _Locator(block, starts)
        low: Optional[str] = masked.lower()
        if low is not None and len(low) != len(masked):
            low = None

        def add(rule: str, start: int, end: int, message: str, exempt_in: tuple[str, ...] = (),
                severity: str = "", _plain: str = plain, _locate: _Locator = locate, _bi: int = bi) -> None:
            no, col = _locate(start)
            f = _make(doc, rule, no, col, message, _plain[start:end], start, end, _bi, exempt_in)
            if severity:
                f.severity = severity
            found.append(f)

        # word lists
        for rule, name, entries, types in lists:
            for entry, key in entries:
                for m in _scan(entry.pattern, key, masked, low):
                    shown = plain[m.start():m.end()]
                    if words.allowed(shown):
                        continue
                    if name in QUOTE_EXEMPT_LISTS and _in_quotes(plain, m.start(), m.end()):
                        continue
                    note = entry.note or RULES[rule][1]
                    add(rule, m.start(), m.end(), _list_message(rule, shown, note), types)
        for name, replacement, pattern, is_phrase, key in flags:
            for m in _scan(pattern, key, masked, low):
                shown = plain[m.start():m.end()]
                if not shown.strip() or words.allowed(shown):
                    continue
                arrow = f" → {replacement}" if replacement else ""
                label = f'"{_show(shown)}"' if is_phrase else f'"{_show(shown)}" ({name})'
                add("project_term", m.start(), m.end(),
                    f"Project word {label}{arrow}. Rewrite the sentence, not just the word.")

        for m in _HEDGE_STACK.finditer(masked):
            add("hedge_stack", m.start(), m.end(),
                f'Stacked hedge "{_show(plain[m.start():m.end()])}". Use one hedge of the same strength; do not '
                "remove the hedge.")
        if bi != title:  # the document title is not changed
            for m in _DASHES.finditer(masked):
                around = masked[max(0, m.start() - 2): m.end() + 2]
                if _RANGE_DASH.search(around):
                    continue
                if block.kind == "table" and _empty_cell(masked, m.start(), m.end()):
                    continue
                if _after_timestamp(masked, m.start()) or _FIELD_AFTER.match(masked, m.end()):
                    continue  # timeline entries and "— Owner: ..." fields
                add("em_dash", m.start(), m.end(),
                    "Dash used to splice or insert a clause. Use a comma, colon, parentheses or a period that keeps "
                    "the same scope (keep ranges, quotations and fiction dialogue).")
        if block.kind != "heading":
            for pattern in _NEG_CONTRAST:
                for m in pattern.finditer(masked):
                    shown = _show(plain[m.start():m.end()])
                    add("negative_contrast", m.start(), m.end(),
                        f'Negative contrast "{tx.display_width_cut(shown, 70)}". Remove the denied part only if '
                        "the claim stays the same; keep it when it corrects a likely misreading.")
        for m in _PERSONIFICATION.finditer(masked):
            add("personification", m.start(), m.end(),
                f'"{_show(plain[m.start():m.end()])}" gives a tool or idea a will or feelings. Say what it does, '
                "unless the function is obvious or the subject is an identifier in a developer document.")
        for pattern in _COUNT:
            for m in pattern.finditer(masked):
                add("count_announcement", m.start(), m.end(),
                    f'Count announcement "{_show(plain[m.start():m.end()])}". Check that the count matches the '
                    "items; keep the count and items as they are and ask if they differ.")

        # emoji
        for m in _EMOJI_CANDIDATE.finditer(masked):
            if tx.is_emoji(m.group(0)):
                add("emoji", m.start(), m.end(),
                    f"Emoji ({m.group(0)}). Remove it if it is decoration; keep it if it carries meaning.")

        # bold rendering (the view keeps code and links as letters so that **`code`** pairs)
        for offset, _snippet, reason, lone in bold_problems(bold_view):
            snippet = _show(plain[max(0, offset - 15): offset + 17])
            add("bold_unrendered", offset, offset + 2,
                f'This bold markup will not render ("{snippet}"): {reason}.', severity="info" if lone else "")

        if block.kind == "heading":
            body = masked.rstrip().rstrip("*_ \t")  # "## **Benefits:**"
            if body.endswith((":", "：")):
                add("heading_colon", len(body) - 1, len(body), "Heading ends with a colon. Remove the colon.")
            continue

        # sentences in this block
        if block.kind in ("para", "list", "callout"):
            spans = tx.split_sentences(masked)
            for s, e in spans:
                sent = masked[s:e].rstrip()
                stripped = sent.rstrip("\"'”’)*_ ")
                if stripped.endswith("!"):
                    add("exclamation", s + len(stripped) - 1, s + len(stripped),
                        "Exclamation mark. Keep it only where the document type and the writer use them.")
            # self-answered question
            for idx, (s, e) in enumerate(spans[:-1]):
                sent = masked[s:e].strip().strip("*_")
                nxt = masked[spans[idx + 1][0]:spans[idx + 1][1]].strip()
                if sent.endswith("?") and word_count(sent) <= 6 and _SELF_Q.match(sent) and not nxt.endswith("?"):
                    add("self_answered_question", s, e,
                        f'Self-answered question "{_show(plain[s:e]).strip("*_")}". Fold it into a statement unless '
                        "the document type keeps it.")
            if block.kind in ("para", "callout"):
                _fragment_runs(doc, masked, plain, spans, locate, bi, found)

    _block_rules(doc, found)
    found = _dedupe(found)
    found.sort(key=lambda f: (f.line, f.col, SEVERITY_ORDER[f.severity], f.rule))

    exempt = set(EXEMPT.get(doc_type or "", ()))
    kept: list[Finding] = []
    exempted: list[Finding] = []
    for f in found:
        if f.rule in exempt or (doc_type is not None and doc_type in f.exempt_in):
            exempted.append(f)
        else:
            kept.append(f)
    return LintResult(kept, exempted, doc_type, reader, words)


def _list_message(rule: str, match: str, note: str) -> str:
    m = _show(match)
    if rule == "ai_vocabulary":
        return f'AI-frequent word "{m}": {note}. Keep it if it is the field\'s term or no plain word says the same.'
    if rule == "stock_phrase":
        return f'Stock phrase "{m}": {note}. Keep any fact that appears only here.'
    if rule == "chat_residue":
        return f'Assistant chat "{m}" left in the text: {note}.'
    if rule == "wordy_phrase":
        return f'Wordy phrase "{m}": {note}, if the meaning and register stay the same.'
    if rule == "metaphor_verb":
        return f'Metaphorical verb "{m}": {note}. Do not replace it with a vague benefit.'
    if rule == "intensifier":
        return f'Intensifier "{m}": {note}.'
    return f'Jargon "{m}": {note}.'


def _fragment_runs(doc: tx.Document, masked: str, plain: str, spans: list[tuple[int, int]],
                   locate: _Locator, bi: int, found: list[Finding]) -> None:
    run: list[tuple[int, int]] = []

    def flush() -> None:
        if len(run) >= 3:
            s = run[0][0]
            snippet = " ".join(plain[a:b].strip() for a, b in run[:4])
            no, col = locate(s)
            found.append(_make(doc, "fragment_run", no, col,
                               f'{len(run)} very short sentences in a row ("{tx.display_width_cut(_show(snippet), 60)}"). '
                               "Write subject and verb when the original gives them; keep promo, slides and fiction.",
                               snippet, s, run[-1][1], bi))
    for s, e in spans:
        sent = masked[s:e].strip()
        if 0 < word_count(sent) <= 3 and not sent.endswith("?") and not sent.endswith(":"):
            run.append((s, e))
        else:
            flush()
            run = []
    flush()


def _block_rules(doc: tx.Document, found: list[Finding]) -> None:
    blocks = doc.blocks
    # bold labels in consecutive items or paragraphs
    group: list[int] = []

    def flush_group() -> None:
        if len(group) >= 2:
            for bi in group:
                block = blocks[bi]
                line = block.lines[0]
                label = _BOLD_LABEL.match(line.masked)
                match = line.content[label.start():label.end()] if label else ""
                found.append(_make(doc, "bold_label_list", line.no, line.offset + 1,
                                   f"Item starts with a bold label and colon ({len(group)} in a row). Keep labels "
                                   "for values; fold labels that only summarize into the sentence; remove the bold.",
                                   match, 0, 0, bi))
    prev_kind = ""
    for bi, block in enumerate(blocks):
        is_label = block.kind in ("list", "para") and bool(_BOLD_LABEL.match(block.lines[0].masked))
        if is_label and (not group or block.kind == prev_kind):
            group.append(bi)
        else:
            flush_group()
            group = [bi] if is_label else []
        prev_kind = block.kind
    flush_group()

    # heavy bold per paragraph
    for bi, block in enumerate(blocks):
        if block.kind not in ("para", "list"):
            continue
        masked, _starts = block.joined(True)
        label = _BOLD_LABEL.match(masked)
        skip = label.end() if label else 0
        spans = list(_BOLD_SPAN.finditer(masked, skip))
        if len(spans) >= 3:
            line = block.lines[0]
            plain, _ = block.joined(False)
            found.append(_make(doc, "heavy_bold", line.no, line.offset + 1,
                               f"{len(spans)} bold phrases in one paragraph. Keep bold only for what readers must not "
                               "miss (a warning, a value to type).", plain[spans[0].start():spans[0].end()], 0, 0, bi))

    # closing summary headings (not the first heading)
    headings = [(bi, b) for bi, b in enumerate(blocks) if b.kind == "heading"]
    total_lines = max(1, len(doc.lines))
    for index, (bi, block) in enumerate(headings):
        if index == 0:
            continue
        line = block.lines[0]
        title = re.sub(r"[*_`]", "", line.masked).strip()
        title = "".join(ch for ch in title if not tx.is_emoji(ch)).strip()
        if _CLOSING.match(title) and line.no >= total_lines * 0.5:
            found.append(_make(doc, "closing_summary", line.no, line.offset + 1,
                               f'Closing summary heading "{title}". Delete the section if it only repeats the body; '
                               "keep new information, next steps, and summaries the request asked for.",
                               title, 0, 0, bi))

    # excess list
    list_items = sum(1 for b in blocks if b.kind == "list")
    paras = sum(1 for b in blocks if b.kind == "para")
    if list_items >= 8 and list_items / max(1, list_items + paras) > 0.6:
        first = next(b for b in blocks if b.kind == "list")
        found.append(_make(doc, "excess_list", first.first_line, 1,
                           f"Most of the text is bullet points ({list_items} items, {paras} paragraphs). Turn reasons "
                           "and conditions back into sentences where a list splits one argument.", "", 0, 0, -1))

    # decorative colon: a paragraph ending with ":" followed by a paragraph, heading or the end
    next_kind: dict[int, str] = {}
    following = "end"
    for line in reversed(doc.lines):
        if line.kind == "blank":
            continue
        next_kind[line.no] = following
        if line.kind == "para" and _FIGURE_LINE.match(line.raw.strip()):
            following = "figure"  # an image or display math is what the colon introduces
        else:
            following = line.kind
    for bi, block in enumerate(blocks):
        if block.kind != "para":
            continue
        last = block.lines[-1]
        text = last.masked.rstrip()
        if text.endswith(":") and not text.endswith("::") and next_kind.get(last.no, "end") in ("para", "heading", "end",
                                                                                                "rule"):
            found.append(_make(doc, "decorative_colon", last.no, len(last.raw.rstrip()),
                               "Paragraph ends with a colon but no list, table, code or quotation follows. Remove the "
                               "colon or finish the sentence.", ":", 0, 0, bi))

    # sentence starts
    current: list[tx.Sentence] = []
    prev_word = ""

    def flush_starts() -> None:
        if len(current) >= 3:
            first = current[0]
            block = blocks[first.block_index]
            no, col = _Locator(block, block.joined(True)[1])(first.start)
            found.append(_make(doc, "sentence_start_repeat", no, col,
                               f'{len(current)} sentences in a row start with "{prev_word}". Vary only where it '
                               "reads as a pattern; keep parallel steps and lists.", prev_word, 0, 0, first.block_index))
    for sent in doc.sentences:
        if sent.kind != "para":
            flush_starts()
            current, prev_word = [], ""
            continue
        m = _WORD.match(sent.masked.strip().lstrip("\"'“‘(*_"))
        w = m.group(0) if m else ""
        if w and w.lower() not in _STOP_STARTS and w.lower() == prev_word.lower():
            current.append(sent)
        else:
            flush_starts()
            current = [sent] if w and w.lower() not in _STOP_STARTS else []
        prev_word = w
    flush_starts()


def _dedupe(found: list[Finding]) -> list[Finding]:
    """One finding per span.

    Drops exact duplicates, the shorter of two overlapping findings of the same rule, and a word-list finding
    that overlaps a stronger or longer word-list finding ("crucial" inside "plays a crucial role", "a deep dive"
    and "deep dive into"). Findings of different regex rules are all kept, even when their spans overlap.
    Runs in O(n log n) for the usual short spans.
    """
    drop = [False] * len(found)
    seen: set[tuple[str, int, int]] = set()
    groups: dict[tuple[int, str], list[int]] = {}
    for i, f in enumerate(found):
        if not f.end or f.block < 0:
            key = (f.rule, f.line, f.col)
            drop[i] = key in seen
            seen.add(key)
            continue
        family = "list" if f.rule in LIST_RULE_NAMES else f.rule
        groups.setdefault((f.block, family), []).append(i)

    def rank(i: int, by_list: bool) -> tuple[int, ...]:
        f = found[i]
        if by_list:  # stronger first, the project's own word first, then the longer phrase
            return (SEVERITY_ORDER[f.severity], 0 if f.rule == "project_term" else 1, f.start - f.end, i)
        return (f.start - f.end, i)

    for (_block, family), indexes in groups.items():
        by_list = family == "list"
        indexes.sort(key=lambda i: (found[i].start, -found[i].end))
        active: list[int] = []
        for i in indexes:
            start = found[i].start
            active = [j for j in active if found[j].end > start]
            for j in active:
                drop[i if rank(i, by_list) > rank(j, by_list) else j] = True
            active.append(i)
    return [f for i, f in enumerate(found) if not drop[i]]


# ---------------------------------------------------------------- output


def counts(findings: list[Finding]) -> dict[str, int]:
    c = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        c[f.severity] += 1
    return c


def kept_words(findings: list[Finding]) -> list[str]:
    seen: list[str] = []
    keys: set[str] = set()
    for f in findings:
        if f.rule in KEPT_WORD_RULES and f.match and f.match.lower() not in keys:
            keys.add(f.match.lower())
            seen.append(f.match)
    return seen


def to_json(result: LintResult) -> dict[str, object]:
    c = counts(result.findings)
    return {
        "format": JSON_FORMAT,
        "tool": TOOL,
        "version": __version__,
        "doc_type": result.doc_type,
        "reader": result.reader,
        "review_findings": len(result.findings),
        "counts": c,
        "no_rule_findings": not result.findings,
        "exempted": len(result.exempted),
        "exempted_rules": sorted({f.rule for f in result.exempted}),
        "words": {"folder": str(result.words.folder) if result.words.folder else None,
                  "count": result.words.count, "sha256": result.words.digest or None},
        "findings": [
            {k: v for k, v in asdict(f).items() if k not in ("start", "end", "exempt_in", "block")}
            for f in result.findings
        ],
    }


def format_text(result: LintResult) -> str:
    c = counts(result.findings)
    out = [
        "Ran the expression and format checks.",
        f"Review findings: {len(result.findings)}",
        "These checks do not judge whether meaning was kept or whether readers will find the text clear.",
        "",
        f"Breakdown: error {c['error']}, warn {c['warn']}, info {c['info']}",
    ]
    if result.doc_type:
        rules = sorted({f.rule for f in result.exempted})
        out.append(f"Doc type: {result.doc_type}. Exempted findings: {len(result.exempted)}"
                   + (f" ({', '.join(rules)})" if rules else ""))
    if result.reader:
        out.append(f"Reader: {result.reader} (recorded only; findings do not change)")
    if result.words.folder:
        out.append(f"Project word list: {result.words.folder} ({tx.plural(result.words.count, 'entry', 'entries')})")
    for f in result.findings:
        out.append("")
        out.append(f"L{f.line} [{f.severity.upper()}] {f.rule}: {f.message}")
        out.append(f"  > {tx.display_width_cut(f.text, 160)}")
    return "\n".join(out) + "\n"


def parse_fail_on(values: Optional[list[str]], allowed: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if part not in allowed:
                raise tx.InputError(f"--fail-on accepts {', '.join(allowed)} (got {part}).")
            result.add(part)
    return result


def fail_hit(findings: list[Finding], fail_on: set[str]) -> bool:
    c = counts(findings)
    if "error" in fail_on and c["error"]:
        return True
    return "warn" in fail_on and bool(c["warn"] or c["error"])


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="readyasu_lint.py",
        description="Check English expressions and Markdown formatting against fixed rules. Findings are places to "
                    "review. Their number is not a judgment of quality, of whether meaning was kept, or of clarity.",
        epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", default="-", help="file to check (UTF-8); omit or use - for standard input")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.add_argument("--strict", action="store_true", help="exit 1 if there is any warn or error finding (same as --fail-on warn)")
    p.add_argument("--fail-on", action="append", metavar="warn|error",
                   help="exit 1 if a finding of this severity or higher exists; repeat or separate with commas")
    p.add_argument("--doc-type", choices=tx.DOC_TYPES, metavar="TYPE",
                   help="document type; exempts rules that are normal for it: " + ", ".join(tx.DOC_TYPES))
    p.add_argument("--reader", choices=tx.READERS, metavar="READER",
                   help="expected reader (recorded only): " + ", ".join(tx.READERS))
    p.add_argument("--words", metavar="DIR", help=f"project word-list folder (default: {tx.WORDS_DIR_NAME}/ at the git top or working folder)")
    p.add_argument("--no-words", action="store_true", help="do not look for or read a project word list")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    tx.configure_stdout()
    args = build_parser().parse_args(argv)
    try:
        fail_on = parse_fail_on(args.fail_on, ("warn", "error"))
        if args.strict:
            fail_on.add("warn")
        words = tx.load_words(args.words, args.no_words)
        text = tx.read_text(args.file)
    except tx.InputError as exc:
        sys.stderr.write(f"readyasu_lint.py: {exc}\n")
        return 2
    result = lint(text, args.doc_type, args.reader, words)
    if args.json:
        sys.stdout.write(json.dumps(to_json(result), ensure_ascii=True, indent=1) + "\n")
    else:
        sys.stdout.write(format_text(result))
    return 1 if fail_hit(result.findings, fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
