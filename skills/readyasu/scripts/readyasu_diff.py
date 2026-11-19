#!/usr/bin/env python3
"""readyasu diff: compare an original and a revised English text.

Shows every change and lists changes that may alter meaning (numbers, negation,
certainty, permission, obligation, scope, hearsay, questions, requests, names)
as places to review. It does not decide whether the meaning is the same.
Standard library only; Python 3.9+.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import difflib
import functools
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, NoReturn, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import readyasu_text as tx  # noqa: E402

__version__ = tx.__version__
TOOL = "readyasu-diff"
JSON_FORMAT = 1
FACT_TYPES = ("pr", "article", "incident", "proposal", "manual", "formal", "paper")
STIFF_REFERENCE_TYPES = ("incident", "formal", "paper")
ENERGY_REFERENCE_TYPES = ("pr", "article", "incident", "manual", "formal", "paper")

HELP_EPILOG = """Meaning risks counted by --fail-on meaning-risk:
  number            a number, its unit (30 seconds -> 30 ms), a month or a weekday was removed, added or changed
  negation          the number of negations changed
  certainty         a hedge (may, likely, planned) was removed or replaced by a stronger one
  booster           always, guaranteed, definitely ... added (counted only for pr, article, incident,
                    proposal, manual, formal, paper)
  permission        a permission phrase (you may, allowed to, optional) appeared or disappeared
  obligation        obligation strength changed (should <-> must, or one appeared or disappeared)
  status            a status word (TBD, pending, under investigation, not yet) disappeared
  hearsay           a hearsay marker (reportedly, according to) appeared or disappeared
  question          a question became a statement or the reverse
  request           a request marker (please, could you) disappeared
  approximation     an approximation word (about, up to, at least) on the same number changed
  scope             a limiting word (only) disappeared, or choice or quantifier scope changed
                    (either/or <-> both/all, some -> all)
  condition         a condition or time limit (if, unless, until, at launch, for now) disappeared
  correlation       a cause word was added to a sentence that stated a correlation
  commitment        a commitment (we will, we guarantee) was added
  citation          a citation ([1], (Smith, 2020)) changed
  name_order        the same names appear in a different order, or a name moved to another sentence
  name              a name left a sentence and the whole text, or was replaced by another name
  material_number   (compose mode) a number in the final draft is not in the material
Reported but not counted: changes to inline code, code blocks, URLs and e-mail addresses; a denied word moved to the
affirmative side; certainty weakened; causal links added; added feelings and actors.

Exit codes:
  0  finished (with or without findings), and --fail-on did not match
  1  --fail-on meaning-risk matched
  2  usage or input error"""


# ---------------------------------------------------------------- patterns


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


NUMBER = re.compile(r"(?<![\w.$€£¥#])(?P<prefix>(?:[A-Z]{1,2})?[$€£¥]|#|[QqVv](?=\d))?(?P<num>\d+(?:,\d{3})*(?:[.:]\d+)*)"
                    r"(?P<suffix>%|[kKmMbB](?![A-Za-z])|(?:st|nd|rd|th)\b)?")
NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000", "million": "1000000", "billion": "1000000000", "dozen": "12",
    "half": "0.5", "twice": "2x", "thrice": "3x",
}
NUMBER_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)
NEGATION = _rx(r"\b(?:not|no|never|none|nothing|nobody|nowhere|neither|nor|without|cannot|unless)\b|n['’]t\b")
CERTAINTY = (
    (1, _rx(r"\b(?:may|might|could|would|possibly|perhaps|maybe|potentially|sometimes|occasionally|conceivably)\b"
            r"|\bin\s+some\s+cases\b|\btends?\s+to\b|\bit(?:\s+is|['’]s)\s+possible\b|\bthere(?:\s+is|['’]s)\s+a\s+chance\b"
            r"|\bhopefully\b|\b(?:unclear|unknown|not\s+clear)\s+(?:whether|if)\b")),
    (2, _rx(r"\b(?:likely|probably|apparently|presumably|seemingly|reportedly)\b|\b(?:appears?|appeared)\s+(?:to|that|like)\b"
            r"|\b(?:seems?|seemed)\b|\b(?:is|are|was|were)\s+believed\s+to\b|\blooks?\s+like\b|\bas\s+far\s+as\s+(?:we|I)\s+know\b"
            r"|\b(?:we|I)\s+assume\b"
            r"|\b(?:is|are)\s+expected\s+to\b|\bsuggests?\b|\bwe\s+(?:believe|think|suspect|estimate)\b"
            r"|\bi\s+(?:believe|think|suspect|guess|expect)\b|\bwe\s+expect\b|\bestimated\b")),
    (3, _rx(r"\bplan(?:s|ned)?\s+to\b|\bplanned\b|\bscheduled\b|\bintend(?:s|ed)?\s+to\b|\baim(?:s|ed)?\s+to\b"
            r"|\bgoing\s+to\b|\btarget(?:s|ed)?\s+(?:to|for)\b|\bby\s+the\s+target\s+date\b")),
)
BOOSTER = _rx(r"\b(?:always|certainly|definitely|guaranteed?|surely|undoubtedly|invariably|reliably)\b"
              r"|\bwithout\s+(?:fail|exception|a\s+doubt)\b|\bensures?\b|\b100\s?%")
PERMISSION = _rx(r"\b(?:you|users?|they|we|customers?|members?)\s+may\b|\b(?:allowed|permitted)\s+to\b"
                 r"|\b(?:is|are)\s+permitted\b|\bfeel\s+free\s+to\b|\b(?:it['’]s|it\s+is)\s+(?:fine|okay|ok|acceptable)\s+to\b"
                 r"|\boptional(?:ly)?\b|\bmay\s+be\s+(?:omitted|skipped|left|used|included|ignored|removed)\b"
                 r"|\bno\s+need\s+to\b|\b(?:don['’]t|do\s+not|doesn['’]t|does\s+not)\s+(?:have|need)\s+to\b"
                 r"|\b(?:is|are)\s+not\s+required\b|\bnot\s+mandatory\b")
OBLIGATION_STRONG = _rx(r"\b(?:must|shall|mandatory|required|requires?)\b|\b(?:have|has|had)\s+to\b|\bneeds?\s+to\b"
                        r"|(?<!\bno\s)\bneeds?\s+(?!to\b|for\b)(?=[\w$€£])"
                        r"|\bis\s+obligated\b")
OBLIGATION_SOFT = _rx(r"\b(?:should|ought\s+to|recommended|advisable|encouraged)\b|\bwe\s+recommend\b|\bbest\s+to\b")
ABILITY = _rx(r"\bcan\b|\bable\s+to\b|\bcapable\s+of\b")
STATUS = _rx(r"\b(?:tbd|tbc|pending|unconfirmed|undecided|tentative(?:ly)?|on\s+hold|in\s+progress|ongoing|underway)\b"
             r"|\bunder\s+way\b|\b(?:is|are|was|still)\s+(?:a\s+|still\s+a\s+)?drafts?\b|\(draft\)|\bin\s+draft\b"
             r"|\bto\s+be\s+(?:determined|decided|confirmed|announced)\b|\bunder\s+(?:investigation|review|discussion)\b"
             r"|\bnot\s+yet\b|\b(?:still\s+)?investigating\b|\bbeing\s+investigated\b"
             r"|\bnot\s+(?:been\s+)?(?:decided|confirmed|finalized|verified)\b|\bhaven['’]t\s+(?:decided|confirmed|verified)\b")
HEARSAY = _rx(r"\b(?:reportedly|allegedly|rumou?red)\b|\baccording\s+to\b|\b(?:is|are|was|were)\s+said\s+to\b"
              r"|\b(?:reported|claims?|claimed|indicated|noted|mentioned|stated|confirmed|announced)\s+that\b|\b(?:i|we)\s+heard\b"
              r"|\b(?:says|said|told\s+(?:us|me|them|him|her|the\s+team))\b"
              r"|\b(?:people|colleagues|users|customers|experts|critics|others|they)\s+(?:say|report)\b"
              r"|\b(?:claims?|claimed|noted|mentioned|stated)\s+(?=(?:the|a|an|it|we|they|this|that|our|its|there)\b)"
              r"|\btells?\s+us\b"
              r"|\b(?:we['’]re|i['’]m|we\s+are|i\s+am)\s+told\b")
REQUEST = _rx(r"\bplease\b|\b(?:could|would|can|will)\s+you\b|\bkindly\b|\bwe\s+ask\s+(?:that|you)\b"
              r"|\bi(?:['’]d|\s+would)\s+like\s+you\s+to\b|\bi\s+need\s+you\s+to\b")
APPROX_BEFORE = _rx(r"(?:not\s+more\s+than|not\s+less\s+than|no\s+fewer\s+than|a\s+maximum\s+of|a\s+minimum\s+of|"
                    r"maximum\s+of|minimum\s+of|about|approximately|approx\.?|around|roughly|nearly|almost|~|up\s+to|at\s+least|at\s+most|"
                    r"more\s+than|less\s+than|fewer\s+than|over|under|some|circa|close\s+to|just\s+over|just\s+under|"
                    r"upwards\s+of|no\s+more\s+than|no\s+less\s+than|below|above|within)\s*$")
APPROX_AFTER = _rx(r"^(?:\s*(?:\+|-ish|ish\b)|\s*(?:[a-z]+\s+)?(?:or\s+so|or\s+more|or\s+less|or\s+fewer|or\s+above|"
                   r"or\s+below)\b)")
CHOICE = _rx(r"\b(?:either|or|one\s+of|any\s+one\s+of|whichever)\b")
ALL_SCOPE = _rx(r"\b(?:both|all|every|each)\b")
LIMITER = _rx(r"(?<!\bnot\s)(?<!n['’]t\s)(?:\b(?:only|solely|exclusively|merely)\b"
              r"|\bjust\s+(?=(?:a|an|the|for|when|if|in|on|one|two|\d)))")
PARTIAL_DET = _rx(r"\b(?:some|several|many|few)\b|\bpart\s+of\b"
                  r"|(?<!\bthe\s)(?<!\bat\s)\bmost\s+(?!of\s+all\b)(?=of\b|people\b|data\b|code\b|work\b|software\b|[a-z]+s\b)(?![a-z]+ly\b)"
                  r"|(?<!\bbe\s)(?<!\bam\s)(?<!['’]m\s)(?<!\bis\s)(?<!\bare\s)(?<!\bwas\s)(?<!\bfeel\s)(?<!\bnot\s)"
                  r"\bcertain\s+(?!that\b|of\b|about\b)(?=[a-z])")
MOST_ANY = _rx(r"(?<!\bthe\s)(?<!\bat\s)\bmost\s+(?![a-z]+ly\b|of\s+all\b|important\b|notabl)(?=[a-z])")
PARTIAL_ADV = _rx(r"\b(?:often|usually|mostly|partly|partially)\b|\bin\s+some\s+cases\b")
STILL_PARTIAL = _rx(r"\b(?:some|several|many|most|few|certain|often|usually|mostly|partly|partially|typically|generally|"
                    r"normally|commonly|frequently|numerous|majority|specific|rarely|seldom|various|occasionally|"
                    r"sometimes|particular|select(?:ed)?|portion|minority|handful|lots?)\b|\bin\s+(?:some|many|most)\s+cases\b"
                    r"|\ba\s+number\s+of\b|\ba\s+few\b|\bpart\s+of\b")
PARTIAL = _rx(r"\b(?:some|several|many|most|few|part\s+of|certain|often|usually|mostly|partly|partially)\b|\bin\s+some\s+cases\b")
TOTAL = _rx(r"\b(?:all|every|always|entire|entirely|whole|never|none|completely|fully)\b")
CORRELATION = _rx(r"\b(?:correlat\w*|coincid\w*)\b|\bassociated\s+with\b|\blinked\s+to\b|\b(?:at|around)\s+the\s+same\s+time\b"
                  r"|\brelated\s+to\b|\balongside\b")
CAUSAL = _rx(r"\b(?:caus\w*|because|therefore|consequently|thus|hence|drives?|drove|triggers?|triggered)\b"
             r"|\blead(?:s)?\s+to\b|\bled\s+to\b|\bresult(?:s|ed)?\s+in\b|\bdue\s+to\b|\bso\s+that\b|\bas\s+a\s+result\b"
             r"|\bthanks\s+to\b|\b(?:meant|means)\s+that\b")
COMMITMENT = _rx(r"\bwe(?:['’]ll|\s+will|\s+shall)\b|\bwe\s+(?:guarantee|promise|commit|pledge)\b|\bwe\s+ensure\b"
                 r"|\bwill\s+never\s+(?:happen|occur)\s+again\b|\bguaranteed?\b|\bwe(?:['’]re|\s+are)\s+committed\s+to\b"
                 r"|\bat\s+no\s+(?:extra|additional)\s+cost\b|\bno\s+(?:extra|additional)\s+(?:cost|charge)s?\b"
                 r"|\b(?:won['’]t|will\s+not)\s+happen\s+again\b")
CITATION = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]|\((?:[A-Z][A-Za-z'-]+(?:\s+(?:[A-Z][A-Za-z'-]+|of|for|and|&)){0,4}"
                      r"(?:\s+et\s+al\.)?(?:,?\s+(?:and|&)\s+[A-Z][A-Za-z'-]+)?),?\s+\d{4}[a-z]?(?:,\s*p+\.\s*\d+)?\)")
QUOTED = re.compile(r"\"([^\"\n]{1,200})\"|“([^”\n]{1,200})”")
CONTRACTION = re.compile(r"\b\w+['’](?:t|re|ve|ll|d|m)\b|\b(?:it|that|there|what|here|let|he|she|who|where|how)['’]s\b",
                         re.IGNORECASE)
CONNECTIVE = _rx(r"^(?:however|therefore|thus|also|additionally|moreover|furthermore|as\s+a\s+result|consequently|"
                 r"in\s+addition|meanwhile|instead|still|so|this|that|these|those|it|such)\b")
FIGURE_STARTS = _rx(r"^(?:let['’]s)\b")
FUTURE = _rx(r"\bwill\b|\bgoing\s+to\b")
LETS = _rx(r"\blet['’]s\b")
CLOSING_RESOLUTION = _rx(r"\bwe(?:['’]ll|\s+will)\s+continue\b|\bwe(?:['’]re|\s+are)\s+committed\b|\bgoing\s+forward\b")
VAGUE_QUANTITY = _rx(r"\b(?:some|several|a\s+few|many|various|a\s+number\s+of|certain)\b")
CONTRAST_DENIED = _rx(r"\bnot\s+(?:just\s+|only\s+|merely\s+|simply\s+)?(?:an?\s+|the\s+|about\s+)?([a-z][\w-]{2,})"
                      r"|\b(?:instead\s+of|rather\s+than)\s+(?:an?\s+|the\s+)?([a-z][\w-]{2,})")
CONDITION = _rx(r"\b(?:if|unless|until|till|whenever|when|while|after|before|as\s+soon\s+as|provided(?:\s+that)?"
                r"|as\s+long\s+as|in\s+case|except\s+(?:when|if)|at\s+launch|at\s+first|initially|for\s+now"
                r"|for\s+the\s+time\s+being|temporarily)\b"
                r"|(?<!\bat\s)\bonce\b(?!\s+(?:a|an|per|every|more|again|or|and)\b)")
NOT_CONDITION = _rx(r"\b(?:check|see|ask(?:s|ed)?|know|wonder(?:ing)?|determine|verify|tell|find\s+out|sure|unsure|decide|"
                    r"confirm)\s+if\b|\bas\s+if\b|\bwhen\s+(?=(?:is|are|was|were|do|does|did|will|would|can|could|should)\s+"
                    r"(?:the|it|we|you|they|this|that|our|your)\b)")
NOT_PERMISSION = _rx(r"\bfeel\s+free\s+to\s+(?:reach\s+out|contact|ask|get\s+in\s+touch|let\s+(?:me|us)\s+know|ping|email|"
                     r"message|drop)\b")
# Stock phrases whose words would otherwise count as obligation, hearsay or condition markers.
STOCK_MARKERS = _rx(r"\bit\s+should\s+be\s+noted\s+that\b|\bit\s+(?:is|['’]s)\s+worth\s+noting\s+that\b|\bwhen\s+it\s+comes\s+to\b"
                    r"|\b(?:that\s+said|having\s+said\s+that|that\s+being\s+said|easier\s+said\s+than\s+done|needless\s+to\s+say)\b"
                    r"|\bafter\s+all\b|\bbefore\s+we\s+(?:begin|dive\s+in|start)\b")
# Negated obligations are not obligations ("you don't have to", "not required").
NEG_OBLIGATION = _rx(r"\b(?:don['’]t|doesn['’]t|didn['’]t|do\s+not|does\s+not|did\s+not|not|no|never)\s+(?:have\s+to|has\s+to|"
                     r"need\s+to|needs?|required|requires?)\b")
# Wording that is not a hedge: requests and "would like".
NOT_HEDGE = _rx(r"\b(?:could|would|can|will)\s+you\b|\bwould\s+(?:like|love|appreciate|prefer|be\s+grateful|be\s+happy|mind)\b"
                r"|\bcould\s+not\b")
MAY_MODAL_NEXT = re.compile(r"\s+(?:I|we|you|they|he|she|it|the|this|these|those|our|your|their|all|everyone)\b")
DATE_FULL = {"January": "January", "February": "February", "March": "March", "April": "April", "June": "June",
             "July": "July", "August": "August", "September": "September", "October": "October",
             "November": "November", "December": "December", "Monday": "Monday", "Tuesday": "Tuesday",
             "Wednesday": "Wednesday", "Thursday": "Thursday", "Friday": "Friday", "Saturday": "Saturday",
             "Sunday": "Sunday"}
DATE_ABBR = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "Jun": "June", "Jul": "July",
             "Aug": "August", "Sep": "September", "Sept": "September", "Oct": "October", "Nov": "November",
             "Dec": "December", "Mon": "Monday", "Tue": "Tuesday", "Tues": "Tuesday", "Wed": "Wednesday",
             "Thu": "Thursday", "Thur": "Thursday", "Thurs": "Thursday", "Fri": "Friday", "Sat": "Saturday",
             "Sun": "Sunday"}
DATE_WORD = re.compile(r"\b(" + "|".join(DATE_FULL) + r"|MONTHMAY)\b|\b(" + "|".join(sorted(DATE_ABBR, key=len, reverse=True))
                       + r")\b\.?(?=,?\s+(?:\d|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b)|\s*\|)")
UNIT_NAMES = {
    "ms": "ms", "msec": "ms", "millisecond": "ms", "milliseconds": "ms", "s": "s", "sec": "s", "secs": "s",
    "second": "s", "seconds": "s", "min": "min", "mins": "min", "minute": "min", "minutes": "min", "h": "h",
    "hr": "h", "hrs": "h", "hour": "h", "hours": "h", "day": "day", "days": "day", "week": "week", "weeks": "week",
    "wk": "week", "wks": "week", "month": "month", "months": "month", "year": "year", "years": "year", "yr": "year",
    "yrs": "year", "kb": "KB", "mb": "MB", "gb": "GB", "tb": "TB", "pb": "PB", "kib": "KiB", "mib": "MiB",
    "gib": "GiB", "tib": "TiB", "byte": "bytes", "bytes": "bytes", "px": "px", "em": "em", "rem": "rem", "pt": "pt",
    "km": "km", "kg": "kg", "lb": "lb", "lbs": "lb", "mph": "mph", "am": "a.m.", "a.m.": "a.m.", "pm": "p.m.",
    "p.m.": "p.m.", "usd": "USD", "eur": "EUR", "gbp": "GBP", "jpy": "JPY", "cad": "CAD", "aud": "AUD",
    "chf": "CHF", "cny": "CNY", "inr": "INR", "dollars": "$", "euros": "€",
    "utc": "UTC", "gmt": "GMT", "pst": "PST", "pdt": "PDT", "est": "EST", "edt": "EDT", "cst": "CST", "cdt": "CDT",
    "mst": "MST", "mdt": "MDT", "cet": "CET", "cest": "CEST", "bst": "BST", "ist": "IST", "jst": "JST", "aest": "AEST",
}
UNIT_AFTER = re.compile(r"\s?-?\s?(a\.m\.|p\.m\.|[A-Za-z]+)(?![\w-])")
CURRENCY_BEFORE = re.compile(r"\b(USD|EUR|GBP|JPY|CAD|AUD|CHF|CNY|INR)\s?$")
UNIT_CODES = {"KB", "MB", "GB", "TB", "PB", "KIB", "MIB", "GIB", "TIB", "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF",
              "CNY", "INR", "AM", "PM", "UTC", "GMT", "PST", "PDT", "EST", "EDT", "CET", "CEST", "JST", "IST"}
VERBISH = re.compile(r"\s+(?:[a-z]+(?:ed|s)|will|would|can|could|must|should|may|might|had|said|told|wrote|led|ran|took|"
                     r"made|did|sent|built|found|got|gave|went|knew|saw)\b")
CLOSING_HEADING = _rx(r"^[#*_\s]*(?:conclusions?|in\s+conclusion|final\s+thoughts|closing\s+thoughts|summary|in\s+summary|wrapping\s+up|"
                      r"wrap-up|key\s+takeaways|takeaways|tl;?dr|recap|in\s+closing)\b")
QUANTIFIER = _rx(r"(?<!\bthe\s)(?<!\bat\s)\b(?:a\s+few|a\s+couple\s+of|some|most|many|few|several|all|every|each)\b"
                 r"(?=\s+(?:of\s+)?[a-z])")
STATISTIC = _rx(r"\b(?:mean|median|average|avg|p\d{2}|percentile|peak)\b")
PRIORITY_WORDS = _rx(r"\b(?:focus\w*|priorit\w*|first|both|as\s+well\s+as|in\s+addition\s+to|along\s+with|and|plus|also)\b")

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers him
his how i if in into is it its itself just me more most my no nor not now of off on once only or other our ours out
over own same she should so some such than that the their theirs them then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your yours yourself
this that these those will shall may might must can could would should one two three into onto upon also very really
""".split())
NAME_STOP = set("""I The A An This That These Those It Its We Our You Your They Their He She His Her If When While
After Before Because Although However Therefore Thus Also In On At For From To By With Of And Or But So Then Here
There What Which Who Why How Please Note Yes No Not All Each Every Some Any Most Many More Monday Tuesday Wednesday
Thursday Friday Saturday Sunday January February March April May June July August September October November December
Let Lets OK Okay""".split())


# ---------------------------------------------------------------- data


@dataclass
class Risk:
    kind: str
    counted: bool
    message: str
    orig_line: int
    rev_line: int
    original: str
    revised: str


@dataclass
class Review:
    kind: str
    message: str
    line: int
    text: str


@dataclass
class Chunk:
    orig: list[tx.Sentence]
    rev: list[tx.Sentence]

    @property
    def orig_text(self) -> str:
        return " ".join(s.masked for s in self.orig)

    @property
    def rev_text(self) -> str:
        return " ".join(s.masked for s in self.rev)

    @property
    def orig_line(self) -> int:
        return self.orig[0].line if self.orig else 0

    @property
    def rev_line(self) -> int:
        return self.rev[0].line if self.rev else 0

    def show_orig(self) -> str:
        return " ".join(s.text for s in self.orig)

    def show_rev(self) -> str:
        return " ".join(s.text for s in self.rev)


@dataclass
class DiffResult:
    changes: list[dict[str, object]]
    risks: list[Risk]
    reviews: list[Review]
    stiffness: list[str]
    stiffness_reference: bool
    energy: list[str]
    energy_reference_items: list[str]
    fact_gaps: list[Review]
    fact_gaps_note: str
    material: dict[str, Any]
    full_diff: str
    doc_type: Optional[str]
    reader: Optional[str]
    stance: Optional[str]
    mode: str
    words: tx.Words = field(default_factory=tx.Words)
    fact_gaps_checked: bool = False

    @property
    def counted(self) -> int:
        return sum(1 for r in self.risks if r.counted)


# ---------------------------------------------------------------- extraction


def number_key(m: re.Match[str]) -> str:
    """Normalized number token: prefix (Q, v, currency) + digits without thousands separators + magnitude or %."""
    prefix = (m.group("prefix") or "").lower()
    suffix = (m.group("suffix") or "").lower()
    if suffix in ("st", "nd", "rd", "th"):
        suffix = ""
    num = m.group("num").replace(",", "")
    if prefix not in ("v", "q") and re.fullmatch(r"\d+\.\d*?0+", num):
        num = num.rstrip("0").rstrip(".")  # "1.0" is 1 and "0.50" is 0.5
    return prefix + num + suffix


_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_SMALL = {**_UNITS, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, **_TENS}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000}
_COMPOUND = re.compile(r"\b(?:(" + "|".join(_TENS) + r")[- ](" + "|".join(_UNITS) + r")|(" + "|".join(_SMALL)
                       + r")\s+(" + "|".join(_SCALES) + r"))\b", re.IGNORECASE)


def _compound_value(m: re.Match[str]) -> str:
    if m.group(1):
        return str(_TENS[m.group(1).lower()] + _UNITS[m.group(2).lower()])
    return str(_SMALL[m.group(3).lower()] * _SCALES[m.group(4).lower()])


def _number_text(text: str) -> str:
    """Spell-out forms that mean the same token: '10 percent' -> '10%', 'version 2' -> 'v2',
    'twenty-five' -> '25', 'two hundred' -> '200'."""
    text = re.sub(r"(\d)\s*(?:percent|per\s+cent)\b", r"\1%", text, flags=re.IGNORECASE)
    text = _COMPOUND.sub(_compound_value, text)
    return re.sub(r"\bversion\s+(\d)", r"v\1", text, flags=re.IGNORECASE)


def numbers(text: str) -> Counter[str]:
    text = _number_text(text)
    c: Counter[str] = Counter()
    for m in NUMBER.finditer(text):
        c[number_key(m)] += 1
    for m in NUMBER_WORD.finditer(text):
        word = m.group(1).lower()
        if word == "one" and _ordinary_word_use(text, m):
            continue
        c[NUMBER_WORDS[word]] += 1
    return c


def mask_month_may(text: str) -> str:
    """A capitalized "May" is the month, not the hedge "may", except at the start of a sentence before a subject
    ("May I ask", "May we")."""
    def repl(m: re.Match[str]) -> str:
        before = text[:m.start()].rstrip(" \t\"'“‘(*_")
        at_start = not before or before[-1] in ".!?:\n" or bool(re.search(r"(?:^|\n)\s*(?:[-*+]|\d+[.)])$", before))
        if at_start and MAY_MODAL_NEXT.match(text, m.end()):
            return m.group(0)
        return "MONTHMAY"
    return re.sub(r"\bMay\b", repl, text)


def dates(text: str) -> Counter[str]:
    """Month and weekday names, abbreviations normalized ("Fri" -> "Friday")."""
    c: Counter[str] = Counter()
    for m in DATE_WORD.finditer(mask_month_may(text)):
        if m.group(1):
            c["May" if m.group(1) == "MONTHMAY" else DATE_FULL[m.group(1)]] += 1
        else:
            c[DATE_ABBR[m.group(2)]] += 1
    return c


def unit_pairs(text: str) -> Counter[str]:
    """Each number with the unit written right after it (or a currency code before it): "30 s", "2 TB", "8"."""
    text = _number_text(text)
    c: Counter[str] = Counter()
    found: list[tuple[str, int, int]] = [(number_key(m), m.start(), m.end()) for m in NUMBER.finditer(text)]
    for m in NUMBER_WORD.finditer(text):
        word = m.group(1).lower()
        if not (word == "one" and _ordinary_word_use(text, m)):
            found.append((NUMBER_WORDS[word], m.start(), m.end()))
    for key, start, end in found:
        unit = ""
        cur = CURRENCY_BEFORE.search(text[max(0, start - 5):start])
        if cur:
            unit = cur.group(1)
        else:
            after = UNIT_AFTER.match(text, end)
            if after:
                unit = UNIT_NAMES.get(after.group(1).lower(), "")
                if not unit and after.group(1).isalpha():
                    # one qualifier between the number and the unit: "30 business days"
                    second = re.match(r"\s([A-Za-z]+)(?![\w-])", text[after.end():])
                    if second and second.group(1).lower() in UNIT_NAMES:
                        unit = after.group(1).lower() + " " + UNIT_NAMES[second.group(1).lower()]
        c[key + " " + (unit or "(no unit)")] += 1
    return c


def hedges(text: str) -> list[tuple[int, str]]:
    """Hedges with their level (1 possible, 2 likely, 3 planned). Requests and "would like" are not hedges.

    Stacked hedges ("could potentially", "may possibly") count once, at the weakest level, so reducing a stack to
    one hedge (SKILL.md) is not reported as a removal."""
    text = NOT_HEDGE.sub(" ", mask_month_may(text))
    spans: list[tuple[int, int, int, str]] = []
    for level, pattern in CERTAINTY:
        spans.extend((m.start(), m.end(), level, m.group(0)) for m in pattern.finditer(text))
    spans.sort()
    found: list[tuple[int, str]] = []
    last_end = -100
    for start, end, level, word in spans:
        gap = text[last_end:start] if last_end >= 0 else ""
        clause_stack = bool(found) and bool(re.match(r"(?:it\s+)?(?:seems?|seemed|appears?|appeared)(?:\s+(?:that|like))?$",
                                                     found[-1][1], re.IGNORECASE)) and len(gap) <= 40 and \
            not re.search(r"[,;:.!?]|\b(?:and|but|or|so|because|although)\b", gap)
        if found and (_stack_gap(gap) or clause_stack):
            prev_level, prev_word = found[-1]
            found[-1] = (min(prev_level, level), prev_word if prev_level <= level else word)
        else:
            found.append((level, word))
        last_end = max(last_end, end)
    return found


STACK_GAP_WORDS = {"be", "that", "it", "to", "is", "was", "were", "are", "also", "still", "even", "ever", "just",
                   "there", "this", "have", "has", "been", "well", "actually", "very", "quite"}


def _stack_gap(gap: str) -> bool:
    """Two hedges form one stack when only a few function words stand between them ("could potentially",
    "it seems that it might")."""
    if re.search(r"[,;:.!?]", gap):
        return False
    words = re.findall(r"[A-Za-z'’]+", gap)
    return len(words) <= 3 and all(w.lower() in STACK_GAP_WORDS for w in words)


NEG_GROUPS = (("not", _rx(r"\b(?:not|no|never|none|nothing|nobody|nowhere|cannot)\b|n['’]t\b")),
              ("without", _rx(r"\bwithout\b")), ("unless", _rx(r"\bunless\b")), ("neither/nor", _rx(r"\b(?:neither|nor)\b")))


def negation_profile(text: str) -> Counter[str]:
    text = NOT_NEGATION.sub(" ", text)
    return Counter({name: len(rx.findall(text)) for name, rx in NEG_GROUPS if rx.search(text)})


def denied_words(text: str) -> set[str]:
    """Words denied by "not (the) X", "rather than X", "instead of X", leaving out "not just/only X" (which affirms X)."""
    found: set[str] = set()
    for m in CONTRAST_DENIED.finditer(text):
        if re.match(r"not\s+(?:just|only|merely|simply)\b", m.group(0), re.IGNORECASE):
            continue
        if m.group(1) and re.search(r"\b(?:do|does|did|will|would|can|could|should|must|may|might)\s+$",
                                    text[max(0, m.start() - 12):m.start()], re.IGNORECASE):
            continue  # "do not use X": the verb is not the denied side
        word = (m.group(1) or m.group(2) or "").lower()
        if word and word not in STOPWORDS:
            found.add(word)
    return found


def conditions(text: str) -> list[str]:
    return [m.group(0) for m in CONDITION.finditer(NOT_CONDITION.sub(" ", text))]


def _ordinary_word_use(text: str, m: re.Match[str]) -> bool:
    """Skip "one" only where it is clearly a pronoun: "no one", "one another", and "the/old/new ... one"
    at the end of a phrase or before who/that/which. "One of", "only one", "exactly one" stay numbers."""
    before = text[max(0, m.start() - 12):m.start()].lower()
    rest = text[m.end():]
    if re.search(r"\bno\s+$", before) or re.match(r"\s+another\b", rest, re.IGNORECASE):
        return True
    after_det = re.search(r"\b(?:the|this|that|which|every|any|each|an?|old|new|other|last|next|same|right|wrong|big|"
                          r"small|main|better|best|bad|good|little|blue|red|green|white|black)\s+$", before)
    if not after_det:
        return False
    nxt = re.match(r"\s+([A-Za-z]+)", rest)
    return nxt is None or nxt.group(1).lower() in ("who", "that", "which")


def approx_map(text: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    text = _number_text(text)
    for m in NUMBER.finditer(text):
        key = number_key(m)
        before = APPROX_BEFORE.search(text[max(0, m.start() - 20):m.start()])
        after = APPROX_AFTER.search(text[m.end():m.end() + 30])
        marks = result.setdefault(key, set())
        if before:
            marks.add(before.group(0).strip().lower())
        if after:
            marks.add(re.sub(r"^[a-z]+\s+(?=or\b)", "", after.group(0).strip().lower()))
    for m in NUMBER_WORD.finditer(text):
        word = m.group(1).lower()
        if word == "one" and _ordinary_word_use(text, m):
            continue
        before = APPROX_BEFORE.search(re.sub(r"\ba\s+$", "", text[max(0, m.start() - 22):m.start()]))
        marks = result.setdefault(NUMBER_WORDS[word], set())
        if before:
            marks.add(before.group(0).strip().lower())
    return result


APPROX_GROUPS = (
    ("at most", ("at most", "no more than", "not more than", "up to", "a maximum of", "maximum of", "within",
                 "or less", "or fewer", "or below")),
    ("at least", ("at least", "no less than", "not less than", "no fewer than", "a minimum of", "minimum of",
                  "upwards of", "or more", "+", "or above")),
    ("about", ("about", "approximately", "approx.", "approx", "around", "roughly", "~", "circa", "some", "close to",
               "or so")),
    ("more than", ("more than", "over", "above", "just over")),
    ("less than", ("less than", "under", "below", "fewer than", "just under")),
)
_APPROX_INDEX = {re.sub(r"\s+", " ", w): g for g, words in APPROX_GROUPS for w in words}
NOT_NEGATION = _rx(r"\bnothing\s+short\s+of\b|\b(?:no|not)\s+(?:more|less|fewer)\s+than\s+(?=[$€£¥~#]?\d|(?:one|two|three|four|five|six|seven|"
                   r"eight|nine|ten|eleven|twelve|twenty|thirty|fifty|hundred|a\s+(?:few|dozen|hundred|thousand))\b)")


def approx_group(word: str) -> str:
    return _APPROX_INDEX.get(re.sub(r"\s+", " ", word.strip().lower()), word.strip().lower())


def count(pattern: re.Pattern[str], text: str) -> int:
    if pattern is NEGATION:
        text = NOT_NEGATION.sub(" ", text)
    return len(pattern.findall(text))


def first(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(0) if m else ""


def obligation_level(text: str) -> tuple[int, str]:
    text = NEG_OBLIGATION.sub(" ", text)
    m = OBLIGATION_STRONG.search(text)
    if m:
        return 2, m.group(0)
    m = OBLIGATION_SOFT.search(text)
    if m:
        return 1, m.group(0)
    return 0, ""


def names(sentence: str, include_initial: bool = False, lower_words: Optional[set[str]] = None) -> list[str]:
    """Capitalized words that are not sentence-initial. With lower_words (words seen in lower case anywhere),
    a sentence-initial word counts too when it looks like a name followed by a verb ("Priya approved ...")."""
    tokens = list(re.finditer(r"[A-Za-z][A-Za-z0-9'’-]*", sentence))
    found: list[str] = []
    for i, m in enumerate(tokens):
        word = m.group(0)
        word = re.sub(r"['’]s?$", "", word)
        if not word or not word[0].isupper() or word in NAME_STOP or word.upper() in UNIT_CODES:
            continue
        if i == 0 and not include_initial:
            if lower_words is None or not _initial_name(word, sentence[m.end():], lower_words):
                continue
        found.append(word)
    return found


def _word_forms(word: str) -> set[str]:
    w = word.lower()
    forms = {w}
    for suffix, repl in (("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
                         ("d", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            forms.add(w[: len(w) - len(suffix)] + repl)
    return forms


def _initial_name(word: str, rest: str, lower_words: set[str]) -> bool:
    if len(word) < 2 or word.lower() in STOPWORDS or re.search(r"(?:s|ing|ly|ed)$", word):
        return False
    if _word_forms(word) & lower_words:
        return False
    return bool(VERBISH.match(rest))


def lower_word_set(*texts: str) -> set[str]:
    """Words written in lower case somewhere in the texts, with simple inflections removed."""
    found: set[str] = set()
    for t in texts:
        for w in re.findall(r"(?<![\w'’-])[a-z][a-z'’-]+", t):
            found |= _word_forms(w)
    return found


def content_words(text: str) -> set[str]:
    words: set[str] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z'’-]{3,}", text):
        w = m.group(0).lower().strip("'’-")
        if w in STOPWORDS or "'" in w or "’" in w:
            continue
        words.add(w)
    return words


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def protected_items(doc: tx.Document) -> Counter[str]:
    items: Counter[str] = Counter()
    fence: list[str] = []
    for line in doc.lines:
        if line.kind == "code":
            fence.append(line.raw)
            continue
        if fence:
            items["code block: " + "\n".join(fence).strip()] += 1
            fence = []
        if line.kind in ("para", "list", "heading", "table"):
            for s, e, kind in tx.protected_spans(line.content):
                if kind == "html":
                    continue
                items[f"{kind}: {line.content[s:e]}"] += 1
    if fence:
        items["code block: " + "\n".join(fence).strip()] += 1
    return items


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


# ---------------------------------------------------------------- alignment


def _align_keys(doc: tx.Document) -> list[str]:
    """Sentence keys for alignment. A later sentence of a list item or table row carries its item's opening words,
    so identical sentences in different items ("Owner: Marco Ruiz.") are not matched across items."""
    keys: list[str] = []
    first_words: dict[int, str] = {}
    for s in doc.sentences:
        n = _norm(s.text)
        if s.kind in ("list", "table"):
            if s.block_index not in first_words:
                first_words[s.block_index] = " ".join(re.sub(r"[*_`]", "", n).split()[:6])
                keys.append(n)
            else:
                keys.append(first_words[s.block_index] + " | " + n)
        else:
            keys.append(n)
    return keys


def align(orig: tx.Document, rev: tx.Document) -> list[Chunk]:
    a = _align_keys(orig)
    b = _align_keys(rev)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    chunks: list[Chunk] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        o = orig.sentences[i1:i2]
        r = rev.sentences[j1:j2]
        if tag == "replace" and len(o) == len(r) and len(o) > 1:
            ratios = [difflib.SequenceMatcher(None, a[i1 + k], b[j1 + k]).ratio() for k in range(len(o))]
            if all(x > 0.35 for x in ratios):
                for k in range(len(o)):
                    chunks.append(Chunk([o[k]], [r[k]]))
                continue
        if tag == "replace" and len(o) > 1 and len(r) > 1:
            chunks.extend(_split_chunk(o, r))
            continue
        chunks.append(Chunk(list(o), list(r)))
    return chunks


def _split_chunk(o: list[tx.Sentence], r: list[tx.Sentence]) -> list[Chunk]:
    """Pair sentences of a replace block monotonically by similarity.

    Each pair becomes a 1:1 chunk; the unpaired sentences between two pairs form their own chunk.
    """
    pairs: list[tuple[int, int]] = []
    j_start = 0
    r_words = [set(_norm(x.text).split()) for x in r]
    for i, so in enumerate(o):
        best, best_j = 0.0, -1
        a = _norm(so.text)
        a_words = set(a.split())
        # rank candidates by shared words (cheap), then measure only the top few exactly
        ranked = sorted(range(j_start, len(r)), key=lambda j: -len(a_words & r_words[j]) / (len(a_words | r_words[j]) or 1))
        for j in ranked[:4]:
            sm = difflib.SequenceMatcher(None, a, _norm(r[j].text))
            if sm.real_quick_ratio() <= max(best, 0.49) or sm.quick_ratio() <= max(best, 0.49):
                continue
            ratio = sm.ratio()
            if ratio > best:
                best, best_j = ratio, j
        if best >= 0.5:
            pairs.append((i, best_j))
            j_start = best_j + 1
    if not pairs:
        return [Chunk(list(o), list(r))]
    chunks: list[Chunk] = []
    pi, pj = 0, 0
    for i, j in pairs:
        if o[pi:i] or r[pj:j]:
            chunks.append(Chunk(list(o[pi:i]), list(r[pj:j])))
        chunks.append(Chunk([o[i]], [r[j]]))
        pi, pj = i + 1, j + 1
    if o[pi:] or r[pj:]:
        chunks.append(Chunk(list(o[pi:]), list(r[pj:])))
    return _attach_leftovers(chunks)


def _chunk_ratio(ch: Chunk) -> float:
    return difflib.SequenceMatcher(None, _norm(" ".join(s.text for s in ch.orig)),
                                   _norm(" ".join(s.text for s in ch.rev))).ratio()


def _attach_leftovers(chunks: list[Chunk]) -> list[Chunk]:
    """Join a one-sided leftover sentence to the neighboring pair when that makes the pair more similar.

    This turns the second half of a split sentence (or the merged-in sentence) into a 1:2 or 2:1 chunk, so its
    numbers and words are compared with the sentence they came from.
    """
    result = list(chunks)
    k = 0
    while k < len(result):
        ch = result[k]
        if (ch.orig and ch.rev) or len(ch.orig) + len(ch.rev) != 1:
            k += 1
            continue
        best: Optional[tuple[float, int, Chunk]] = None
        for nb in (k - 1, k + 1):
            if not 0 <= nb < len(result) or not result[nb].orig or not result[nb].rev:
                continue
            pair = result[nb]
            if ch.orig:
                merged = Chunk(pair.orig + ch.orig if nb < k else ch.orig + pair.orig, pair.rev)
            else:
                merged = Chunk(pair.orig, pair.rev + ch.rev if nb < k else ch.rev + pair.rev)
            ratio = _chunk_ratio(merged)
            if ratio > _chunk_ratio(pair) and _leftover_overlap(ch, pair) >= 1 and (best is None or ratio > best[0]):
                best = (ratio, nb, merged)
        if best is None:
            k += 1
            continue
        result[best[1]] = best[2]
        del result[k]
        if best[1] < k:
            k -= 1
    return result


def _leftover_overlap(leftover: Chunk, pair: Chunk) -> int:
    """Content words of a one-sided leftover sentence that appear on the pair's other side but not on its own side."""
    if leftover.orig:
        return len(content_words(leftover.orig_text) & (content_words(pair.rev_text) - content_words(pair.orig_text)))
    return len(content_words(leftover.rev_text) & (content_words(pair.orig_text) - content_words(pair.rev_text)))


def attach_adjacent(chunks: list[Chunk], orig: tx.Document, rev: tx.Document) -> list[Chunk]:
    """Join a deleted (or added) sentence to the changed sentence right before or after it in the document when that
    makes the pair more similar: its content was merged into the neighbor ("..., and sleepiness also improved")."""
    o_index = {id(x): k for k, x in enumerate(orig.sentences)}
    r_index = {id(x): k for k, x in enumerate(rev.sentences)}
    result = list(chunks)
    k = 0
    while k < len(result):
        ch = result[k]
        if (ch.orig and ch.rev) or len(ch.orig) + len(ch.rev) != 1:
            k += 1
            continue
        side_o = bool(ch.orig)
        pos = o_index[id(ch.orig[0])] if side_o else r_index[id(ch.rev[0])]
        best: Optional[tuple[float, int, Chunk]] = None
        for nb, pair in enumerate(result):
            if not pair.orig or not pair.rev:
                continue
            idx = [o_index[id(x)] for x in pair.orig] if side_o else [r_index[id(x)] for x in pair.rev]
            own = ch.orig[0] if side_o else ch.rev[0]
            same_block = any(x.block_index == own.block_index for x in (pair.orig if side_o else pair.rev))
            adjacent = idx[-1] + 1 == pos or idx[0] - 1 == pos
            if not adjacent and not same_block:
                continue
            if pos > idx[-1]:
                merged = Chunk(pair.orig + ch.orig, pair.rev) if side_o else Chunk(pair.orig, pair.rev + ch.rev)
            else:
                merged = Chunk(ch.orig + pair.orig, pair.rev) if side_o else Chunk(pair.orig, ch.rev + pair.rev)
            ratio = _chunk_ratio(merged) if adjacent else 0.0
            # or: most of the leftover's content words are words the neighbor gained (or lost)
            left = content_words(ch.orig_text if side_o else ch.rev_text)
            gained = (content_words(pair.rev_text) - content_words(pair.orig_text)) if side_o else \
                (content_words(pair.orig_text) - content_words(pair.rev_text))
            overlap = len(left & gained)
            moved_in = overlap >= 2 and overlap >= len(left) / 2
            score = ratio + (1.0 if moved_in else 0.0)
            if ((ratio > _chunk_ratio(pair) and overlap >= 1) or moved_in) and (best is None or score > best[0]):
                best = (score, nb, merged)
        if best is None:
            k += 1
            continue
        result[best[1]] = best[2]
        del result[k]
        k = 0 if best[1] < k else k
    result.sort(key=lambda c: c.orig_line or c.rev_line)
    return result


def pair_moved(chunks: list[Chunk]) -> list[Chunk]:
    """Pair deleted and added sentences that are similar (a sentence moved and edited) so they are compared."""
    dels = [(ci, k) for ci, ch in enumerate(chunks) if ch.orig and not ch.rev for k in range(len(ch.orig))]
    ins = [(ci, k) for ci, ch in enumerate(chunks) if ch.rev and not ch.orig for k in range(len(ch.rev))]
    # Sentences inside an uneven chunk (2 -> 1, 1 -> 3 ...) that closely match a one-sided sentence elsewhere were
    # moved, not merged; pair them too, with a stricter threshold so split halves stay with their sentence.
    uneven = [ci for ci, ch in enumerate(chunks) if ch.orig and ch.rev and len(ch.orig) != len(ch.rev)]
    dels_u = [(ci, k) for ci in uneven for k in range(len(chunks[ci].orig))] if ins else []
    ins_u = [(ci, k) for ci in uneven for k in range(len(chunks[ci].rev))] if dels else []
    if (not dels or not ins) and not (dels_u and ins) and not (ins_u and dels):
        return chunks
    if (len(dels) + len(dels_u)) * (len(ins) + len(ins_u)) > 40000:
        return chunks
    candidates: list[tuple[float, tuple[int, int], tuple[int, int]]] = []

    def consider(d: tuple[int, int], i: tuple[int, int], threshold: float) -> None:
        m = difflib.SequenceMatcher(None, _norm(chunks[d[0]].orig[d[1]].text), _norm(chunks[i[0]].rev[i[1]].text))
        if m.real_quick_ratio() >= threshold and m.quick_ratio() >= threshold:
            ratio = m.ratio()
            if ratio >= threshold:
                candidates.append((ratio, d, i))

    for d in dels:
        for i in ins:
            consider(d, i, 0.6)
        for i in ins_u:
            consider(d, i, 0.8)
    for d in dels_u:
        for i in ins:
            consider(d, i, 0.8)
    candidates.sort(key=lambda c: -c[0])
    used_d: set[tuple[int, int]] = set()
    used_i: set[tuple[int, int]] = set()
    pairs: list[Chunk] = []
    for _ratio, d, i in candidates:
        if d in used_d or i in used_i:
            continue
        used_d.add(d)
        used_i.add(i)
        pairs.append(Chunk([chunks[d[0]].orig[d[1]]], [chunks[i[0]].rev[i[1]]]))
    if not pairs:
        return chunks
    result: list[Chunk] = []
    for ci, ch in enumerate(chunks):
        rest_o = [x for k, x in enumerate(ch.orig) if (ci, k) not in used_d]
        rest_r = [x for k, x in enumerate(ch.rev) if (ci, k) not in used_i]
        if rest_o or rest_r:
            result.append(ch if (len(rest_o), len(rest_r)) == (len(ch.orig), len(ch.rev)) else Chunk(rest_o, rest_r))
    result.extend(pairs)
    result.sort(key=lambda ch: ch.orig_line or ch.rev_line)
    return result


# ---------------------------------------------------------------- comparisons


def compare_chunk(ch: Chunk, doc_type: Optional[str], risks: list[Risk], reviews: list[Review],
                  orig_all: str, extra_sources: str, proper_names: Optional[set[str]] = None, rev_all: str = "") -> None:
    o, r = STOCK_MARKERS.sub(" ", ch.orig_text), STOCK_MARKERS.sub(" ", ch.rev_text)
    so, sr = ch.show_orig(), ch.show_rev()

    def risk(kind: str, counted: bool, message: str) -> None:
        risks.append(Risk(kind, counted, message, ch.orig_line, ch.rev_line, so, sr))

    def review(kind: str, message: str, text: Optional[str] = None) -> None:
        reviews.append(Review(kind, message, ch.rev_line or ch.orig_line, text if text is not None else (sr or so)))

    if not o.strip() and r.strip():
        # added sentences: numbers and status words are checked on the whole text
        if COMMITMENT.search(r):
            risk("commitment", True, f'Commitment added: "{first(COMMITMENT, r)}"')
        if BOOSTER.search(r):
            word = first(BOOSTER, r)
            if doc_type in FACT_TYPES:
                risk("booster", True, f'Certainty word added: "{word}"')
            else:
                review("booster", f'Certainty word added: "{word}". Do not add guarantees the original lacks.')
        for word in _list_hits("feelings", r):
            if word not in _list_hits("feelings", orig_all):
                review("feeling_added", f'Feeling word added: "{word}". Do not add feelings the original does not state.')
        if CAUSAL.search(r):
            review("causal_added", f'Added sentence states a cause: "{first(CAUSAL, r)}". Check that the original '
                   "or material says so.")
        if count(NEGATION, r) or OBLIGATION_STRONG.search(r) or PERMISSION.search(r):
            review("added", "Added sentence holds a negation, obligation or permission. Check that the original or "
                   "material says so.")
        return
    if not r.strip():
        return  # deleted sentences are reviewed in compare()

    on, rn = numbers(o), numbers(r)
    if on != rn:
        removed = sorted((on - rn).elements())
        added = sorted((rn - on).elements())
        parts = []
        if removed:
            parts.append("removed " + ", ".join(removed))
        if added:
            note = ""
            source_numbers = _cached_numbers(extra_sources + "\n" + orig_all)
            elsewhere = [n for n in added if source_numbers.get(n)]
            if elsewhere:
                verb = "appears" if len(elsewhere) == 1 else "appear"
                note = f" ({', '.join(elsewhere)} {verb} elsewhere in the original or material)"
            parts.append("added " + ", ".join(added) + note)
        risk("number", True, "Number changed: " + "; ".join(parts))
    else:
        oa, ra = approx_map(o), approx_map(r)
        for key in sorted(set(oa) & set(ra)):
            if {approx_group(w) for w in oa[key]} != {approx_group(w) for w in ra[key]}:
                before = ", ".join(sorted(oa[key])) or "none"
                after = ", ".join(sorted(ra[key])) or "none"
                risk("approximation", True, f"Approximation on {key} changed: {before} → {after}")
        uo, ur = unit_pairs(o), unit_pairs(r)
        if uo != ur:
            risk("number", True, "Unit changed: " + ", ".join(sorted((uo - ur).elements())) + " → "
                 + ", ".join(sorted((ur - uo).elements())))
    do_, dr = dates(o), dates(r)
    if do_ != dr:
        parts = []
        if do_ - dr:
            parts.append("removed " + ", ".join(sorted((do_ - dr).elements())))
        if dr - do_:
            parts.append("added " + ", ".join(sorted((dr - do_).elements())))
        risk("number", True, "Month or weekday changed: " + "; ".join(parts))

    o_neg, r_neg = o, r
    if PERMISSION.search(o) and PERMISSION.search(r):
        # "You don't have to restart" -> "Restarting is optional": a negated obligation is a permission
        o_neg, r_neg = NEG_OBLIGATION.sub(" ", o), NEG_OBLIGATION.sub(" ", r)
    neg_o, neg_r = count(NEGATION, o_neg), count(NEGATION, r_neg)
    not_just = re.compile(r"\b(?:not|n['’]t)\s+(?:just|only|merely|simply)\b|n['’]t\s+(?:just|only|merely|simply)\b", re.IGNORECASE)
    nj_o, nj_r = len(not_just.findall(o_neg)), len(not_just.findall(r_neg))
    quiet = re.compile(r"\b(?:silent(?:ly)?|quiet(?:ly)?)\b", re.IGNORECASE)
    if neg_r == neg_o + 1 and quiet.search(o) and not quiet.search(r):
        risk("negation", False, f"Number of negations changed: {neg_o} → {neg_r}. \"silently\" or \"quietly\" became a "
             "negation (\"no alert\", \"without an error message\"); fine only when the text says what was missing.")
    elif neg_o != neg_r and neg_o - nj_o == neg_r - nj_r:
        risk("negation", False, f"Number of negations changed: {neg_o} → {neg_r}, only by \"not just\" or \"not only\". "
             "Check that what it affirmed is still affirmed (\"not just X, Y\" keeps X).")
    elif neg_o != neg_r:
        risk("negation", True, f"Number of negations changed: {neg_o} → {neg_r}")
    else:
        prof_o, prof_r = negation_profile(o_neg), negation_profile(r_neg)
        den_o, den_r = denied_words(o), denied_words(r)
        swapped_o = {w for w in den_o - den_r if re.search(r"\b" + re.escape(w) + r"\b", r, re.IGNORECASE)}
        swapped_r = {w for w in den_r - den_o if re.search(r"\b" + re.escape(w) + r"\b", o, re.IGNORECASE)}
        if prof_o != prof_r:
            gone = ", ".join(sorted((prof_o - prof_r).elements()))
            new = ", ".join(sorted((prof_r - prof_o).elements()))
            risk("negation", True, f"Negation changed: {gone} → {new}. Check that the same thing is still denied.")
        elif swapped_o and swapped_r:
            risk("negation", True, f'What is denied changed: "not {sorted(swapped_o)[0]}" → "not {sorted(swapped_r)[0]}"')

    q_orig = [s for s in ch.orig if _is_question(s.text)]
    q_rev = [s for s in ch.rev if _is_question(s.text)]
    questions_o, questions_r = len(q_orig), len(q_rev)
    if questions_o != questions_r:
        message = f"Number of questions changed: {questions_o} → {questions_r}"
        folded = questions_o > questions_r and len(ch.orig) > questions_o and \
            all(len(s.text.split()) <= 6 and not hedges(s.masked) and
                re.match(r"\s*(?:what|why|how|who|where|which|the|a|an|so|and|but)\b", s.masked, re.IGNORECASE)
                for s in q_orig)
        polite = questions_r > questions_o and bool(q_rev) and \
            bool(re.match(r"\s*(?:could|would|can|will)\s+you\b", q_rev[0].masked, re.IGNORECASE)) and \
            (bool(REQUEST.search(o)) or _imperative(ch.orig))
        if folded:
            risk("question", False, message + ". A short self-answered question was folded into a statement; "
                 "fine when the answer is kept.")
        elif polite:
            risk("question", False, message + ". A request became a polite question; fine when the stated "
                 "relationship asks for it (register.md).")
        else:
            risk("question", True, message)
    has_question = questions_o or questions_r

    # Hedges are compared on the statements only, so folding a self-answered question still shows a dropped hedge.
    o_st = " ".join(x.masked for x in ch.orig if not _is_question(x.text))
    r_st = " ".join(x.masked for x in ch.rev if not _is_question(x.text))
    if o_st.strip() and r_st.strip():
        if PERMISSION.search(o_st) and PERMISSION.search(r_st):
            # a permission "may" on both sides ("You may include" -> "You are allowed to include") is not a hedge
            o_st = re.sub(r"\b((?:you|users?|they|we|customers?|members?)\s+)may\b", r"\1", o_st, flags=re.IGNORECASE)
            r_st = re.sub(r"\b((?:you|users?|they|we|customers?|members?)\s+)may\b", r"\1", r_st, flags=re.IGNORECASE)
        if count(ABILITY, r_st) >= count(ABILITY, o_st):
            # "can possibly" -> "can" reduces a stack (SKILL.md); "can" stays as the hedge
            o_st = re.sub(r"\b(can)\s+(?:possibly|potentially|conceivably|maybe)\b", r"\1", o_st, flags=re.IGNORECASE)
        ho, hr = hedges(o_st), hedges(r_st)
        lv_o, lv_r = sorted(lv for lv, _ in ho), sorted(lv for lv, _ in hr)
        list_o, list_r = sorted(w.lower() for _, w in ho), sorted(w.lower() for _, w in hr)
        set_o, set_r = set(list_o), set(list_r)
        gone = next((w for _, w in ho if w.lower() not in set_r), ho[0][1] if ho else "")
        now = next((w for _, w in hr if w.lower() not in set_o), "")
        if len(hr) < len(ho) or (lv_o != lv_r and len(hr) == len(ho) and all(b >= a for a, b in zip(lv_o, lv_r))):
            if gone.lower() == "may" and ABILITY.search(r_st) and not ABILITY.search(o_st):
                risk("certainty", True, '"may" became "can": a possibility or permission now reads as ability')
            else:
                risk("certainty", True, f'Certainty strengthened: "{gone}" → ' + (f'"{now}"' if now else "a plain statement"))
        elif len(hr) > len(ho) or lv_o != lv_r:
            wo = next((w for _, w in ho if w.lower() not in set_r), "")
            review("certainty_weakened", 'Certainty weakened: ' + (f'"{wo}"' if wo else "a plain statement")
                   + f' → "{now}". Check that the original was not more certain.')
        elif list_o != list_r and gone and now:
            review("hedge_changed", f'Hedge changed at the same strength: "{gone}" → "{now}".')
    if not has_question:
        bo, br = count(BOOSTER, o), count(BOOSTER, r)
        if br > bo:
            word = first(BOOSTER, r)
            if doc_type in FACT_TYPES and not OBLIGATION_STRONG.search(o):
                risk("booster", True, f'Certainty word added: "{word}"')
            else:
                review("booster", f'Certainty word added: "{word}". Do not add guarantees the original lacks.')

    po_m = PERMISSION.search(NOT_PERMISSION.sub(" ", mask_month_may(o)))
    po = bool(po_m)
    pr_ = bool(PERMISSION.search(NOT_PERMISSION.sub(" ", mask_month_may(r))))
    if po and not pr_ and po_m is not None and po_m.group(0).lower().endswith(" may") and \
            re.search(r"\b(?:might|could)\b", r, re.IGNORECASE):
        pass  # "Users may see a delay" -> "Users might see a delay": a possibility, compared as a hedge
    elif po != pr_:
        word = first(PERMISSION, o if po else r)
        risk("permission", True, f'Permission {"removed" if po else "added"}: "{word}"')

    obl_o, w_obl_o = obligation_level(o)
    obl_r, w_obl_r = obligation_level(r)
    if obl_o != obl_r:
        risk("obligation", True, "Obligation strength changed: "
             + (f'"{w_obl_o}"' if w_obl_o else "none") + " → " + (f'"{w_obl_r}"' if w_obl_r else "none"))

    if ABILITY.search(o) and not ABILITY.search(r) and not PERMISSION.search(r) and not OBLIGATION_STRONG.search(r):
        possibility = re.search(r"\b(\w+)\s+can\s+(\w+)", o, re.IGNORECASE)
        person = r"(?:i|you|we|they|he|she|users?|customers?|admins?|administrators?|people|members?|teams?|anyone|everyone)"
        if possibility and not re.fullmatch(person, possibility.group(1), re.IGNORECASE) and \
                re.search(r"\b" + re.escape(possibility.group(2)[:5]), r, re.IGNORECASE) and not has_question:
            risk("certainty", True, f'"can {possibility.group(2)}" became a plain statement: if "can" meant possibility, '
                 "the sentence now says it always happens")
        else:
            review("ability", f'Ability phrase "{first(ABILITY, o)}" disappeared. Check that the sentence still says what '
                   'is possible; if "can" meant possibility, the sentence now says it always happens.')

    st_o, st_r = STATUS.findall(o), STATUS.findall(r)
    if st_o and not st_r:
        risk("status", True, f'Status word disappeared: "{st_o[0]}"')

    h_o, h_r = bool(HEARSAY.search(o)), bool(HEARSAY.search(r))
    if h_o != h_r:
        risk("hearsay", True, f'Hearsay marker {"removed" if h_o else "added"}: "{first(HEARSAY, o if h_o else r).strip()}"')

    rq_o, rq_r = bool(REQUEST.search(o)), bool(REQUEST.search(r))
    if rq_o and not rq_r:
        risk("request", True, f'Request marker removed: "{first(REQUEST, o)}"')
    elif rq_r and not rq_o:
        review("request_added", f'Request marker added: "{first(REQUEST, r)}". Check that the sentence was a request.')

    lim_o, lim_r = count(LIMITER, o), count(LIMITER, r)
    if lim_o > lim_r:
        risk("scope", True, f'Limiting word removed: "{first(LIMITER, o)}"')
    elif lim_r > lim_o:
        review("limiter_added", f'Limiting word added: "{first(LIMITER, r)}". Check that the original had that limit.')

    q_o = Counter(_quantifier(m.group(0)) for m in QUANTIFIER.finditer(o))
    q_r = Counter(_quantifier(m.group(0)) for m in QUANTIFIER.finditer(r))
    if q_o and q_r and q_o != q_r and sum(q_o.values()) == sum(q_r.values()):
        before = ", ".join(sorted((q_o - q_r).elements()))
        after = ", ".join(sorted((q_r - q_o).elements()))
        risk("scope", True, f'Quantifier changed: "{before}" → "{after}"')
    if on and on == rn:
        st_o = Counter(m.group(0).lower() for m in STATISTIC.finditer(o))
        st_r = Counter(m.group(0).lower() for m in STATISTIC.finditer(r))
        if st_o != st_r and st_o:
            risk("number", True, "Statistic changed: " + (", ".join(sorted((st_o - st_r).elements())) or "none") + " → "
                 + (", ".join(sorted((st_r - st_o).elements())) or "none"))

    cond_o, cond_r = conditions(o), conditions(r)
    contrast = re.compile(r"\b(?:but|although|though|however|yet|whereas)\b", re.IGNORECASE)
    if len(cond_o) > len(cond_r) and all(w.lower() == "while" for w in cond_o if w.lower() not in
                                         {x.lower() for x in cond_r}) and len(contrast.findall(r)) > len(contrast.findall(o)):
        pass  # concessive "while" rewritten as "but" / "although"
    elif len(cond_o) > len(cond_r):
        gone_c = next((w for w in cond_o if w.lower() not in {x.lower() for x in cond_r}), cond_o[0])
        risk("condition", True, f'Condition or time limit removed: "{gone_c}". Check that the sentence did not '
             "become true in more cases.")
    elif len(cond_r) > len(cond_o):
        new_c = next((w for w in cond_r if w.lower() not in {x.lower() for x in cond_o}), cond_r[0])
        review("condition_added", f'Condition added: "{new_c}". Do not add conditions the original lacks.')

    if (CHOICE.search(o) and not CHOICE.search(r) and ALL_SCOPE.search(r) and not ALL_SCOPE.search(o)) or \
            (ALL_SCOPE.search(o) and not ALL_SCOPE.search(r) and CHOICE.search(r) and not CHOICE.search(o)):
        risk("scope", True, f'Choice scope changed: "{first(CHOICE, o) or first(ALL_SCOPE, o)}" → '
             f'"{first(CHOICE, r) or first(ALL_SCOPE, r)}"')
    elif CHOICE.search(o) and not CHOICE.search(r) and len(re.findall(r"\band\b", r, re.IGNORECASE)) > \
            len(re.findall(r"\band\b", o, re.IGNORECASE)):
        risk("scope", True, f'Choice scope changed: "{first(CHOICE, o)}" → "and"')
    elif (PARTIAL_DET.search(o) or PARTIAL_ADV.search(o) or MOST_ANY.search(o)) and not STILL_PARTIAL.search(r):
        if count(TOTAL, r) > count(TOTAL, o) and (PARTIAL_DET.search(o) or PARTIAL_ADV.search(o)):
            word = first(PARTIAL_DET, o) or first(PARTIAL_ADV, o)
            risk("scope", True, f'Quantifier scope changed: "{word.strip()}" → "{first(TOTAL, r)}"')
        elif PARTIAL_DET.search(o):
            risk("scope", True, f'Quantifier "{first(PARTIAL_DET, o).strip()}" disappeared; the sentence may now cover everything')
        else:
            review("quantifier_gone", f'"{(first(PARTIAL_ADV, o) or first(MOST_ANY, o)).strip()}" disappeared. Check that the sentence did not become '
                   "always true.")

    ca_o, ca_r = count(CAUSAL, o), count(CAUSAL, r)
    if ca_r > ca_o:
        if CORRELATION.search(o) and not ca_o:
            risk("correlation", True, f'Cause word "{first(CAUSAL, r)}" added to a sentence that stated a '
                 f'correlation ("{first(CORRELATION, o)}")')
        else:
            review("causal_added", f'Causal link added: "{first(CAUSAL, r)}". Keep facts listed side by side if the '
                   "original did not connect them.")

    if count(COMMITMENT, r) > count(COMMITMENT, o):
        risk("commitment", True, f'Commitment added: "{first(COMMITMENT, r)}"')

    if Counter(CITATION.findall(o)) != Counter(CITATION.findall(r)):
        risk("citation", True, "Citation changed: " + ", ".join(CITATION.findall(o)) + " → "
             + ", ".join(CITATION.findall(r)))

    if proper_names is not None and rev_all:
        n_o = _sentence_names(ch.orig, proper_names)
        n_r = _sentence_names(ch.rev, proper_names)
        gone_n = sorted(n for n in n_o - n_r if not re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", rev_all))
        if gone_n:
            new_n = sorted(n for n in n_r - n_o if not re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", orig_all))
            risk("name", True, f'Name gone from the text: {", ".join(gone_n)}' + (f' (now {", ".join(new_n)})' if new_n else "")
                 + ". Check who does what.")

    if len(ch.orig) == 1 and len(ch.rev) == 1:
        no, nr = names(ch.orig[0].masked, True), names(ch.rev[0].masked, True)
        if len(no) >= 2 and Counter(no) == Counter(nr) and no != nr:
            by_o, by_r = bool(re.search(r"\bby\b", o)), bool(re.search(r"\bby\b", r))
            if by_o != by_r:
                review("voice", "Active/passive voice changed with the same names. Check who does what.")
            else:
                risk("name_order", True, f'Names appear in a different order ({", ".join(no)} → {", ".join(nr)}). '
                     "Check who does what to whom.")

    for m in CONTRAST_DENIED.finditer(o):
        denied = (m.group(1) or m.group(2) or "").lower()
        if not denied or denied in STOPWORDS or re.match(r"not\s+(?:just|only|merely|simply)\b", m.group(0), re.IGNORECASE):
            continue
        for s in ch.rev:
            text = s.masked.lower()
            if re.search(r"\b" + re.escape(denied) + r"\b", text) and not NEGATION.search(text) and \
                    not re.search(r"\b(?:instead\s+of|rather\s+than)\b", text) and PRIORITY_WORDS.search(text):
                risk("contrast_reversed", False, f'"{denied}" was denied in the original and now appears on the '
                     f'affirmative side ("{first(PRIORITY_WORDS, text)}"). Check that the claim did not flip.')
                break

    quotes_o = Counter(a or b for a, b in QUOTED.findall(o))
    quotes_r = Counter(a or b for a, b in QUOTED.findall(r))
    if quotes_o and quotes_o != quotes_r:
        lost = [q for q in quotes_o if q not in quotes_r]
        if lost:
            review("quote", f'Text in quotation marks changed or disappeared: "{lost[0]}". Restore quoted words, '
                   "labels and dialogue.")

    feelings_o = _list_hits("feelings", o)
    feelings_all = _cached_feelings(orig_all)
    for word in _list_hits("feelings", r):
        if word not in feelings_o and word not in feelings_all:
            review("feeling_added", f'Feeling word added: "{word}". Do not add feelings the original does not state.')

    if any(s.kind == "quote" for s in ch.orig + ch.rev):
        review("quote_changed", "Text inside a block quotation changed. Restore it unless it is the writer's own note "
               "rather than a quotation.")

    orig_starts = {x.masked.strip().lstrip("\"'“‘(*_").split(" ")[0].lower() for x in ch.orig}
    for s in ch.rev:
        start = s.masked.strip().lstrip("\"'“‘(*_")
        cm = CONNECTIVE.match(start)
        if cm and cm.group(0).split(" ")[0].lower() not in orig_starts:
            review("connection", f'Rewritten sentence starts with "{cm.group(0)}". Check what it connects to.', s.text)
            break


SUBJECT_WORDS = {"i", "you", "we", "they", "he", "she", "it", "the", "a", "an", "this", "that", "these", "those",
                 "our", "your", "my", "their", "his", "her", "its", "there", "here", "everyone", "someone", "nobody"}


def _imperative(sentences: list[tx.Sentence]) -> bool:
    """A sentence that starts with a verb rather than a subject ("Send the report by Friday.")."""
    for x in sentences:
        words = re.findall(r"[A-Za-z'’]+", x.masked)
        if words and words[0].lower() not in SUBJECT_WORDS and not _is_question(x.text):
            return True
    return False


@functools.lru_cache(maxsize=8)
def _cached_numbers(text: str) -> Counter[str]:
    return numbers(text)


@functools.lru_cache(maxsize=8)
def _cached_feelings(text: str) -> list[str]:
    return _list_hits("feelings", text)


def _sentence_names(sentences: list[tx.Sentence], proper: set[str]) -> set[str]:
    """Names in sentences: capitalized words after the first word, plus a first word that is capitalized
    in the middle of some sentence elsewhere (so "Several" or "Feel" at the start is not a name)."""
    found: set[str] = set()
    for x in sentences:
        found |= set(names(x.masked))
        first = names(x.masked, include_initial=True)[:1]
        if first and first[0] in proper:
            found.add(first[0])
    return found


def _quantifier(word: str) -> str:
    w = re.sub(r"\s+", " ", word.lower())
    return "all" if w in ("all", "every", "each") else w


def _is_question(text: str) -> bool:
    return text.rstrip().rstrip("\"'”’)*_").endswith("?")


_LIST_CACHE: dict[str, list[tx.ListEntry]] = {}


def _list_hits(name: str, text: str) -> list[str]:
    if name not in _LIST_CACHE:
        _LIST_CACHE[name] = tx.load_list(name)
    hits: list[str] = []
    for entry in _LIST_CACHE[name]:
        for m in entry.pattern.finditer(text):
            w = m.group(0).lower()
            if w not in hits:
                hits.append(w)
    return hits


def _dedupe_risks(risks: list[Risk]) -> list[Risk]:
    """One counted risk per change: two scope findings on the same pair, or "may" -> "can" reported as both
    certainty and permission, count once."""
    result: list[Risk] = []
    seen_scope: set[tuple[int, int]] = set()
    may_can: set[tuple[int, int]] = {(x.orig_line, x.rev_line) for x in risks if x.message.startswith('"may" became "can"')}
    for x in risks:
        key = (x.orig_line, x.rev_line)
        if x.counted and x.kind == "scope" and key != (0, 0):
            if key in seen_scope:
                continue
            seen_scope.add(key)
        if x.kind == "permission" and key in may_can and x.message.lower().endswith(' may"'):
            continue
        result.append(x)
    return result


def moved_names(chunks: list[Chunk], lower_words: Optional[set[str]] = None) -> list[Risk]:
    """Names that left one changed sentence and appeared in another (owners swapped between list items)."""
    lw = lower_words if lower_words is not None else set()
    singles = [(ch, set(names(ch.orig[0].masked, lower_words=lw)), set(names(ch.rev[0].masked, lower_words=lw)))
               for ch in chunks if len(ch.orig) == 1 and len(ch.rev) == 1]
    result: list[Risk] = []
    for ch, no, nr in singles:
        moved: list[str] = []
        target = 0
        for name in sorted(no - nr):
            for ch2, no2, nr2 in singles:
                if ch2 is not ch and name in nr2 and name not in no2:
                    moved.append(name)
                    target = ch2.rev_line
                    break
        if moved:
            result.append(Risk("name_order", True, f'{", ".join(moved)} moved to another sentence (revised line '
                               f"{target}). Check who does what.", ch.orig_line, ch.rev_line, ch.show_orig(),
                               ch.show_rev()))
    return result


ITEM_LINE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")


def moved_names_in_lines(changes: list[dict[str, object]], lower_words: Optional[set[str]] = None) -> list[Risk]:
    """The same check on changed list items and table rows, for owners or assignees swapped between items.
    Only item lines count: re-wrapping a paragraph moves names between lines without moving them between items."""
    lw = lower_words if lower_words is not None else set()
    pairs: list[tuple[int, int, str, str]] = []
    for c in changes:
        old = str(c["original"]).split("\n") if c["original"] else []
        new = str(c["revised"]).split("\n") if c["revised"] else []
        if len(old) == len(new):
            for k, (a, b) in enumerate(zip(old, new)):
                if ITEM_LINE.match(a) and ITEM_LINE.match(b):
                    pairs.append((int(str(c["orig_line"])) + k, int(str(c["rev_line"])) + k, a, b))
    info = [(ol, rl, a, b, _item_names(a, lw), _item_names(b, lw)) for ol, rl, a, b in pairs]
    result: list[Risk] = []
    for ol, rl, a, b, no, nr in info:
        moved: list[str] = []
        target = 0
        for name in sorted(no - nr):
            for _ol2, rl2, _a2, _b2, no2, nr2 in info:
                if rl2 != rl and name in nr2 and name not in no2:
                    moved.append(name)
                    target = rl2
                    break
        if moved:
            result.append(Risk("name_order", True, f'{", ".join(moved)} moved to another line (revised line {target}). '
                               "Check who does what.", ol, rl, a.strip(), b.strip()))
    return result


def _strip_item(line: str) -> str:
    return re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\|\s*)(?:\[[ xX]\]\s+)?", "", line)


def _item_names(line: str, lower_words: set[str]) -> set[str]:
    """Names in a list item or table row, including a leading owner ("- [ ] Priya: Draft ...", "| Priya | ...")."""
    text = _strip_item(tx.mask(line))
    found = set(names(text, lower_words=lower_words))
    cells = [c for c in text.split("|")] if line.lstrip().startswith("|") else [text]
    for cell in cells:
        m = re.match(r"\s*[*_]*([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+)?)[*_]*\s*(?::|$)", cell)
        if m:
            for word in m.group(1).split():
                if word not in NAME_STOP and not (_word_forms(word) & lower_words):
                    found.add(word)
    return found


def added_actors(orig: tx.Document, rev: tx.Document, materials: str, chunks: list[Chunk]) -> list[Review]:
    o_all = " ".join(s.masked for s in orig.sentences) + "\n" + materials
    o_low = o_all.lower()
    o_names = set(names(o_all)) | {w for w in re.findall(r"\b[A-Z][A-Za-z0-9'-]+\b", materials)}
    o_names |= set(re.findall(r"\b[A-Z][A-Za-z0-9'-]+\b", o_all))
    lower_words = lower_word_set(o_all, " ".join(s.masked for s in rev.sentences))
    result: list[Review] = []
    seen: set[str] = set()
    for ch in chunks:
        for s in ch.rev:
            hits = _list_hits("roles", REQUEST.sub(" ", s.masked))
            if re.search(r"(?<![\w.])I(?![\w.])", s.masked) and not re.search(r"(?<![\w.])I(?![\w.])", o_all):
                hits.append("I")
            for role in hits:
                if role in seen:
                    continue
                if role != "I":
                    low = role.lower()
                    stem = low[:-1] if low.endswith("s") and len(low) > 3 else low
                    plural = "s?" if len(stem) > 3 else ""
                    if re.search(r"(?<![\w-])" + re.escape(stem) + plural + r"(?![\w-])", o_low):
                        continue
                seen.add(role)
                result.append(Review("actor_added", f'"{role}" is not in the original or material. Check that the '
                                     "rewrite did not create an actor, owner or recipient.", s.line, s.text))
            for name in names(s.masked, lower_words=lower_words):
                if name in seen or name in o_names or name.lower() in o_low or _word_forms(name) & lower_words:
                    continue
                seen.add(name)
                result.append(Review("actor_added", f'Name "{name}" is not in the original or material. Check that '
                                     "the rewrite did not add a person, team or product.", s.line, s.text))
    return result


def disappeared_words(orig: tx.Document, rev: tx.Document) -> list[str]:
    o = " ".join(s.masked for s in orig.sentences)
    r = " ".join(s.masked for s in rev.sentences)
    rev_stems = {_stem(w) for w in content_words(r)}
    lost = sorted(w for w in content_words(o) if _stem(w) not in rev_stems)
    return lost


def _similar(a: str, b: str) -> float:
    sm = difflib.SequenceMatcher(None, _norm(a), _norm(b))
    if sm.real_quick_ratio() < 0.5 or sm.quick_ratio() < 0.5:
        return 0.0
    return sm.ratio()


def _trailing_closing(headings: list[str]) -> list[str]:
    """Closing-section headings ("Conclusion", "Final thoughts") at the end of the heading list."""
    found: list[str] = []
    for h in reversed(headings):
        if not CLOSING_HEADING.search(h):
            break
        found.append(h.strip())
    return found


def stiffness(orig: tx.Document, rev: tx.Document, chunks: Optional[list[Chunk]] = None) -> list[str]:
    o = " ".join(s.masked for s in orig.sentences)
    r = " ".join(s.masked for s in rev.sentences)
    items: list[str] = []
    # contractions are counted only in sentences that were kept or rewritten, not in deleted or added ones
    deleted = {id(x) for ch in chunks or [] if not ch.rev for x in ch.orig}
    added = {id(x) for ch in chunks or [] if not ch.orig for x in ch.rev}
    for ch in chunks or []:
        if ch.orig and ch.rev and len(ch.orig) != len(ch.rev) and len(ch.orig) * len(ch.rev) <= 400:
            for x in ch.orig:
                if all(_similar(x.text, y.text) < 0.5 for y in ch.rev):
                    deleted.add(id(x))
            for y in ch.rev:
                if all(_similar(x.text, y.text) < 0.5 for x in ch.orig):
                    added.add(id(y))
    o_kept = " ".join(s.masked for s in orig.sentences if id(s) not in deleted)
    r_kept = " ".join(s.masked for s in rev.sentences if id(s) not in added)
    ai_forms = re.compile(r"\b\w+n['’]t\s+(?:just|only|merely|simply)\b|[;,—–]\s*(?:it|that|they)['’](?:s|re)\b"
                          r"|\bit['’]s\s+(?:worth\s+noting|important\s+to\s+note)\b|\bhere['’]s\b|\blet['’]s\s+(?:dive|explore|take)\b",
                          re.IGNORECASE)
    o_kept, r_kept = ai_forms.sub(" ", o_kept), ai_forms.sub(" ", r_kept)
    co, cr = len(CONTRACTION.findall(o_kept)), len(CONTRACTION.findall(r_kept))
    if co >= 2 and cr < co / 2:
        items.append(f"Contractions dropped from {co} to {cr}. Check that the rewrite did not make the register stiffer.")
    stiff_o = _list_hits("stiff-words", o)
    for word in _list_hits("stiff-words", r):
        if word not in stiff_o:
            items.append(f'Stiff word added: "{word}". Use the plain word unless the original register needs it.')
    return items


def energy(orig: tx.Document, rev: tx.Document, doc_type: Optional[str],
           chunks: Optional[list[Chunk]] = None) -> tuple[list[str], list[str]]:
    """Return (items, reference_only_items). Exclamation marks in deleted or added sentences are not counted."""
    skip = {id(x) for ch in chunks or [] if not ch.rev for x in ch.orig} | \
        {id(x) for ch in chunks or [] if not ch.orig for x in ch.rev}

    def stats(doc: tx.Document) -> tuple[int, int, int]:
        excl = sum(1 for s in doc.sentences if id(s) not in skip and s.masked.rstrip().rstrip("\"'”’)*_").endswith("!"))
        emoji = sum(len(tx.emoji_in(ln.masked)) for ln in doc.lines if ln.kind in ("para", "list", "heading", "table"))
        heads = sum(1 for b in doc.blocks if b.kind == "heading")
        return excl, emoji, heads
    eo, mo, ho = stats(orig)
    er, mr, hr = stats(rev)
    if doc_type not in ("pr", "minutes"):
        # removing a repeat-only closing section at the end is reported elsewhere
        ho -= len(_trailing_closing([b.lines[0].content for b in orig.blocks if b.kind == "heading"]))
        hr -= len(_trailing_closing([b.lines[0].content for b in rev.blocks if b.kind == "heading"]))
    items: list[str] = []
    reference: list[str] = []
    if er < eo:
        items.append(f"Exclamation marks dropped from {eo} to {er}. Check that the writer's energy was not lost.")
    if mr < mo:
        msg = f"Emoji dropped from {mo} to {mr}. Check that the writer's energy was not lost."
        if doc_type and doc_type not in ("promo", "mail"):
            reference.append(msg)
        else:
            items.append(msg)
    if hr < ho:
        msg = f"Headings dropped from {ho} to {hr}. Keep the number and order of headings."
        if doc_type and doc_type not in ("promo", "minutes", "mail"):
            reference.append(msg)
        else:
            items.append(msg)
    return items, reference


_GAP_EXCLUDE = re.compile(r"\d|\b(?:may|might|could|possibly|perhaps|likely|probably|appears?|seems?|plan(?:s|ned)?|"
                          r"expect\w*|if|when|unless|hope|aim\w*|goal|target)\b", re.IGNORECASE)
_BUILTIN_GAPS = [
    ("figure", r"\b(?:lay(?:s|ing)?|laid) the (?:foundation|groundwork)\b|\bpav(?:e|es|ed|ing) the way\b|\bquietly (?:break|breaks|broke|broken|breaking)\b"),
    ("effect", r"\b(?:improv|enhanc|boost|increas)\w* (?:the )?(?:reliability|stability|quality|performance|usability|productivity|efficiency)\b|\bseamless(?:ly)?\b"),
    ("degree", r"\b(?:significantly|dramatically|drastically|substantially|vastly|greatly)\b"),
    ("change", r"\b(?:shortened|sped up|reduced|increased|decreased|lowered|raised(?!\s+(?:a|an|the)?\s*(?:concerns?|questions?|issues?|points?)\b))\b"),
]


def load_gap_rules() -> tuple[list[tuple[str, re.Pattern[str]]], str]:
    path = tx.LISTS_DIR / "fact-gaps.txt"
    rules: list[tuple[str, re.Pattern[str]]] = []
    try:
        content = path.read_text(encoding="utf-8-sig")
        for number, raw in enumerate(content.splitlines(), 1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            kind, sep, pattern = raw.partition("\t")
            if not sep or kind not in ("figure", "effect", "degree", "change"):
                raise ValueError(f"line {number}: write kind<TAB>regex with kind figure, effect, degree or change")
            rules.append((kind, re.compile(pattern, re.IGNORECASE)))
        if not rules:
            raise ValueError("no rules")
        return rules, ""
    except (OSError, ValueError, re.error) as exc:
        return ([(k, re.compile(p, re.IGNORECASE)) for k, p in _BUILTIN_GAPS],
                f"Could not read references/lists/fact-gaps.txt ({exc}); used the built-in list.")


GAP_HINTS = {
    "figure": "a metaphor may hide the content; what actually happens?",
    "effect": "only an effect is stated; what changed?",
    "degree": "only a degree word; by how much?",
    "change": "a change without before and after values",
}


def fact_gaps(doc: tx.Document) -> tuple[list[Review], str]:
    rules, note = load_gap_rules()
    result: list[Review] = []
    for s in doc.sentences:
        if s.kind not in ("para", "list"):
            continue
        text = s.masked
        if text.rstrip().endswith("?") or _GAP_EXCLUDE.search(text) or VAGUE_QUANTITY.search(text) or \
                CLOSING_RESOLUTION.search(text):
            continue
        for kind, pattern in rules:
            m = pattern.search(text)
            if m:
                result.append(Review(kind, f'"{m.group(0)}": {GAP_HINTS[kind]}', s.line, s.text))
                break
    return result, note


def material_check(final: tx.Document, materials: str, original: str) -> dict[str, Any]:
    """Compare the final draft with the material (and original): numbers and names not found there."""
    materials = re.sub(r"(?m)^(\s*)(?:\d+[.)]|[-*+])\s+", r"\1", materials)  # list markers are not values
    source = materials + "\n" + original
    src_numbers = numbers(source)
    src_low = source.lower()
    missing_numbers: list[dict[str, object]] = []
    matched: list[dict[str, object]] = []
    src_lines = [ln for ln in materials.split("\n") if ln.strip()] + \
        ["(original) " + ln for ln in original.split("\n") if ln.strip()]
    src_units = unit_pairs(source)
    src_dates = dates(source)
    orig_sentences = {_norm(x.text) for x in tx.parse(original).sentences} if original.strip() else set()
    missing_units: list[dict[str, object]] = []
    line_numbers = [(ln, numbers(ln)) for ln in src_lines]
    for s in final.sentences:
        unchanged = _norm(s.text) in orig_sentences
        for n in numbers(s.masked):
            if not src_numbers.get(n):
                missing_numbers.append({"value": n, "line": s.line, "text": s.text})
            elif not unchanged:
                hit = next((ln for ln, nums in line_numbers if n in nums), "")
                matched.append({"value": n, "line": s.line, "material_line": hit.strip()[:160]})
        if unchanged:
            continue
        for pair in unit_pairs(s.masked):
            if not pair.endswith("(no unit)") and not src_units.get(pair) and src_numbers.get(pair.split(" ")[0]):
                missing_units.append({"value": pair, "line": s.line, "text": s.text})
        for word in dates(s.masked):
            if not src_dates.get(word):
                missing_units.append({"value": word, "line": s.line, "text": s.text})
    missing_names: list[dict[str, object]] = []
    seen: set[str] = set()
    lower_words = lower_word_set(source, " ".join(s.masked for s in final.sentences))
    for s in final.sentences:
        for name in names(s.masked, lower_words=lower_words):
            if name.lower() in src_low or name in seen or _word_forms(name) & lower_words:
                continue
            seen.add(name)
            missing_names.append({"value": name, "line": s.line, "text": s.text})
    hedges_lost: list[str] = []
    final_low = " ".join(s.masked for s in final.sentences).lower()
    for pattern in (STATUS, HEARSAY):
        for m in pattern.finditer(materials):
            w = m.group(0).lower()
            if w not in final_low and w not in hedges_lost:
                hedges_lost.append(w)
    for _level, pattern in CERTAINTY:
        for m in pattern.finditer(mask_month_may(materials)):
            w = m.group(0).lower()
            if w not in final_low and w not in hedges_lost:
                hedges_lost.append(w)
    return {"numbers_not_in_material": missing_numbers, "names_not_in_material": missing_names,
            "units_dates_not_in_material": missing_units,
            "matched_numbers": matched, "material_hedges_not_in_final": hedges_lost}


# ---------------------------------------------------------------- full diff


def word_diff(a: str, b: str) -> str:
    ta = re.findall(r"\s+|[\w'’]+|[^\w\s]", a)
    tb = re.findall(r"\s+|[\w'’]+|[^\w\s]", b)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=len(ta) * len(tb) > 250000).get_opcodes():
        if tag == "equal":
            out.append("".join(ta[i1:i2]))
            continue
        if i2 > i1:
            out.append("[-" + "".join(ta[i1:i2]) + "-]")
        if j2 > j1:
            out.append("{+" + "".join(tb[j1:j2]) + "+}")
    return "".join(out)


def _segment(old_idx: list[int], new_idx: list[int], ai: list[int], bi: list[int], k: int, l_: int
             ) -> tuple[int, int, int, int]:
    """Line range (i1, i2, j1, j2) for some non-blank lines; an empty side sits after the previous non-blank line."""
    if old_idx:
        i1, i2 = old_idx[0], old_idx[-1] + 1
    else:
        i1 = i2 = (ai[k - 1] + 1) if k > 0 else 0
    if new_idx:
        j1, j2 = new_idx[0], new_idx[-1] + 1
    else:
        j1 = j2 = (bi[l_ - 1] + 1) if l_ > 0 else 0
    return i1, i2, j1, j2


def _pair_lines(a: list[str], b: list[str], oi: list[int], nj: list[int]) -> list[tuple[int, int, int, int]]:
    """Split a replace block of non-blank lines into segments, pairing similar lines in order (best total similarity).

    Deleting one paragraph then shows as a deletion instead of shifting every later pairing by one."""
    whole = (oi[0], oi[-1] + 1, nj[0], nj[-1] + 1)
    if len(oi) <= 1 or len(nj) <= 1 or len(oi) * len(nj) > 10000:  # merges and splits stay one change
        return [whole]
    n, m = len(oi), len(nj)
    sim = [[0.0] * m for _ in range(n)]
    for x in range(n):
        for y in range(m):
            sm = difflib.SequenceMatcher(None, a[oi[x]], b[nj[y]])
            if sm.real_quick_ratio() >= 0.5 and sm.quick_ratio() >= 0.5:
                r = sm.ratio()
                sim[x][y] = r if r >= 0.5 else 0.0
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for x in range(n - 1, -1, -1):
        for y in range(m - 1, -1, -1):
            best = max(score[x + 1][y], score[x][y + 1])
            if sim[x][y]:
                best = max(best, sim[x][y] + score[x + 1][y + 1])
            score[x][y] = best
    pairs: list[tuple[int, int]] = []
    x = y = 0
    while x < n and y < m:
        if sim[x][y] and score[x][y] == sim[x][y] + score[x + 1][y + 1]:
            pairs.append((oi[x], nj[y]))
            x, y = x + 1, y + 1
        elif score[x + 1][y] >= score[x][y + 1]:
            x += 1
        else:
            y += 1
    if not pairs:
        return [whole]
    segments: list[tuple[int, int, int, int]] = []
    px, py = 0, 0  # positions in oi / nj
    for i, j in pairs:
        x, y = oi.index(i), nj.index(j)
        if px < x or py < y:
            old_part, new_part = oi[px:x], nj[py:y]
            i1 = old_part[0] if old_part else (oi[px - 1] + 1 if px else oi[0])
            i2 = old_part[-1] + 1 if old_part else i1
            j1 = new_part[0] if new_part else (nj[py - 1] + 1 if py else nj[0])
            j2 = new_part[-1] + 1 if new_part else j1
            segments.append((i1, i2, j1, j2))
        segments.append((i, i + 1, j, j + 1))
        px, py = x + 1, y + 1
    if px < len(oi) or py < len(nj):
        old_part, new_part = oi[px:], nj[py:]
        i1 = old_part[0] if old_part else oi[px - 1] + 1
        i2 = old_part[-1] + 1 if old_part else i1
        j1 = new_part[0] if new_part else nj[py - 1] + 1
        j2 = new_part[-1] + 1 if new_part else j1
        segments.append((i1, i2, j1, j2))
    return segments


def line_changes(a_text: str, b_text: str) -> tuple[list[dict[str, object]], str]:
    a = a_text.split("\n")
    b = b_text.split("\n")
    if a and a[-1] == "":
        a.pop()
    if b and b[-1] == "":
        b.pop()
    changes: list[dict[str, object]] = []
    out: list[str] = []
    # Match non-blank lines only: blank lines between paragraphs would otherwise anchor every paragraph to the one
    # at the same position, so deleting one paragraph would pair each later paragraph with its neighbor.
    ai = [i for i, x in enumerate(a) if x.strip()]
    bi = [j for j, x in enumerate(b) if x.strip()]
    segments: list[tuple[int, int, int, int]] = []
    for tag, k1, k2, l1, l2 in difflib.SequenceMatcher(None, [a[i] for i in ai], [b[j] for j in bi],
                                                       autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        old_idx, new_idx = ai[k1:k2], bi[l1:l2]
        if tag == "replace":
            segments.extend(_pair_lines(a, b, old_idx, new_idx))
        else:
            segments.append(_segment(old_idx, new_idx, ai, bi, k1, l1))
    for i1, i2, j1, j2 in segments:
        old, new = a[i1:i2], b[j1:j2]
        if all(not x.strip() for x in old) and all(not x.strip() for x in new):
            continue
        changes.append({"orig_line": i1 + 1 if old else i1, "rev_line": j1 + 1 if new else j1,
                        "original": "\n".join(old), "revised": "\n".join(new)})
        head = f"@ original line {i1 + 1 if old else i1} → revised line {j1 + 1 if new else j1}"
        if len(old) != len(new):
            head += f" ({tx.plural(len(old), 'line')} → {tx.plural(len(new), 'line')})"
        out.append(head)
        for x in old:
            out.append(f"  - {x}")
        for x in new:
            out.append(f"  + {x}")
        if len(old) == 1 and len(new) == 1:
            out.append(f"  ~ {word_diff(old[0], new[0])}")
    return changes, "\n".join(out)


# ---------------------------------------------------------------- main compare


def compare(orig_text: str, rev_text: str, doc_type: Optional[str] = None, reader: Optional[str] = None,
            stance: Optional[str] = None, materials: str = "", want_fact_gaps: bool = False,
            words: Optional[tx.Words] = None) -> DiffResult:
    orig = tx.parse(orig_text)
    rev = tx.parse(rev_text)
    chunks = attach_adjacent(pair_moved(align(orig, rev)), orig, rev)
    risks: list[Risk] = []
    reviews: list[Review] = []
    orig_all = " ".join(s.masked for s in orig.sentences)
    rev_all = " ".join(s.masked for s in rev.sentences)
    lower_words = lower_word_set(orig_all, rev_all, materials)
    proper = {n for x in orig.sentences + rev.sentences for n in names(x.masked)} | set(names(materials))
    for ch in chunks:
        compare_chunk(ch, doc_type, risks, reviews, orig_all, materials, proper, rev_all)
    risks.extend(moved_names(chunks, lower_words))
    risks[:] = _dedupe_risks(risks)

    # whole-text checks catch sentences that were deleted, added, split or moved
    o_nums, r_nums = numbers(orig_all), numbers(" ".join(s.masked for s in rev.sentences))
    reported_o: Counter[str] = Counter()
    reported_r: Counter[str] = Counter()
    for r in risks:
        if r.kind in ("number", "approximation"):
            reported_o.update(numbers(r.original))
            reported_r.update(numbers(r.revised))
    # sets, not counts: deleting a sentence that only repeats a number that stays elsewhere is not a change
    lost = sorted(n for n in set(o_nums) - set(r_nums) if not reported_o.get(n))
    gained = sorted(n for n in set(r_nums) - set(o_nums) if not reported_r.get(n))
    if lost or gained:
        risks.append(Risk("number", True, "Number missing from or added to the whole text: "
                          + ("removed " + ", ".join(sorted(lost)) if lost else "")
                          + ("; " if lost and gained else "") + ("added " + ", ".join(sorted(gained)) if gained else ""),
                          0, 0, "", ""))
    st_o_all = STATUS.findall(orig_all)
    st_r_all = STATUS.findall(" ".join(s.masked for s in rev.sentences))
    gone = sorted({m.lower() for m in st_o_all} - {m.lower() for m in st_r_all})
    if gone and len(st_r_all) < len(st_o_all) and not any(r.kind == "status" for r in risks):
        risks.append(Risk("status", True, f'Status word missing from the whole text: "{gone[0]}"', 0, 0, "", ""))
    for ch in chunks:
        if ch.orig and not ch.rev:
            text = ch.show_orig()
            if NEGATION.search(ch.orig_text) or CERTAINTY[0][1].search(ch.orig_text) or OBLIGATION_STRONG.search(ch.orig_text):
                reviews.append(Review("deleted", "Deleted sentence held a negation, hedge or obligation. Check that "
                                      "nothing appears only here, and that its content does not come back elsewhere "
                                      f"with a different negation or hedge. (original line {ch.orig_line})", 0, text))

    po, pr_ = protected_items(orig), protected_items(rev)
    for item in sorted((po - pr_).elements()):
        risks.append(Risk("protected", False, "Text that must not change is gone or changed: " + tx.display_width_cut(item, 120),
                          0, 0, item, ""))
    for item in sorted((pr_ - po).elements()):
        risks.append(Risk("protected", False, "New or changed text in code or URLs: " + tx.display_width_cut(item, 120),
                          0, 0, "", item))

    reviews.extend(added_actors(orig, rev, materials, chunks))
    lost_words = disappeared_words(orig, rev)
    if lost_words:
        shown = ", ".join(lost_words[:25]) + (f" (and {len(lost_words) - 25} more)" if len(lost_words) > 25 else "")
        reviews.append(Review("words_gone", f"Words that disappeared: {shown}", 0, ""))

    oh = [b.lines[0].content.strip() for b in orig.blocks if b.kind == "heading"]
    rh = [b.lines[0].content.strip() for b in rev.blocks if b.kind == "heading"]
    removed_h = list((Counter(oh) - Counter(rh)).elements())
    trailing = set(_trailing_closing(oh)) if doc_type not in ("pr", "minutes") else set()
    if len(oh) > len(rh) and len(removed_h) == len(oh) - len(rh) and all(h in trailing for h in removed_h):
        reviews.append(Review("heading", f'Closing section removed: "{removed_h[0]}". Fine only when the section '
                              "repeated the body and held no number, condition or next step found nowhere else.", 0, ""))
    elif len(oh) == len(rh):
        for a, b in zip(oh, rh):
            if a != b:
                reviews.append(Review("heading", f'Heading changed: "{a}" → "{b}". Check that warnings, conditions '
                                      "and the section's role were kept.", 0, b))
    elif oh != rh:
        reviews.append(Review("heading", f"Number of headings changed: {len(oh)} → {len(rh)}. Keep the number and "
                              "order of headings.", 0, ""))

    if stance:
        for ch in chunks:
            for s in ch.rev:
                t = s.masked
                if stance == "rule" and LETS.search(t):
                    reviews.append(Review("stance", 'Rule document: "let\'s" in a rewritten sentence. State the rule '
                                          "(\"Always ...\", \"We ...\").", s.line, s.text))
                elif stance == "explain" and FUTURE.search(t) and not FUTURE.search(ch.orig_text):
                    reviews.append(Review("stance", 'Explanation or report: "will" added. Do not turn finished '
                                          "changes or current behavior into plans.", s.line, s.text))
                elif stance == "recommend" and OBLIGATION_STRONG.search(t) and not OBLIGATION_STRONG.search(ch.orig_text):
                    reviews.append(Review("stance", "Recommendation: an obligation word was added. Do not turn advice "
                                          "into obligation.", s.line, s.text))

    stiff = stiffness(orig, rev, chunks)
    en_items, en_ref = energy(orig, rev, doc_type, chunks)
    gaps: list[Review] = []
    gaps_note = ""
    if want_fact_gaps and doc_type not in ("essay", "promo"):
        gaps, gaps_note = fact_gaps(rev)
    material: dict[str, Any] = {}
    if materials.strip():
        material = material_check(rev, materials, orig_text)
    changes, full = line_changes(orig_text, rev_text)
    reported = {r.message.split(" moved")[0] for r in risks if r.kind == "name_order"}
    risks.extend(r for r in moved_names_in_lines(changes, lower_words) if r.message.split(" moved")[0] not in reported)
    return DiffResult(changes, risks, reviews, stiff, doc_type in STIFF_REFERENCE_TYPES, en_items, en_ref,
                      gaps, gaps_note, material, full, doc_type, reader, stance, "rewrite", words or tx.Words(),
                      want_fact_gaps and doc_type not in ("essay", "promo"))


def compose(final_text: str, materials: str, doc_type: Optional[str] = None, reader: Optional[str] = None,
            stance: Optional[str] = None, want_fact_gaps: bool = False,
            words: Optional[tx.Words] = None) -> DiffResult:
    final = tx.parse(final_text)
    material = material_check(final, materials, "")
    risks = [Risk("material_number", True, f'Number {item["value"]} is not in the material', 0, int(str(item["line"])),
                  "", str(item["text"])) for item in material["numbers_not_in_material"]]
    risks += [Risk("material_number", True, f'{item["value"]} is not in the material (unit, month or weekday)', 0,
                   int(str(item["line"])), "", str(item["text"])) for item in material["units_dates_not_in_material"]]
    gaps: list[Review] = []
    note = ""
    if want_fact_gaps and doc_type not in ("essay", "promo"):
        gaps, note = fact_gaps(final)
    return DiffResult([], risks, [], [], False, [], [], gaps, note, material, "", doc_type, reader, stance,
                      "compose", words or tx.Words(), want_fact_gaps and doc_type not in ("essay", "promo"))


# ---------------------------------------------------------------- output


def check_line(items: list[str], reference: list[str], reference_only: bool) -> str:
    if reference_only:
        n = len(items) + len(reference)
        return f"reference {n}" if n else "none"
    parts = []
    if items:
        parts.append(f"candidates {len(items)}")
    if reference:
        parts.append(f"reference {len(reference)}")
    return ", ".join(parts) if parts else "none"


def stiffness_line(result: DiffResult) -> str:
    return check_line(result.stiffness, [], result.stiffness_reference)


def energy_line(result: DiffResult) -> str:
    return check_line(result.energy, result.energy_reference_items, result.doc_type in ENERGY_REFERENCE_TYPES)


def _excerpts(a: str, b: str, width: int = 120) -> tuple[str, str]:
    """Cut both sides to about `width` characters, starting shortly before the first difference."""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    start = i - 40 if i > 60 else 0
    while start > 0 and not a[start - 1].isspace():
        start -= 1
    lead = "…" if start else ""
    return (tx.display_width_cut(lead + a[start:].strip(), width) if a else "",
            tx.display_width_cut(lead + b[start:].strip(), width) if b else "")


def format_sections(result: DiffResult) -> list[str]:
    out: list[str] = []
    if result.mode == "rewrite":
        out.append(f"== Changed places ({len(result.changes)}) ==")
        if not result.changes:
            out.append("- None")
        for c in result.changes[:10]:
            n_old = len(str(c["original"]).split("\n")) if c["original"] else 0
            n_new = len(str(c["revised"]).split("\n")) if c["revised"] else 0
            extra = f" ({tx.plural(n_old, 'line')} → {tx.plural(n_new, 'line')})" if n_old != n_new else ""
            out.append(f"@ original line {c['orig_line']} → revised line {c['rev_line']}{extra}")
            a, b = _excerpts(str(c["original"]).replace("\n", " / "), str(c["revised"]).replace("\n", " / "))
            out.append(f"  original: {a}")
            out.append(f"  revised:  {b}")
        if len(result.changes) > 10:
            out.append(f"- {len(result.changes) - 10} more places: see == Full diff ==")
        out.append("")
    counted = [r for r in result.risks if r.counted]
    other = [r for r in result.risks if not r.counted]
    out.append(f"== Meaning risks ({len(counted)} counted, {len(other)} not counted; check against the original and material) ==")
    if not result.risks:
        out.append("- None found. This does not prove the meaning is the same.")
    for r in counted + other:
        if r.orig_line:
            where = f" (original line {r.orig_line} → revised line {r.rev_line})"
        elif r.rev_line:
            where = f" (revised line {r.rev_line})"
        else:
            where = ""
        mark = "" if r.counted else " [not counted]"
        out.append(f"- [{r.kind}]{mark} {r.message}{where}")
        if r.original:
            out.append(f"  original: {tx.display_width_cut(r.original, 160)}")
        if r.revised:
            out.append(f"  revised:  {tx.display_width_cut(r.revised, 160)}")
    out.append("")
    if result.mode == "rewrite":
        out.append(f"== Review findings from the diff ({len(result.reviews)}) ==")
        if not result.reviews:
            out.append("- None")
        for v in result.reviews:
            where = f" (revised line {v.line})" if v.line else ""
            out.append(f"- [{v.kind}] {v.message}{where}")
            if v.text and v.kind != "words_gone":
                out.append(f"  > {tx.display_width_cut(v.text, 160)}")
        out.append("")
        out.append(f"== Stiffness ({stiffness_line(result)}) ==")
        for item in result.stiffness or ["None"]:
            out.append(f"- {item}")
        out.append("")
        out.append(f"== Energy ({energy_line(result)}) ==")
        for item in result.energy or ([] if result.energy_reference_items else ["None"]):
            out.append(f"- {item}")
        for item in result.energy_reference_items:
            out.append(f"- (reference) {item}")
        out.append("")
    if result.material:
        m = result.material
        out.append("== Material match ==")
        nums = m["numbers_not_in_material"]
        names_ = m["names_not_in_material"]
        out.append(f"- Not in the material (numbers): {len(nums)}")
        for item in nums:
            out.append(f"  line {item['line']}: {item['value']}  > {tx.display_width_cut(str(item['text']), 120)}")
        out.append(f"- Not in the material (names): {len(names_)}")
        for item in names_:
            out.append(f"  line {item['line']}: {item['value']}")
        units = m.get("units_dates_not_in_material", [])
        out.append(f"- Number found, but its unit, month or weekday is not in the material: {len(units)}")
        for item in units:
            out.append(f"  line {item['line']}: {item['value']}  > {tx.display_width_cut(str(item['text']), 120)}")
        matched = m["matched_numbers"]
        if matched:
            out.append("- Values on changed lines that match a material line, or an original line marked (original) "
                       "(shows only that the line has the same value):")
            for item in matched[:15]:
                out.append(f"  line {item['line']}: {item['value']}  ← {item['material_line']}")
            if len(matched) > 15:
                out.append(f"  ({len(matched) - 15} more; see --json)")
        lost = m["material_hedges_not_in_final"]
        if lost:
            out.append("- Hedge or status words in the material that the final draft lacks: " + ", ".join(lost))
        out.append("")
    if result.fact_gaps or result.fact_gaps_note or result.fact_gaps_checked:
        out.append(f"== Fact gaps ({len(result.fact_gaps)}; partial list, not counted) ==")
        if not result.fact_gaps and not result.fact_gaps_note:
            out.append("- None found (the list is partial)")
        for g in result.fact_gaps:
            out.append(f"- line {g.line} [{g.kind}] {g.message}")
            out.append(f"  > {tx.display_width_cut(g.text, 160)}")
        if result.fact_gaps_note:
            out.append(f"- {result.fact_gaps_note}")
        out.append("")
    if result.mode == "rewrite":
        out.append(f"== Full diff ({len(result.changes)} places; not shortened) ==")
        out.append(result.full_diff or "- No changes")
    return out


def format_text(result: DiffResult) -> str:
    counted = result.counted
    head = ["Compared the original and the revised text." if result.mode == "rewrite"
            else "Compared the final draft with the material (compose mode).",
            f"Changed places: {len(result.changes)}. Meaning risks counted: {counted}. "
            f"Review findings: {len(result.reviews)}.",
            "A full diff does not prove that the meaning is the same.",
            f"Stiffness check: {stiffness_line(result)}",
            f"Energy check: {energy_line(result)}"]
    if result.doc_type or result.reader or result.stance:
        head.append("Doc type: " + (result.doc_type or "not given") + "; reader: " + (result.reader or "not given")
                    + "; stance: " + (result.stance or "not given"))
    return "\n".join(head + [""] + format_sections(result)) + "\n"


def to_json(result: DiffResult) -> dict[str, object]:
    return {
        "format": JSON_FORMAT, "tool": TOOL, "version": __version__, "mode": result.mode,
        "doc_type": result.doc_type, "reader": result.reader, "stance": result.stance,
        "changes": result.changes,
        "meaning_risk_count": result.counted,
        "meaning_risks": [asdict(r) for r in result.risks],
        "review": [asdict(v) for v in result.reviews],
        "stiffness": {"line": stiffness_line(result), "items": result.stiffness, "reference_only": result.stiffness_reference},
        "energy": {"line": energy_line(result), "items": result.energy, "reference": result.energy_reference_items},
        "fact_gaps": [asdict(g) for g in result.fact_gaps], "fact_gaps_note": result.fact_gaps_note,
        "fact_gaps_checked": result.fact_gaps_checked,
        "material": result.material,
        "full_diff": result.full_diff,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.exit(2)


def read_materials(names_: Optional[list[str]]) -> str:
    parts: list[str] = []
    for name in names_ or []:
        parts.append(tx.read_text(name))
    return "\n".join(parts)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="readyasu_diff.py",
                description="Compare an original and a revised text, show every change, and list meaning risks and "
                            "review findings. A full diff does not prove that the meaning is the same; this tool does "
                            "not decide that.",
                epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+", metavar="FILE",
                   help="original and revised text (UTF-8; one of them may be - for standard input); "
                        "with --compose, only the final draft")
    p.add_argument("--compose", action="store_true",
                   help="compose mode: compare one final draft with the --material files only")
    p.add_argument("--material", action="append", metavar="FILE", help="material file; repeatable")
    p.add_argument("--stance", choices=tx.STANCES, help="stance: recommend, rule or explain")
    p.add_argument("--doc-type", choices=tx.DOC_TYPES, metavar="TYPE", help="document type: " + ", ".join(tx.DOC_TYPES))
    p.add_argument("--reader", choices=tx.READERS, metavar="READER", help="expected reader (recorded only)")
    p.add_argument("--fact-gaps", action="store_true", help="list some fact-gap candidates in the revised text")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.add_argument("--fail-on", action="append", metavar="meaning-risk", help="exit 1 if a counted meaning risk exists")
    p.add_argument("--words", metavar="DIR", help="project word-list folder (recorded; used by lint)")
    p.add_argument("--no-words", action="store_true", help="do not look for a project word list")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    tx.configure_stdout()
    args = build_parser().parse_args(argv)
    try:
        fail = False
        for value in args.fail_on or []:
            for part in value.split(","):
                if part.strip() and part.strip() != "meaning-risk":
                    raise tx.InputError(f"--fail-on accepts meaning-risk (got {part.strip()}).")
                fail = fail or part.strip() == "meaning-risk"
        if args.compose:
            if len(args.files) != 1 or not args.material:
                raise tx.InputError("--compose takes one final draft and at least one --material.")
        elif len(args.files) != 2:
            raise tx.InputError("Give two files: the original and the revised text.")
        if args.files.count("-") > 1:
            raise tx.InputError("Only one of the files can be standard input.")
        words = tx.load_words(args.words, args.no_words)
        texts = [tx.read_text(name) for name in args.files]
        materials = read_materials(args.material)
    except tx.InputError as exc:
        sys.stderr.write(f"readyasu_diff.py: {exc}\n")
        return 2
    if args.compose:
        result = compose(texts[0], materials, args.doc_type, args.reader, args.stance, args.fact_gaps, words)
    else:
        result = compare(texts[0], texts[1], args.doc_type, args.reader, args.stance, materials, args.fact_gaps,
                         words)
    if args.json:
        sys.stdout.write(json.dumps(to_json(result), ensure_ascii=True, indent=1) + "\n")
    else:
        sys.stdout.write(format_text(result))
    return 1 if fail and result.counted else 0


if __name__ == "__main__":
    sys.exit(main())
