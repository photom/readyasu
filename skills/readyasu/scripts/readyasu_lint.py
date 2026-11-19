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
from typing import Callable, Iterator, NamedTuple, NoReturn, Optional

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
  script also exempts bold_label_list for a run of speaker names ("**G:**", "**MAYA:**", "**Speaker 1:**").
  slides also exempts every finding in notes to the requester before the first slide (before the first heading,
  "---" or "Slide 1" line) or after the last one (after the last "---" when no heading or "Slide N" line follows
  it; a setext heading's underline is not a "---").
  mail also exempts an assistant's preamble after an interjection ("Sure! Here's a revised version:") unless a
  greeting or "Subject:" follows it or it offers a drafted mail ("a letter you can adapt").
  mail still reports an offer about the drafted mail after its sign-off or a thematic break. Other types report an
  offer after a thematic break with no greeting or sign-off before it only when it names a draft ("adjust the tone").
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
_NONSPACE = re.compile(r"\S")


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


def _before_space_and_emoji(text: str, pos: int) -> int:
    """The offset before the spaces and emoji that end at pos ("We shipped! 🎉 " before "This")."""
    j = pos
    while True:
        while j > 0 and text[j - 1].isspace():
            j -= 1
        if j == 0:
            return j
        last = text[j - 1]  # an emoji ends with a symbol, U+FE0F, a keycap mark or a tag character
        if not (_EMOJI_CANDIDATE.match(last) or last == "\uFE0F" or "\U000E0020" <= last <= "\U000E007F"):
            return j
        window = max(0, j - 32)  # long enough for a joined emoji such as 👨‍👩‍👧‍👦
        spans = tx.emoji_spans(text[window:j])
        if not spans or spans[-1][1] != j - window:
            return j
        j = window + spans[-1][0]


def _starts_sentence(text: str, pos: int) -> bool:
    """True if text[pos:] starts the block, a table cell, a sentence (after . ! ? : or …) or a line with a capital.

    Opening quotes, brackets and emphasis markers before pos are skipped, and so are the spaces and emoji before them
    ("🚀 This ...", "We shipped v2! 🎉 This ..."). text keeps its line breaks (pass masked, not flat), so a capital
    that starts a line after a bold title line starts a sentence.
    """
    i = pos
    while i > 0 and text[i - 1] in "\"'“‘([*_":
        i -= 1
    if i == 0:
        return True
    j = _before_space_and_emoji(text, i)
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
    before = left > 0 and _NONSPACE.search(plain, 0, left) is not None  # searched in place: linear in a long block
    after = _NONSPACE.search(plain, right) is not None
    return ("…" if before else "") + shown + ("…" if after else "")


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
# Words before a plural noun that are not singular nouns themselves ("but the new features.", "but a few tweaks.").
_NOT_A_NOUN = frozenset("""
the a an new old few many several other same different real main key only right wrong best worst next last first
latest big small good bad great more most less least all some any no every each such own whole full simple single
actual final critical technical general additional potential basic specific generic
""".split())
_ADJECTIVE_ENDS = ("ive", "ous", "ful", "less", "able", "ible")


def _plural(word: str) -> bool:
    return len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is", "ics"))


def _singular_noun(word: str) -> bool:
    """A guess from the word's shape: not plural, not a determiner and not shaped like an adjective."""
    return not _plural(word) and word not in _NOT_A_NOUN and not word.endswith(_ADJECTIVE_ENDS) \
        and not (word.endswith("ed") and not word.endswith("eed")) and not _progressive(word) \
        and not word.endswith(("'s", "’s"))


def _noun_phrase_ends(text: str, pos: int, last: str) -> bool:
    """True if the noun phrase after "but" whose word `last` ends at pos ends its clause soon (see above)."""
    prev = last.lower()
    tokens = list(_NP_TOKENS.finditer(text, pos, min(len(text), pos + 80)))
    for count, m in enumerate(tokens):
        word = m.group(0).lower()
        if not word[0].isalnum():
            return True  # punctuation ends the clause
        plural = _plural(prev)
        if word in _NP_GOES_ON:
            return not (plural and word == "to")  # "the team needs to review it"
        if word in _CLAUSE_VERBS or word.endswith(("n't", "n’t")) or plural or count >= 3 or (
                len(word) > 3 and word.endswith("ed") and not word.endswith("eed") and not prev.endswith("ly")):
            return False
        # An -s word right after a singular noun at the end of the clause is a verb: "but the patch works.",
        # "but the principle matters." ("but the new features." keeps the noun phrase.)
        at_end = count + 1 >= len(tokens) or not tokens[count + 1].group(0)[0].isalnum()
        if at_end and _plural(word) and _singular_noun(prev):
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
# Words that start a sentence without being part of its subject: a clause opener, a conjunction, or an imperative.
_NOT_SUBJECT_START = (r"(?:if|when|whenever|unless|although|though|because|since|while|once|until|whether|as|after|"
                      r"before|whereas|and|but|or|so|please|just|never|kindly|always|simply|do|let['’]s)\b")
# A name or one to three words, the first capitalized: "React", "Node.js", "Remote work", "Ledgerly Flow", "What we
# need". A dot only inside a word, so the subject does not run back over the end of the previous sentence ("We tried.
# This ...").
_CAP_SUBJECT = r"(?-i:[A-Z])[\w+#'’-]*(?:\.[\w+#'’-]+)*(?:\s+[\w+#'’-]+(?:\.[\w+#'’-]+)*){0,2}"
# In the one-sentence form, a pronoun that ends a longer subject is the subject itself, so the match starts there: "He
# said it wasn't his fault; it was the vendor's." is found from "it".
_NOT_PRONOUN_END = "".join(r"(?<!\s(?i:" + word + "))" for word in ("it", "this", "that", "they", "he", "she", "we",
                                                                     "you", "i"))
_NEG_CONTRAST = (
    # "It isn't X; it's Y", "Remote work isn't a perk—it's a paradigm shift." A subject of two or three words without a
    # determiner must start the sentence, and both subjects must agree ("He wasn't the one who called; she was." is
    # not a contrast); checked in _expression_rules.
    re.compile(
        r"(?:\b(?P<s1>(?:this|that|these|those|the|our|your|its|their|my)\s+[\w-]+(?:\s+[\w-]+)?|"
        r"it|this|that|these|they|which|he|she)|"
        # A name starts a token (the lookbehind), so a long run such as "A.A.A." is scanned once.
        r"(?<![\w.+#'’-])(?!" + _NOT_SUBJECT_START + r")(?P<name>" + _CAP_SUBJECT + _NOT_PRONOUN_END + r"))"
        + _NEG_BE + r"\s+"
        r"(?P<just>just\s+|only\s+|merely\s+|simply\s+|about\s+)?(?P<denied>[^.;:!?\n]{1,80}?)[,;—–]\s*"
        r"(?P<s2>it|this|that|they|he|she)(?P<be2>['’]s|\s+is|\s+was|\s+are|\s+were|['’]re)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:just|only|merely|simply)\b[^.;!?\n]{1,60}?,?\s*\bbut\s+(?:also\s+)?[\w'’-]+",
               re.IGNORECASE),
    # "This is not a bug, but a feature." Only a noun phrase on both sides: "It is not a big change, but it fixes
    # the crash", "The outage was not a major one, but customers noticed it" and "The fix was not tested, but ..."
    # are concessions.
    re.compile(
        r"(?:\b(?:is|was|are|were)\s+not|\b(?:isn|wasn|aren|weren)['’]t|['’](?:s|re)\s+not)\s+"
        r"(?:a|an|the|about)\s+[^.;:!?,\n]{1,40}?,?\s+but\s+" + _BUT_NOUN_PHRASE, re.IGNORECASE),
    re.compile(r"(?:\b(?:doesn['’]t|don['’]t|didn['’]t|does\s+not|do\s+not|isn['’]t|aren['’]t|wasn['’]t|weren['’]t|"
               r"(?:is|are|was|were)\s+not)|(?<![Ll]et)['’](?:re|s)\s+not)\s+(?:just|only|merely|simply)\s+"
               r"[^.;:!?\n]{1,60}?[,;—–]\s*(?:it|they|this|we|you|he|she)\b", re.IGNORECASE),
    re.compile(r"\b(?:isn['’]t|is\s+not)\s+(?:just\s+|really\s+)?about\b[^.;!?\n]{1,60}?[.;,—–]\s*"
               r"(?:it['’]s|it\s+is)\s+about\b", re.IGNORECASE),
)
_NOT_JUST_BUT = 1  # index of the "not just X but also Y" pattern, which is reported also inside a condition
_NOT_A_BUT = 2  # index of the "not a X, but Y" pattern, whose noun phrase after "but" is checked
_NOT_X_IT_IS = 0  # index of the "isn't X; it's Y" pattern, which skips a status or place like the two-sentence form
# The one-sentence form after a reminder that opens the sentence, where the subject may be a noun in lower case
# without a determiner: "Remember, onboarding isn't a sprint; it's a marathon.", "Ultimately, success isn't a
# destination, it's a journey." Checked like _NEG_CONTRAST[_NOT_X_IT_IS].
_REMINDER_CONTRAST = re.compile(
    r"\b(?:remember|ultimately|honestly|after\s+all|in\s+the\s+end|at\s+the\s+end\s+of\s+the\s+day|keep\s+in\s+mind|"
    r"the\s+truth\s+is|the\s+reality\s+is)[,:]\s+"
    r"(?!" + _NOT_SUBJECT_START + r"|there\b|nobody\b|nothing\b|everyone\b)(?P<s1>[a-z][\w-]*(?:\s+[a-z][\w-]*)?)"
    + _NEG_BE + r"\s+(?P<just>just\s+|only\s+|merely\s+|simply\s+|about\s+)?(?P<denied>[^.;:!?\n]{1,80}?)[,;—–]\s*"
    r"(?P<s2>it|this|that|they)(?P<be2>['’]s|\s+is|\s+was|\s+are|\s+were|['’]re)\b", re.IGNORECASE)
# A heading that is "Not X, but Y" ("## Not a linter, but a formatter"), with an article, "about" or "just" after
# "not", like the sentence form: "## Not supported, but planned" and "## Not now, but soon" are not contrasts.
_HEADING_CONTRAST = re.compile(
    r"^[*_\s]*not\s+(?:a|an|the|about|just|only|merely|simply)\s+[^.;:!?,\n]{1,40}?,?\s+but\s+(?:also\s+)?"
    + _BUT_NOUN_PHRASE, re.IGNORECASE)

# Two sentences: "It isn't a tool. It's a philosophy." / "We didn't need a new tool. We needed a shared way."
# The second sentence has the same subject and the same verb (a form of "be", or the verb that was denied); the
# checks are in _two_sentence_contrast. The subject of the first is a pronoun or one to three words at the start of
# the sentence (checked there with _starts_sentence, so emphasis, a callout label or two spaces may come before it),
# the first capitalized: "Remote work isn't a perk.", "Ledgerly Flow isn't just a tool.", "What we need isn't more
# meetings." An imperative is not a subject ("Please don't use the old endpoint. It uses ..."). The second sentence
# is in a lookahead, so that it can start the next match ("This isn't a tool. It's not a framework. It's a
# mindset."); emphasis may close and open between the two ("**This isn't a tool.** **It's a mindset.**"). A pronoun
# in lower case is a subject only right after a colon ("The truth is simple: it isn't a tool. It's a mindset.").
_NEG_TWO = re.compile(
    r"(?<![\w.+#'’-])(?P<s1>It|This|That|They|These|Those|We|I|You|He|She|it|this|that|they|these|those|we|you|he|she|"
    r"(?!(?i:please|just|never|kindly|always|simply|do|let['’]s)\b)" + _CAP_SUBJECT + r")"
    r"(?:\s+(?:isn['’]t|is\s+not|wasn['’]t|was\s+not|aren['’]t|are\s+not|weren['’]t|were\s+not|am\s+not)|"
    r"['’](?:s|re|m)\s+not"
    r"|\s+(?:doesn['’]t|don['’]t|didn['’]t|does\s+not|do\s+not|did\s+not)\s+"
    r"(?:(?:just|simply|merely|only|really)\s+)?(?P<v1>[a-z]+))\b"  # "We didn't just ship features."
    r"(?P<rest1>[^.!?\n]{0,80})\.[*_]*(?=\s+[*_]*(?P<s2>It|This|That|They|These|Those|We|I|You|He|She)"
    r"(?:(?P<be2>['’]s|\s+is|\s+was|\s+are|\s+were|['’]re|['’]m|\s+am)|\s+(?P<v2>[a-z]+))\b)")
_SUBJECT_GROUPS = ({"it", "this", "that"}, {"they", "these", "those"}, {"we"}, {"i"}, {"you"}, {"he"}, {"she"})


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
# Also the state of an account, a setting or a change: "Your subscription isn't affected. It's active until May."
_STATUS_WORDS = frozenset((
    "sure", "ready", "done", "available", "able", "aware", "certain", "finished", "complete", "here", "there",
    "back", "home", "around", "free", "busy", "online", "offline", "late", "involved", "allowed", "going", "yet",
    "affected", "unaffected", "impacted", "active", "inactive", "enabled", "disabled", "expired", "valid", "invalid",
    "open", "closed", "live", "visible", "hidden", "deprecated", "supported", "installed", "configured", "empty",
    "locked", "pending", "scheduled", "cancelled", "canceled", "paused", "resolved", "fixed", "broken", "merged",
    "deployed", "released", "due", "overdue", "up", "down"))
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


def _states_status(text: str, denied: str, after: int) -> bool:
    """True if the denied part (the text after "is not") or what follows the second "it is" at after states a status
    or a place, goes on with an -ing form, or the second part goes on with "still", "now", "not" or "also":
    "They're not coming to the offsite. They're on leave.", "The API isn't stable yet; it's still in beta.", "It
    isn't X. It is not Y.", "It isn't cheap. It's also slow." """
    first = _first_word(denied, 0, _SKIP_ADVERBS)
    second = _first_word(text, after, _SKIP_ADVERBS)
    return any(word in _STATUS_WORDS or word in _STATUS_PLACES or _progressive(word) for word in (first, second)) \
        or second in ("still", "currently", "now", "not", "never", "also")


# "It's" + a past participle is "it has" or a passive, not "it is" + a noun phrase: "This isn't the first time. It's
# happened twice this quarter.", "This isn't a regression. It's been broken since 2.3."
_PARTICIPLES = frozenset("""
been gone done got gotten had made taken given seen known become come run written broken chosen driven fallen forgotten
grown begun spoken shown thrown worn left kept lost found held built sent spent paid said told brought bought caught
taught thought felt meant met put set led won sold stood understood
""".split())
_PERFECT_ADVERBS = _SKIP_ADVERBS | {"already", "just", "since", "recently", "finally", "ever", "long"}
# An adjective that a to-, that- or wh-clause follows after "it is (not)": the "it" is a dummy subject. "It isn't
# clear what caused the spike.", "It is not possible to delete a project. It is possible to archive it."
_EXTRAPOSED_ADJECTIVES = frozenset("""
clear unclear possible impossible likely unlikely usual unusual common uncommon rare easy hard difficult known unknown
obvious necessary true surprising safe practical feasible fair okay ok required recommended advisable appropriate
""".split())
_EXTRAPOSED_NEXT = frozenset(("to", "that", "what", "why", "how", "when", "where", "whether", "if", "who", "which"))


def _has_participle(text: str, after: int) -> bool:
    """True if a past participle follows "it's" at after (see _PARTICIPLES)."""
    word = _first_word(text, after, _PERFECT_ADVERBS)
    return word in _PARTICIPLES or (len(word) > 4 and word.endswith("ed") and not word.endswith("eed"))


def _extraposed(text: str, pos: int = 0) -> bool:
    """True if the words at pos are an adjective of _EXTRAPOSED_ADJECTIVES and a to-, that- or wh-clause."""
    words = (m.group(0).lower() for m in _NEXT_WORDS.finditer(text, pos, min(len(text), pos + 80)))
    for word in words:
        if word in _SKIP_ADVERBS:
            continue
        return word in _EXTRAPOSED_ADJECTIVES and next(words, "") in _EXTRAPOSED_NEXT
    return False


def _be_contrast_skipped(text: str, s1: str, denied: str, s2: str, be2: str, after: int) -> bool:
    """True if "s1 is not <denied> ... s2 <be2>" (be2 ending at after) is not a contrast: a status or place, "it's" + a
    past participle, or a dummy "it" before an adjective and a clause."""
    return _states_status(text, denied, after) or (be2 in ("'s", "’s") and _has_participle(text, after)) \
        or (s1.lower() == "it" and _extraposed(denied)) or (s2.lower() == "it" and _extraposed(text, after))


# After a colon, a pronoun in lower case starts a contrast only when a verb, a noun phrase or "just" is denied ("they
# don't ship features", "it isn't a tool", "it's not just an update"), not an adjective ("it's not hard").
_DENIED_NOUN = re.compile(r"\s+(?:just|only|merely|simply|really|about|a|an|the|my|our|your|his|her|its|their|one|"
                          r"another|some)\b", re.IGNORECASE)


def _after_colon(text: str, pos: int) -> bool:
    """True if a colon comes before pos, after spaces, opening quotes and emphasis."""
    i = pos
    while i > 0 and (text[i - 1].isspace() or text[i - 1] in "\"'“‘(*_"):
        i -= 1
    return i > 0 and text[i - 1] == ":"


# A change over time, not a contrast between two things: the first sentence ends with a past time ("I didn't like it
# at first. I like it now.") or the second with "now" and the like ("I didn't really get it at twenty-six. I get it
# now.").
_THEN_END = re.compile(r"\b(?:at\s+first|back\s+then|at\s+the\s+time|until\s+recently|(?:years|months|weeks|days|"
                       r"a\s+year|a\s+month|a\s+week|long)\s+ago)[\s*_]*$", re.IGNORECASE)
_NOW_END = re.compile(r"[^.!?]{0,40}?\b(?:now|today|anymore|any\s+more|nowadays|these\s+days|again|at\s+last)"
                      r"[\s*_\"”’)]*(?:[.!?]|$)", re.IGNORECASE)


def _over_time(text: str, rest1: str, after: int) -> bool:
    """True if a two-sentence contrast, whose first sentence goes on with rest1 after the negation and whose second
    goes on at after, compares two times (_THEN_END, _NOW_END)."""
    return bool(_THEN_END.search(rest1) or _NOW_END.match(text, after))


def _two_sentence_end(text: str, masked: str, m: re.Match[str]) -> int:
    """Where the contrast that _NEG_TWO matched as m ends (the verb of the second sentence), or -1 if it is none."""
    if not _same_subject(m.group("s1"), m.group("s2")) or not _starts_sentence(masked, m.start()):
        return -1
    if m.group("s1").islower() and not (_after_colon(masked, m.start())
                                        and (m.group("v1") or _DENIED_NOUN.match(m.group("rest1")))):
        return -1  # "Here's the thing: it's not hard. It's barely even cooking." is not checked
    if m.group("v1") is None and m.group("be2") is not None:
        if _be_contrast_skipped(text, m.group("s1"), m.group("rest1"), m.group("s2"), m.group("be2").strip(),
                                m.end("be2")) or _over_time(text, m.group("rest1"), m.end("be2")):
            return -1
        return m.end("be2")
    if m.group("v1") is not None and m.group("v2") is not None \
            and m.group("v2").lower() in _verb_forms(m.group("v1")) \
            and not _over_time(text, m.group("rest1"), m.end("v2")):
        return m.end("v2")
    return -1


def _two_sentence_contrast(text: str, masked: str) -> Iterator[tuple[int, int]]:
    """(start, end) of each two-sentence contrast: from the first subject to the verb of the second sentence.

    text is the block's flat text, masked the same with its line breaks (for _starts_sentence). When a subject of
    several words is rejected, the search goes on from its second word, so a run of capitalized words over a line
    break does not hide the pronoun that starts the line ("Hi team" then "We don't sell software. We sell ..."); after
    a rejected one-word subject it goes on after that word, so a negated title line does not hide the contrast on the
    next line ("**It's not about the tools**" then "We didn't adopt a framework. We adopted a habit.")."""
    pos = 0
    while True:
        m = _NEG_TWO.search(text, pos)
        if m is None:
            return
        end = _two_sentence_end(text, masked, m)
        if end >= 0:
            yield m.start(), end
            pos = m.end()
            continue
        space = re.search(r"\s+", m.group("s1"))
        pos = m.start("s1") + space.end() if space else m.end("s1")


# Software and documents only: people (an agent, an assistant) may want, remember and do things happily. A server
# (in a restaurant) and a class (of students) are often people, so they count only after a software word ("the web
# server", "the base class").
_PERSON_SUBJECT = (r"(?:code|codebase|data|dataset|tool|system|function|method|logs?|architecture|design|"
                   r"framework|api|metrics?|numbers|graph|chart|compiler|tests?|errors?|repository|repo|pipeline|"
                   r"model|algorithm|database|schema|spreadsheet|dashboard|platform|app|application|script|"
                   r"service|daemon|scheduler|linter|cache|engine|library|plugin|bot|monitor|software|"
                   r"program|cli|sdk|workflow|logic|parser|module|component|"
                   r"(?:web|api|app|application|build|mail|dns|http|https|database|db|file|game|proxy|backend|origin|"
                   r"test|dev|staging|production|prod|sql|mcp|language|media|ci|auth|license|update|graphql|grpc)\s+"
                   r"server|(?:base|parent|child|abstract|wrapper|helper|utility|derived|super|java|python|ruby)\s+class)")
# "feels" is left out: "The dashboard feels faster" is perception, not a feeling.
_PERSON_VERB = (r"(?:tells?(?:\s+a\s+(?:[\w-]+\s+)?story)?|speaks?(?:\s+volumes)?|whispers?|screams?|sings?|knows?|"
                r"wants?|loves?|hates?|cares?|believes?|remembers?|forgets?|understands?|thinks?|refuses?|insists?|"
                r"begs?|"
                r"cries|craves?|longs?|dreams?|deserves?|demands?|breathes?|yearns?|resents?|watch(?:es)?\s+over|"
                r"gladly|happily|tirelessly|patiently|eagerly|cheerfully|lovingly|proudly|stubbornly|dutifully|"
                r"graciously|kindly|politely|bravely|(?:chooses?|chose|decides?|decided)\s+to|"
                r"has\s+a\s+(?:story|mind\s+of\s+its\s+own)|is\s+(?:happy|unhappy|angry|eager|reluctant))")
_PERSON_ADVERB = (r"(?:itself|quietly|silently|now|always|really|never|carefully|faithfully|dutifully|lovingly|"
                  r"gladly|happily|tirelessly|patiently|eagerly|cheerfully|proudly|stubbornly|graciously|kindly|"
                  r"politely|bravely)")
# Negated, only "care": "The scheduler doesn't care that rows went missing." "doesn't know" and "doesn't remember"
# usually state what a program has no data for ("The cache doesn't know about the new key").
_PERSON_NEGATED = r"(?:(?:does|do|did|would)n['’]t|won['’]t|(?:does|do|did|would|will)\s+not)\s+(?:really\s+)?care"
# A determiner and up to two modifiers before the subject: "These numbers tell a story.", "The customer survey data
# tells a compelling story."
_PERSONIFICATION = re.compile(
    r"\b(?:the|this|that|these|those|your|our|their|its|each|every|my)\s+(?:\w+\s+){0,2}?" + _PERSON_SUBJECT +
    r"\s+(?:(?:will|would)\s+)?(?:" + _PERSON_ADVERB + r"\s+)?"
    r"(?:(?:seems?|seemed|appears?|appeared)\s+to\s+)?(?:" + _PERSON_VERB + "|" + _PERSON_NEGATED + r")\b",
    re.IGNORECASE)

# Questions of up to six words; _SELF_Q_LONG has the forms that may run to nine ("But what does this mean for
# small teams?").
_SELF_Q = re.compile(
    r"^(?:(?:and|so|but)\s+)?(?:the\s+\w+(?:\s+\w+)?|why\s+does\s+(?:this|it|that)\s+matter|why\s+(?:is\s+)?(?:this|that)\s+important|"
    r"so\s+what|sound\s+familiar|why|how|what['’]s\s+the\s+catch|the\s+best\s+part|the\s+kicker)\?$",
    re.IGNORECASE)
_SELF_Q_LONG = re.compile(
    r"^(?:(?:and|so|but)\s+)?(?:what\s+does\s+(?:this|that|it)\s+mean(?:\s+for\s+\w+(?:\s+\w+)?)?|"
    r"what,\s*then,\s*(?:is|was|are|were)\s+the\s+\w+(?:\s+\w+)?)\?$",
    re.IGNORECASE)
# An answer that opens like this marks the question before it as self-answered ("What is the gap? Simply put, ...").
_ANSWER_OPENER = re.compile(
    r"^[*_\"“]*(?:simply\s+put|put\s+simply|in\s+short|in\s+a\s+word|(?:the\s+)?short\s+answer|the\s+answer\b|"
    r"here['’]s\s+the\s+thing|the\s+truth\s+is|spoiler)", re.IGNORECASE)
# "In today's rapidly evolving healthcare landscape,": the looser form of the stock-phrases.txt openers. The words
# between "today's" and the noun are modifiers, not a pronoun, an article or a verb's helper, and the noun ends the
# phrase, so "In today's call we reviewed the business plan" (minutes) is not reported.
_TODAYS_GAP_STOP = (r"(?:we|i|you|they|he|she|it|its|our|your|their|his|her|my|the|a|an|this|that|these|those|and|or|"
                    r"but|so|to|of|for|with|on|in|at|by|from|about|as|into|was|were|is|are|be|been|had|have|has|did|"
                    r"do|does|will|would|can|could|should|may|might|must|not|no)")
_TODAYS_OPENER = re.compile(
    r"\bin\s+today['’]s\s+(?:(?!" + _TODAYS_GAP_STOP + r"\b)[\w-]+\s+){0,4}?"
    r"(?:world|landscape|age|era|environment|climate|market|marketplace|economy|society|business)\b"
    r"(?=[\s\"”)\]*_]*(?:[,;:.!?—–|]|$))", re.IGNORECASE)
# An assistant's preamble before a text it drafted or revised. Checked in _preambles; the forms:
# - after an interjection that starts the sentence ("Certainly! Here's a revised version:", "Sure! Here's a draft
#   email you can send:"), with any of the nouns below; a noun of group "other" or "options" or "message" without
#   a verb only when a greeting or "Subject:" follows ("Sure, here's the updated schedule:" is a reply);
# - a revision lead-in (group "revised"): a revision adjective and a text noun (group "text": "Here's a polished
#   version of your email:", "Here's your revised email:") or any other noun (group "other": "Here's the updated
#   invitation:"), which is reported only when a mail follows, so "Here are the updated numbers:" is not;
# - an offer of a drafted mail ("Here's a reply you can send to Jordan:"): a mail noun (group "draft") and a verb
#   such as "you can send"; a generic noun (version, text, message, options) only before "send" or "forward", so
#   "Here are the options you can use with `tinyq worker`:" and "Here is the message you can use to test the
#   webhook:" are not reported;
# - a mail noun or a generic noun other than "options" without a verb, when a greeting or "Subject:" follows and the
#   noun is offered as a draft (_DRAFT_SIGN: "Here's a draft email to your landlord:" then "Dear Mr. Patel,"), and
#   "Here's a draft:".
# A mail or text noun followed by "template", "example", "address" and the like names something else ("Here is the
# email template you can copy for outage notices:", "Here's the updated email address:"). Without a verb, a noun
# followed by "from ..." or by a clause with its own subject and a past-tense verb is a mail someone wrote or sent
# (_SENT_AFTER), not a draft.
_REVISION_ADJECTIVE = (
    r"(?:revised|polished|rewritten|reworded|rephrased|edited|improved|refined|tightened|proofread|updated|"
    r"simplified|condensed|corrected|reworked|shortened|softened|streamlined|restructured|cleaned[- ]up|"
    r"cleaner|clearer|shorter|tighter|simpler|friendlier|warmer|softer|firmer|stronger|punchier|smoother|crisper|"
    r"sharper|briefer|longer|gentler|livelier|snappier|bolder|plainer|better|(?:more|less)\s+[\w-]+)")
# A noun after these words names something else: "email template", "email address", "note format".
_NOT_COMPOUND = (r"(?!\s+(?:templates?|examples?|samples?|formats?|address(?:es)?|threads?|signatures?|headers?|"
                 r"footers?|body|subjects?|lists?|clients?|servers?|settings)\b)")
_TEXT_NOUN = (r"(?:versions?|text|drafts?|copy|rewrites?|e-?mails?|mail|messages?|repl(?:y|ies)|responses?|notes?|"
              r"letters?|paragraphs?|sentences?|bio|intro(?:duction)?|posts?|summary|wording|phrasing|essay|"
              r"statement|announcement|description|caption|abstract|speech|outline|passage)" + _NOT_COMPOUND)
_MAIL_NOUN = r"(?:repl(?:y|ies)|drafts?|responses?|e-?mails?|notes?|rewrites?|letters?)" + _NOT_COMPOUND
# A word before the noun, optionally with a comma: "a tighter, friendlier version", "a revised, more concise
# version", "a professional and heartfelt resignation letter". Not a pronoun, a modal, a form of "be" or a word that
# opens a clause, so the noun phrase does not run into a clause ("the form where you can send notes").
_MODIFIER = (r"(?!(?:you|we|i|they|he|she|it|can|could|will|would|should|may|might|must|is|are|was|were|that|which|"
             r"who|where|when|to)\b)[\w-]+,?\s+")
# After the revision word, not a preposition or a determiner either: "the updated pricing for the email campaign"
# names pricing, not an email.
_NOUN_MODIFIER = (r"(?!(?:of|for|in|on|at|from|with|by|about|as|the|a|an|this|these|those|your|my|our|their)\b)"
                  + _MODIFIER)
_PREAMBLE = re.compile(
    r"(?P<interjection>\b(?:certainly|sure|absolutely|of\s+course|great\s+question)(?:[!.,]\s+|\s*[—–]\s*))?"
    r"\b(?:here(?:['’]s|\s+is|\s+are)|(?P<below>below\s+(?:is|are)))\s+(?P<det>a|an|the|your|some)\s+"
    r"(?:(?P<revised>(?:" + _MODIFIER + r"){0,4}?" + _REVISION_ADJECTIVE +
    r",?\s+(?:(?:" + _NOUN_MODIFIER + r"){0,3}?(?P<text>" + _TEXT_NOUN + r")\b|(?P<other>[\w-]+)))"
    r"|(?P<pre>(?:" + _MODIFIER + r"){0,5}?)(?:(?P<draft>" + _MAIL_NOUN + r")(?:\s+" + _MAIL_NOUN + r")?"
    r"|(?P<generic>versions?|text|options?|messages?))\b)"
    r"(?:[^.!?:\n]{0,40}?\b(?:you\s+(?:can|could|might|may)|for\s+you\s+to)\s+"
    r"(?P<verb>send|use|copy|paste|forward|adapt)\b)?",
    re.IGNORECASE)
# "I've revised your email to sound more confident:", "I have polished your cover letter:". Checked in _preambles like
# a lead-in that starts with "Below is": reported after an interjection (in mail only before a greeting or
# "Subject:"), or before a greeting or "Subject:".
_REVISED_YOUR = re.compile(
    r"(?P<interjection>\b(?:certainly|sure|absolutely|of\s+course|great\s+question)(?:[!.,]\s+|\s*[—–]\s*))?"
    r"\bI(?:['’]ve|\s+have)\s+(?:just\s+)?(?:revised|rewritten|polished|reworded|rephrased|edited|improved|refined|"
    r"tightened|proofread|updated|simplified|condensed|corrected|reworked|shortened|softened|streamlined|"
    r"restructured|cleaned\s+up)\s+your\s+(?:[\w-]+\s+){0,2}?" + _TEXT_NOUN + r"\b", re.IGNORECASE)
_EXAMPLE_WORD = re.compile(r"\b(?:sample|example|template|boilerplate)s?\b", re.IGNORECASE)
# A mail noun without a verb is a draft for the requester only after "a", "an" or "your", or with one of these words
# ("Here's the suggested reply:"); "Here's the email that went out on Monday:" shares a mail.
_DRAFT_SIGN = re.compile(r"\b(?:possible|suggested|proposed|draft|revised)\b", re.IGNORECASE)
# Past tense and past participles: "Here is the letter my grandfather wrote", "the reply I got", "the email that went
# out". Present forms in _IRREGULAR (does, says, has) are left out.
_PAST = (r"(?:[a-z]+ed|" + "|".join(sorted(
    {form for forms in _IRREGULAR.values() for form in forms.split()} - {"does", "says", "has"}
    | {"got", "put", "read", "was", "were", "forwarded", "shared"}, key=lambda w: (-len(w), w))) + r")")
_SENT_SUBJECT = (r"(?:i|we|he|she|they|you(?!\s+(?:asked|requested|wanted|needed)\b)|"
                 r"(?:my|our|his|her|their|the)\s+(?:[\w'’-]+\s+){0,2}?[\w'’-]+|"
                 r"(?!I['’])(?-i:[A-Z])[\w'’-]*(?:\s+[\w'’-]+){0,2}?)")
_SENT_VERB = r"(?:just\s+|already\s+|finally\s+|recently\s+)?(?:(?:had|has|have)\s+)?" + _PAST + r"\b"
# After the noun: "from ...", a relative clause in the past ("that went out", "which we sent"), a clause with its own
# subject ("my grandfather wrote", "I got", "we received"), or a participle with "by" ("written by Sam"). "Here's the
# letter you asked for:" and "Here's a draft I've put together:" speak to the requester and are not matched.
_SENT_AFTER = re.compile(
    r"\s+(?:from\b|(?:that|which|who)\s+(?:" + _SENT_SUBJECT + r"\s+)?" + _SENT_VERB + "|"
    + _SENT_SUBJECT + r"\s+" + _SENT_VERB + "|" + _PAST + r"\s+(?:by|from)\b)", re.IGNORECASE)
_PREAMBLE_COLON = re.compile(r"[^.!?:]{0,80}:")  # the clause ends with a colon: the drafted text comes next
_PREAMBLE_END = re.compile(r"[^.!?:]{0,80}[.!:]?\s*$")  # the clause ends the block
_SUBJECT = re.compile(r"^\s*[*_]*subject\s*:", re.IGNORECASE)

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
# "January – March", "20% – 30%", "Q1 – Q3", "10 kg – 12 kg", "9 am – noon". Month and weekday names need a capital
# ("may" is a verb) and a word end ("Janet", "Monica" and "Sunil" are names); a unit is one of _UNIT, so "We fixed 3
# bugs — 2 remain." is a clause.
_UNIT = (r"(?:[aApP]\.?[mM]\.?|°[CF]?|[nµum]?s|secs?|mins?|h|hrs?|d|wks?|mo|yrs?|days?|weeks?|months?|years?|"
         r"hours?|minutes?|seconds?|nights?|[mck]?m|in|ft|mi|yds?|[mk]?g|lbs?|oz|[mM]?[lL]|gal|qt|[kKMGTP]i?[Bb]|"
         r"miles?|feet|foot|inch(?:es)?|pounds?|ounces?|grams?|kilos?|lit(?:er|re)s?|met(?:er|re)s?|cups?|tbsp|tsp|"
         r"[kKMG]?bps|[kMG]?Hz|[kMG]?Wh?|m?V|m?Ah?|px|pt|r?em|dpi|fps|rpm|psi|mph|kph|km/h|[kKMBx]|bn)(?![\w/])")
_ENDPOINT = (
    r"(?:(?:[$€£¥]\s?)?[~≈]?\d[\d,.:]*(?:\s?%)?|[vV]\d+(?:\.\d+)*[a-z]?|Q[1-4]|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
    r"Mon|Tues?|Wed|Thu(?:rs?)?|Fri|Sat|Sun)(?![A-Za-z])\.?|(?i:noon|midday|midnight)(?![A-Za-z]))"
    r"(?:\s?" + _UNIT + r")?")  # "9 am", "5 km", "10 GB"
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
         # "Day 2", "Step 1", "Part II", "Option A", "wk 46", "Slide 3", "Act II"
         r"(?:day|week|wk|sprint|phase|step|part|chapter|lesson|module|stage|option|slide|section|session|episode|"
         r"segment|act|scene|unit|exercise|milestone|round|lecture|appendix)\s+"
         r"(?:\d+(?:\.\d+)*[a-z]?|(?-i:[IVX]{1,4}|[A-Za-z]))(?![\w.])")
_ZONE = r"(?:\s*\(?(?:utc|gmt|[a-z]{1,3}[sd]?t)(?:\s*[+-]\s*\d{1,2}(?::?\d{2})?)?\)?)?"
_VERSION = (r"(?:(?:version|revision|rev\.?|release|v)\s*\d+(?:\.\d+)*[a-z]?|"
            # "1.2.0 — Added dedup", "2.0.0-rc1"; "9.30" is left to _TIME, so a run of them has one reading
            r"(?!\d{1,2}\.\d{2}(?![\d.-]))\d+\.\d+(?:\.\d+)*(?:-[\w.]+)?)")
_STAMP_LABEL = (r"(?:(?:effective|updated|last\s+updated|last\s+revised|revised|published|released|issued|dated?)"
                r"(?:\s+on)?:?\s+)?")
# "2026-11-13 (Fri)", "Monday (Mar 3)", "Tue (11/12)": a weekday, date or time in parentheses after a date or time.
_STAMP_NOTE = r"(?:\s*\(\s*(?:" + _TIME + "|" + _DATE + r")" + _ZONE + r"\s*\))?"
_ONE_STAMP = r"(?:" + _STAMP_LABEL + r"(?:" + _TIME + "|" + _DATE + r")" + _ZONE + _STAMP_NOTE + "|" + _VERSION + r")"
# "Dec 3–5", "v1.0–v1.4", "2.0.0 – 2.3.1"
_RANGE_END = r"(?:(?:" + _TIME + "|" + _DATE + r")" + _ZONE + "|" + _VERSION + r"|\d{1,2}(?:st|nd|rd|th)?)"
# Stamps in a row need a separator, so a long run of digits and dots ("1.11.11.1...") cannot be split in
# exponentially many ways. No "^": the line starts at pos, which is after a line break for a later line.
_STAMPS = _ONE_STAMP + r"(?:[\s,]+" + _ONE_STAMP + r")*"
_STAMP = re.compile(r"[\s*_\[(]*" + _STAMPS + r"(?:[\s,]*(?:[-–—]|to\b)\s*" + _RANGE_END
                    + r"(?:[\s,]+" + _STAMPS + r")?)?[\s,]*[*_\])]*\s*$", re.IGNORECASE)
# Any other numbered label that is all that comes before a dash at the start of a line: a capitalized word and a
# number or a roman numeral ("Milestone 2", "Episode 12", "SEGMENT 2", "Exercise 4.2"), or a range ("Units 3–5"),
# with stamps after it ("Session 3, Nov 12"). Checked in _label_dash only on a line with no sentence end after the
# dash, so "Python 3.9 – the oldest we support – is end of life in October." is still reported. Prepositions and
# quantifiers do not label anything: "Over 50 — and counting", "In 2024 — the year we shipped".
_LINE_LABEL = re.compile(
    r"[\s*_\[(]*(?!(?:over|about|nearly|almost|only|just|under|around|roughly|exactly|approximately|in|on|at|by|for|"
    r"to|from|with|after|before|since|until|and|or|but|the|a|an|of|all|some|every|each|than|up|down)\b)"
    r"(?-i:[A-Z][a-z]+|[A-Z]{2,})\s+(?:\d+(?:\.\d+)*[a-z]?|(?-i:[IVXLC]{1,6}))(?![\w.])"
    r"(?:\s*[-–]\s*(?:\d+(?:\.\d+)*[a-z]?|(?-i:[IVXLC]{1,6}))(?![\w.]))?(?:[\s,]+" + _STAMPS + r")?"
    r"[\s,]*[*_\])]*\s*$", re.IGNORECASE)
# A date, a due time or an owner after a dash at the end of a list item or a title line: "- Grace: confirm the quote
# — Fri 8 Mar", "— next meeting", "— before HR meeting", "- Fix the alert — Marco", "Platform team weekly — Tue 5 Mar
# 2024, 10:00–10:45", "On-call handoff — wk 46 (Nov 11–18)". Checked in _trailing_tag.
_EVENT = (r"(?:meeting|call|standup|stand-up|sync|review|retro|retrospective|planning|demo|offsite|release|launch|"
          r"deadline|freeze|cutover|migration|handoff|kickoff|kick-off)s?")
_DUE_WORD = (r"(?:(?:next|this|last)\s+(?:" + _EVENT + r"|week|month|quarter|sprint|time|morning|afternoon|evening|"
             r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)|today|tomorrow|tonight|asap|eod|eow|eom|"
             r"cob|tbd|tbc|ongoing|in\s+progress|end\s+of\s+(?:the\s+)?(?:day|week|month|quarter|sprint|year))")
_STAMP_RUN = _STAMPS + r"(?:[\s,]*(?:[-–—]|to\b)\s*" + _RANGE_END + r")?"
# "Fri 20 Nov", "Fri 20 Nov (Thu)", "EOD", "the 20th", "mid-November", "end of Q3"; then optionally a time or day
# ("5 pm on Friday", "Friday noon", "end of day Friday").
_DUE_WHEN = (r"(?:" + _STAMP_RUN + r"(?:\s*\(\s*" + _STAMP_RUN + r"\s*\))?|" + _DUE_WORD
             + r"|the\s+\d{1,2}(?:st|nd|rd|th)|(?:early|mid|late|end\s+of)[\s-]+(?:" + _MONTH + "|" + _WEEKDAY
             + r"|q[1-4]|(?:the\s+)?(?:week|month|quarter|year)))"
             r"(?:[\s,]+(?:(?:on|at)\s+)?(?:" + _STAMP_RUN + r"|noon|midday|midnight))?")
_DUE_TAIL = re.compile(
    r"[ \t]*[*_(\[]*(?:(?:(?:due|deadline|eta|target)[*_]*\s*:?[*_]*\s+(?:(?:by|before|on)\s+)?"
    r"|(?:by|before|after|until|till|on|from|no\s+later\s+than)\s+)?" + _DUE_WHEN +
    r"|(?:due\s+)?(?:by|before|after|until)\s+(?:the\s+)?(?:[\w-]+\s+){0,2}?" + _EVENT + r")"
    r"[*_)\]]*[.;]?[ \t]*$", re.IGNORECASE)
_OWNER = r"(?:@[\w.-]+|[A-Z][\w'’-]+(?:[ \t]+[A-Z][\w'’-]+)?)"
_OWNER_TAIL = re.compile(r"[ \t]*[*_(\[]*" + _OWNER + r"(?:[ \t]*(?:,|&|\+|/|and)[ \t]*" + _OWNER + r")*"
                         r"[*_)\]]*[.;]?[ \t]*$")
_SENTENCE_MARK = re.compile(r"[.!?](?:\s|$)")
# A man page's NAME line: "logsift — filter and summarize structured log files", "grep, egrep — print lines".
_NAME_LINE = re.compile(r"[*_\s]*[\w.+:-]+(?:[*_]*\s*,\s*[*_]*[\w.+:-]+)*[*_\s]*")
# A field label after a dash: "Fix the alert — Owner: Marco Ruiz — Due: Dec 5".
_FIELD_AFTER = re.compile(r"\s*[*_]*[A-Z][\w/&-]*(?:[ \t]+[\w/&-]+){0,2}[*_]*:[*_]*(?:\s|$)")
# A paragraph that starts like a lettered or numbered item, "(a)", "a)", "(iv)", "(1)", is a list after a colon.
_LETTERED_ITEM = re.compile(r"^(?:\((?:[a-z]|[ivx]{1,6}|\d{1,3})\)|(?:[a-z]|[ivx]{1,6})\))\s", re.IGNORECASE)
# A line of a field block ("Date: Friday, Dec 18" then "Time: 5:30 pm"): a capitalized label of up to four words, a
# colon and a value. A paragraph of two or more such lines is a list after a colon.
_FIELD_LINE = re.compile(r"^[*_]*[A-Z][\w'’/&().-]*(?:[ \t]+[\w'’/&().-]+){0,3}[*_]*:[*_]*[ \t]+\S")
# A paragraph that is only an image or display math still follows a colon.
_FIGURE_LINE = re.compile(r"^(?:\[?!\[[^\]]*\](?:\([^()]*\)|\[[^\]]*\])(?:\]\([^()]*\))?\s*)+$|^\$\$|^\\\[")
# Every code point that can start an emoji in tx.emoji_spans, and the keycap mark of 1️⃣ and #️⃣.
_EMOJI_CANDIDATE = re.compile("[\u00A9\u00AE\u203C\u2049\u2122\u2139\u2190-\u2BFF\u20E3\u3030\u303D\u3297\u3299"
                              "\U0001F000-\U0001FAFF]")

_BOLD_LABEL = re.compile(r"^\s*(?:\*\*|__)([^*_\n]{1,60}?)(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*:)(?:\s|$)")
_LINE_BOLD_LABEL = re.compile(_BOLD_LABEL.pattern, re.MULTILINE)  # a bold label at the start of any line
# A speaker's name in a script or transcript: one to three capitalized words or initials, then an optional number
# ("Speaker 1", "Participant 3", "Caller 12") and an optional note in parentheses ("G", "OWEN", "Dr. Lee", "Peter
# Hardwick", "P2", "MAYA (V.O.)", "DEV (into the phone, whispering)", "Q").
_SPEAKER = re.compile(r"(?:[A-Z][\w'’.-]*)(?:\s+[A-Z][\w'’.-]*){0,2}(?:\s+\d{1,3})?(?:\s*\([^()\n]{1,40}\))?")
# The text inside cannot contain the delimiter, so an unclosed ** stops at the next one (linear time).
_BOLD_SPAN = re.compile(r"\*\*(?=\S)(?:[^*\n]|\*(?!\*))+?(?<=\S)\*\*|__(?=\S)(?:[^_\n]|_(?!_))+?(?<=\S)__")
_STOP_STARTS = {"the", "a", "an"}
_LINK_DEFINITION = re.compile(r"^\s*\[[^\]]+\]:\s*\S")
# A letter's salutation on a line of its own ends with a colon in US business letters. "To the ...:" and "To all
# ...:" name the addressee with a capital or a role ("To the Graduate Admissions Committee:", "To the editor:", "To
# all staff:", "To All Residents of Building C:"), so "To the point:" and "To all of this:" are still reported.
_ADDRESSEE = (r"(?:editors?|committee|manager|managers|team|teams|board|council|panel|members|residents|parents|families|"
              r"staff|director|department|chair|reviewers?|employees|tenants|students|faculty|volunteers|customers|"
              r"users|contributors|colleagues|attendees|participants|concerned|hands)")
_SALUTATION = re.compile(r"^\s*(?:dear\b|to\s+whom\s+it\s+may\s+concern\b|(?:ladies\s+and\s+)?gentlemen\b|"
                         r"(?:hello|hi|greetings)\b[^.!?]{0,40}:\s*$|"
                         r"to\s+(?:the|all)\s+(?:(?-i:[A-Z])[^.!?:\n]{0,60}|(?:[\w'’-]+\s+){0,4}?" + _ADDRESSEE
                         + r")\s*:\s*$)", re.IGNORECASE)
# A mail's greeting on a line of its own ("Hi Ana,", "Dear Mr. Lee:", "Hello team"). After it, "Here's a draft reply
# you can send to the customer:" is the writer's own mail, not an assistant's preamble.
_GREETING = re.compile(r"^\s*(?:hi|hello|hey|dear|greetings|good\s+(?:morning|afternoon|evening)|"
                       r"to\s+whom\s+it\s+may\s+concern)\b(?:[^.!?:\n]|(?<=mr|ms|dr)\.|(?<=mrs)\.){0,40}[,:!]?\s*$",
                       re.IGNORECASE)
# A mail's sign-off: "Best,", "Kind regards,", "Thanks," then a name. Without a comma only when a name line follows.
_SIGN_OFF = re.compile(
    r"^\s*[*_]*(?:best(?:\s+(?:regards|wishes))?|(?:kind|warm|warmest|with)\s+(?:regards|thanks|wishes)|regards|"
    r"thanks(?:\s+(?:again|so\s+much))?|thank\s+you|many\s+thanks|cheers|sincerely|yours(?:\s+(?:truly|sincerely|"
    r"faithfully))?|warmly|respectfully|all\s+the\s+best|take\s+care)[*_]*\s*(?P<comma>,)?[*_]*\s*$", re.IGNORECASE)
# An offer that speaks about the drafted mail itself: "Let me know if you'd like me to adjust the tone or make it more
# concise!", "Would you like me to create a shorter version?" After the sign-off or a thematic break it is the
# assistant's, not the writer's, so it is reported in mail too.
# "Draft" alone is left out ("the draft agenda" in a postscript is the writer's), and so is an editing verb with any
# object ("Feel free to tweak the config" after a thematic break in a README).
_DRAFT_TALK = re.compile(
    r"\b(?:tone|concise|wording|phrasing|formality|(?:more|less|too|a\s+bit)\s+(?:formal|casual)|"
    r"(?:this|that)\s+draft|(?:" + _REVISION_ADJECTIVE + r"|different|another|alternative|alternate)\s+"
    r"(?:version|draft|take)|(?:adjust|tweak|rewrite|rephrase|reword|tailor|personali[sz]e|polish|shorten|edit)\s+"
    r"(?:it|this|the\s+(?:tone|wording|length|email|message|letter|note|post|draft|text|reply|bio|intro))|"
    r"(?:make|keep)\s+it\s+(?:shorter|longer|more|less))\b", re.IGNORECASE)
# After a thematic break in a document with no greeting or sign-off before it (not mail), _DRAFT_TALK alone is too
# loose: "If you'd like a different version of the binary, see Releases.", "Feel free to suggest clearer wording",
# "Feel free to tweak it for your team" end READMEs and guides. There an offer needs words that name a draft, or the
# assistant offering to change the text itself ("Let me know if you want me to tailor it to your PR template!").
_DRAFT_SPECIFIC = re.compile(
    r"\b(?:(?:this|that)\s+draft|(?:adjust|change|tweak|soften|shift|warm\s+up|tone\s+down|make)\s+the\s+tone|"
    r"version\s+of\s+(?:the|this|your)\s+(?:e-?mail|message|letter|reply|response)|"
    r"(?:adjust|tweak|rewrite|rephrase|reword|tailor|personali[sz]e|polish|shorten|edit|revise|soften)\s+"
    r"(?:the|this|your)\s+(?:e-?mail|message|letter|reply|response|draft))\b", re.IGNORECASE)
_SELF_OFFER = re.compile(r"\b(?:(?:like|want|prefer)\s+me\s+to|shall\s+i|i\s+can\s+also|"
                         r"i['’]d\s+be\s+happy\s+to|i['’]m\s+happy\s+to)\b", re.IGNORECASE)
# A header that starts an earlier message in a pasted thread.
_MESSAGE_HEADER = re.compile(r"^\s*(?:(?:from|sent)\s*:|-{2,}\s*(?:original|forwarded)\s+message\s*-{2,})|"
                             r"^\s*on\b[^\n]{0,200}(?:\n[^\n]{0,200})?\bwrote\s*:\s*$", re.IGNORECASE | re.MULTILINE)


def _draft_offer(sentence: str, mode: str) -> bool:
    """True if the sentence of an offer talks about the drafted text: _DRAFT_TALK in "loose" mode; in "strict" mode,
    _DRAFT_SPECIFIC, or the assistant offering to change the text itself with _DRAFT_TALK."""
    if mode == "loose":
        return bool(_DRAFT_TALK.search(sentence))
    return bool(_DRAFT_SPECIFIC.search(sentence) or (_SELF_OFFER.search(sentence) and _DRAFT_TALK.search(sentence)))


# The start of an offer, for offers that no word list has: "Would you like a shorter version for SMS as well?",
# "Feel free to adjust the dates, discount amount, or tone to fit your brand voice."
_OFFER_OPENER = re.compile(
    r"(?:would\s+you\s+like|do\s+you\s+want|want\s+me\s+to|shall\s+i|let\s+me\s+know\s+if|feel\s+free\s+to|"
    r"if\s+you['’]d\s+(?:like|prefer)|i\s+can\s+also|i['’]d\s+be\s+happy\s+to|i['’]m\s+happy\s+to)\b", re.IGNORECASE)
_AFTER_DRAFT_NOTE = ("an offer to change the draft, after the sign-off or a thematic break: delete it (reported in "
                     "every doc type)")
# Underscores that open or close emphasis, not those inside a snake_case_name.
_EMPHASIS_UNDERSCORE = re.compile(r"(?<!\w)_+|_+(?!\w)")


def _words_view(masked: str) -> str:
    """masked with emphasis underscores as spaces (same offsets), so that word lists, project words and the
    pattern rules see the words in "_seamless_", "__leverage__" and "_may potentially_"."""
    if "_" not in masked:
        return masked
    return _EMPHASIS_UNDERSCORE.sub(lambda m: " " * len(m.group(0)), masked)


def _after_rule(doc: tx.Document, block: tx.Block) -> bool:
    """True if a thematic break ("---") is the last line before the block that is not blank. A setext heading's
    underline is not a thematic break."""
    index = block.lines[0].no - 2  # the 0-based index of the line before the block
    while index >= 0 and doc.lines[index].kind == "blank":
        index -= 1
    return index >= 0 and doc.lines[index].kind == "rule" and not doc.lines[index].setext


def _sentence_around(text: str, start: int, end: int, limit: int = 300) -> str:
    """The sentence of text that holds [start, end), up to limit characters on each side."""
    left = max(text.rfind(mark, max(0, start - limit), start) for mark in ".!?") + 1
    rights = [i for i in (text.find(mark, end, end + limit) for mark in ".!?") if i >= 0]
    return text[max(left, start - limit):min(rights) + 1 if rights else min(len(text), end + limit)]


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
# Placeholders written after the option in a man page or a help text: LEVEL, KEY=PATTERN, FILE..., <path>, [WHEN].
_METAVAR = r"(?:[A-Z][A-Z0-9_]*(?:=[A-Z][A-Z0-9_]*)?|<[\w.-]+>)(?:\.\.\.)?"
_METAVARS = re.compile(_METAVAR + r"(?:[\s\[\]|,]+" + _METAVAR + r")*[\s\[\]|,]*")
# A type or default note in parentheses after the term in an API reference: "`timeout` (float) – ...", "`cache`
# (`bool`, default `True`) – ...". No dash inside, so a clause in parentheses with a dash is still checked.
_TYPE_NOTE = re.compile(r"\([^()\n—–]{1,60}\)")


def _term_ends(masked: str, plain: str, line: int) -> tuple[int, int]:
    """Where a dash may stand after the term that starts the line at offset line: (end of the term, end of the
    placeholders after it), or (-1, -1) when the line does not start with inline code or a URL.

    "- `--threads N` — number of workers" is an option list: the dash separates a term from its description.
    Aliases joined by a comma, a slash or "or" count as one term ("- `-h`, `--help` — show help"), and so do
    placeholders in capitals or angle brackets outside the backticks ("`-l`, `--level` LEVEL — show only ...") and
    one type note in parentheses ("- `timeout` (float) – HTTP timeout in seconds", _TYPE_NOTE). A
    link with words ("[Guide](guide.md) — ...") is still checked, and so is a line with no code or URL at all, even
    after a bracket or emphasis ("[UPDATE — the fix is live.]", "_IMPORTANT_ — back up first."). Computed once per
    line: neither run can pass a dash, so both end at or before the first dash on the line.
    """
    glue = _TERM_GLUE.match(masked, line)  # matches the empty string at least
    end = glue.end() if glue else line
    # Code and URLs are spaces in masked and characters in plain.
    if not any(masked[i] == " " and not plain[i].isspace() for i in range(line, end)):
        return -1, -1
    # The glue stops inside an opening parenthesis that holds words: one type note may follow the term.
    paren = masked.rfind("(", line, end)
    if paren >= 0 and masked.find(")", paren, end) < 0:
        note = _TYPE_NOTE.match(masked, paren)
        if note:
            glue = _TERM_GLUE.match(masked, note.end())
            end = glue.end() if glue else note.end()
    run = _METAVARS.match(masked, end)
    return end, run.end() if run else end


# An all-capitals label of up to four words that starts a line (after brackets or emphasis): a stage direction or a
# section label ("**[COLD OPEN — ambient sound: wind, birds]**", "[THEME MUSIC — 10 sec, then under]").
_CAPS_LABEL = re.compile(r"[\s*_\[(]*[A-Z][A-Z0-9&'’/+-]+(?:[ \t]+[A-Z][A-Z0-9&'’/+-]*){0,3}[\s*_\])]*")
_SENTENCE_END = re.compile(r"[.!?][\])*_\"”’]*(?:\s|$)")
# A screenplay scene heading, whose dashes separate its parts: "INT. KITCHEN — NIGHT", "EXT. PARKING LOT – DAY",
# "INT./EXT. CAR — MOVING — DAY", "**INT. MAYA'S APARTMENT — CONTINUOUS**". Checked like _CAPS_LABEL: no sentence may
# end after the dash on the line.
_SCENE_HEADING = re.compile(r"[\s*_\[(]*(?:INT\.?/EXT|EXT\.?/INT|I/E|INT|EXT)\.[ \t]+[A-Z0-9]")


class _DashLine(NamedTuple):
    """What the em_dash rule needs to know about one line of a block, computed once per line (so that a long line
    with many dashes is scanned once, not once per dash)."""

    end: int  # the offset where the line ends
    term_end: int  # _term_ends
    placeholders_end: int
    label_end: int  # where an all-capitals label at the line start ends, or -1
    scene: bool  # the line is a screenplay scene heading
    last_stop: int  # where the last sentence end on the line starts (_SENTENCE_END), or -1
    reply_subject: bool  # a Subject: line of a reply or forward, or in a pasted message's header


def _label_dash(masked: str, line: int, start: int, end: int, last_stop: int) -> bool:
    """True if a numbered label (_LINE_LABEL) is all that comes before the dash at masked[start:end] on its line, which
    starts at offset line, and no sentence ends after the dash on the line (the last one starts at last_stop): "##
    Milestone 2 — Beta"."""
    if start - line > 60 or not _LINE_LABEL.match(masked, line, start):
        return False
    return last_stop < end


def _caps_label_dash(line: int, start: int, end: int, label_end: int, last_stop: int) -> bool:
    """True if the dash at [start, end) follows an all-capitals label that ends at label_end (_CAPS_LABEL, matched on
    plain from the line start, so code is not a label) and no sentence ends after it on the line (the last one starts
    at last_stop). A sentence after the label is still checked: "[UPDATE — the fix is now live for all customers.]",
    "_IMPORTANT_ — back up first."."""
    return start == label_end and label_end > line and last_stop < end


def _trailing_tag(masked: str, kind: str, line: int, line_end: int, start: int, end: int) -> bool:
    """True if the dash at masked[start:end] is followed, up to the end of its line (line_end), by a date, a due time
    or (in a list item) an owner, on a list item or on a title line: a heading, or the first line of a paragraph with
    no sentence end before the dash, no period after the tag, and no lower-case word on the next line that would
    continue a sentence ("- Ivo: estimate egress savings — next meeting", "Platform team weekly — Tue 5 Mar 2024"
    then "Attendees: ...")."""
    if line_end - end > 60:
        return False
    if kind == "list":
        return bool(_DUE_TAIL.match(masked, end, line_end) or _OWNER_TAIL.match(masked, end, line_end))
    if kind not in ("para", "heading") or _SENTENCE_MARK.search(masked, line, start) \
            or masked[end:line_end].rstrip().endswith((".", ";")):
        return False
    if kind == "para" and (line > 0 or masked[line_end + 1:line_end + 2].islower()):
        return False
    return bool(_DUE_TAIL.match(masked, end, line_end))


# A mail's subject line. A reply or forward ("Re:", "Fwd:", "AW:") keeps the subject it answers, and so does a
# message pasted with its header; a new subject is checked like a title.
_SUBJECT_LINE = re.compile(r"[ \t]*[*_]*subject[*_]*[ \t]*:[*_]*[ \t]*(?P<reply>(?:re|fwd?|aw|wg|sv|tr)[ \t]*:)?",
                           re.IGNORECASE)


def _dash_line(masked: str, plain: str, line: int, kind: str) -> _DashLine:
    """The _DashLine of the line that starts at offset line, in a block of this kind."""
    end = masked.find("\n", line)
    end = len(masked) if end < 0 else end
    caps = _CAPS_LABEL.match(plain, line)
    stop = -1
    for m in _SENTENCE_END.finditer(masked, line, end):
        stop = m.start()
    subject = _SUBJECT_LINE.match(plain, line)
    term_end, placeholders_end = _term_ends(masked, plain, line)
    return _DashLine(end, term_end, placeholders_end, caps.end() if caps else -1,
                     bool(_SCENE_HEADING.match(plain, line)), stop,
                     bool(subject and (subject.group("reply")
                                       or (kind == "para" and _MESSAGE_HEADER.search(plain)))))


# A news or press dateline that opens a paragraph: a place in capitals, then optionally a state or country, a date
# and a news agency or wire ("HARBOR CITY —", "SAN FRANCISCO, March 3, 2025 —", "PORTLAND, Ore. (AP) —", "LONDON,
# March 3 (Reuters) —", "AUSTIN, Texas, Jan. 5, 2026 /PRNewswire/ --"). Checked in _dateline.
_DATELINE = re.compile(
    r"[*_]*(?P<place>[A-Z][A-Z.'’&-]+(?:[ \t]+[A-Z][A-Z.'’&-]*){0,3})"
    r"(?:,[ \t]*[A-Z][A-Za-z.]*(?:[ \t]+[A-Z][A-Za-z.]*)?)?"  # ", Calif.", ", N.Y.", ", New Mexico"
    r"(?:,?[ \t]+(?i:" + _DATE + r"))?"
    r"(?:[ \t]*\([A-Z][\w .&/-]{0,30}\)|[ \t]*/[A-Za-z][\w .&-]{0,30}/)?[*_]*[ \t]*")
# Words in capitals that open a paragraph as a label or an announcement, not as a place: "UPDATE — The fix is
# live.", "BREAKING NEWS — Acme ...", "PRO TIP — Save often."
_NOT_PLACES = frozenset("""
NOTE NOTES UPDATE UPDATED UPDATES EDIT EDITED FYI IMPORTANT WARNING CAUTION DANGER TIP TIPS PSA BREAKING NEWS SPOILER
SPOILERS CORRECTION DISCLAIMER REMINDER ALERT URGENT TL;DR TLDR PS P.S. NB N.B. ETA ANNOUNCEMENT ACTION TODO DONE FIXED
RESOLVED QUESTION ANSWER SUMMARY CONTEXT BACKGROUND PROBLEM SOLUTION RESULT RESULTS STATUS OK OKAY YES NO AND BUT OR SO
THE A AN I WE IT THIS THAT NEW HOT TAKE PRO FUN FACT SIDE HEADS UP FULL DISCLOSURE QUICK BIG LAST FINAL BONUS LIVE
NOW TODAY TONIGHT WATCH LISTEN READ SEE ALSO MORE SALE FREE OFFER DEAL LIMITED TIME ONLY SPECIAL EXCLUSIVE
ATTENTION GOOD BAD GREAT HUGE WOW YAY THANKS LOL OMG GAME CHANGER PLOT TWIST STOP REAL TALK TRUE STORY LESSON LESSONS
KEY TAKEAWAY TAKEAWAYS RULE MYTH TRUTH REALITY CONFESSION UNPOPULAR OPINION THREAD ICYMI FINALLY OFFICIALLY JUST
ANNOUNCING INTRODUCING COMING SOON OUT AVAILABLE WELCOME HELLO HI HEY CONGRATS CONGRATULATIONS PLEASE NOTICE MEMO FAQ
WHY WHAT HOW WHEN WHERE WHO MY OUR YOUR ME YOU US THEY HE SHE IS ARE WAS NOT NEVER ALWAYS EVERY ALL ONE FIRST NEXT TOP
BEST STEP PART CHAPTER ROUND DAY WEEK INT EXT I/E INT./EXT EXT./INT INT/EXT EXT/INT
""".split())


def _dateline(masked: str, start: int, end: int) -> bool:
    """True if the dash at masked[start:end] follows a dateline (_DATELINE) that opens the block, and a capitalized
    word follows the dash."""
    if start > 80:
        return False
    m = _DATELINE.fullmatch(masked, 0, start)
    if m is None or any(word.strip(".") in _NOT_PLACES or word in _NOT_PLACES for word in m.group("place").split()):
        return False
    nxt = re.match(r"[ \t]*[*_\"“‘']*([^\W\d_])", masked[end:end + 8])
    return bool(nxt and nxt.group(1).isupper())


def _line_start(newlines: list[int], pos: int) -> int:
    """The offset where the line that holds pos starts, given the sorted offsets of the line breaks."""
    i = bisect.bisect_left(newlines, pos)
    return newlines[i - 1] + 1 if i else 0


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


# A line that starts a slide in a deck written without headings: "**Slide 1: Title**", "Slide 2 - Agenda".
_SLIDE_LINE = re.compile(r"^[\s*_#]*slide\s+\d+\b", re.IGNORECASE)


def _slide_notes(doc: tx.Document) -> set[int]:
    """Indexes of the blocks that are notes to the requester around a deck, not slides: the blocks before the first
    heading, thematic break or "Slide 1" line ("Here's a revised version of your deck:"), and the blocks after the last
    thematic break when no heading or "Slide N" line comes after it and a slide start or another break comes before it
    ("---" then "Let me know if you'd like me to add speaker notes."). A setext heading's underline is not a break."""
    rules = [ln.no for ln in doc.lines if ln.kind == "rule" and not ln.setext]
    starts = [b.lines[0].no for b in doc.blocks
              if b.kind == "heading" or (b.kind == "para" and _SLIDE_LINE.match(b.lines[0].content))]
    if not rules and not starts:
        return set()
    first = min(rules + starts)
    notes = {bi for bi, b in enumerate(doc.blocks) if b.lines[-1].no < first}
    if rules and not any(no > rules[-1] for no in starts) and first < rules[-1]:
        notes.update(bi for bi, b in enumerate(doc.blocks) if b.lines[0].no > rules[-1])
    return notes


def _allowed_spans(allow: list[tuple[re.Pattern[str], str]], seen: str, low: Optional[str]) -> list[tuple[int, int]]:
    """(start, end) of each occurrence of an allow.txt entry in a block's words view."""
    return [m.span() for pattern, key in allow for m in _scan(pattern, key, seen, low) if m.end() > m.start()]


def _drop_allowed(found: list[Finding], since: int, allowed: list[tuple[int, int]]) -> None:
    """Remove the word-list, chat and project-word findings in found[since:] that lie inside an allowed phrase:
    with "plays a crucial role" in allow.txt, neither that phrase nor "crucial" inside it is reported."""
    if allowed:
        found[since:] = [f for f in found[since:] if f.rule not in LIST_RULE_NAMES
                         or not any(s <= f.start and f.end <= e for s, e in allowed)]


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
    allow = [(pattern, _first_key(entry)) for entry, pattern in words.allow_patterns()]
    title = _title_block(doc)
    first_prose = -1
    greeted = False  # a greeting line came before this block
    signed = False  # a mail's sign-off came before this block, after the last greeting or message header
    mail_seen = False  # a greeting or a sign-off came before this block

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
        # A new message in a pasted thread starts with a greeting or a header ("From:", "On ... wrote:"): the offers
        # in it are its writer's, not an assistant's after the mail. Only offers before the header (offset
        # header_at) can be after the mail.
        header = _MESSAGE_HEADER.search(plain) if block.kind == "para" else None
        header_at = header.start() if header else len(plain)
        if greeting:
            signed = False
        # After the mail: after its sign-off, or right after a thematic break ("---" then the assistant's offer) in
        # mail or after a greeting or sign-off (loose: any talk about the draft). After a thematic break elsewhere,
        # only an offer with words about a draft (strict: "adjust the tone", "this draft").
        rule_before = _after_rule(doc, block)
        loose = signed or (rule_before and (doc_type == "mail" or mail_seen))
        offer_mode = "loose" if loose else "strict" if rule_before else ""
        if header_at == 0:
            offer_mode = ""  # the block starts an earlier message
        sign_off = block.kind == "para" and _SIGN_OFF.match(block.lines[0].content)
        new_sign_off = bool(sign_off and (sign_off.group("comma") or len(block.lines) > 1))
        signed = (signed or new_sign_off) and not header
        mail_seen = mail_seen or greeting or new_sign_off
        is_title = bi == title  # the document title is not changed: only emoji and bold markup are reported
        quotes: Optional[_Quotes] = None

        def add(rule: str, start: int, end: int, message: str, exempt_in: tuple[str, ...] = (),
                severity: str = "", _plain: str = plain, _locate: _Locator = locate, _bi: int = bi) -> None:
            no, col = _locate(start)
            f = _make(doc, rule, no, col, message, _plain[start:end], start, end, _bi, exempt_in)
            if severity:
                f.severity = severity
            found.append(f)

        allowed: Optional[list[tuple[int, int]]] = None  # where allow.txt entries occur in the block, once needed

        # word lists
        listed = len(found)
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
                    exempt_in = types
                    if offer_mode and "mail" in types and name == "closing-courtesies" and m.start() < header_at \
                            and _draft_offer(_sentence_around(seen, m.start(), m.end()), offer_mode):
                        exempt_in = tuple(t for t in types if t != "mail")
                        note = _AFTER_DRAFT_NOTE
                    add(rule, m.start(), m.end(), _list_message(rule, shown, note), exempt_in)
        if allow and len(found) > listed:
            allowed = _allowed_spans(allow, seen, low)
            _drop_allowed(found, listed, allowed)
        if offer_mode == "strict" and any(f.rule == "chat_residue" and doc_type not in f.exempt_in
                                          for f in found[listed:]):
            offer_mode = "loose"  # the paragraph is already assistant chat ("Let me know if you'd like ...")
        if offer_mode and not is_title:
            for m in _OFFER_OPENER.finditer(seen, 0, header_at):
                if _starts_sentence(masked, m.start()) \
                        and _draft_offer(_sentence_around(seen, m.start(), m.end()), offer_mode):
                    quotes = quotes or _Quotes(plain)
                    if not quotes.inside(m.start(), m.end()):
                        add("chat_residue", m.start(), m.end(),
                            _list_message("chat_residue", plain[m.start():m.end()], _AFTER_DRAFT_NOTE))
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
            prev = doc.blocks[bi - 1] if bi else None
            name_line = block.kind == "para" and prev is not None and prev.kind == "heading" \
                and prev.lines[0].masked.strip(" *_").upper() == "NAME"
            _expression_rules(flat, masked, plain, bold_view, block, add, name_line)
            _preambles(doc, block, flat, masked, plain, bi == first_prose, after_greeting, add)
            if allow and len(found) > listed:
                _drop_allowed(found, listed, _allowed_spans(allow, seen, low) if allowed is None else allowed)

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
                size = word_count(sent)
                if (size <= 6 and _SELF_Q.match(sent)) or (size <= 9 and _SELF_Q_LONG.match(sent)) or \
                        (size <= 10 and _ANSWER_OPENER.match(nxt)):
                    add("self_answered_question", s, e,
                        f'Self-answered question "{_show(plain[s:e]).strip("*_")}". Fold it into a statement unless '
                        "the document type keeps it.")
            if block.kind in ("para", "callout"):
                _fragment_runs(doc, view, plain, spans, locate, bi, found)

    _block_rules(doc, found)
    # Notes to the requester before or after the slides ("Here's a revised version of your deck:", "I kept it short —
    # slide 3 has placeholder numbers.") are kept as they are in slides, so no finding in them is reported there.
    notes = _slide_notes(doc)
    if notes:
        for f in found:
            if f.block in notes:
                f.exempt_in = f.exempt_in + ("slides",)

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


def _expression_rules(flat: str, masked: str, plain: str, letters: str, block: tx.Block, add: _Add,
                      name_line: bool = False) -> None:
    """Pattern rules on one block (not the title): hedges, dashes, negative contrast, personification, counts and
    the looser "in today's ..." opener.

    flat is masked with emphasis underscores and line breaks as spaces, letters is plain with code, URLs and tags
    as letters; all have the offsets of plain. name_line is True for the paragraph under a man page's NAME heading.
    """
    for m in _HEDGE_STACK.finditer(flat):
        if _MODAL_ADVERB.match(m.group(0)) and _rhetorical_hedge(flat, m.start()):
            continue  # "What could possibly go wrong?"
        add("hedge_stack", m.start(), m.end(),
            f'Stacked hedge "{_show(plain[m.start():m.end()])}". Use one hedge of the same strength; do not '
            "remove the hedge.")
    # letters, not masked, so that a dash after inline code is found like any other.
    newlines = [m.start() for m in re.finditer("\n", masked)]
    lines: dict[int, _DashLine] = {}  # by the offset where the line starts
    for m in _DASHES.finditer(letters):
        around = masked[max(0, m.start() - 2): m.end() + 2]
        if _RANGE_DASH.search(around):
            continue
        if block.kind == "table" and _empty_cell(masked, m.start(), m.end()):
            continue
        # Report the dash itself, not the space or line break before it.
        ds = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
        de = ds + (2 if letters.startswith("--", ds) else 1)
        line = _line_start(newlines, ds)
        info = lines.get(line)
        if info is None:
            info = lines[line] = _dash_line(masked, plain, line, block.kind)
        if info.reply_subject:
            continue  # "Subject: Re: Partnership opportunity — Brightwave x Tallyhop": a reply keeps its subject
        label_end = ds if info.scene else info.label_end  # a scene heading is a label that ends at each dash
        if _after_timestamp(masked, ds) or _FIELD_AFTER.match(masked, m.end()) or _attribution(masked, ds) \
                or _range_dash(masked, ds, de) \
                or (info.term_end >= 0 and ds in (info.term_end, info.placeholders_end)) \
                or _caps_label_dash(line, ds, de, label_end, info.last_stop) \
                or _label_dash(masked, line, ds, de, info.last_stop) \
                or _dash_bullet(masked, ds, de) or _trailing_tag(masked, block.kind, line, info.end, ds, de) \
                or (name_line and line == 0 and _NAME_LINE.fullmatch(masked, 0, ds)) \
                or (block.kind == "para" and line == 0 and _dateline(masked, ds, de)):
            continue  # timelines, "— Owner: ..." fields, "— Jeff Atwood", "Monday – Friday", "`-v` — verbose",
            # "Decisions:" then "– Budget approved", "— Fri 8 Mar", "logsift — filter log files" under NAME,
            # "HARBOR CITY — Andrés ..."
        add("em_dash", ds, de,
            f'Dash in "{_context(plain, ds, de)}" used to splice or insert a clause. Use a comma, colon, parentheses '
            "or a period that keeps the same scope (keep ranges, quotations, code, and fiction narration and dialogue).")
    contrasts: list[tuple[int, int]] = []
    for k, pattern in enumerate(_NEG_CONTRAST):
        for m in pattern.finditer(flat):
            if k == _NOT_A_BUT and not _but_noun_phrase(flat, m):
                continue
            if k == _NOT_X_IT_IS:
                name = m.group("name") or ""
                if not _same_subject(m.group("s1") or name, m.group("s2")) \
                        or (len(name.split()) > 1 and not _starts_sentence(masked, m.start())):
                    continue  # "He wasn't the one who called; she was."
                if not m.group("just") and _be_contrast_skipped(flat, m.group("s1") or name, m.group("denied"),
                                                                m.group("s2"), m.group("be2").strip(), m.end()):
                    continue  # "She's not in the office this week; she's at the conference."
            if k == _NOT_JUST_BUT or not _after_subordinator(flat, m.start()):
                contrasts.append(m.span())
    for m in _REMINDER_CONTRAST.finditer(flat):
        if _starts_sentence(masked, m.start()) and _same_subject(m.group("s1"), m.group("s2")) \
                and (m.group("just") or not _be_contrast_skipped(flat, m.group("s1"), m.group("denied"), m.group("s2"),
                                                                 m.group("be2").strip(), m.end())):
            contrasts.append(m.span())
    if block.kind == "heading":
        contrasts.extend(m.span() for m in _HEADING_CONTRAST.finditer(flat) if _but_noun_phrase(flat, m))
    for start, end in contrasts:
        shown = _show(plain[start:end])
        add("negative_contrast", start, end,
            f'Negative contrast "{tx.display_width_cut(shown, 70)}". Remove the denied part only if '
            'the claim stays the same ("not just X" affirms X; keep X); keep it when it corrects a likely misreading.')
    for start, end in _two_sentence_contrast(flat, masked):
        shown = _show(plain[start:end])
        add("negative_contrast", start, end,
            f'Two-sentence negative contrast "{tx.display_width_cut(shown, 70)}". Join it into one sentence that '
            'keeps the negation (SKILL.md "Two-sentence negative contrast"), unless the second sentence adds a '
            "separate claim.")
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


def _mail_follows(doc: tx.Document, block: tx.Block, masked: str, end: int, strict: bool = False) -> bool:
    """True if a drafted mail or message follows the clause that ends at end in the block's masked text: a greeting
    or "Subject:" on the next line of the block, or, when nothing else follows in the block, a greeting, "Subject:",
    block quote or code fence as the next line of the document that is not blank or a thematic break ("---", which
    assistants put between the preamble and the draft). With strict, only a greeting or "Subject:" (also as the
    first line of a block quote) counts."""
    if _NONSPACE.search(masked, end):
        line_end = masked.find("\n", end)
        if line_end < 0 or masked[end:line_end].strip():
            return False
        nxt = masked[line_end + 1:_line_at(masked, line_end + 1)[1]]
        return bool(_GREETING.match(nxt) or _SUBJECT.match(nxt))
    index = block.lines[-1].no  # the 0-based index of the line after the block
    while index < len(doc.lines) and doc.lines[index].kind in ("blank", "rule"):
        index += 1
    if index >= len(doc.lines):
        return False
    line = doc.lines[index]
    if line.kind in ("quote", "fence", "code") and not strict:
        return True
    return line.kind in ("para", "list", "quote") and bool(_GREETING.match(line.content)
                                                           or _SUBJECT.match(line.content))


def _sent_mail(text: str, pos: int, lead_end: int) -> bool:
    """True if the noun that ends at pos names a mail someone wrote or sent (_SENT_AFTER), unless the clause up to
    lead_end speaks to the requester ("Here's an email I wrote for you:")."""
    if not _SENT_AFTER.match(text, pos):
        return False
    end = lead_end if lead_end > pos else min(len(text), pos + 80)
    return not re.search(r"\bfor\s+you\b", text[pos:end], re.IGNORECASE)


def _preambles(doc: tx.Document, block: tx.Block, flat: str, masked: str, plain: str, first: bool,
               after_greeting: int, add: _Add) -> None:
    """An assistant's preamble before a drafted or revised text (see _PREAMBLE), at the start of a sentence and not
    after a greeting line ("Hi Ana," then "Here's a draft reply you can send to the customer:" is the writer's mail).

    The lead-in ends with a colon, ends the block, or (in the first prose block) goes on with more sentences up to a
    colon that ends the block ("Sure — here's a draft you can send. It's polite but firm:"). After an interjection:
    reported when the clause ends with a colon, in the first prose block, or when a greeting or "Subject:" follows the
    paragraph ("Sure! Here's a draft email. I kept it polite but firm." then "Dear Mr. Lee,"); when no greeting or
    "Subject:" follows, a noun that is not a text ("Sure, here's the updated schedule:", "Sure, here are the
    options:") is not reported, and the rest is exempt in mail, where it may be the writer's own reply, unless it
    offers a drafted mail with a verb ("a resignation letter you can adapt", or "a version you can use" before a
    quotation or code block). Without one, only in
    the first prose block: a revision lead-in when the clause ends with a colon (in mail only when a drafted mail follows; with a noun
    that is not a text, only when a greeting or "Subject:" follows), "Here's a draft:" like a revision lead-in, an
    offer of a drafted mail when a drafted mail or message follows, and a mail noun without a verb offered as a draft
    (_DRAFT_SIGN) when a greeting or "Subject:" follows. Without a verb, a mail someone wrote or sent ("Here's a quick
    note from our CEO:", "Here is the letter my grandfather wrote in 1944:") is never reported. A lead-in that starts
    with "Below is" or "Below are", and "I've revised your email ...:" (_REVISED_YOUR), are reported without an
    interjection only when a greeting or "Subject:" follows the colon. after_greeting is the offset after a greeting
    line in this or an earlier block, or -1.
    """
    block_end = len(masked.rstrip())
    block_colon = first and masked[:block_end].endswith(":")

    def lead_in(m: re.Match[str]) -> tuple[int, bool]:
        """(start, interjection) of a preamble match, or (-1, False) if it does not start a sentence or follows a
        greeting. An interjection that does not start the sentence is left out: "I'm not sure. Here's a reply ..."."""
        start = m.start()
        interjection = bool(m.group("interjection")) and _starts_sentence(masked, start)
        if m.group("interjection") and not interjection:
            start = m.end("interjection")
        if 0 <= after_greeting <= start or not _starts_sentence(masked, start):
            return -1, False
        return start, interjection

    def report(start: int, end: int, exempt_in: tuple[str, ...] = ()) -> None:
        scope = "" if exempt_in else " (reported in every doc type)"
        add("chat_residue", start, end,
            f'Assistant chat "{_show(plain[start:end])}" left in the text: delete the preamble; it '
            f"speaks to the requester, not the reader{scope}.", exempt_in)

    for m in _REVISED_YOUR.finditer(flat):
        start, interjection = lead_in(m)
        colon = _PREAMBLE_COLON.match(flat, m.end())
        if start < 0 or not colon:
            continue
        follows = _mail_follows(doc, block, masked, colon.end(), strict=True)
        if interjection or (first and follows):
            report(start, m.end(), () if follows else ("mail",))  # in a mail, "Sure, I've edited your note:" is a reply
    for m in _PREAMBLE.finditer(flat):
        start, interjection = lead_in(m)
        if start < 0:
            continue
        colon = _PREAMBLE_COLON.match(flat, m.end())
        ends = _PREAMBLE_END.match(flat, m.end())
        lead_end = colon.end() if colon else ends.end() if ends else block_end if block_colon else -1
        verb = (m.group("verb") or "").lower()
        draft = (m.group("draft") or "").lower()
        generic = (m.group("generic") or "").lower()
        if not verb and _sent_mail(flat, m.end(), lead_end):
            continue  # "Here is the letter my grandfather wrote in 1944:", "Here's a quick note from our CEO:"
        exempt_in: tuple[str, ...] = ()
        if interjection:
            follows = bool(colon and _mail_follows(doc, block, masked, colon.end(), strict=True)) \
                or _mail_follows(doc, block, masked, block_end, strict=True)
            if not (colon or (first and lead_end >= 0) or follows):
                continue  # reported before a greeting: "Sure! Here's a draft email. I kept it polite." then "Dear ..."
            if not follows:
                # An offer of the text to the requester: "a resignation letter you can adapt", "a version you can use".
                offer = bool(verb) and generic not in ("option", "options")
                if not offer and (m.group("other") or generic in ("option", "options", "message", "messages")):
                    continue  # a reply: "Sure, here's the updated schedule:", "Sure, here are the options:"
                if not (offer and (draft or _mail_follows(doc, block, masked,
                                                          lead_end if lead_end >= 0 else block_end))):
                    exempt_in = ("mail",)  # "Sure! Here's a revised version:" may be the writer's own reply in a mail
        elif not first:
            continue
        elif m.group("below") and not (colon and _mail_follows(doc, block, masked, colon.end(), strict=True)):
            continue  # "Below is an updated summary of the API:"
        elif m.group("revised"):
            if not colon:
                continue
            if m.group("other"):
                if not _mail_follows(doc, block, masked, colon.end(), strict=True):
                    continue  # "Here are the updated numbers:" then a table
            elif not _mail_follows(doc, block, masked, colon.end()):
                exempt_in = ("mail",)  # "Here is the revised version of the agenda:" then a list, in a mail
        elif draft in ("draft", "drafts", "rewrite", "rewrites") and not m.group("pre") and colon \
                and colon.end() == m.end("draft") + 1:
            if not _mail_follows(doc, block, masked, colon.end()):
                exempt_in = ("mail",)  # "Here's a draft:" then the plan, reported like a revision lead-in
        elif verb and (draft or verb in ("send", "forward")):
            if lead_end < 0 or not _mail_follows(doc, block, masked, lead_end):
                continue
        elif draft or generic in ("version", "versions", "text", "message", "messages"):
            pre = m.group("pre") or ""
            offered = m.group("det").lower() in ("a", "an", "your") or draft in ("draft", "drafts") \
                or bool(_DRAFT_SIGN.search(pre))
            if lead_end < 0 or not offered or _EXAMPLE_WORD.search(pre) \
                    or not _mail_follows(doc, block, masked, lead_end, strict=True):
                continue  # "Here's a sample reply:" in a support guide, "Here's the email that went out:"
        else:
            continue
        report(start, m.end(), exempt_in)


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
    # The speaker of each block that is a turn of a dialogue or an interview (a run of speaker-name labels in which a
    # name repeats), and of each block in a run of speaker-name labels without a repeat (character names in script),
    # for sentence_start_repeat.
    turns: dict[int, str] = {}
    cast: dict[int, str] = {}

    def flush_group() -> None:
        if len(group) < 2:
            return
        labels = [_BOLD_LABEL.match(blocks[bi].lines[0].masked) for bi in group]
        names = [label.group(1).strip() if label else "" for label in labels]
        speakers = all(_SPEAKER.fullmatch(name) for name in names)
        if speakers and len({name.lower() for name in names}) < len(names):
            turns.update((bi, name.lower()) for bi, name in zip(group, names))
            return  # turns of a dialogue or an interview: "**G:** ...", "**O:** ...", "**G:** ..."
        if speakers:
            cast.update((bi, name.lower()) for bi, name in zip(group, names))
        what = "Item" if blocks[group[0]].kind == "list" else "Paragraph"
        for bi, label in zip(group, labels):
            line = blocks[bi].lines[0]
            match = line.content[label.start():label.end()] if label else ""
            found.append(_make(doc, "bold_label_list", line.no, line.offset + 1,
                               f"{what} starts with a bold label and colon ({len(group)} in a row). Keep labels "
                               "for values; fold labels that only summarize into the sentence; remove the bold.",
                               match, 0, 0, bi, ("script",) if speakers else ()))  # character names in a script
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
        # A bold label that starts a line is a field name, not emphasis: "**Status:** Final" then "**Author:** Sam".
        # Lines are stripped and a bold span does not cross a line, so the label's span starts where the label does.
        labels = {m.start() for m in _LINE_BOLD_LABEL.finditer(masked)}
        spans = [m for m in _BOLD_SPAN.finditer(masked) if m.start() not in labels]
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
    fields = {b.lines[0].no for b in blocks if b.kind == "para" and len(b.lines) >= 2
              and all(_FIELD_LINE.match(ln.masked) for ln in b.lines)}
    for line in reversed(doc.lines):
        if line.kind == "blank":
            continue
        next_kind[line.no] = following
        if line.kind == "para" and _FIGURE_LINE.match(line.raw.strip()):
            following = "figure"  # an image or display math is what the colon introduces
        elif line.kind == "para" and (_LETTERED_ITEM.match(line.content) or line.no in fields):
            following = "list"  # "In this policy:" then "(a) ..." and "(b) ...", "Details:" then "Date: ..."
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
        if text.endswith(":") and not text.endswith("::") \
                and not any(m.end() >= len(text) for m in _MESSAGE_HEADER.finditer(plain)):  # "On ... wrote:"
            no, col = _Locator(block, starts)(len(text) - 1)
            found.append(_make(doc, "decorative_colon", no, col,
                               "Paragraph ends with a colon but no list, table, code or quotation follows. Remove the "
                               "colon or finish the sentence.", ":", 0, 0, bi))

    # sentence starts. A run ends where the speaker of a dialogue changes ("**Interviewer:** So ..." then "**Dana:**
    # So ..."); a run that goes on across speaker-name labels without a repeat is exempt in script.
    current: list[tx.Sentence] = []
    prev_word = ""
    prev_speaker: Optional[str] = None
    prev_character: Optional[str] = None
    crossed = False  # the run goes on across two character names

    def flush_starts() -> None:
        if len(current) >= 3:
            first = current[0]
            block = blocks[first.block_index]
            no, col = _Locator(block, block.joined(True)[1])(first.start)
            found.append(_make(doc, "sentence_start_repeat", no, col,
                               f'{len(current)} sentences in a row start with "{prev_word}". Vary only where it '
                               "reads as a pattern; keep parallel steps and lists.", prev_word, 0, 0, first.block_index,
                               ("script",) if crossed else ()))
    for sent in doc.sentences:
        speaker = turns.get(sent.block_index)
        if sent.kind != "para" or speaker != prev_speaker:
            flush_starts()
            current, prev_word, crossed = [], "", False
        character = cast.get(sent.block_index)
        cross = character != prev_character and bool(current)
        prev_speaker, prev_character = speaker, character
        if sent.kind != "para":
            continue
        # A bold label is not the sentence's first word: "**Speaker 1:** So ..." then "**Speaker 2:** In ...".
        label = _BOLD_LABEL.match(sent.masked)
        m = _WORD.match(sent.masked[label.end() if label else 0:].lstrip("\"'“‘(*_"))  # none if code starts it
        w = m.group(0) if m else ""
        if w[:1].isdigit():
            w = ""  # numbered clauses ("3.1 ...", "3.2 ...") and figures are not a repeated word
        if w and w.lower() not in _STOP_STARTS and w.lower() == prev_word.lower():
            current.append(sent)
            crossed = crossed or cross
        else:
            flush_starts()
            current = [sent] if w and w.lower() not in _STOP_STARTS else []
            crossed = False
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
