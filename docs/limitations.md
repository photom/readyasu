# Limitations

## What the checks can and cannot do

- The scripts match fixed patterns. They report places to review; they do not decide whether meaning was kept or whether the text is easy to read. A run with no findings does not prove anything about meaning.
- Lint counts are not a score. A rise or fall in "Review findings" says nothing about readability.
- The record from `yomiyasu_en_check.py` shows that the checks ran on a final draft with a given hash. Anyone who can edit both the draft and the record can change them; the record helps find skipped runs, it does not prevent tampering or prove human approval.

## Known gaps in lint

- Word lists match surface forms. A listed word used in its literal or technical sense ("unlock the door", "robust statistics", "elevate the platform by 2 meters") is still reported; use `.yomiyasu-en-words/allow.txt` or keep the word and give the reason.
- Words mentioned as examples inside quotation marks (a style guide that says to avoid "delve") are reported like any other use.
- Rhythm-level AI patterns (every paragraph the same length, a "rule of three" in every sentence, a summary sentence at the end of every paragraph) are not detected.
- Negative contrast, personification and self-answered questions are detected only in common forms.
- Sentence splitting uses punctuation and a short list of abbreviations; unusual abbreviations can split a sentence in two.
- Markdown parsing covers headings (ATX and setext), lists, block quotes, tables, fenced and indented code, HTML comments and front matter. Deeply nested structures and raw HTML blocks may be classified roughly.

## Known gaps in diff

- Sentences are paired by similarity. When a rewrite reorders or merges many sentences, a change may be reported against a neighboring sentence, or a number may be listed as removed in one place and added in another.
- Negation, hedges, permission, obligation and scope are compared by counting marker words in paired sentences. Changes expressed without those words (an antonym such as "succeeded" → "failed", a verb that changes direction, "increase" → "decrease") are not caught. Read every changed sentence.
- "Names in a different order" uses capitalized words; swapped roles described with common nouns ("the client asked the vendor") are not caught.
- Added actors are found from a list of role words and capitalized names.
- Fact gaps are a partial list of figures, effects, degree words and changes without values.

## What has been tested

- The scripts are tested with pytest (unit tests for the text handling, every lint rule, every meaning-risk kind, check run and verify, and the consistency of the documents with the scripts) on Linux with Python 3.13. CI runs the tests on Python 3.9 and 3.14 on Linux and 3.12 on Windows.
- The rewriting procedure (SKILL.md) has not yet been measured by running a model on a test set, and installs through the plugin, skills CLI and GitHub CLI have not been tried.
