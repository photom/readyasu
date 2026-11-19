# Reading the check output, and reviewing by eye

Read this when you look at lint findings in SKILL.md Step 2, item 1, and when you check the findings of `readyasu_check.py run` in Step 4. When Python cannot run, follow section 4.

Findings are places to check against the original (the material, when composing), not orders to change. Do not keep rephrasing only to make findings disappear. Revise once only, and run again after the revision (SKILL.md Step 4). Having no findings does not prove that the meaning was kept. Lint gives no score; do not treat the number of findings as a pass mark.

## 1. The first lines of the output

- Line 1 says what to do next. Follow it.
- Line 2 is the status line (it starts with `readyasu-check:`). Copy it into the check record. When you ran verify before submitting, copy the second line of the verify output instead.
- "Checks run:" summarizes what ran; it corresponds to "Checks run" in the check record.
- "Stiffness check:" and "Energy check:" give values such as "none", "candidates 2" or "reference 1". Copy them to the lines of the same name in the check record. "reference" means the doc type normally changes these things (stiffness in incident, formal and paper; energy in pr, article, incident, manual, formal and paper); still read the section. When these lines are absent (compose mode), leave them out of the record.
- "Review findings: original N → final M" counts lint rule matches before and after. It is not a score, and a rise or fall says nothing about readability. Copy the values to "Review findings" in the check record.
- "Flagged words kept:" lists stock vocabulary, metaphorical verbs, jargon and project words that are still in the final draft and were in the original. Reread each sentence with the Step 2 questions (SKILL.md Step 5).
- "Flagged words added by the rewrite:" lists such words that your rewrite introduced. Restore the original wording.

## 2. Sections of the output

### == Changed places ==

A summary of the first ten changes, shortened to about 120 characters. Look here first for changes you did not intend; check shortened places and the eleventh onward in "Full diff". When a place says "(N lines → M lines)", different paragraphs may be paired; read the pairs around it.

### == Meaning risks ==

Each item is tagged with its kind. Counted kinds make `--fail-on meaning-risk` fail; "[not counted]" kinds are listed for review only. Compare each with your note from before rewriting (SKILL.md "Top rule: keep the meaning"). Restore unintended changes. Keep a change based on the material only when it meets fact-recovery.md section 3, and report it under "Fact check".

| Kind | What it means | What to do |
|---|---|---|
| number | A number was removed, added or changed: digits, number words, quarters and versions (Q3, v2), currency and magnitudes ($1.5M, 5k), percentages; a unit written next to an unchanged number (30 seconds → 30 ms, 30 days → 30 business days); a month or weekday name. The whole-text line catches numbers that disappeared from or appeared in the whole text | Restore, unless it is a fill or correction from a source (fact-recovery.md), an absolute date you added after a relative one, or a count word you removed with a count announcement or a cleft list ("Three things:") while every item stayed |
| approximation | about, up to, at least, more than... on the same number changed | Restore the original approximation |
| negation | The number of negations (not, no, never, n't, without, unless...) changed in the paired sentences; or the count stayed the same but the kind changed ("does not restart" → "restarts without delay"); or what is denied swapped sides ("the replicas, not the primary" → "the primary, not the replicas") | Read both. Removing "not only" or turning "not X but Y" into "Y" also changes the count; that is fine only when the rephrase test passes |
| certainty | A hedge (may, might, could, would, likely, seems, appears to/that, it's possible, is believed to, we expect, planned...) disappeared or was replaced by a stronger one, also inside the answer of a folded self-answered question. Stacked hedges ("could potentially", "can possibly") count as one, so reducing a stack to one hedge is not reported | Restore the hedge at the same strength |
| booster | always, guaranteed, definitely, ensures... was added. Counted only for pr, article, incident, proposal, manual, formal and paper (not when the original sentence already has a strong obligation word such as must or required); otherwise listed as a review finding | Remove the added certainty |
| permission | you may, allowed to, optional, no need to... appeared or disappeared | Restore; permission is not ability ("may" is not "can") |
| obligation | should ↔ must, or an obligation word appeared or disappeared | Restore the original strength |
| status | TBD, pending, under investigation, not yet, unconfirmed... disappeared | Restore the state; do not turn it into a finding or a plan |
| hearsay | reportedly, according to, says, said, told us, claims, noted, mentioned, colleagues say, users report... appeared or disappeared | Restore; hearsay is not assertion |
| question | A question became a statement or the reverse. A short self-answered question folded into a statement, and a request turned into a polite question, are listed as not counted | Restore the sentence type, except when you folded a self-answered question into a statement (SKILL.md "Decoration and ad copy") or turned a request into a polite question for a stated relationship (register.md section 7) |
| request | please, could you... disappeared | Restore the request form; a bare imperative changes politeness |
| scope | A limiting word (only, solely) disappeared; either/or ↔ both/all; or a determiner such as some, most, many or several disappeared with no other partial word, or a partial word became all/every | Restore the scope |
| condition | A condition or time limit disappeared: if, unless, until, when, while, once, before, after, as soon as, as long as, provided, at launch, initially, for now, temporarily | Restore it; without it the sentence is true in more cases. A rewrite that keeps the condition in other words is fine |
| correlation | A cause word was added to a sentence that stated only a correlation | Restore the correlation wording |
| commitment | we will, we guarantee, will never happen again... was added | Remove it unless the request or material states the commitment |
| citation | A citation ([1], (Smith, 2020)) changed | Restore; which source supports which claim must not move |
| name_order | The same names appear in a different order, or a name moved to another sentence or line (owners swapped between list items) | Check who does what to whom; restore if the roles swapped |
| material_number | (compose) A number in the final draft is not in the material | Remove it or use the material's value |
| contrast_reversed [not counted] | A word the original denied ("not X", "rather than X"; not "not just X", which affirms X) now appears with focus, priority, first, both, and... | If X moved to the affirmative side, the claim flipped; restore the negation (rephrase-test.md section 3). A rewrite such as "First, reduce X" can also appear; read which side X is on |
| protected [not counted] | Inline code, URLs, e-mail addresses or code blocks changed | Restore them exactly |

Some forms are not caught. Compare sentences without findings against your note too.

### == Review findings from the diff ==

| Kind | What to check |
|---|---|
| certainty_weakened | The rewrite is less certain than the original. Restore unless the original overstated something a source corrects |
| hedge_changed | A hedge was replaced by another of the same level. Usually fine; check the nuance |
| ability | can / able to disappeared. Check that the sentence still says what is possible |
| request_added | A request marker appeared. Check that the sentence was a request (register.md) |
| quantifier_gone | An adverb such as often, usually or mostly disappeared without a replacement. Check that the sentence did not become always true |
| limiter_added | only, solely... appeared. Do not add limits the original lacks |
| condition_added | if, unless, until, at launch... appeared. Do not add conditions the original lacks |
| causal_added | because, led to, as a result... appeared. Keep facts side by side if the original did not connect them |
| booster | Certainty word added (in doc types where it is not counted). Remove guarantees the original lacks |
| voice | Active/passive changed with the same names. Check who acts |
| quote | Text in quotation marks changed or disappeared. Restore dialogue, quoted words and labels |
| quote_changed | Text inside a block quotation (`>`) changed. Block quotations are compared sentence by sentence like the body, so their meaning risks are counted too. Restore quotations; callouts such as `> **Note:**` or `> [!WARNING]` are the writer's own text and may be revised |
| feeling_added | A feeling word appeared that the original lacks. Do not add feelings, even in essays |
| connection | A rewritten sentence starts with a connective or "this/it". Say what it connects to; fix or ask |
| actor_added | A role (team, manager, we, you...) or a name appeared that is in neither the original nor the material. Remove invented actors, owners and recipients |
| deleted | A deleted sentence held a negation, hedge or obligation. Check that nothing appears only there |
| added | An added sentence holds a negation, obligation or permission. Check that the original or material says so |
| words_gone | Content words that no longer appear anywhere. Check that no fact went with them |
| heading | A heading changed or the number of headings changed, or a closing section ("Conclusion", "Final thoughts") was removed. Check the warnings, conditions and roles it held; a closing section may go only when it repeated the body |
| stance | With `--stance`: "let's" in a rule document, "will" added in an explanation, or an obligation added to a recommendation |

### == Stiffness ==

Contractions dropped by more than half, or stiff words (utilize, facilitate, prior to, in accordance with...) appeared. Unless the request asked for a more formal register, restore the original's register. In incident, formal and paper this is reference only.

### == Energy ==

Exclamation marks, emoji or headings decreased. Check that the writer's energy was not lost where the document type keeps it (promo, mail, essay voice), and that headings kept their number and order. In pr, article, incident, manual, formal and paper this is reference only; for other specified types, emoji and heading items are reference only (except promo and mail for emoji, and promo, minutes and mail for headings).

### == Material match ==

Shown when material was passed (`--material`, or material sections on standard input).
- "Not in the material (numbers)" and "(names)": values in the final draft found in neither the material nor the original. In compose mode, numbers here are counted meaning risks. When you filled a value, the excerpt must have the line it came from (fact-recovery.md section 2, step 6).
- "Matches a material line": shows only that a material line has the same value; lines marked "(original)" come from the original, not the material. It does not prove the line is the source or that the value is right.
- "Hedge or status words in the material that the final draft lacks": check that the final draft kept "planned", "not yet", "may" and the like where it uses those values.

### == Fact gaps ==

With `--fact-gaps`: sentences of the final draft that give only a metaphor (figure), an effect (effect), a degree word (degree) or a change without values (change). The list is partial and not counted. Sentences with a number, a hedge or plan word, a vague quantity or a closing resolution are never listed. Fill only when a source has the content (fact-recovery.md); otherwise ask under "Fact check" or leave it. Not shown for essay and promo.

### Attempts

The first line counts attempts and revisions. Rerunning on an unchanged final draft (for example when verify did not match) is not a revision. A run continues the previous one only when the original (in compose mode, the material) is the same, the working folder is the same, the session ID (`--session` or `READYASU_SESSION`, when both runs have one) is the same, and the previous run was less than two hours ago; otherwise a new run starts at attempt 1. For a new request about the same text, add `--new-run` (SKILL.md Step 3).

### == Lint findings on the final draft ==

The lint findings of the final draft; see section 3 for each rule.

### == Full diff ==

Every changed line pair, not shortened. `~` lines show word-level changes as `[-removed-]{+added+}`. The same text is in `attempt-N.diff.txt` next to the record.

## 3. Lint rules

| Rule | Severity | How to look at it |
|---|---|---|
| `bold_unrendered` | error | Markdown will show the asterisks. Fix the markup: no space inside `**text**`; add a space after a closing `**` that follows punctuation and precedes a letter (`**Note:** This`). A lone `**` (the only one in the paragraph, as in `**kwargs`) is info: add the closing `**` if bold was meant, or put code in backticks. `**` between letters or digits (`2**3`) is not reported |
| `emoji` | warn | Remove decoration; keep emoji that carry meaning (a status icon in a table the reader needs). Exempt in promo and mail |
| `em_dash` | warn | Replace clause-splicing dashes with punctuation that keeps the scope; split into two sentences when a reason or condition would reach farther. Keep in fiction narration and dialogue, quotations, ranges and code. Not reported in the document title (the first level-1 heading), for a dash that is a whole table cell, after a time, date or version (or a range of them) that starts a line or item (`09:12 — Config change`, `10:00–10:15 — Status`, `Version 2.1 — Effective January 1`), before a field label (`— Owner: Marco`), or on a line that only names the author under a quotation (`— Jeff Atwood`) |
| `chat_residue` | warn | Assistant chat left in a document: delete. In mail, courtesies, offers and closings (`closing-courtesies.txt`, including "I hope this helps") are not reported; the writer's own sign-off stays. Interjections such as "Sure!" and "Of course!" (`chat-interjections.txt`) are reported only where they start a sentence, and not in essay, script and mail, or inside double quotation marks |
| `stock_phrase` | warn | Openers, signposts and closers that announce instead of saying. Delete, and keep any fact that appears only there |
| `hedge_stack` | warn | Use one hedge of the same strength. Never remove the hedge entirely. After "it seems" or "it appears", "could" counts only as a possibility (`could be`, `could have`), not as an ability (`the attacker could read any file`) |
| `heading_colon` | warn | Remove the colon from the heading (also inside emphasis, as in `## **Benefits:**`) |
| `bold_label_list` | warn | SKILL.md "Bold and labels": keep labels for values, fold summary labels into the sentence, remove the bold. Exempt in minutes and slides |
| `heavy_bold` | warn | Keep bold only for what readers must not miss |
| `ai_vocabulary` | info | slop-catalog.md section 3 and section 10. Keep the field's terms |
| `wordy_phrase` | info | slop-catalog.md section 7. Use the short form when meaning and register stay the same |
| `metaphor_verb` | info | slop-catalog.md section 1. Say what changed; do not replace with a vague benefit. Not exempted in any type; each doc-type file says which uses to keep |
| `intensifier` | info | SKILL.md "Wordiness, zombie nouns and stock vocabulary": delete when stacked, on an absolute, or in technical and formal text |
| `jargon` | info | domains/business.md section 3 |
| `negative_contrast` | info | SKILL.md "Self-labeling and negative contrast" and rephrase-test.md section 3. Keep negations that correct a likely misreading. A concession (`not tested, but it shipped`) is not reported, and the two-sentence form needs the same subject and verb (`It isn't a tool. It's a mindset.`) |
| `personification` | info | SKILL.md "Metaphorical verbs and personification". Keep obvious functions and identifier subjects in developer documents |
| `self_answered_question` | info | Fold into a statement. Exempt in slides, promo and script |
| `fragment_run` | info | Write subject and verb when the original gives them. Exempt in minutes, slides, essay, promo and script |
| `count_announcement` | info | Check that the count matches the items; if not, ask without changing either. Exempt in slides |
| `closing_summary` | info | Delete a closing section that only repeats; keep new information, next steps and requested summaries. Exempt in slides |
| `excess_list` | info | Turn reasons and conditions back into sentences where a list splits one argument; keep parallel lists. Exempt in pr, incident, minutes, manual and slides |
| `exclamation` | info | Keep only where the type and writer use them. Exempt in essay, promo, mail and script |
| `sentence_start_repeat` | info | Vary only where it reads as a pattern; keep parallel steps. Numbered clauses (`3.1`, `3.2`) do not count |
| `decorative_colon` | info | Remove the colon or finish the sentence |
| `project_term` | info | A word from `.readyasu-words/flag.txt` or `flag-patterns.txt`. Rewrite the sentence, not just the word; the replacement after "→" is the project's preferred term |

## 4. Reviewing by eye (when Python cannot run)

Write `readyasu-check: not_run reason=no_python` in the check record and write "Checks not run: lint (no_python), diff (no_python), final match (no_python)" (add "material match (no_python)" when material was given). Then, before submitting:

1. Compare every sentence of the final draft with the original for numbers, negations, hedges, permission and obligation words, status words, hearsay, questions, requests, limits (only), names and their order, citations, code and URLs.
2. Search the final draft for the lint rules in section 3: emoji, dashes, bold labels, stock phrases, chat residue, stacked hedges, headings with colons.
3. Check that you added no actors, feelings, causes, commitments or guarantees.
4. Do not write that the checks were run.
