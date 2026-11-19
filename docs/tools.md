# Bundled scripts

The three scripts in `skills/readyasu/scripts/` need only the Python standard library and support Python 3.9 and later. On Windows, run them with `py -3` instead of `python3`. Messages are in English. All of them read UTF-8 (a BOM is allowed) and accept `-` for standard input.

The scripts report places to review. They do not decide whether the meaning was kept or whether the text is easy to read. `references/review-points.md` explains every section of the output and every rule.

## readyasu_lint.py

```bash
python3 readyasu_lint.py [--json] [--strict] [--fail-on warn|error] [--doc-type TYPE] [--reader READER]
                         [--words DIR | --no-words] [file]
```

Lists English expressions and Markdown formatting worth reviewing in one document.

- Checks paragraphs, list items, headings, table rows and callouts (`> **Note:**`, `> [!WARNING]`, `> 💡 **Tip:**`, `> *Note:*`; a callout runs from its label to the end of the block quote, across blank `>` lines). Ignores code (fenced, indented and inline, including fenced code inside block quotes, indented code inside list items and inline code that wraps to the next line), URLs, e-mail addresses, HTML blocks and comments, front matter (YAML `---` or TOML `+++`) and block quotations, including unprefixed lines that continue a quoted paragraph.
- One finding per place: when word-list matches overlap, the more severe one (then a project word, then the longer phrase) is kept. Findings of different pattern rules on the same words are all kept.
- Severities: `error` (bold that will not render), `warn` and `info`. The rules are listed in review-points.md section 3. The word lists behind several rules are in `references/lists/` (see its README).
- `--doc-type` exempts rules that are normal for the type; exempted findings are counted separately and do not count toward `--strict` or `--fail-on`. `--help` prints the table.
- `--reader` is recorded only.
- `--json` prints `format`, `tool`, `version`, `doc_type`, `reader`, `review_findings`, `counts`, `no_rule_findings`, `exempted`, `exempted_rules`, `words` and `findings` (each with `line`, `col`, `rule`, `severity`, `message`, `match`, `text`). `col` is the 1-based character column in the original line; `match` and `text` show the original text, not the masked form.
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
- `--material FILE` (repeatable) adds the material match: numbers and names in the revised text found in neither the material nor the original.
- `--compose` compares one final draft with the material only; numbers not in the material are counted risks.
- `--fact-gaps` lists some sentences that give only a metaphor, effect, degree word or change without values (not for essay and promo). The patterns are in `references/lists/fact-gaps.txt`; if that file cannot be read, a built-in copy is used and the section says so.
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

A run groups the attempts on one original. A new attempt continues the previous run only when the original (in compose mode, the material, whether or not it was adopted as the original) is the same, the working folder is the same, the session ID is the same (each session ID keeps its own run), and the previous attempt was less than two hours ago. `--new-run` always starts a new run; use it only on the first run of a new request. The revision count comes from the run's latest record, so `--run-id` resumes a run with its own count. An attempt whose final draft is identical to the previous attempt's is not counted as a revision.

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
  index/by-source/<sha256>.json
```

A record shows that the checks ran on a final draft with that hash. Anyone who can edit both the draft and the records can change them.

### Exit codes

| Code | run | verify |
|---|---|---|
| 0 | All checks finished and no `--fail-on` condition matched | The record matches |
| 1 | A `--fail-on` condition matched (record written) | No record, or it does not match |
| 2 | Usage or input error; nothing written | Usage or input error |
| 3 | Some checks did not finish, the record could not be written, or an internal error (`partial`) | |

## Project word lists

Put a folder named `.readyasu-words/` at the top of the git repository (the working folder outside git). In a linked git worktree without its own folder, the folder of the main checkout is used. Pass `--words DIR` to use another folder, or `--no-words` to use none.

| File | Format | Effect |
|---|---|---|
| `allow.txt` | One word or phrase per line | Findings whose matched text equals an entry are not reported, for list-based rules and project words. The comparison ignores case, treats ' and ’ alike and treats any run of spaces or line breaks as one space |
| `flag.txt` | `word` or `word<TAB>replacement` per line | Reported as `project_term` with the text it matched; the replacement (up to 80 characters) is shown after "→". Lines indented with a TAB are ignored. Matching follows the word-list rules (case-insensitive, `*` suffix wildcard, ' and ’ alike) |
| `flag-patterns.txt` | `name<TAB>regular expression` per line | Reported as `project_term` with the matched text and the name. Python regular expression syntax; case-sensitive unless the pattern says `(?i)` |

Lines starting with `#` and blank lines are ignored. Each file may have up to 10,000 lines. A third TAB column in `flag.txt`, a longer replacement, a line in `flag-patterns.txt` without exactly one TAB, an invalid regular expression, or a file that is not UTF-8 stops lint, diff and check with exit 2 and names the file and line.
