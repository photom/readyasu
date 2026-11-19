# Limitations

## What the checks can and cannot do

- The scripts match fixed patterns. They report places to review; they do not decide whether meaning was kept or whether the text is easy to read. A run with no findings does not prove anything about meaning.
- Lint counts are not a score. A rise or fall in "Review findings" says nothing about readability.
- The record from `readyasu_check.py` shows that the checks ran on a final draft with a given hash. Anyone who can edit both the draft and the record can change them; the record helps find skipped runs, it does not prevent tampering or prove human approval.

## Known gaps in lint

- Word lists match surface forms. A listed word used in its literal or technical sense ("unlock the door", "robust statistics", "elevate the platform by 2 meters") is still reported; use `.readyasu-words/allow.txt` or keep the word and give the reason.
- Words mentioned as examples inside quotation marks (a style guide that says to avoid "delve") are reported like any other use. Only interjections such as "Sure!" are treated as dialogue inside double quotation marks (or with `--doc-type` essay, script or mail); dialogue in single quotation marks is reported.
- Rhythm-level AI patterns (every paragraph the same length, a "rule of three" in every sentence, a summary sentence at the end of every paragraph) are not detected.
- Negative contrast, personification and self-answered questions are detected only in common forms. "Not X, but Y" is reported only with an article or "about" after "not" and a noun phrase after "but"; the two-sentence form only when both sentences have the same subject and verb. Personification is checked only for software and document subjects (the tool, the system, the code); "the agent" and "the assistant" are left out because they are often people.
- Interjections ("Sure!", "Great question") are reported only at the start of a block, a table cell, a sentence or a line that starts with a capital, so one that follows a comma is missed.
- Sentence splitting uses punctuation and a short list of abbreviations; unusual abbreviations can split a sentence in two. Words that are also abbreviations before a number (no, max, fig, Dec) end a sentence unless a digit follows, and a single capital letter is treated as an initial only before a capitalized word that does not usually start a sentence ("John F. Kennedy", but "Plan B. It was cheaper."), so "Plan B. Kennedy approved it." stays one sentence.
- The em_dash rule skips timeline entries, fields and attributions by pattern: a time, date or version at the start of a line or item, alone or as a range ("09:12", "Dec 5", "2025-12-03", "Day 2", "10:00–10:15", "Dec 3–5", "Version 2.1", "Last updated: March 2026"), a capitalized label of up to three words with a colon after the dash ("— Owner: Marco"), and a line that is only a dash and a capitalized name after a sentence ("— Jeff Atwood", "— Plato, Republic"). Other separators are still reported.
- Markdown parsing covers headings (ATX and setext), lists (a line indented at least to an item's text belongs to the item, even after a blank line or a fence), block quotes (with lazy continuation lines and fenced code inside), tables, fenced and indented code, HTML comments and YAML or TOML front matter (only with a key or comment on line 2 and a closing line). A block quote indented four or more spaces inside a list item is checked as text. Deeply nested structures and raw HTML blocks may be classified roughly: a line that starts with a block-level tag (`<div>`, `<p>`, `<details>`) or holds a single tag is skipped, but text on the lines between `<div>` and `</div>` is checked.

## Known gaps in diff

- Sentences are paired by similarity. A deleted sentence and an added sentence that are similar enough are compared as a moved sentence, and half of a split sentence is joined to its neighbor. When a rewrite reorders or merges many sentences, a change may still be reported against a neighboring sentence, or a number may be listed as removed in one place and added in another.
- Negation, hedges, permission, obligation, conditions and scope are compared by counting marker words in paired sentences. Changes expressed without those words (an antonym such as "succeeded" → "failed", a verb that changes direction, "increase" → "decrease") are not caught. Read every changed sentence.
- "Names in a different order", names moved between sentences or lines, and names gone from the text use capitalized words; a name at the start of a sentence counts for "name" only when it is also capitalized in the middle of some sentence; swapped roles described with common nouns ("the client asked the vendor") are not caught. A name at the start of a sentence counts only when it is followed by a verb and does not appear in lower case anywhere.
- "over" and "under" before a number are read as approximations, also when they are prepositions ("spread over 3 regions").
- Units are compared only when written right after the number (one qualifier word may sit between: "30 business days"). Months and weekdays are compared by name; dates written only as numbers are compared as numbers.
- "One" is treated as a pronoun, not the number 1, only in "no one", "one another", and after "the", "this", "old", "new" and similar words at the end of a phrase or before "who", "that" or "which" ("the old one."). A count written that way ("keep the one.") is not compared.
- Added actors are found from a list of role words and capitalized names.
- Fact gaps are a partial list of figures, effects, degree words and changes without values.

## What has been tested

- The scripts are tested with pytest (unit tests for the text handling, every lint rule, every meaning-risk kind, check run and verify, and the consistency of the documents with the scripts) on Linux with Python 3.13. CI runs the tests on Python 3.9 and 3.14 on Linux and 3.12 on Windows.
- The rewriting procedure (SKILL.md) has not yet been measured by running a model on a test set, and installs through the plugin, skills CLI and GitHub CLI have not been tried.
