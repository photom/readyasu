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
from typing import Callable, Iterator, NoReturn, Optional

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
LIST_LABELS = {"closing-courtesies": "courtesies, offers and closings", "chat-interjections": "interjections"}
# Single list entries that are normal in some doc types: (list name, phrase) -> doc types. Not part of
# PARTIAL_EXEMPT, which lists whole word lists.
ENTRY_EXEMPT: dict[tuple[str, str], tuple[str, ...]] = {
    ("closing-courtesies", "thank you for your attention"): ("slides", "script"),  # the closing slide or line
    ("ai-vocabulary", "key takeaways"): ("slides",),  # a summary slide is normal in slides
}
# Lists whose matches inside double quotation marks are dialogue, not residue, and that are reported only at the
# start of a sentence ("Of course! Here is ..." but not "The answer, of course! was ...").
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
    for (name, phrase), types in ENTRY_EXEMPT.items():
        rows.append(f"  {' and '.join(types)} also exempt{'s' if len(types) == 1 else ''} \"{phrase}\" ({name}.txt).")
    return "\n".join(rows)


HELP_EPILOG = """Rules exempted by --doc-type:
""" + "\n".join(f"  {k:<9} {', '.join(v) if v else 'none'}" for k, v in EXEMPT.items()) + "\n" + _partial_help() + """
  Interjections are reported only where they start a sentence, and never inside double quotation marks.
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


def _starts_sentence(text: str, pos: int) -> bool:
    """True if text[pos:] starts the block, a table cell, a sentence (after . ! ? : or …) or a line with a capital.

    Opening quotes, brackets and emphasis markers before pos are skipped.
    """
    i = pos
    while i > 0 and text[i - 1] in "\"'“‘([*_":
        i -= 1
    if i == 0:
        return True
    j = i
    while j > 0 and text[j - 1].isspace():
        j -= 1
    if j == i:
        return False
    if j == 0:
        return True
    if "\n" in text[j:i] and text[pos:pos + 1].isupper():
        return True
    while j > 0 and text[j - 1] in "\"'”’)]*_":
        j -= 1
    return j > 0 and text[j - 1] in ".!?:…|"


class _Quotes:
    """Answers whether a span of one block's text sits between double quotation marks, in O(log n) per span."""

    def __init__(self, text: str) -> None:
        self.straight = [m.start() for m in re.finditer('"', text)]
        self.opening = [m.start() for m in re.finditer("“", text)]
        self.closing = [m.start() for m in re.finditer("”", text)]

    def inside(self, start: int, end: int) -> bool:
        """True if an odd number of " come before start and one comes at or after end, or the last curly quote
        before start opens one that closes at or after end."""
        if bisect.bisect_left(self.straight, start) % 2 == 1 and self.straight[-1] >= end:
            return True
        o = bisect.bisect_left(self.opening, start)
        c = bisect.bisect_left(self.closing, start)
        last_open = self.opening[o - 1] if o else -1
        last_close = self.closing[c - 1] if c else -1
        return last_open > last_close and bool(self.closing) and self.closing[-1] >= end


def _in_quotes(text: str, start: int, end: int) -> bool:
    """True if text[start:end] sits between double quotation marks in the same block."""
    return _Quotes(text).inside(start, end)


def _clause_prefix(text: str, start: int, limit: int = 120) -> str:
    """The text from the last clause mark (. ; : ! ? , or a dash) before start, or the block start, to start."""
    i = start
    floor = max(0, start - limit)
    while i > floor and text[i - 1] not in ".;:!?,—–":
        i -= 1
    return text[i:start]


def _context(plain: str, start: int, end: int, width: int = 24) -> str:
    """A short one-line snippet of plain around [start, end) for a message, cut at word boundaries."""
    left = max(0, start - width)
    right = min(len(plain), end + width)
    while left < start and left > 0 and not plain[left - 1].isspace():
        left += 1  # do not start inside a word
    while right > end and right < len(plain) and not plain[right].isspace():
        right -= 1  # do not end inside a word
    shown = _show(plain[left:right])
    return ("…" if plain[:left].strip() else "") + shown + ("…" if plain[right:].strip() else "")


# ---------------------------------------------------------------- regex rules

_HEDGE_STACK = re.compile(
    r"\b(?:may|might|could|can|would)\s+(?:potentially|possibly|perhaps|conceivably|maybe)\b"
    r"|\b(?:possibly|perhaps|maybe)\s+(?:may|might|could)\b"
    # "it seems ... may": within one clause. "could" only as a possibility ("could be", "could have"), not an
    # ability ("the attacker could read any file"), and not after nobody, no one or none.
    r"|\bit\s+(?:seems|appears)\s+(?:that\s+)?"
    r"(?:(?!\b(?:but|and|or|so|yet|because|although|though|while|whereas|if|when|unless|nobody|no\s+one|none)\b)"
    r"[^.;:,!?\n]){0,40}?"
    r"\b(?:might|(?-i:may)|could(?=\s+(?:be|have|potentially|possibly)\b))(?:\s+(?:possibly|potentially|perhaps)\b)?"
    r"|\b(?:likely|probably)\s+(?:may|might|could)\b"
    r"|\bmight\s+(?:likely|probably)\b",
    re.IGNORECASE)
# "What could possibly go wrong?", "no way we could possibly finish", "as fast as you can possibly go": the adverb
# stresses a question, a negation or a comparison; it is not a second hedge. The question word opens the clause;
# the negation or comparison is among the last four words before the modal.
_HEDGE_QUESTION = re.compile(r"\s*[\"“*_]*(?:what|who|how|why|where|which)\b", re.IGNORECASE)
_HEDGE_NEGATION = re.compile(
    r"\b(?:no\s+way|nothing|nobody|no\s+one|none|never|hardly|scarcely|barely|cannot|not|as\s+[\w-]+\s+as)\b"
    r"|n['’]t\b", re.IGNORECASE)
_MODAL_ADVERB = re.compile(r"(?:may|might|could|can|would)\s", re.IGNORECASE)


def _rhetorical_hedge(text: str, start: int) -> bool:
    """True if the modal at start follows a question word that opens the clause, or a close negation."""
    prefix = _clause_prefix(text, start)
    if _HEDGE_QUESTION.match(prefix):
        return True
    return bool(_HEDGE_NEGATION.search(" ".join(prefix.split()[-4:])))

# After "but": a noun phrase that starts with an article, a possessive, "about" or "rather", or one word that ends
# the clause ("not a tool but infrastructure."), never a pronoun or a verb ("but customers noticed it").
_BUT_NOUN_PHRASE = (
    r"(?:rather\s+)?(?:(?:a|an|the|about|my|our|your|his|her|its|their|one|something)\s+[\w'’-]+"
    r"|(?!(?:it|we|they|he|she|i|you|there|this|that|these|those|nobody|everyone|someone|none|nothing)\b)"
    r"[\w'’-]+(?=\s*(?:[.;:!?,)]|$)))")
# The noun phrase after "but" must end the clause within a few words or go on with a preposition or a relative
# clause ("but a platform for building products", "but a feature we built"). A verb after it makes "but" open a
# new clause, a concession: "not a blocker, but the team should review it", "but our largest customer noticed it",
# "but the default timeout went from 30s to 10s", "but the tests pass".
_NP_GOES_ON = frozenset((
    "of", "for", "in", "on", "with", "from", "at", "by", "to", "into", "onto", "that", "which", "who", "whom",
    "whose", "where", "and", "or", "than", "like", "about", "across", "over", "under", "within", "without",
    "between", "through", "per", "beyond", "we", "you", "they", "i"))
_CLAUSE_VERBS = frozenset("""
will would should could can may might must shall is are was were am be been being has have had does do did
gets got seems seemed looks looked went came took made gave found said saw ran began broke brought built bought
caught chose drew drove fell felt fought flew forgot grew heard held kept knew left lost meant met paid rose sent
sold spent stood stole struck taught thought told understood won wrote became spoke threw wore ate sank shook
still also already never always just now really probably actually usually often rarely finally quickly
eventually suddenly
""".split())
_NP_TOKENS = re.compile(r"[\w'’-]+|[^\w\s]")


def _noun_phrase_ends(text: str, pos: int, last: str) -> bool:
    """True if the noun phrase after "but" whose word `last` ends at pos ends its clause soon (see above)."""
    prev = last.lower()
    for count, m in enumerate(_NP_TOKENS.finditer(text, pos, min(len(text), pos + 80))):
        word = m.group(0).lower()
        if not word[0].isalnum():
            return True  # punctuation ends the clause
        plural = len(prev) > 3 and prev.endswith("s") and not prev.endswith(("ss", "us", "is", "ics"))
        if word in _NP_GOES_ON:
            return not (plural and word == "to")  # "the team needs to review it"
        if word in _CLAUSE_VERBS or word.endswith(("n't", "n’t")) or plural or count >= 3 or (
                len(word) > 3 and word.endswith("ed") and not word.endswith("eed") and not prev.endswith("ly")):
            return False
        prev = word
    return True


# Clauses that make a negation a condition, a time or a concession: "If the value is not set, it is read from the
# environment", "Although the API is not stable, it is widely used".
_SUBORDINATORS = frozenset((
    "if", "when", "whenever", "unless", "although", "though", "because", "since", "while", "once", "until",
    "whether", "as", "after", "before", "whereas"))
_CLAUSE_WORD = re.compile(r"[A-Za-z]+")

_NEG_BE = (r"(?:['’]s\s+not|\s+is\s+not|\s+was\s+not|\s+are\s+not|\s+were\s+not|['’]re\s+not|"
           r"\s+isn['’]t|\s+aren['’]t|\s+wasn['’]t|\s+weren['’]t)")
_NEG_CONTRAST = (
    re.compile(
        r"\b(?:(?:this|that|these|those|the|our|your|its|their|my)\s+[\w-]+(?:\s+[\w-]+)?|"
        r"it|this|that|these|they|which|he|she|(?-i:[A-Z][\w.+#-]*))" + _NEG_BE + r"\s+"  # "React isn't ..."
        r"(?:just\s+|only\s+|merely\s+|simply\s+|about\s+)?[^.;:!?\n]{1,80}?[,;—–]\s*"
        r"(?:it|this|that|they|he|she)(?:['’]s|\s+is|\s+was|\s+are|\s+were|['’]re)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:just|only|merely|simply)\b[^.;!?\n]{1,60}?,?\s*\bbut\s+(?:also\s+)?[\w'’-]+",
               re.IGNORECASE),
    # "This is not a bug, but a feature." Only a noun phrase on both sides: "It is not a big change, but it fixes
    # the crash", "The outage was not a major one, but customers noticed it" and "The fix was not tested, but ..."
    # are concessions.
    re.compile(
        r"(?:\b(?:is|was|are|were)\s+not|\b(?:isn|wasn|aren|weren)['’]t|['’](?:s|re)\s+not)\s+"
        r"(?:a|an|the|about)\s+[^.;:!?,\n]{1,40}?,?\s+but\s+" + _BUT_NOUN_PHRASE, re.IGNORECASE),
    re.compile(r"\b(?:doesn['’]t|don['’]t|didn['’]t|does\s+not|do\s+not|isn['’]t|aren['’]t|wasn['’]t|weren['’]t|"
               r"(?:is|are|was|were)\s+not)\s+(?:just|only|merely|simply)\s+"
               r"[^.;:!?\n]{1,60}?[,;—–]\s*(?:it|they|this|we|he|she)\b", re.IGNORECASE),
    re.compile(r"\b(?:isn['’]t|is\s+not)\s+(?:just\s+|really\s+)?about\b[^.;!?\n]{1,60}?[.;,—–]\s*"
               r"(?:it['’]s|it\s+is)\s+about\b", re.IGNORECASE),
)
_NOT_JUST_BUT = 1  # index of the "not just X but also Y" pattern, which is reported also inside a condition
_NOT_A_BUT = 2  # index of the "not a X, but Y" pattern, whose noun phrase after "but" is checked
# A heading that is "Not X, but Y" ("## Not a linter, but a formatter"), with an article, "about" or "just" after
# "not", like the sentence form: "## Not supported, but planned" and "## Not now, but soon" are not contrasts.
_HEADING_CONTRAST = re.compile(
    r"^[*_\s]*not\s+(?:a|an|the|about|just|only|merely|simply)\s+[^.;:!?,\n]{1,40}?,?\s+but\s+(?:also\s+)?"
    + _BUT_NOUN_PHRASE, re.IGNORECASE)

# Two sentences: "It isn't a tool. It's a philosophy." / "We didn't need a new tool. We needed a shared way."
# The second sentence has the same subject and the same verb (a form of "be", or the verb that was denied); the
# checks are in _two_sentence_contrast.
_NEG_TWO = re.compile(
    r"(?:^|(?<=[.!?]\s))(?P<s1>It|This|That|They|These|Those|We|I|You|"
    r"(?:The|This|That|These|Those|Our|Your|Their|My)\s+\w+(?:\s+\w+)?|What\s+\w+\s+\w+|"
    r"[A-Z][\w.+#-]*)"  # a name: "Kubernetes isn't just a scheduler. It's a platform."
    r"(?:\s+(?:isn['’]t|is\s+not|wasn['’]t|was\s+not|aren['’]t|are\s+not|weren['’]t|were\s+not|am\s+not)|"
    r"['’](?:s|re|m)\s+not"
    r"|\s+(?:doesn['’]t|don['’]t|didn['’]t|does\s+not|do\s+not|did\s+not)\s+(?P<v1>[a-z]+))\b"
    r"(?P<rest1>[^.!?\n]{0,80})\.\s+(?P<s2>It|This|That|They|These|Those|We|I|You)"
    r"(?:(?P<be2>['’]s|\s+is|\s+was|\s+are|\s+were|['’]re|['’]m|\s+am)|\s+(?P<v2>[a-z]+))\b")
_SUBJECT_GROUPS = ({"it", "this", "that"}, {"they", "these", "those"}, {"we"}, {"i"}, {"you"})


def _same_subject(first: str, second: str) -> bool:
    a, b = first.lower(), second.lower()
    if not any(a in group for group in _SUBJECT_GROUPS):
        # A noun phrase or a name: "The fix isn't ... It's ...", "The tools aren't ... They're ...", "React ..."
        return b in ("it", "this", "that", "they", "these", "those")
    return any(a in group and b in group for group in _SUBJECT_GROUPS)


# Common irregular verbs: "We didn't build a new tool. We built a shared process."
_IRREGULAR = {
    "begin": "began begun", "break": "broke broken", "bring": "brought",
    "build": "built", "buy": "bought", "catch": "caught", "choose": "chose chosen", "come": "came",
    "become": "became", "do": "did done does", "drive": "drove driven", "fall": "fell fallen", "feel": "felt",
    "find": "found", "forget": "forgot forgotten", "get": "got gotten", "give": "gave given",
    "go": "went gone", "grow": "grew grown", "have": "had has", "hear": "heard", "hold": "held",
    "keep": "kept", "know": "knew known", "lead": "led", "leave": "left", "lose": "lost", "make": "made",
    "mean": "meant", "meet": "met", "pay": "paid", "run": "ran", "say": "said says", "see": "saw seen",
    "sell": "sold", "send": "sent", "speak": "spoke spoken", "spend": "spent", "stand": "stood",
    "take": "took taken", "teach": "taught", "tell": "told", "think": "thought", "understand": "understood",
    "win": "won", "write": "wrote written",
}
_DOUBLES = re.compile(r"(?:^|[^aeiou])[aeiou][bdgklmnprt]$")  # stop → stopped, plan → planning


def _verb_forms(verb: str) -> set[str]:
    v = verb.lower()
    forms = {v, v + "s", v + "es", v + "ed", v + "d", v + "ing"}
    if v.endswith("e"):
        forms.add(v[:-1] + "ing")
    if v.endswith("y"):
        forms |= {v[:-1] + "ies", v[:-1] + "ied"}
    if _DOUBLES.search(v):
        forms |= {v + v[-1] + "ed", v + v[-1] + "ing"}
    forms.update(_IRREGULAR.get(v, "").split())
    return forms


# A state or status, not a thing that the second sentence replaces: "I'm not sure. I'm checking with the team.",
# "We're not ready to ship. We're still waiting on QA.", "They aren't available. They are at the offsite."
_STATUS_WORDS = frozenset((
    "sure", "ready", "done", "available", "able", "aware", "certain", "finished", "complete", "here", "there",
    "back", "home", "around", "free", "busy", "online", "offline", "late", "involved", "allowed", "going", "yet"))
# Where someone is: "I'm not in the office today. I'm at the dentist."
_STATUS_PLACES = frozenset(("in", "on", "at", "off", "out", "away"))
_SKIP_ADVERBS = frozenset(("really", "quite", "yet", "actually", "entirely", "fully", "totally", "completely",
                           "very", "so", "too", "always"))
_NEXT_WORDS = re.compile(r"[A-Za-z'’]+")


def _first_word(text: str, pos: int = 0, skip: frozenset[str] = frozenset()) -> str:
    for m in _NEXT_WORDS.finditer(text, pos, min(len(text), pos + 80)):
        word = m.group(0).lower()
        if word not in skip:
            return word
    return ""


def _progressive(word: str) -> bool:
    return len(word) > 4 and word.endswith("ing") and not word.endswith("thing")


def _two_sentence_contrast(text: str) -> Iterator[re.Match[str]]:
    for m in _NEG_TWO.finditer(text):
        if not _same_subject(m.group("s1"), m.group("s2")):
            continue
        if m.group("v1") is None and m.group("be2") is not None:
            first = _first_word(m.group("rest1"), 0, _SKIP_ADVERBS)
            second = _first_word(text, m.end(), _SKIP_ADVERBS)
            if any(word in _STATUS_WORDS or word in _STATUS_PLACES or _progressive(word) for word in (first, second)) \
                    or second in ("still", "currently", "now", "not", "never"):
                continue  # "They're not coming to the offsite. They're on leave.", "It isn't X. It is not Y."
            yield m
        elif m.group("v1") is not None and m.group("v2") is not None \
                and m.group("v2").lower() in _verb_forms(m.group("v1")):
            yield m


# Software and documents only: people (an agent, an assistant) may want, remember and do things happily.
_PERSON_SUBJECT = (r"(?:code|codebase|data|dataset|tool|system|function|method|class|logs?|architecture|design|"
                   r"framework|api|metrics?|numbers|graph|chart|compiler|tests?|errors?|repository|repo|pipeline|"
                   r"model|algorithm|database|schema|spreadsheet|dashboard|platform|app|application|script|"
                   r"service|server|daemon|scheduler|linter|cache|engine|library|plugin|bot|monitor|software|"
                   r"program|cli|sdk|workflow|logic|parser|module|component)")
# "feels" is left out: "The dashboard feels faster" is perception, not a feeling.
_PERSON_VERB = (r"(?:tells?(?:\s+a\s+story)?|speaks?(?:\s+volumes)?|whispers?|screams?|sings?|knows?|wants?|loves?|"
                r"hates?|cares?|believes?|remembers?|forgets?|understands?|thinks?|refuses?|insists?|begs?|"
                r"cries|craves?|longs?|dreams?|deserves?|demands?|breathes?|yearns?|resents?|watch(?:es)?\s+over|"
                r"gladly|happily|tirelessly|patiently|eagerly|cheerfully|lovingly|proudly|stubbornly|dutifully|"
                r"graciously|kindly|politely|bravely|(?:chooses?|chose|decides?|decided)\s+to|"
                r"has\s+a\s+(?:story|mind\s+of\s+its\s+own)|is\s+(?:happy|unhappy|angry|eager|reluctant))")
_PERSON_ADVERB = (r"(?:itself|quietly|silently|now|always|really|never|carefully|faithfully|dutifully|lovingly|"
                  r"gladly|happily|tirelessly|patiently|eagerly|cheerfully|proudly|stubbornly|graciously|kindly|"
                  r"politely|bravely)")
_PERSONIFICATION = re.compile(
    r"\b(?:the|this|that|your|our|its|each|every|my)\s+(?:\w+\s+)?" + _PERSON_SUBJECT +
    r"\s+(?:(?:will|would)\s+)?(?:" + _PERSON_ADVERB + r"\s+)?"
    r"(?:(?:seems?|seemed|appears?|appeared)\s+to\s+)?" + _PERSON_VERB + r"\b",
    re.IGNORECASE)

_SELF_Q = re.compile(
    r"^(?:(?:and|so|but)\s+)?(?:the\s+\w+(?:\s+\w+)?|why\s+does\s+(?:this|it|that)\s+matter|why\s+(?:is\s+)?(?:this|that)\s+important|"
    r"what\s+does\s+(?:this|that|it)\s+mean(?:\s+for\s+\w+(?:\s+\w+)?)?|so\s+what|sound\s+familiar|why|how|"
    r"what['’]s\s+the\s+catch|the\s+best\s+part|the\s+kicker|"
    r"what,\s*then,\s*(?:is|was|are|were)\s+the\s+\w+(?:\s+\w+)?)\?$",
    re.IGNORECASE)
# An answer that opens like this marks the question before it as self-answered ("What is the gap? Simply put, ...").
_ANSWER_OPENER = re.compile(
    r"^[*_\"“]*(?:simply\s+put|put\s+simply|in\s+short|in\s+a\s+word|(?:the\s+)?short\s+answer|the\s+answer\b|"
    r"here['’]s\s+the\s+thing|the\s+truth\s+is|spoiler)", re.IGNORECASE)
# "In today's rapidly evolving healthcare landscape": the looser form of the stock-phrases.txt openers.
_TODAYS_OPENER = re.compile(
    r"\bin\s+today['’]s\s+(?:[\w-]+\s+){0,4}?(?:world|landscape|age|era|environment|climate|market|marketplace|"
    r"economy|society|business)\b", re.IGNORECASE)
# An assistant's preamble before a mail it drafted ("Certainly! Here's a reply you can send to Jordan:"): residue
# even in mail, where "Here's a draft of the agenda" from the writer is normal.
_PREAMBLE = re.compile(
    r"(?:\b(?:certainly|sure|absolutely|of\s+course|great\s+question)[!.,]\s+)?"
    r"\bhere(?:['’]s|\s+is|\s+are)\s+(?:a|an|the|your|some)\s+(?:[\w-]+\s+){0,3}?"
    r"(?:reply|replies|draft|drafts|version|versions|response|responses|e-?mails?|messages?|note|rewrite|letter|"
    r"text|options?)\b[^.!?:\n]{0,40}?"
    r"\b(?:you\s+(?:can|could|might|may)\s+(?:send|use|copy|paste|forward|adapt)|for\s+you\s+to\s+(?:send|use))\b",
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
# Range endpoints on both sides of a spaced dash: "Monday – Friday", "9 am – 5 pm", "$5 – $10", "v1.2 – v1.4",
# "January – March", "20% – 30%", "Q1 – Q3". Month and weekday names need a capital ("may" is a verb).
_ENDPOINT = (
    r"(?:(?:[$€£¥]\s?)?[~≈]?\d[\d,.:]*(?:\s?%)?|[vV]\d+(?:\.\d+)*[a-z]?|Q[1-4]|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
    r"Mon|Tues?|Wed|Thu(?:rs?)?|Fri|Sat|Sun)\.?)"
    r"(?:\s?(?:[aApP]\.?[mM]\.?|[A-Za-zµ°]{1,5}))?")  # "9 am", "5 km", "10 GB"
_RANGE_BEFORE = re.compile(r"(?:^|(?<=[\s(\[]))" + _ENDPOINT + r"[,.]?[ \t]*$")
_RANGE_AFTER = re.compile(r"[ \t]*" + _ENDPOINT + r"(?![\w$€£¥])")
_DASH_ONLY = "—–―-"
# An attribution under a quotation: a line that is only a dash and a name ("— Jeff Atwood", "— Plato, Republic").
_NAME_WORD = r"(?:[A-Z]\.|[A-Z][\w'’-]+)"
_ATTRIBUTION = re.compile(
    r"(?:—|―|–|--)[ \t]*" + _NAME_WORD + r"(?:[ \t]+(?:" + _NAME_WORD + r"|de|van|von|der|da|di|du|la|le|bin|al))*"
    r"(?:,[ \t]*[A-Z0-9*_“\"][^\n]{0,60})?[ \t]*(?:\n|$)")
# A time, date or version at the start of a line, before a dash: "09:12 — Config change rolled out",
# "10:00–10:15 — Status updates", "Version 2.1 — Effective January 1, 2027".
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|"
          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)\.?"
_TIME = (r"\d{1,2}(?:[:.]\d{2})?\s*[-–]\s*\d{1,2}(?:[:.]\d{2})?\s*[ap]\.?m\.?|"  # "9–10 am"
         r"\d{1,2}[:.]\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?")
_DATE = (r"\d{4}-\d{1,2}-\d{1,2}(?:T\d{1,2}:\d{2}(?::\d{2})?Z?)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
         r"\d{4}/\d{1,2}/\d{1,2}|\d{1,2}\.\d{1,2}\.\d{2,4}|"
         + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH
         + r"(?:\s+\d{4})?|" + _MONTH + r"\s+\d{4}|" + _WEEKDAY + r"|(?:19|20)\d{2}|q[1-4](?:\s+\d{4})?|"
         r"t\s*[+-]\s*\d+\s*(?:min|m|h|d|s)?|"
         # "Day 2", "Step 1", "Part II", "Option A"
         r"(?:day|week|sprint|phase|step|part|chapter|lesson|module|stage|option)\s+"
         r"(?:\d+(?:\.\d+)*[a-z]?|(?-i:[IVX]{1,4}|[A-Za-z]))(?![\w.])")
_ZONE = r"(?:\s*\(?(?:utc|gmt|[a-z]{1,3}[sd]?t)(?:\s*[+-]\s*\d{1,2}(?::?\d{2})?)?\)?)?"
_VERSION = (r"(?:(?:version|revision|rev\.?|release|v)\s*\d+(?:\.\d+)*[a-z]?|"
            # "1.2.0 — Added dedup", "2.0.0-rc1"; "9.30" is left to _TIME, so a run of them has one reading
            r"(?!\d{1,2}\.\d{2}(?![\d.-]))\d+\.\d+(?:\.\d+)*(?:-[\w.]+)?)")
_STAMP_LABEL = (r"(?:(?:effective|updated|last\s+updated|last\s+revised|revised|published|released|issued|dated?)"
                r"(?:\s+on)?:?\s+)?")
_ONE_STAMP = r"(?:" + _STAMP_LABEL + r"(?:" + _TIME + "|" + _DATE + r")" + _ZONE + "|" + _VERSION + r")"
_RANGE_END = r"(?:(?:" + _TIME + "|" + _DATE + r")" + _ZONE + r"|\d{1,2}(?:st|nd|rd|th)?)"  # "Dec 3–5"
# Stamps in a row need a separator, so a long run of digits and dots ("1.11.11.1...") cannot be split in
# exponentially many ways. No "^": the line starts at pos, which is after a line break for a later line.
_STAMPS = _ONE_STAMP + r"(?:[\s,]+" + _ONE_STAMP + r")*"
_STAMP = re.compile(r"[\s*_\[(]*" + _STAMPS + r"(?:[\s,]*(?:[-–—]|to\b)\s*" + _RANGE_END
                    + r"(?:[\s,]+" + _STAMPS + r")?)?[\s,]*[*_\])]*\s*$", re.IGNORECASE)
# A field label after a dash: "Fix the alert — Owner: Marco Ruiz — Due: Dec 5".
_FIELD_AFTER = re.compile(r"\s*[*_]*[A-Z][\w/&-]*(?:[ \t]+[\w/&-]+){0,2}[*_]*:[*_]*(?:\s|$)")
# A paragraph that is only an image or display math still follows a colon.
_FIGURE_LINE = re.compile(r"^(?:\[?!\[[^\]]*\](?:\([^()]*\)|\[[^\]]*\])(?:\]\([^()]*\))?\s*)+$|^\$\$|^\\\[")
# Every code point tx.is_emoji accepts, and the keycap mark of 1️⃣ and #️⃣.
_EMOJI_CANDIDATE = re.compile("[\u2190-\u2BFF\u20E3\U0001F000-\U0001FAFF]")

_BOLD_LABEL = re.compile(r"^\s*(?:\*\*|__)([^*_\n]{1,60}?)(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:)(?:\s|$)")
# The text inside cannot contain the delimiter, so an unclosed ** stops at the next one (linear time).
_BOLD_SPAN = re.compile(r"\*\*(?=\S)(?:[^*\n]|\*(?!\*))+?(?<=\S)\*\*|__(?=\S)(?:[^_\n]|_(?!_))+?(?<=\S)__")
_STOP_STARTS = {"the", "a", "an"}
_LINK_DEFINITION = re.compile(r"^\s*\[[^\]]+\]:\s*\S")
# A letter's salutation on a line of its own ends with a colon in US business letters.
_SALUTATION = re.compile(r"^\s*(?:dear\b|to\s+whom\s+it\s+may\s+concern\b|(?:ladies\s+and\s+)?gentlemen\b|"
                         r"(?:hello|hi|greetings)\b[^.!?]{0,40}:\s*$)", re.IGNORECASE)
# A mail's greeting on a line of its own ("Hi Ana,", "Dear Mr. Lee:", "Hello team"). After it, "Here's a draft reply
# you can send to the customer:" is the writer's own mail, not an assistant's preamble.
_GREETING = re.compile(r"^\s*(?:hi|hello|hey|dear|greetings|good\s+(?:morning|afternoon|evening)|"
                       r"to\s+whom\s+it\s+may\s+concern)\b(?:[^.!?:\n]|(?<=mr|ms|dr)\.|(?<=mrs)\.){0,40}[,:!]?\s*$",
                       re.IGNORECASE)
# Underscores that open or close emphasis, not those inside a snake_case_name.
_EMPHASIS_UNDERSCORE = re.compile(r"(?<!\w)_+|_+(?!\w)")


def _words_view(masked: str) -> str:
    """masked with emphasis underscores as spaces (same offsets), so that word lists, project words and the
    pattern rules see the words in "_seamless_", "__leverage__" and "_may potentially_"."""
    if "_" not in masked:
        return masked
    return _EMPHASIS_UNDERSCORE.sub(lambda m: " " * len(m.group(0)), masked)


def _strip_end(sentence: str) -> str:
    """The sentence without the closing quotes, brackets, emphasis and emoji at its end ("Happy restoring! 🎉")."""
    stripped = sentence.rstrip("\"'”’)*_ ")
    spans = tx.emoji_spans(stripped)
    while spans and spans[-1][1] == len(stripped):
        stripped = stripped[:spans.pop()[0]].rstrip("\"'”’)*_ ")
    return stripped


def _after_timestamp(text: str, pos: int) -> bool:
    """True if the text from the start of the line to pos is only a time, date or version (or a range of them)."""
    start = text.rfind("\n", max(0, pos - 61), pos) + 1
    if start == 0 and pos > 60:
        return False
    return bool(_STAMP.match(text, start, pos))


def _range_dash(text: str, start: int, end: int) -> bool:
    """True if the dash at text[start:end] joins two range endpoints ("Monday – Friday", "$5 – $10")."""
    return bool(_RANGE_BEFORE.search(text, max(0, start - 24), start) and _RANGE_AFTER.match(text, end))


# What may sit around the code or URLs of one term (masked to spaces): emphasis, link brackets, and the comma,
# slash or "or" between aliases. Matched with fullmatch, which stops at the first other character.
_TERM_GLUE = re.compile(r"(?:[\s*_\[\]()|,/]|(?<!\w)or\b)*")


def _term_dash(masked: str, plain: str, start: int) -> bool:
    """True if only inline code or a URL (with emphasis, or as a link) comes before the dash on its line.

    "- `--threads N` — number of workers" is an option list: the dash separates a term from its description.
    Aliases joined by a comma, a slash or "or" count as one term ("- `-h`, `--help` — show help"). A link with
    words ("[Guide](guide.md) — ...") is still checked.
    """
    line = masked.rfind("\n", 0, start) + 1
    return bool(plain[line:start].strip()) and bool(_TERM_GLUE.fullmatch(masked, line, start))


def _line_at(text: str, pos: int) -> tuple[int, int]:
    """(start, end) of the line of text that holds pos."""
    end = text.find("\n", pos)
    return text.rfind("\n", 0, pos) + 1, len(text) if end < 0 else end


def _dash_bullet(text: str, start: int, end: int) -> bool:
    """True if the dash at text[start:end] is a bullet in plain text ("Decisions:" then "– Budget approved").

    The dash starts its line, and the line before ends with a colon or the line before or after starts with the
    same dash.
    """
    line = start
    while line > 0 and text[line - 1] in " \t":
        line -= 1
    if line > 0 and text[line - 1] != "\n":
        return False  # checked first, so a long line with many dashes is not scanned for each
    line_end = _line_at(text, start)[1]
    dash = text[start:end]

    def bulleted(other: str) -> bool:
        return other.startswith(dash) and other[len(dash):len(dash) + 1] not in _DASH_ONLY

    if line > 0:
        prev = text[_line_at(text, line - 1)[0]:line - 1].strip()
        if prev.rstrip("*_").endswith(":") or bulleted(prev):
            return True
    return line_end < len(text) and bulleted(text[line_end + 1:_line_at(text, line_end + 1)[1]].strip())


def _attribution(text: str, pos: int) -> bool:
    """True if the dash at pos starts a line that names the author of the sentence above it ("— Jeff Atwood")."""
    start = pos
    while start > 0 and text[start - 1] in " \t":
        start -= 1
    if start == 0 or text[start - 1] != "\n":
        return False
    j = start - 1
    while j > 0 and text[j - 1].isspace():
        j -= 1
    return j > 0 and text[j - 1] in ".!?\"”’)*_" and bool(_ATTRIBUTION.match(text, pos))


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
    lists = [(rule, name, [(entry, _first_key(entry.phrase),
                            types + ENTRY_EXEMPT.get((name, entry.phrase.lower()), ()))
                           for entry in tx.load_list(name)])
             for rule, name, types in LIST_RULES]
    flags = []
    for name, replacement, pattern in words.flags:
        is_phrase = pattern.pattern == tx.phrase_regex(name)  # flag.txt entry, not a flag-patterns.txt regex
        flags.append((name, replacement, pattern, is_phrase, _first_key(name) if is_phrase else ""))
    title = _title_block(doc)
    first_prose = -1
    greeted = False  # a greeting line came before this block

    for bi, block in enumerate(doc.blocks):
        if block.kind == "quote":
            continue  # quotations are not revised; callouts are checked like paragraphs
        masked, starts = block.joined(True)
        plain, _ = block.joined(False)  # same offsets as masked; used for what messages show
        bold_view = tx.mask(plain, "x")  # code, URLs and tags as letters
        view = tx.split_view(plain)  # code and URLs as letters, tags as spaces: the words a reader sees
        if not view.strip():
            continue
        if first_prose < 0 and block.kind in ("para", "list", "callout"):
            first_prose = bi
        seen = _words_view(masked)  # emphasis underscores as spaces; for words and pattern rules
        flat = seen.replace("\n", " ")  # hard-wrapped lines read as one line; same offsets
        locate = _Locator(block, starts)
        low: Optional[str] = seen.lower()
        if low is not None and len(low) != len(seen):
            low = None
        # The offset after which a drafted mail's text follows its greeting (0: a greeting came in an earlier
        # block; -1: none yet).
        greeting = block.kind == "para" and bool(_GREETING.match(block.lines[0].content))
        after_greeting = 0 if greeted else (starts[1][0] if greeting and len(starts) > 1 else -1)
        greeted = greeted or greeting
        is_title = bi == title  # the document title is not changed: only emoji and bold markup are reported
        quotes: Optional[_Quotes] = None

        def add(rule: str, start: int, end: int, message: str, exempt_in: tuple[str, ...] = (),
                severity: str = "", _plain: str = plain, _locate: _Locator = locate, _bi: int = bi) -> None:
            no, col = _locate(start)
            f = _make(doc, rule, no, col, message, _plain[start:end], start, end, _bi, exempt_in)
            if severity:
                f.severity = severity
            found.append(f)

        # word lists
        for rule, name, entries in ([] if is_title else lists):
            for entry, key, types in entries:
                for m in _scan(entry.pattern, key, seen, low):
                    shown = plain[m.start():m.end()]
                    if words.allowed(shown):
                        continue
                    if name in QUOTE_EXEMPT_LISTS:
                        if not _starts_sentence(masked, m.start()):
                            continue
                        quotes = quotes or _Quotes(plain)
                        if quotes.inside(m.start(), m.end()):
                            continue
                    note = entry.note or RULES[rule][1]
                    add(rule, m.start(), m.end(), _list_message(rule, shown, note), types)
        for name, replacement, pattern, is_phrase, key in ([] if is_title else flags):
            for m in _scan(pattern, key, seen, low):
                shown = plain[m.start():m.end()]
                if not shown.strip() or words.allowed(shown):
                    continue
                arrow = f" → {replacement}" if replacement else ""
                label = f'"{_show(shown)}"' if is_phrase else f'"{_show(shown)}" ({name})'
                add("project_term", m.start(), m.end(),
                    f"Project word {label}{arrow}. Rewrite the sentence, not just the word.")

        if not is_title:
            _expression_rules(flat, masked, plain, bold_view, block, bi == first_prose, add, after_greeting)

        # emoji
        if _EMOJI_CANDIDATE.search(masked):
            for es, ee in tx.emoji_spans(masked):
                add("emoji", es, ee,
                    f"Emoji ({plain[es:ee]}). Remove it if it is decoration; keep it if it carries meaning.")

        # bold rendering (the view keeps code and links as letters so that **`code`** pairs)
        for offset, _snippet, reason, lone in bold_problems(bold_view):
            snippet = _show(plain[max(0, offset - 15): offset + 17])
            add("bold_unrendered", offset, offset + 2,
                f'This bold markup will not render ("{snippet}"): {reason}.', severity="info" if lone else "")

        if block.kind == "heading":
            # Tested on the view, so a heading that ends with code or a link ("## Option: `--force`") is not
            # reported, and the column is the colon's.
            body = view.rstrip().rstrip("*_ \t")  # "## **Benefits:**"
            if not is_title and body.endswith((":", "：")):
                add("heading_colon", len(body) - 1, len(body), "Heading ends with a colon. Remove the colon.")
            continue

        # sentences in this block, split where code or a URL starts a sentence
        if block.kind in ("para", "list", "callout"):
            spans = tx.split_sentences(view)
            for s, e in spans:
                stripped = _strip_end(masked[s:e])
                if stripped.endswith("!"):
                    bang = s + len(stripped) - 1
                    add("exclamation", bang, bang + 1,
                        f'Exclamation mark in "{_context(plain, bang, bang + 1)}". Keep it only where the document '
                        "type and the writer use them.")
            # self-answered question
            for idx, (s, e) in enumerate(spans[:-1]):
                sent = masked[s:e].strip().strip("*_")
                nxt = masked[spans[idx + 1][0]:spans[idx + 1][1]].strip()
                if not sent.endswith("?") or nxt.endswith("?"):
                    continue
                if (word_count(sent) <= 6 and _SELF_Q.match(sent)) or \
                        (word_count(sent) <= 10 and _ANSWER_OPENER.match(nxt)):
                    add("self_answered_question", s, e,
                        f'Self-answered question "{_show(plain[s:e]).strip("*_")}". Fold it into a statement unless '
                        "the document type keeps it.")
            if block.kind in ("para", "callout"):
                _fragment_runs(doc, view, plain, spans, locate, bi, found)

    _block_rules(doc, found)

    # Split before removing overlaps, so that an exempted finding does not hide a reported one.
    exempt = set(EXEMPT.get(doc_type or "", ()))
    kept: list[Finding] = []
    exempted: list[Finding] = []
    for f in found:
        if f.rule in exempt or (doc_type is not None and doc_type in f.exempt_in):
            exempted.append(f)
        else:
            kept.append(f)

    def order(f: Finding) -> tuple[int, int, int, str]:
        return (f.line, f.col, SEVERITY_ORDER[f.severity], f.rule)

    return LintResult(sorted(_dedupe(kept), key=order), sorted(_dedupe(exempted), key=order), doc_type, reader, words)


_Add = Callable[..., None]


def _but_noun_phrase(text: str, m: re.Match[str]) -> bool:
    """True if the noun phrase after "but" at the end of match m ends its clause (_noun_phrase_ends)."""
    last = re.search(r"[\w'’-]+$", m.group(0))
    return last is None or _noun_phrase_ends(text, m.end(), last.group(0))


def _after_subordinator(text: str, start: int) -> bool:
    """True if the clause that ends at start opens with, or ends with, if/when/although/because ..."""
    words = _CLAUSE_WORD.findall(_clause_prefix(text, start))
    return bool(words) and (words[0].lower() in _SUBORDINATORS or words[-1].lower() in _SUBORDINATORS)


def _expression_rules(flat: str, masked: str, plain: str, letters: str, block: tx.Block, first: bool,
                      add: _Add, after_greeting: int = -1) -> None:
    """Pattern rules on one block (not the title): hedges, dashes, negative contrast, personification, counts,
    the looser "in today's ..." opener and an assistant's preamble.

    flat is masked with emphasis underscores and line breaks as spaces, letters is plain with code, URLs and tags
    as letters; all have the offsets of plain. after_greeting is the offset after a greeting line in this or an
    earlier block, or -1.
    """
    for m in _HEDGE_STACK.finditer(flat):
        if _MODAL_ADVERB.match(m.group(0)) and _rhetorical_hedge(flat, m.start()):
            continue  # "What could possibly go wrong?"
        add("hedge_stack", m.start(), m.end(),
            f'Stacked hedge "{_show(plain[m.start():m.end()])}". Use one hedge of the same strength; do not '
            "remove the hedge.")
    # letters, not masked, so that a dash after inline code is found like any other.
    for m in _DASHES.finditer(letters):
        around = masked[max(0, m.start() - 2): m.end() + 2]
        if _RANGE_DASH.search(around):
            continue
        if block.kind == "table" and _empty_cell(masked, m.start(), m.end()):
            continue
        # Report the dash itself, not the space or line break before it.
        ds = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
        de = ds + (2 if letters.startswith("--", ds) else 1)
        if _after_timestamp(masked, ds) or _FIELD_AFTER.match(masked, m.end()) or _attribution(masked, ds) \
                or _range_dash(masked, ds, de) or _term_dash(masked, plain, ds) or _dash_bullet(masked, ds, de):
            continue  # timelines, "— Owner: ..." fields, "— Jeff Atwood", "Monday – Friday", "`-v` — verbose",
            # "Decisions:" then "– Budget approved"
        add("em_dash", ds, de,
            f'Dash in "{_context(plain, ds, de)}" used to splice or insert a clause. Use a comma, colon, parentheses '
            "or a period that keeps the same scope (keep ranges, quotations and fiction dialogue).")
    contrasts: list[re.Match[str]] = []
    for k, pattern in enumerate(_NEG_CONTRAST):
        for m in pattern.finditer(flat):
            if k == _NOT_A_BUT and not _but_noun_phrase(flat, m):
                continue
            if k == _NOT_JUST_BUT or not _after_subordinator(flat, m.start()):
                contrasts.append(m)
    contrasts.extend(_two_sentence_contrast(flat))
    if block.kind == "heading":
        contrasts.extend(m for m in _HEADING_CONTRAST.finditer(flat) if _but_noun_phrase(flat, m))
    for m in contrasts:
        shown = _show(plain[m.start():m.end()])
        add("negative_contrast", m.start(), m.end(),
            f'Negative contrast "{tx.display_width_cut(shown, 70)}". Remove the denied part only if '
            'the claim stays the same ("not just X" affirms X; keep X); keep it when it corrects a likely misreading.')
    for m in _PERSONIFICATION.finditer(flat):
        add("personification", m.start(), m.end(),
            f'"{_show(plain[m.start():m.end()])}" gives a tool or idea a will or feelings. Say what it does, '
            "unless the function is obvious or the subject is an identifier in a developer document.")
    for pattern in _COUNT:
        for m in pattern.finditer(flat):
            add("count_announcement", m.start(), m.end(),
                f'Count announcement "{_show(plain[m.start():m.end()])}". Check that the count matches the '
                "items; keep the count and items as they are and ask if they differ.")
    for m in _TODAYS_OPENER.finditer(flat):
        add("stock_phrase", m.start(), m.end(), _list_message("stock_phrase", plain[m.start():m.end()],
                                                              "delete the opener"))
    for m in _PREAMBLE.finditer(flat):
        # Only a preamble: a clause that ends with a colon before the drafted text, or a first paragraph that holds
        # nothing else ("Here's a draft you can use for the deck. I added the numbers." is the writer's mail), and
        # not after a greeting ("Hi Ana," then "Here's a draft reply you can send to the customer:").
        if 0 <= after_greeting <= m.start():
            continue
        rest = flat[m.end():]
        if re.match(r"[^.!?:]{0,80}:", rest) or (first and re.fullmatch(r"[^.!?:]{0,80}[.!]?\s*", rest)):
            add("chat_residue", m.start(), m.end(),
                f'Assistant chat "{_show(plain[m.start():m.end()])}" left in the text: delete the preamble; it '
                "speaks to the requester, not the reader (reported in every doc type).")


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
        return (f'Metaphorical verb "{m}": {note}. Use only what the original or material says; otherwise keep it '
                "and ask. Do not replace it with a vague benefit.")
    if rule == "intensifier":
        return f'Intensifier "{m}": {note}.'
    return f'Jargon "{m}": {note}.'


# Verbs that start an instruction. "Open Settings.", "Click Save." and "Run `apt update`." are whole sentences (the
# subject is the reader), so they are not fragments; a lone "Build." or "Ship." still is.
_IMPERATIVES = frozenset("""
open close click double-click right-click tap press type enter select choose pick check uncheck clear run restart
reboot start stop save install uninstall update upgrade download upload add remove delete set copy paste cut move
drag drop rename create edit go navigate scroll expand collapse enable disable turn switch toggle unplug plug
connect disconnect insert eject sign log wait repeat return exit quit launch load mount unmount clone fetch pull
push commit merge build deploy test verify confirm cancel accept submit review read see note use try replace attach
detach import export print call send reply ask tell keep leave put place hold release tighten loosen fill empty
wash rinse mix stir heat bake boil chop slice pour measure write label lock unlock charge apply configure reset
refresh reload restore back follow find search sort filter share invite assign schedule book visit contact
""".split())


def _imperative(sentence: str) -> bool:
    """True if the sentence starts with an instruction verb and has a word after it ("Click Save.")."""
    words = _WORD.findall(sentence)
    return len(words) >= 2 and words[0].lower() in _IMPERATIVES


def _fragment_runs(doc: tx.Document, view: str, plain: str, spans: list[tuple[int, int]],
                   locate: _Locator, bi: int, found: list[Finding]) -> None:
    """Runs of three or more short sentences. view is tx.split_view(plain): inline code and URLs count as words."""
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
        sent = view[s:e].strip()
        if 0 < word_count(sent) <= 3 and not sent.endswith("?") and not sent.endswith(":") and not _imperative(sent):
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
        for es, ee in reversed(tx.emoji_spans(title)):
            title = title[:es] + title[ee:]
        title = title.strip()
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
        if next_kind.get(last.no, "end") not in ("para", "heading", "end", "rule"):
            continue
        if _LINK_DEFINITION.match(last.content) or (len(block.lines) == 1 and _SALUTATION.match(last.content)):
            continue  # "[g]: https://example.com/guide", "Dear Ms. Alvarez:"
        # Code, URLs and e-mail are letters in this view, so "run: `pip install x`" does not end with a colon.
        plain, starts = block.joined(False)
        text = tx.split_view(plain).rstrip()
        if text.endswith(":") and not text.endswith("::"):
            no, col = _Locator(block, starts)(len(text) - 1)
            found.append(_make(doc, "decorative_colon", no, col,
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
        m = _WORD.match(sent.masked.lstrip("\"'“‘(*_"))  # no word when the sentence starts with code
        w = m.group(0) if m else ""
        if w[:1].isdigit():
            w = ""  # numbered clauses ("3.1 ...", "3.2 ...") and figures are not a repeated word
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
        out.append(f"L{f.line}:{f.col} [{f.severity.upper()}] {f.rule}: {f.message}")
        out.append(f"  > {tx.excerpt(f.text, f.col, len(f.match))}")
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
