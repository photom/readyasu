# Usage

## Calling the skill

- Name it in the request: "Revise this with readyasu." and paste the text.
- Send only `/readyasu` (Codex: `$readyasu`): the skill revises the body text the AI wrote in its previous answer, or the file it wrote in that answer. If there is none, it looks at the `.md` and `.txt` files directly under the working folder, leaving out instruction files (`AGENTS.md`, `CLAUDE.md`) and its own helper files (`*.material.txt`, `*.request.txt`, `*.orig.md`). One file: it revises that file. Two or more: it asks which. None: it asks you to paste the text.
- When it revises a file, it writes the final draft to a new file in the same folder and does not overwrite the original. Ask "update the file" to have the final draft copied over the original; a copy of the original is kept under `.readyasu/drafts/`, named after its path with `/` replaced by `__` (`docs__README.orig.md`). Pasted text and its final draft are saved under `.readyasu/drafts/` for the checks.

## Telling it more

| What | Example | Effect |
|---|---|---|
| Document type | "This is a PR description." | Reads `references/doc-types/pr.md` and keeps that type's normal forms |
| Readers | "For customers with no technical background." | `general`: terms readers need explained are listed as "Needs an explanation", and replaced only from the material or with an everyday word of the same scope |
| Relationship | "An email to a client from our support team." | Adjusts politeness the way that relationship would write; adds no apologies, thanks or commitments |
| Material | "Here is the spec: ..." | Missing values may be filled from it, with the source quoted under "Fact check" |
| Text only | "Return only the text." | No report sections; the checks still run |
| No questions | "Don't ask me anything." | Proceeds without asking about type or reader, and leaves out questions for the writer |

Without these, it infers the type when the text gives clear clues and does not change politeness.

## What you get back

```markdown
### Revised text
(the revised text)

---

### What changed
- original wording → revised wording (reason)

### AI-like wording kept
- (only when wording was kept for meaning)

### Questions for the writer
- (only when the body depends on an answer)

### Fact check
- (only when facts were filled, corrected or questioned)

### Check record
- Writer, reader, setting: Writer: not decided / Reader: not decided / Setting: article (inferred)
- Checks run: lint, diff, final match
- Checks not run: None
- Stiffness check: none
- Energy check: none
- Review findings: original 14 → final 2 (counts are not scores; a rise or fall does not mean better or worse readability)
- readyasu-check: executed via=verify run=... attempt=1 final=sha256:... mode=rewrite checks=lint,diff meaning_risk=0
```

"Checks run" lists what actually ran. A record of the checks shows only that they ran; it does not show that the meaning was kept or that the text reads well.

## Using it every time

Add a line to your instruction file (`CLAUDE.md` for Claude Code, `AGENTS.md` for Codex), for example:

```text
When you write English prose for people to read (articles, PR descriptions, reports, mail), revise it with the readyasu skill before returning it.
```

When installed as a Claude Code plugin, the skill name is `readyasu:readyasu`.

## Project words

Put a folder named `.readyasu-words/` at the top of your repository:

- `allow.txt`: one word or phrase per line that lint should not report (for example a product name that happens to be on a list).
- `flag.txt`: one word per line that lint should report as `project_term`. Write `word<TAB>replacement` to show the preferred term.
- `flag-patterns.txt`: `name<TAB>regular expression` per line, for forms a word list cannot express.

See [tools.md](./tools.md#project-word-lists) for the exact rules.

## Records

`readyasu_check.py run` writes records to `.readyasu/` at the top of the git repository (the working folder outside git). The folder contains its own `.gitignore`, so the records are not committed. Delete the folder whenever you like; `verify` then reports that no record matches. Deleting it also deletes the drafts and the copies of originals that were updated in place, so keep any copy you still need.
