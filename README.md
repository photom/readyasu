# readyasu

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

readyasu is an agent skill that revises AI-generated English prose so it reads like a careful person wrote it. It is an unofficial English adaptation of [yomiyasu](https://github.com/nanaism/yomiyasu), a skill for Japanese text by nanaism. readyasu is maintained separately by photom and is not affiliated with the yomiyasu project. The name puts the English "read" in place of "yomi" ("read" in Japanese) in yomiyasu.

It follows the same design as yomiyasu: keep the meaning first, add nothing, change only what a reader would stumble over, and run fixed-pattern checks on the final draft before returning it.

## What it does

readyasu finds and rewrites:

- stock AI vocabulary and phrases ("delve", "seamless", "a testament to", "In today's fast-paced world", "It's worth noting that"),
- metaphorical verbs for ordinary events ("unlock", "supercharge", "navigate the complexities of"),
- tools and ideas written as if they had feelings or a will ("the code tells a story"),
- negative contrast used for effect ("It's not a dashboard, it's a command center"), self-answered questions ("The result?") and ad-copy fragments,
- announcements and closings that only repeat ("Let's take a closer look", "In conclusion"),
- assistant chat left in a document ("I hope this helps!", "Certainly! Here's a revised version:"),
- decoration: bold labels with colons at the start of every list item, heavy bold, emoji, clause-splicing em dashes, colons at the end of headings.

It tries to leave parts that already read naturally as they are.

It keeps the meaning: numbers, negations, conditions, who does what, hedges and how strongly a claim is made (permission, ability, obligation, guarantees). Its instructions tell it not to add facts that are not in the original, the request, the material you provide, or what you said, opened or ran in the conversation (fills from the conversation are listed with their source), and to keep the original wording and ask the writer where the meaning cannot be decided from the text.

It knows thirteen document types (pull request descriptions, technical articles, incident reports, proposals, minutes, manuals, slides, essays and fiction, formal documents, marketing copy, mail and chat, papers, scripts) and is told not to change the usual style of each type. You can also tell it how much the readers know (expert, informed, general) and who writes to whom.

The package is a set of instructions (`SKILL.md` and `references/`) plus three Python scripts that check the final draft.

## Install

```bash
# skills CLI
npx skills add photom/readyasu

# GitHub CLI
gh skill install photom/readyasu readyasu
```

As a Claude Code plugin, run these two commands in Claude Code. The skill is then named `readyasu:readyasu`.

```text
/plugin marketplace add photom/readyasu
/plugin install readyasu@readyasu
```

To install by hand, copy the `skills/readyasu/` folder into the skills folder of your agent (for example `.claude/skills/readyasu/` for Claude Code, or `.agents/skills/readyasu/` for Codex).

Do not edit files inside the installed skill folder; updates may replace it. Put project words in `.readyasu-words/` and your own instructions in `CLAUDE.md` or `AGENTS.md`.

These install methods have not been tested yet; see [docs/limitations.md](./docs/limitations.md).

## Usage

Name the skill in the request and paste the draft.

```text
Revise this with readyasu.
(paste the text here)
```

Sending only `/readyasu` makes the skill revise the text the AI wrote in its previous answer, or the single draft (`.md` or `.txt`) directly under the working folder. When it works on a file, it does not overwrite the file; it saves the final draft in the same folder under a new name.

You can tell it the document type, the readers, and the relationship ("This is an email to a client"). With a relationship, it adjusts politeness the way a person in that relationship would write. If you say nothing, it infers the type from the text when it can and does not change the politeness.

After the revised text, it reports what it changed and the record of the checks it ran, and, when there is something to say, the AI-like wording it chose to keep and questions for the writer. Ask for "the text only" to get the revised text alone; the checks still run.

Agents use readyasu only when you ask for it: when the request names it, when you send `/readyasu`, or when you clearly ask for skill-based revision of English prose. To use it every time an agent writes English prose, add a line to your instruction file, for example in `CLAUDE.md` or `AGENTS.md`:

```text
When you write English prose for people to read (articles, PR descriptions, reports, mail), revise it with the readyasu skill before returning it.
```

See [docs/usage.md](./docs/usage.md) for more.

## Bundled scripts

The scripts need only the Python standard library and are written for Python 3.9 and later. On Windows, run them with `py -3` instead of `python3`.

- `scripts/readyasu_lint.py` lists expressions and Markdown formatting worth reviewing in one document: stock vocabulary and phrases, chat residue, wordy phrases, metaphorical verbs, intensifiers, jargon, stacked hedges, negative contrast, personification, self-answered questions, fragment runs, count announcements, closing summaries, emoji, clause-splicing dashes, bold labels, heavy bold, bold that will not render, and words from your project list.
- `scripts/readyasu_diff.py` compares the original and the revised text. It shows every change and lists changes that may alter the meaning: numbers and their units, months and weekdays, negations, hedges, permission and obligation words, status words such as "TBD", hearsay, questions and requests, limits such as "only", conditions such as "if" and "at launch", choice and quantifier scope, citations, names in a different order or moved to another line, and added commitments. It also lists added actors and feelings, causal links, words that disappeared, and changes in register and energy.
- `scripts/readyasu_check.py` runs lint on the final draft and diff on the original and the final draft, and keeps a record in `.readyasu/` at the top of the git repository (or in the working folder outside git). `verify` checks right before submitting that the final draft is the one that was checked.

```bash
python3 skills/readyasu/scripts/readyasu_lint.py article.md
python3 skills/readyasu/scripts/readyasu_diff.py original.md revised.md
python3 skills/readyasu/scripts/readyasu_check.py run --source original.md --final final.md
python3 skills/readyasu/scripts/readyasu_check.py verify --final final.md
```

A project word list in `.readyasu-words/` (`allow.txt`, `flag.txt`, `flag-patterns.txt`) removes wrong findings and adds project-specific words. See [docs/tools.md](./docs/tools.md).

The scripts only report places to review. They do not judge whether the meaning was kept or whether the text is easy to read.

## Limits

The checks catch fixed patterns only. Places without findings still need to be read against the original. The rewriting procedure has not yet been measured by running a model on a test set. [docs/limitations.md](./docs/limitations.md) lists what the checks miss and what has been tested.

## License

The code and documents in this repository are released under the [MIT License](./LICENSE). readyasu is derived from [yomiyasu](https://github.com/nanaism/yomiyasu) by nanaism (Aiichiro Oga), also released under the MIT License; its copyright notice is kept in [LICENSE](./LICENSE). readyasu is not an official part of the yomiyasu project.
