# Bundled scripts

The three scripts in `skills/readyasu/scripts/` need only the Python standard library and support Python 3.9 and later. On Windows, run them with `py -3` instead of `python3`. Messages are in English. All of them read UTF-8 (a BOM is allowed) and accept `-` for standard input.

The scripts report places to review. They do not decide whether the meaning was kept or whether the text is easy to read. `references/review-points.md` explains every section of the output and every rule.

## readyasu_lint.py

```bash
python3 readyasu_lint.py [--json] [--strict] [--fail-on warn|error] [--doc-type TYPE] [--reader READER]
                         [--words DIR | --no-words] [file]
```

Lists English expressions and Markdown formatting worth reviewing in one document.

- Checks paragraphs, list items (including later paragraphs of an item, indented to the item's text), headings, table rows and callouts (`> **Note:**`, `> [!WARNING]`, `> 💡 **Tip:**`, `> **⚠️ Warning:**`, `> *Note:*`; a callout runs from its label to the end of the block quote, across blank `>` lines). Ignores code (fenced, indented and inline, including fenced code inside block quotes, fenced and indented code inside list items, a fence opened on a list item's marker line (`1. ```bash`), indented code right after a heading, rule, table, or the line that ends a `<pre>` block or an HTML comment, and inline code that wraps to the next line), URLs, e-mail addresses, HTML blocks and comments, the content of `<pre>`, `<script>`, `<style>` and `<textarea>` blocks (up to the closing tag, also when the block is indented inside a list item), front matter (YAML `---` or TOML `+++`, with a key or comment on the second line and a closing line) and block quotations, including unprefixed lines that continue a quoted paragraph.
- The document title (the first level-1 heading) is not changed, so only `emoji` and `bold_unrendered` are reported in it.
- Words inside underscore emphasis (`_seamless_`, `__leverage__`, `_may potentially_`) are matched like other words by the word lists, project words and pattern rules; a word inside a snake_case name outside backticks is not.
- One finding per place: when word-list matches overlap, the more severe one (then a project word, then the longer phrase) is kept. Findings of different pattern rules on the same words are all kept. Overlaps are resolved after `--doc-type` exemptions, so an exempted match does not hide a reported one.
- Severities: `error` (bold that will not render), `warn` and `info`. The rules are listed in review-points.md section 3. The word lists behind several rules are in `references/lists/` (see its README).
- `--doc-type` exempts rules that are normal for the type, and a few single list entries ("thank you for your attention" in slides and script, "key takeaways" in slides); exempted findings are counted separately and do not count toward `--strict` or `--fail-on`. `--help` prints the table. Some findings depend on their place: in script, a run of bold labels that are speaker names (`**G:**`, `**MAYA:**`, `**Speaker 1:**`) is exempt from bold_label_list, and so is a sentence_start_repeat run that goes on across such names; in slides, every finding in the notes to the requester before the first slide (before the first heading, `---` or `Slide 1` line) or after the last one (after the last `---` when no heading or `Slide N` line follows it; a setext heading's underline is not a `---`) is exempt; and in mail, an offer about the drafted mail after its sign-off or a thematic break ("Let me know if you'd like me to adjust the tone") is not exempt, while an assistant's preamble after an interjection ("Sure! Here's a revised version:") is exempt unless a greeting or `Subject:` line follows it or it offers a drafted mail with a verb ("Of course! Here's a resignation letter you can adapt:"). The doc type also changes which offers count after a thematic break: in mail, or after a greeting or sign-off in any type, any talk about the draft (tone, wording, a shorter version, "tweak it"); otherwise only words that name a draft ("this draft", "adjust the tone", "a shorter version of the email") or the assistant offering to change the text itself ("Want me to make it shorter?"), so a README's closing note to its readers is not reported. A greeting or a message header (`From:`, `On ... wrote:`, `-----Original Message-----`) starts a new message in a pasted thread, also when the quoted text follows the header in the same paragraph.
- The text output gives each finding as `L<line>:<column> [SEVERITY] rule: message`, followed by the original line; a line longer than 160 characters is cut around the match, with `…` where it was cut. The em_dash and exclamation messages quote the words around the mark.
- `--reader` is recorded only.
- `--json` prints `format`, `tool`, `version`, `doc_type`, `reader`, `review_findings`, `counts`, `no_rule_findings`, `exempted`, `exempted_rules`, `words` and `findings` (each with `line`, `col`, `rule`, `severity`, `message`, `match`, `text`). `col` is the 1-based character column in the original line (for a dash, the dash itself, even at the start of a wrapped line); `match` and `text` show the original text, not the masked form.
- The file may be a named pipe (`readyasu_lint.py <(git show HEAD:README.md)`); a folder or a missing file is an input error.
- Exit codes: 0 finished and no `--fail-on` condition matched; 1 a condition matched; 2 usage or input error.

## readyasu_diff.py

```bash
python3 readyasu_diff.py [options] ORIGINAL REVISED
python3 readyasu_diff.py --compose --material MATERIAL [options] FINAL
```

Compares the original and the revised text sentence by sentence (sentences are paired by similarity) and line by line.

- Output sections: Changed places, Meaning risks, Review findings from the diff, Stiffness, Energy, Material match (with `--material`), Fact gaps (with `--fact-gaps`), Full diff.
- Meaning risks are tagged with a kind. `--help` lists the counted kinds; `--fail-on meaning-risk` exits 1 if any counted risk exists.
- `--doc-type`: booster words (always, guaranteed) are counted only for pr, article, incident, proposal, manual, formal and paper. Stiffness is reference only for incident, formal and paper; energy for pr, article, incident, manual, formal and paper.
- `--stance recommend|rule|explain` adds stance findings ("let's" in a rule document, "will" added in an explanation, obligation added to a recommendation).
- `--material FILE` (repeatable) adds the material match: numbers and names in the revised text found in neither the material nor the original, and units, months, weekdays, frequencies or value orders ("from 400 to 100" against "100 -> 400") that differ from the material.
- `--compose` compares one final draft with the material only; numbers not in the material are counted risks.
- `--fact-gaps` lists some sentences that give only a reference to a value, owner or time they do not give, metaphor, effect, degree word or change without values (not for essay, script and promo). The patterns are in `references/lists/fact-gaps.txt`; if that file cannot be read, a built-in copy is used and the section says so.
- Exit codes: 0 finished and `--fail-on` did not match; 1 it matched; 2 usage or input error.

## readyasu_check.py

```bash
python3 readyasu_check.py run --final FINAL (--source ORIGINAL | --material MATERIAL) [options]
python3 readyasu_check.py run --stdin [options]
python3 readyasu_check.py verify --final FINAL|- [--state-dir DIR] [--json]
```

`run` runs lint on the final draft (and on the original, for the before-and-after count), diff on the original and the final draft (compose mode: the material match), and writes a record. Without a subcommand, `run` is assumed.

### Inputs

- `--source` (or `--original`): the original. Must be a different file from the final draft.
- `--material` (repeatable): material files. Lines `<<<readyasu:material SOURCE>>>` inside them are separators and are not compared.
- With only `--material` (compose mode), if one material is very close to the final draft, it is used as the original and diff runs too; the output says so.
- `--stdin`: read everything from standard input, separated by lines that are exactly `<<<readyasu:original>>>`, `<<<readyasu:material SOURCE>>>` (SOURCE optional, up to 200 characters) and `<<<readyasu:final>>>`. Any other line starting with `<<<readyasu:` stops with exit 2. An original or material section is required, unless `--material FILE` is also given. An empty original or material stops with exit 2. A record is still written (see `--state-dir` and `--no-record`).

### Options

| Option | Meaning |
|---|---|
| `--stance`, `--doc-type`, `--reader` | Passed to lint and diff and stored in the record |
| `--fact-gaps` | Show fact-gap candidates (not counted) |
| `--fail-on meaning-risk,warn,error` | Exit 1 after writing the record when a condition matches |
| `--timeout SECONDS` | Total time for the lint and diff child processes (default 90); on timeout the status is `partial` |
| `--run-id ID`, `--new-run` | Continue a given run, or start a new one |
| `--session ID` | Stored in the record (default: `READYASU_SESSION`) |
| `--state-dir DIR` | Where records go (default: `READYASU_STATE_DIR`, else `.readyasu/` at the git top, else in the working folder) |
| `--no-record` | Write no record (status `unrecorded`); only when the user asked, or when no writable folder exists |
| `--words DIR`, `--no-words` | Project word list for lint |
| `--json` | Print the result as JSON (includes the lint and diff JSON) |

### Output

1. What to do next (attempt and revision count, and the verify command to run).
2. The status line: `readyasu-check: executed via=run run=ID attempt=N final=sha256:XXXXXXXXXXXX mode=rewrite|compose checks=lint,diff[,material] meaning_risk=N` (compose mode without an adopted original: `checks=lint,material`). `checks=` lists only the checks that finished. Other statuses: `unrecorded`, `partial` (with `reason=check_error` when a check did not finish, `reason=record_error` when the record could not be written, `reason=internal_error`), `not_run reason=usage_error`.
3. `Checks run:`, the record path, `Stiffness check:` and `Energy check:` (not in compose mode), `Review findings: original N → final M`, and when present `Flagged words kept:` and `Flagged words added by the rewrite:`.
4. The diff sections and the lint findings on the final draft.
5. The first line and the status line again.

### Runs and attempts

A run groups the attempts on one original. A new attempt continues the previous run only when the original (in compose mode, the material, whether or not it was adopted as the original) is the same, the working folder is the same, the session ID is the same (each session ID keeps its own run; each working folder too), and the previous attempt was less than two hours ago. `--new-run` always starts a new run; use it only on the first run of a new request. The revision count comes from the run's latest record, so `--run-id` resumes a run with its own count. An attempt whose final draft is identical to the previous attempt's is not counted as a revision.

### verify

`verify` hashes the final draft and looks for a record with the same hash. It writes nothing.

- Match: line 1 starts with "The hash matches the record", line 2 is `readyasu-check: executed via=verify ...`. Exit 0.
- No match: line 2 is `readyasu-check: unverified via=verify final=sha256:... reason=no_record|record_unreadable|hash_mismatch|superseded`. `superseded` means the text matches an earlier attempt of a run that has a later attempt with a different final draft. Exit 1.

The hash is taken over a canonical form: line endings normalized to `\n`, leading and trailing empty lines removed, one final newline. Any other change, including a single character or trailing spaces on a line, gives a different hash.

### Records

```text
.readyasu/
  .gitignore                 # "*": records are not committed
  state.json                 # last run and attempt
  runs/<run>/attempt-N.json  # the record
  runs/<run>/attempt-N.diff.txt
  index/by-final/<sha256>.json
  index/by-source/<sha256>[-<session>]~<folder>.json  # one per original (and session) and working folder
```

A record shows that the checks ran on a final draft with that hash. Anyone who can edit both the draft and the records can change them.

### Exit codes

| Code | run | verify |
|---|---|---|
| 0 | All checks finished and no `--fail-on` condition matched | The record matches |
| 1 | A `--fail-on` condition matched (record written) | No record, or it does not match |
| 2 | Usage or input error; nothing written | Usage or input error |
| 3 | Some checks did not finish, the record could not be written, or an internal error (`partial`) | An internal error |

## Project word lists

Put a folder named `.readyasu-words/` at the top of the git repository (the working folder outside git). In a linked git worktree without its own folder, the folder of the main checkout is used. Pass `--words DIR` to use another folder, or `--no-words` to use none.

| File | Format | Effect |
|---|---|---|
| `allow.txt` | One word or phrase per line | Findings of list-based rules (including chat residue) and project words are not reported where their matched text equals an entry or lies inside an occurrence of one, so "plays a crucial role" also hides "crucial" in that phrase and "robust statistics" hides "robust" there, but not elsewhere. The comparison ignores case, treats ' and ’ alike and treats any run of spaces or line breaks as one space; an entry matches whole words, and a `*` in it is literal |
| `flag.txt` | `word` or `word<TAB>replacement` per line | Reported as `project_term` with the text it matched; the replacement (up to 80 characters) is shown after "→". Lines indented with a TAB are ignored. Matching follows the word-list rules (case-insensitive, `*` suffix wildcard, ' and ’ alike) |
| `flag-patterns.txt` | `name<TAB>regular expression` per line | Reported as `project_term` with the matched text and the name. Python regular expression syntax; case-sensitive unless the pattern says `(?i)` |

Lines starting with `#` and blank lines are ignored. Each file may have up to 10,000 lines. A third TAB column in `flag.txt`, a longer replacement, a line in `flag-patterns.txt` without exactly one TAB, an invalid regular expression, or a file that is not UTF-8 stops lint, diff and check with exit 2 and names the file and line (for a file that is not UTF-8, also the byte offset of the first bad byte).

## Lint detection details

The patterns behind the gaps in [limitations.md](./limitations.md#known-gaps-in-lint), with examples of what is missed and what is still reported. review-points.md section 3 describes each rule from the reviewer's side.

### Negative contrast

| Part of the pattern | What is checked | Missed, or reported by mistake |
| --- | --- | --- |
| "Not X, but Y" | An article or "about" after "not" (in a heading also "just", "only", "merely" or "simply"); after "but", a noun phrase that starts with an article, a possessive, "about" or "rather", or a single word that ends the clause | "## Not supported, but planned" is not reported; "not a bug, but intended behavior" is missed |
| The noun phrase after "but" | It must end the clause within about four words or go on with a preposition, "that", "which" or a pronoun ("but a platform for building products"); a verb after it makes the sentence a concession, which is not reported | Concessions: "not a blocker, but the team should review it", "but the default timeout went from 30s to 10s", "but the tests pass", "but the patch works" |
| The verb test | A guess from word shapes: modals, a short list of irregular past forms, -ed words, a word after a plural, an -s word that ends the clause after a word that does not look like an adjective or a determiner | A real contrast with such a word is missed ("but a feature requested by users", "but the sales team", "but the user needs."); a concession whose noun looks like an adjective is reported ("but the initiative helps.") |
| Clauses | A negation in a clause that opens with if, when, although, because, since, while, once, until, as and similar words is not reported | A real contrast inside such a clause is missed |
| Subject in lower case | Checked only as a pronoun right after a colon when a noun phrase, "just" or a verb is denied ("The truth is simple: it isn't a tool. It's a mindset."), or as a noun of one or two words after a reminder that opens the sentence ("Remember, onboarding isn't a sprint; it's a marathon.") | "Here's the thing: it's not hard. It's barely even cooking." is missed; the reminder form after "To be clear," or "But" is missed |
| Start of a sentence | A capitalized word at the start of a line counts as the start of a sentence, after emoji too ("**The big shift**" then "This isn't a tool. It's a mindset.") | In hard-wrapped text, a line that starts mid-sentence with a capitalized subject is checked as a sentence |
| Subject of the one-sentence form | A capitalized word before the negation, or one to three words that start the sentence ("React isn't a framework; it's a library.", "Remote work isn't a perk; it's a paradigm shift."); the two subjects must agree (he and he, a noun phrase and it or they) | Any short opening is checked the same way ("Honestly the fix isn't slow, it's ..."); a longer subject without a determiner is missed ("Working from home every day isn't a perk; it's ...") |
| Subject and verb of the two-sentence form | The same subject (a pronoun, or one to three words that start the sentence, followed by "it" or "they"; any short opening before the negation counts, "In practice it isn't X. It's Y.") and the same verb (common irregular and doubled past forms included: "build" and "built", "stop" and "stopped"; "just", "simply", "merely", "only" or "really" may come before the denied verb) | A longer subject is missed ("The new billing service isn't slow. It's ...") |
| Imperatives | A sentence that opens with please, just, never, kindly, always, simply or do is an imperative, not a subject | |
| Passives and a dummy "it" | Neither form is reported for "it's" and a past participle, or for a dummy "it" before one of a short list of adjectives (clear, possible, likely, easy, known, necessary and similar) and a to-, that- or wh-clause | A passive with "it's" is missed ("This isn't a bug. It's designed to work this way."); "It isn't enough to ship features. It's ..." is still reported |
| Status, place, -ing, "still", "not", "also" | Neither form is reported when either part states a status or a place (sure, ready, done, available, affected, active, enabled, expired, open, fixed, deployed and similar; in, on, at, off), goes on with an -ing form, or the second part goes on with "still", "not" or "also"; in the one-sentence form, "just", "only", "merely" or "simply" after the negation keeps it reported | Not reported: "It's not a bug. It's working as designed.", "It isn't in the cloud, it's on your laptop.", "The API isn't stable yet; it's still in beta." |
| Change over time | The two-sentence form is not reported when the first sentence ends with "at first", "back then", "at the time", "until recently" or "... ago", or the second ends within a few words with now, today, anymore, these days or again ("I didn't like it at first. I like it now.") | A real contrast that ends that way is missed ("We don't sell software. We sell outcomes now.") |

### Personification

| What is checked | Missed |
| --- | --- |
| Software and document subjects (the tool, the system, the code, the logic) after a determiner (the, this, these, their and similar) and up to two other words | A longer subject: "The new customer survey data tells a story" |
| "the agent" and "the assistant" are left out, because they are often people; "server" and "class" count only after a software word ("the web server", "the base class") | "The server knows which client sent the request" |
| Of the negated forms, only "doesn't care" ("The scheduler doesn't care that rows went missing") | "doesn't know", "doesn't remember" and "doesn't understand" usually state what a program has no data for, so their personifying uses are missed |

### Assistant preambles (chat_residue)

| Case | Reported when | Missed, or reported by mistake |
| --- | --- | --- |
| Without an interjection | Only in the first paragraph. A revision lead-in needs a colon after it; an offer of a drafted mail ("Here's a reply you can send to Jordan:") needs a greeting, quotation, code block or `Subject:` line after it (a revision lead-in in mail needs one too); a mail noun without a verb ("Here's a draft email:") and a revision of something that is not a text ("Here's the updated invitation:") need a greeting or `Subject:` line. A thematic break between the preamble and the mail is skipped | A preamble that ends with a period before the revised text, or one later in the document |
| A mail noun without a verb | Needs a sign that it is offered as a draft: "a", "an", "your", possible, suggested, proposed, draft, revised | "Here's the email:" before a drafted mail |
| A noun followed by "from ..." or by a clause with its own subject and a past-tense verb | Never reported (one with "for you" is still reported) | "Here's a draft I wrote based on your notes:" |
| A lead-in whose paragraph goes on with another sentence | After an interjection, only when a greeting or `Subject:` line follows the paragraph or the paragraph ends with a colon | Without an interjection: "Here's a draft email you can send to your landlord. I kept it polite but firm." then "Dear Mr. Lee," |
| After an interjection with no greeting or `Subject:` line after it | A noun that is not a text needs an offering verb ("you can use", "you can adapt"); in mail, only an offer of a drafted mail with a verb is reported | "Sure! Here are the updated slides:" and "Sure! Here's the updated invitation:" before a drafted text without a greeting; in mail, "Sure! Here's a polished version of your email:" directly above the mail body |
| The noun phrase | Up to five words may come before the noun | A longer noun phrase |
| "Below is", "Below are", "I've revised (rewritten, polished, edited ...) your <text>" | Without an interjection, only when a greeting or `Subject:` line follows its colon | One before a drafted post or bio: "Below is a polished version of your LinkedIn post:" |
| Genres, without an interjection | Only the genres the pattern knows | "Here's a LinkedIn post celebrating your promotion:", "Here are the release notes for version 3.2.0:", even before `---` |
| A writer's own first paragraph | | Reported: "Here is the revised version of the config:" or "Here's an updated version of your function:" in a PR or a forum answer |

### Offers about a drafted text (chat_residue)

- In mail, an offer about the drafted mail ("Let me know if you'd like me to adjust the tone") is reported only after the mail's sign-off (a closing such as "Best," with a comma or a name line after it) or in the paragraph right after a thematic break, and only when the sentence names the tone, the wording, the formality, a shorter or another version, "adjust it" or "make it more ...". An offer at the end of the mail's last paragraph is missed, and a writer's postscript about the tone after the sign-off is reported.
- A greeting or a header line (`From:` or `Sent:` at the start of a paragraph line, `On ... wrote:`, `-----Original Message-----`, `---------- Forwarded message ----------`) starts a new message, so a writer's offer after an earlier message in a pasted thread is not reported, also when the quoted text follows the header in the same paragraph. A message in a thread with neither a greeting nor such a header (only a name and a date above it) still counts the earlier sign-off.
- Outside mail, after a thematic break with no greeting or sign-off before it, an offer needs words that name a draft ("this draft", "adjust the tone", "a shorter version of the email", "edit the message") or the assistant offering to change the text itself ("want me to", "would you like me to", "I can also"), unless the paragraph already has assistant chat. So "Feel free to personalize it with your own projects!" alone after a drafted post is missed, and a template's closing "Feel free to edit the message to fit your incident." is reported.

### Sentence splitting

- Words that are also abbreviations before a number (no, max, fig, Dec) end a sentence unless a digit follows.
- A single capital letter is treated as an initial only before a capitalized word that does not usually start a sentence ("John F. Kennedy", but "Plan B. It was cheaper."), so "Plan B. Kennedy approved it." stays one sentence.
- An abbreviation right after a number ("450 ms.", "5 p.m.") ends a sentence only before a capitalized word that usually starts one, other than "I". "Meet at 5 p.m. The room is booked." is two sentences; "at 5 p.m. Smith joined" and "At 9 a.m. I restarted the service." are one, so "We left at 5 p.m. I stayed." is one sentence too.
- Emoji right after the end mark stay with the sentence when a new sentence or the end follows ("We shipped v2! 🎉" then "Thanks to everyone."), so the exclamation mark is still found.
- Inline code or a URL after sentence-ending punctuation counts as a capitalized word and starts a new sentence ("The fix? `retry()` now wraps every call." is two sentences), also after an unlisted abbreviation.

### em_dash

| Skipped | Examples | Missed, or still reported |
| --- | --- | --- |
| A time, date, version or numbered label at the start of any line or item, alone or as a range, also on a hard-wrapped line | "09:12", "Dec 5", "2025-12-03", "2025/12/03", "03.12.2025", "2026-11-13 (Fri)", "Day 2", "Step 1", "Part II", "Option A", "Slide 1", "Section 3", "Act II", "10:00–10:15", "9–10 am", "Dec 3–5", "Version 2.1", "1.2.0", "v1.0–v1.4", "2.0.0 – 2.3.1", "Last updated: March 2026", a weekday with a date in parentheses ("Monday (Mar 3)", "Tue (11/12)") | Missed: "We met at" then "10:00 — it was short." |
| A spaced dash between two range endpoints: numbers with a currency sign, %, am/pm or a common unit (kg, GB, ms, days, cups), versions, Q1–Q4, noon, midday, midnight, capitalized month and weekday names as whole words | "2019 – 2021", "9 am – noon" | Checked: "3 bugs — Janet". Missed: "We grew 20% – 30 new customers signed" |
| Inline code or a URL (also in bold or as link text) that is all that comes before the dash on its line, alone or as aliases joined by a comma, a slash or "or"; also with placeholders in capitals or angle brackets after it, or one note in parentheses without a dash | "`-h`, `--help` — show help", "`--level` LEVEL — show only ...", "`timeout` (float) – HTTP timeout" | Missed: "`retry()` (new) – it wraps every call", "`retry()` API — ..." |
| A dash that starts a line in plain text after a line that ends with a colon, or next to a line that starts with the same dash | Bullets in plain-text minutes or mail | |
| A capitalized label of up to three words with a colon after the dash | "— Owner: Marco" | |
| A line that is only a dash and a capitalized name after a sentence | "— Jeff Atwood", "— Plato, Republic" | |
| On a line with no sentence end after the dash: a dash after any capitalized word and a number at the start of the line | "## Milestone 2 — Beta" | Missed: "Apollo 11 — the mission". Reported: "Python 3.9 – the oldest we support – is end of life." |
| On a line with no sentence end after the dash: a dash after an all-capitals label of up to four words (a stage direction) | "**[COLD OPEN — ambient sound]**" | Missed: "NOTE — this one is fine". Reported: "[UPDATE — the fix is now live.]" |
| On a line with no sentence end after the dash: a screenplay scene heading that starts with "INT.", "EXT.", "INT./EXT." or "I/E." | "INT. KITCHEN — NIGHT" | Reported: "INT Kitchen — Night" (no period, mixed case) |
| A dash after only names on the paragraph under a man page's `NAME` heading | "logsift — filter log files" | |
| A dash before a date, a due time or, in a list item, an owner (one to a few capitalized names or @handles) that ends a list item or a title line (a heading, or the first line of a paragraph with no sentence end before the dash, no period after and no lower-case continuation on the next line) | Due times: next meeting, this week, by Friday, due Fri 20 Nov, ETA: Friday, by 5 pm on Friday, before the HR meeting, EOD | Missed: "- We rebuilt the parser — Huge Win", "Our launch slipped — next week". Reported: "On-call handoff — notes" in a paragraph, a title alone on the first line, "Rafa – here's the deck" |
| A mail's `Subject:` line, a title block that opens the document (two or more short lines, the first starting with a capital, none ending with a sentence or clause mark) and a table cell with no sentence end, unless "and", "but", "or", "yet", "so" or "plus" follows the dash | "Subject: Resignation — last day December 5" | Missed: "\| Cache \| slower — we fixed it \|" |
| A dash after only a capitalized name that opens a list item, when lower case follows with no sentence end | "- Ana — draft the notice" | Missed: "- Honestly — it was fine" |
| A dash after a short label that starts a line, when a date or time follows | "Christmas Eve – 6pm (family Mass)" | |
| Speech that breaks off: a dash right before a closing quotation mark, or "I wasn't — we weren't" in a speaker's turn or a quotation | | Other dashes in dialogue, transcribed speech and quotations are reported |
| A dash after a news dateline that opens a paragraph, when a capitalized word follows it (a place in capitals, optionally with a state, a date and an agency) | "HARBOR CITY — Andrés ...", "SAN FRANCISCO, March 3, 2025 — Acme ...", "WASHINGTON (AP) — ..." | Missed: a clause dash after other words in capitals that open a paragraph, unless one of them is a common label word ("GREEN LIGHT — The board approved the budget."). Reported: "UPDATE — The fix is live.", "BIG NEWS — We launched." |

### Markdown parsing

- Headings: ATX and setext.
- Lists: a line indented at least to an item's text belongs to the item, even after a blank line or a fence. As in CommonMark, a new list interrupts a paragraph only with a bullet or "1.", so a wrapped line that starts with "1998." continues the paragraph, also inside a list item, while a sibling item ("2." after "1.") still starts an item. Inside an item, a fence indented four or more columns past the item's text after a blank line is indented code, and a fence may open on the marker line (`1. ```bash`).
- Block quotes, with lazy continuation lines and fenced code inside. A block quote indented four or more spaces inside a list item is checked as text.
- Tables, and fenced and indented code. Indented code is recognized also right after a heading, a rule, a table, or the line that ends a `<pre>` block or an HTML comment, but not right after a paragraph line, which it continues, or inside an HTML block such as `<div>` or `<p>`, which runs to a blank line. An indented line without `|` right after a table row is code, not a row.
- HTML comments, and `<pre>`, `<script>`, `<style>` and `<textarea>` blocks: their content, up to the line with the closing tag, is treated as code. A block that is never closed runs to the end of the document, as in CommonMark; inside a list item the opening tag may be indented up to three columns past the item's text.
- YAML or TOML front matter, only with a key or comment on line 2 and a closing line.
- Raw HTML: a line that starts with a block-level tag (`<div>`, `<p>`, `<details>`) or holds a single tag is skipped, but text on the lines between `<div>` and `</div>` is checked, indented or not.
