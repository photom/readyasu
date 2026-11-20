# Changelog

## 0.2.0

Fixes from fourteen review rounds, and a fixed measurement in place of open-ended review. The plan's exit conditions were not all met (see below), so this release ships the last commit that passed the merge gate (52804a4) as is; only the version number changed.

- Review rounds 1 to 14: fixes in lint (Markdown parsing, sentence splitting, chat residue and assistant preambles, negative contrast, personification, dashes, emoji and bold rules), diff (numbers, units, dates and frequencies, negation and denied sides, conditions, scope, names, moved and merged sentences), check (runs, attempts, sessions, records, verify), and in SKILL.md, the references and the docs.
- Renamed from yomiyasu-en to readyasu, because the old name looked like an official part of the yomiyasu series. The README and this changelog say that readyasu is an unofficial adaptation, maintained separately and not part of the yomiyasu project.
- Added UNICODE-LICENSE.txt, the Unicode copyright and permission notice for the emoji code point list in `readyasu_text.py`.
- Convergence work: a fixed evaluation set built from the review rounds (kept outside the repository, split into dev and held-out) replaced new review sets as the measure. Changes were merged only with no regression on dev. diff now reports fewer false positives on harmless rewrites, and the em_dash rule skips separators in titles, `Subject:` lines, table cells, owner and schedule entries, and speech that breaks off.
- docs/limitations.md: one to three sentences per item, with the detailed forms moved to "Lint detection details" in docs/tools.md; new sections "Measured quality" and "Known issues in 0.2.0". Statements about what diff reports were corrected: "we recommend", "30 full business days", "keep the one" → "keep the two", a dropped clause with a name, and a list count dropped while ordinal sentences stay are reported, although the docs said they were not; a weekday abbreviation before "(May 3)" or a numeric date in parentheses is not compared, although the docs said it was.

Measured on the fixed set (dev was used while fixing; held-out was measured once, at the end):

| Metric | Target | dev | held-out | held-out at v0.1.0 |
| --- | --- | --- | --- | --- |
| diff miss rate | 5% or less | 3.0% (44 / 1,480) | 5.9% (22 / 372) | 5.4% |
| diff false-positive rate | 5% or less | 3.5% (46 / 1,309) | 4.3% (14 / 326) | 6.1% |
| Human documents with a warn or error lint finding | 25% or less | 20.7% (41 / 198) | 28.6% (14 / 49) | 28.6% |
| AI documents caught (warn or error) | none | 95.5% (126 / 132) | 87.9% (29 / 33) | 87.9% |

Exit conditions not met: the held-out miss rate (5.9%) and the held-out share of human documents (28.6%) are above target; the last review round still had one high finding; and two held-out cases regressed. The remaining limits are in docs/limitations.md.

## 0.1.0

First version: the yomiyasu concept ported to English prose.

readyasu is an unofficial adaptation of [yomiyasu](https://github.com/nanaism/yomiyasu) by nanaism and is not part of the yomiyasu project.

- SKILL.md: meaning-first rules (claim, weight, strength, function), add nothing, stance and verb forms, actors and objects, paragraph logic, negative contrast, inflated nouns, metaphorical verbs and personification, punctuation and dashes, bold and labels, headings, decoration and ad copy, wordiness and stock vocabulary; a five-step procedure with lint, diff, one revision, and verify; the output format.
- references: slop catalog, rephrase test, fact check, document types and readers, register, review points, thirteen doc-type files, three domain files, and word lists.
- scripts: `readyasu_lint.py`, `readyasu_diff.py`, `readyasu_check.py` (`run`, `verify`), standard library only.
- Project word lists in `.readyasu-words/` (`allow.txt`, `flag.txt` with optional replacements, `flag-patterns.txt`).
- Tests and CI.

Not ported from yomiyasu: the optional Claude Code / Codex hook, the `start`, `export` and `end` subcommands of check, and the Japanese-specific rules (kanji and kana, commas after short topics, Sino-Japanese words, calques).
