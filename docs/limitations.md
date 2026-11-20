# Limitations

## What the checks can and cannot do

- The scripts match fixed patterns. They report places to review; they do not decide whether meaning was kept or whether the text is easy to read. A run with no findings does not prove anything about meaning.
- Lint counts are not a score. A rise or fall in "Review findings" says nothing about readability.
- The record from `readyasu_check.py` shows that the checks ran on a final draft with a given hash. Anyone who can edit both the draft and the record can change them; the record helps find skipped runs, it does not prevent tampering or prove human approval.

## Known gaps in lint

The exact forms that each rule skips, with examples of what is missed and what is still reported, are under [Lint detection details](./tools.md#lint-detection-details) in tools.md.

- Word lists match surface forms. A listed word used in its literal or technical sense ("unlock the door", "robust statistics", "elevate the platform by 2 meters") is still reported; add the phrase to `.readyasu-words/allow.txt` (an entry also hides the listed word inside it, only there) or keep the word and give the reason.
- Word lists, project words and the pattern rules see words inside underscore emphasis (`_seamless_`, `__leverage__`), but not a word inside a snake_case name that is not in backticks (`enable_seamless_mode`).
- Words mentioned as examples inside quotation marks (a style guide that says to avoid "delve") are reported like any other use. Only interjections such as "Sure!" are treated as dialogue inside double quotation marks (or with `--doc-type` essay, script or mail); dialogue in single quotation marks is reported.
- Rhythm-level AI patterns (every paragraph the same length, a "rule of three" in every sentence, a summary sentence at the end of every paragraph) are not detected.
- Negative contrast and self-answered questions are detected only in common forms. The negative_contrast rule guesses subjects, verbs and concessions from word shapes and short word lists, so some real contrasts are missed ("not a bug, but intended behavior", "The new billing service isn't slow. It's ...") and a few concessions are reported ("not a bug, but the initiative helps.").
- Personification is checked only for software and document subjects after a determiner and up to two other words, and of the negated forms only "doesn't care" is reported, so "The new customer survey data tells a story" and "The server knows which client sent the request" are missed.
- The looser "In today's ... landscape" opener is reported only when the noun ends the phrase (a comma, a dash or the end of the sentence follows) and only modifiers come before it, so "In today's fast-paced business environment teams must adapt" is missed (the fixed phrases in stock-phrases.txt, such as "In today's fast-paced world", are still found).
- Interjections ("Sure!", "Great question") are reported only at the start of a block, a table cell, a sentence or a line that starts with a capital, so one that follows a comma is missed.
- An assistant's preamble without an interjection ("Here's a polished version of your email:") is found only in the first paragraph and only in fixed shapes, each of which needs a colon or a greeting, quotation, code block or `Subject:` line after it. So one that ends with a period before the revised text, one later in the document and one that names a genre the pattern does not know ("Here's a LinkedIn post celebrating your promotion:") are missed, and a writer's own lead-in of the same shape ("Here is the revised version of the config:" in a PR) is reported.
- In mail, an offer about the drafted mail ("Let me know if you'd like me to adjust the tone") is reported only after the mail's sign-off or right after a thematic break, and only when it names the tone, the wording, the formality or another version; an offer at the end of the mail's last paragraph is missed, and a writer's postscript about the tone after the sign-off is reported. Outside mail, an offer after a thematic break that no word list has is reported only when it names a draft or the assistant offers to change the text, so "Feel free to personalize it with your own projects!" alone after a drafted post is missed.
- In slides, notes to the requester are recognized only before the first heading, `---` or `Slide 1` line and after the last `---` when no heading or `Slide N` line follows it; no finding in them is reported. A closing offer after the last slide of a deck without `---` separators is still reported, and nothing is reported in a first slide with no heading before the first `---`, or in a last slide after the last `---` that starts with neither a heading nor a `Slide N` line (such as a bold title).
- bold_label_list treats a repeating run of bold speaker names ("Speaker 1", "P2", "DEV (into the phone, whispering)") as the turns of a dialogue, so a repeated numbered or capitalized summary label ("**Step 1:**", "**Step 2:**", "**Step 1:**"; "**Pros:**", "**Cons:**", "**Pros:**") is missed; in script any run of such labels is exempt, so section labels in a video script ("**Hook:**", "**Body:**") are missed there. heavy_bold does not count a bold label at the start of any line, so bold used as emphasis at line starts is missed. sentence_start_repeat ends a run where the speaker of such a dialogue changes, so a repeated opener across turns is missed, and in script a run across speaker names that do not repeat is exempt.
- Emoji are found from a fixed Unicode 15 table, so emoji added after Unicode 15 outside U+1F000–U+1FAFF are missed. The emoji among the miscellaneous symbols and dingbats (☀, ✈, ❤, ⚠, ✔) are reported even without the emoji selector U+FE0F, because many systems draw them as emoji, also where they are meant as plain symbols (♠ ♥ in a card game); symbols that are emoji only with the selector (ℹ️, ▶️, ‼️, ➡️, ©️) are reported only with it, and arrows and symbols that are not emoji (→, ➜, ♪, ★, ✓) or that are followed by the text selector U+FE0E are not reported.
- Sentence splitting uses punctuation and a short list of abbreviations; unusual abbreviations can split a sentence in two. Initials, abbreviations after a number and inline code at a sentence boundary are guessed from the next word, so "Plan B. Kennedy approved it." and "We left at 5 p.m. I stayed." stay one sentence.
- The em_dash rule skips dashes by pattern: timeline entries ("09:12 —", "2026-11-13 (Fri) —"), ranges, option lists, attributions, title blocks, `Subject:` lines, table cells without a sentence end, date, due-time and owner tags, schedule entries, datelines, scene headings and speech that breaks off. A clause dash that matches one of these patterns is missed ("We grew 20% – 30 new customers signed", "| Cache | slower — we fixed it |"), and other dashes in dialogue, transcribed speech and quotations are reported, because a scripted line or a made-up quotation cannot be told from a recorded one.
- fragment_run does not count a sentence that starts with a common instruction verb and has a word after it ("Open Settings.", "Click Save."), so a run of short slogans that start with such a verb ("Sign up now. Start free.") is missed.
- hedge_stack skips a modal and adverb after a question word that opens the clause or a negation or "as ... as" among the four words before it ("What could possibly go wrong?"); a real stacked hedge in such a clause is missed.
- Markdown is parsed for the common structures (see [Markdown parsing](./tools.md#markdown-parsing)). Deeply nested structures and raw HTML blocks may be classified roughly: a line that starts with a block-level tag (`<div>`, `<p>`, `<details>`) or holds a single tag is skipped, but text on the lines between `<div>` and `</div>` is checked, indented or not, and a block quote indented four or more spaces inside a list item is checked as text.

## Known gaps in diff

- Sentences are paired by similarity. A deleted sentence and an added sentence that are similar enough are compared as a moved sentence, and half of a split sentence is joined to its neighbor. When a rewrite reorders or merges many sentences, a change may still be reported against a neighboring sentence, or a number may be listed as removed in one place and added in another.
- Negation, hedges, permission, obligation, conditions and scope are compared by counting marker words in paired sentences. Changes expressed without those words (an antonym such as "succeeded" → "failed", a verb that changes direction, "increase" → "decrease") are not caught. Read every changed sentence.
- Names (for names in a different order, names moved between sentences or lines, and names gone or replaced) are capitalized words outside headings, which are often in Title Case. A word at the start of a sentence, a line, a list label ("- **Dana**:") or a timeline entry ("- 14:22 — Lee") counts as a name only when it is also capitalized in the middle of some sentence (for added actors: when a verb follows it and it does not appear in lower case anywhere), and a capitalized word that appears in lower case in the final draft ("Peak latency" folded to "peak latency") is not treated as a gone name. Swapped roles described with common nouns ("the client asked the vendor") are not caught.
- Added evaluations ("a big improvement", "which is excellent") and recommendations in other words ("I recommend", "the best choice") are not detected; read for them. "We recommend", "recommended", "advisable" and "encouraged" count as a soft obligation (like "should"), so adding one is reported.
- "over" and "under" before a number are read as approximations, also when they are prepositions ("spread over 3 regions").
- Units are compared only when written right after the number or after one qualifier word ("30 business days"). With two words in between no unit is read, so "30 full business days" → "30 full calendar days" is missed and "30 business days" → "30 full business days" is reported as a unit change.
- Months and weekdays are compared by name; dates written only as numbers are compared as numbers, so "3/5" → "5/3" is missed.
- "One" is treated as a pronoun, not the number 1, only in "no one", "one another", and after "the", "this", "old", "new" and similar words at the end of a phrase or before "who", "that" or "which" ("the old one."). A count written that way is not read as 1: "keep the one." → "keep them all" is not reported, and "keep the one." → "keep the two." is reported only as an added 2.
- Added actors are found from a list of role words and capitalized names.
- Fact gaps are a partial list of references (a deadline, a vague owner or time), figures, effects, degree words and changes without values.
- A decimal's trailing zero is ignored ("0.50" equals 0.5, "1.0" equals 1), except after a product or version word ("Python 3.10", "Node 18.20", "version 2.10"); a version written without such a word ("3.10 is out") is compared as 3.1.
- "unable to" counts as a negation ("could not"); "failed to" does not, so "failed to deliver on time" → "delivered late" passes, and so does "failed to deliver" → "delivered".
- Role and term acronyms (CEO, ARR, QA...) are compared only when one replaces another in the same sentence; one that disappears is listed only under the words that disappeared.
- A dropped restrictive "who"/"that" clause is checked only on a plural subject that starts the sentence; a name inside the dropped clause is still reported as a gone name ("Engineers who know Rust can review it" → "Engineers can review it").
- Harmless rewordings are recognized by form, so a real change written in one of the forms below passes.

| Passed as harmless | Example |
| --- | --- |
| "currently" dropped before an -ing verb or "in beta" | "is currently testing" → "is testing" |
| A list count dropped while its items stay | "three things to check: logs, metrics and traces" → "Check logs, metrics and traces" |
| "not X" → "rather than X" before the same word | "to HR, not to your manager" → "to HR rather than to your manager" |
| "not" and a word → "un" and that word | "not clear" → "unclear" |
| An ongoing state restated with "not ... yet" | "still pending" → "not approved yet" |
| "you should X" → "X" | "You should restart the server." → "Restart the server." |
| "may/might/could" and "possibly" → the modal alone | "may possibly fail" → "may fail" |

## What has been tested

- The scripts are tested with pytest (unit tests for the text handling, every lint rule, every meaning-risk kind, check run and verify, and the consistency of the documents with the scripts) on Linux with Python 3.13. CI runs the tests on Python 3.9 and 3.14 on Linux and 3.12 on Windows.
- The rewriting procedure (SKILL.md) has not yet been measured by running a model on a test set, and installs through the plugin, skills CLI and GitHub CLI have not been tried.

## Measured quality

lint and diff were measured on a fixed evaluation set built from the pairs and corpora of earlier review rounds. The set lives outside this repository. It is split into dev, which was used while fixing, and held-out, which was measured once, at the end. A diff miss is a meaning change with no counted risk; a false positive is a harmless rewrite with a counted risk. Cases of a kind that these documents say is not counted, and cases whose expected result is ambiguous, are left out.

| Metric | Target | dev | held-out (measured once) | held-out at the start (v0.1.0) |
| --- | --- | --- | --- | --- |
| diff miss rate | 5% or less | 3.0% (44 / 1,480) | 5.9% (22 / 372) | 5.4% |
| diff false-positive rate | 5% or less | 3.5% (46 / 1,309) | 4.3% (14 / 326) | 6.1% |
| Human documents with a warn or error lint finding | 25% or less | 20.7% (41 / 198) | 28.6% (14 / 49) | 28.6% |
| AI documents with a warn or error lint finding (caught) | none | 95.5% (126 / 132) | 87.9% (29 / 33) | 87.9% |

The other targets were no high findings in the review of the results, no regressions on the fixed set, and two passing rounds in a row, in at most three rounds. Not met: the held-out miss rate, the held-out share of human documents, no high findings (the last round still had one), and no regressions (two held-out cases regressed; see below).

## Known issues in 0.2.0

- A weekday abbreviation before a parenthesized date that starts with "May" or a digit is compared only after a word such as on, by or due, or after a colon or dash, so "The demo is Fri (May 3)." → "The demo is Mon (May 3)." and "Fri (3/5)" → "Mon (3/5)" are not reported. Before a written date ("Fri, May 3", "Fri 3/5", "Fri (June 3)") it is compared.
- A swap of the denied sides is missed when one side is a pronoun: "done by us, not by the supplier" → "done by the supplier, not by us" is not reported.
- Two held-out cases regressed through exemptions added in round 1 of the convergence work: "You should back up your data before upgrading." → "Back up data before upgrading is common." passes as an imperative rewrite, and "available 24/7" → "available on weekdays" is not reported.
