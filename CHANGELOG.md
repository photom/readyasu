# Changelog

## 0.1.0

First version: the yomiyasu concept ported to English prose.

readyasu is an unofficial adaptation of [yomiyasu](https://github.com/nanaism/yomiyasu) by nanaism and is not part of the yomiyasu project.

- SKILL.md: meaning-first rules (claim, weight, strength, function), add nothing, stance and verb forms, actors and objects, paragraph logic, negative contrast, inflated nouns, metaphorical verbs and personification, punctuation and dashes, bold and labels, headings, decoration and ad copy, wordiness and stock vocabulary; a five-step procedure with lint, diff, one revision, and verify; the output format.
- references: slop catalog, rephrase test, fact check, document types and readers, register, review points, thirteen doc-type files, three domain files, and word lists.
- scripts: `readyasu_lint.py`, `readyasu_diff.py`, `readyasu_check.py` (`run`, `verify`), standard library only.
- Project word lists in `.readyasu-words/` (`allow.txt`, `flag.txt` with optional replacements, `flag-patterns.txt`).
- Tests and CI.

Not ported from yomiyasu: the optional Claude Code / Codex hook, the `start`, `export` and `end` subcommands of check, and the Japanese-specific rules (kanji and kana, commas after short topics, Sino-Japanese words, calques).
