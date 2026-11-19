# Document types and readers

Read this when the reader is specified as informed or general (SKILL.md section 2, Step 1), or when you are unsure how to decide the type or reader.

## 1. Clues for the type

| Type | Clues in the request | Clues in the text |
|---|---|---|
| pr | PR, pull request, change description | "Summary / Changes / Testing" headings, issue numbers, file and branch names |
| article | tech blog, article, post | An introduction, code blocks with explanations, "In this article" |
| incident | incident, outage, postmortem, retrospective | Start time, impact, root cause, mitigation, action items, a timeline with timestamps |
| proposal | proposal, pitch, business case, RFC | Background, goal, options, cost, expected effect, a decision requested |
| minutes | minutes, meeting notes | Date, attendees, agenda, decisions, action items with owners |
| manual | manual, guide, how-to, runbook | Numbered steps, a run of imperatives, prerequisites, notes and warnings |
| slides | slides, deck, talk | `---` page separators, Marp-style front matter, short headings with bullets per page |
| essay | essay, diary, personal blog, fiction | First-person narration, experiences and feelings, dialogue and narration |
| formal | policy, contract, regulation, terms, specification | Numbered clauses, "shall", defined terms, effective dates, parties |
| promo | feature article, marketing copy, product page, review roundup | "Top 10", "best", rankings, prices and where to buy, calls to action |
| mail | email, chat, Slack message, reply, DM | A greeting ("Hi Sam"), a sign-off, a signature |
| paper | paper, preprint, thesis, research report | "In this study", related work, citations ([1], (Smith 2020)), "Discussion", "Conclusion" |
| script | screenplay, script, storyboard, dialogue | `NAME: line` or `NAME` above lines, scene headings, stage directions, SFX cues |

- Documents that fit none (company-wide announcements, weekly reports, chat posts sharing a link, release notes) get no type.
- An article that recommends products or places is promo, even on a personal blog.
- Specifications are formal (readers follow them as rules). Documents that show how to use something step by step are manual. When a document spans two types (slides with a script, minutes containing a proposal), use the main type if one is clear; otherwise do not decide.
- The stance (recommend, rule, explain) is decided separately from the type. Do not derive the stance from the type.

## 2. Clues for the reader

- expert: shares the field's terms and assumptions with the writer.
- informed: knows general technical or business words, but not this field's abbreviations, internal names or assumed procedures (a backend engineer reading about ML, a product manager reading a design document). For non-technical documents, read informed as "used to reading work documents".
- general: does not know the field's terms or assumptions (customers, the public, other departments).

## 3. When you may proceed on an inference

- Type: (a) the request's destination points to one type and the text has no clue for another type, or (b) the text has two or more clues for one type and none for another. Minutes and slides need at least one clue of form (attendees and agenda; `---` separators or Marp front matter).
- Reader: (a) the request or destination names the reader, or (b) the type is pr or minutes and nothing in the request or text conflicts with expert.
- Otherwise you are not confident. A value decided from the destination ("for the company wiki") is inferred, not specified.
- A reader is specified only when the request states the level or describes what the readers know ("for readers with no technical background", "the readers are ML researchers"). Naming a group ("for our customers", "for the team") gives an inferred level (register.md section 2).
- When the specified type and the text's form disagree ("these are minutes" but the text is a proposal), follow the specified type and do not reshape the text into that type's form.

## 4. Ask or proceed without deciding

Ask once, before rewriting, only when the answer changes the rewrite (for example, a general reader would need many terms explained) and you can ask. Otherwise proceed without deciding.

- Ask at most once per request, even when there are several drafts.
- An answer such as "up to you", or no answer, leaves the value undecided; do not ask again.
- Do not mix questions about facts into this question; they go with your answer after the rewrite (`fact-recovery.md`).
- For promo, do not ask new fact questions; ask only about claims that look exaggerated (`doc-types/promo.md`).

## 5. When you do not decide

Apply all of SKILL.md section 1 and no doc-type exemptions. Do not add explanations for any reader, and do not output "Needs an explanation".

## 6. Adjustments allowed on an inference

On an inferred type, apply the exemptions in the type's file. On an inferred reader, do not rephrase terms and do not output "Needs an explanation" (section 8 needs a specified reader).

## 7. The three readers

| Reader | Terms | Sentence length and omissions |
|---|---|---|
| expert | Keep terms, abbreviations and identifiers. Add no explanations and output no "Needs an explanation" | Keep the field's usual omissions. Split a long sentence only when you can name the misreading |
| informed | Keep general technical and business words. Rephrase or gloss field-only words and internal names only when specified and the original or material explains them; otherwise, when the reader was specified, output "Needs an explanation" (on an inferred reader, output nothing; section 6) | Same as expert |
| general | Rephrase or gloss unexplained terms only when specified, from the original or material or with an everyday word of the same scope; otherwise, when the reader was specified, output "Needs an explanation" (on an inferred reader, output nothing; section 6) | Section 9 |

- In developer documents (reader expert or informed, about software), do not treat sentences whose subject is an identifier ("`scheduler` requeues failed jobs") as personification. Real personification ("the code tells a story") is still fixed. Identifiers are not rephrased even for general readers.

## 8. Terms

| Class | Example (synthetic) | expert | informed | general |
|---|---|---|---|---|
| A. Term explained in the original or material | "TTL (how long the cache keeps an entry)" | Keep | Keep | Keep |
| B. Unexplained field terms and abbreviations | idempotent, p95, depreciation, reorder point | Keep | Keep general technical and business words (API, server, cost of goods). Field-only words: rephrase or gloss only when the material defines them and the reader was specified; otherwise "Needs an explanation" when the reader was specified | Rephrase or gloss only when the material defines them and the reader was specified; otherwise "Needs an explanation" when the reader was specified |
| C. Internal names, internal abbreviations, project names | blue env, P1 response, month-end close | Keep | When the reader was specified: "Needs an explanation" (or a gloss when the material explains it) | Same |
| D. Coinages, buzzwords, inflated nouns | "north star", "AI-native", "single pane of glass" | As in SKILL.md "Inflated nouns" | Same | Same |
| E. Identifiers, code, UI labels, product names, legal terms, numbers with units | `retry_limit`, the **Save** button, PostgreSQL | Keep (including identifier-subject sentences) | Same | Keep; never rephrase; "Needs an explanation" if needed |
| F. Jargon with an everyday word of the same scope | "onboard" (a user), "sunset" (a product) | Keep | Keep | May use the everyday word of the same scope when specified |

Rephrase only when all of these hold:

1. The user specified informed or general (including an answer to your question). Never on an inference.
2. The rephrasing comes from a definition in the original or material, or an everyday word covers exactly the same scope (class F). Do not write definitions from the model's general knowledge; that adds an explanation the original does not have.
3. Only one rephrasing fits.
4. Write one line under "What changed": "term → rephrasing (reader: general)".

Never rephrase class E, terms the original defines, words that correspond to a heading or table label, or words inside quotations. The rule to use provided definitions and value-to-state mappings (SKILL.md "Add nothing") applies to every reader.

## 9. Sentence length and omissions

- Length and omissions per type follow section 3 of each file in doc-types.
- Only when general was specified, you may split a sentence that carries two or more requests or conditions when connectives can keep their relation. Do not widen splitting on an inferred general.
- Do not drop steps that experts would skip; the original decided what to include.

## 10. How to write "Needs an explanation"

- Put it under "Questions for the writer" (create the heading for it if there are no other questions). Form: `- Needs an explanation: "TTL" (paragraph 3; not explained in the original or material)`. Never put it in the body.
- Up to three, counted separately from the three questions. When there are more, choose headings, the first paragraph and words that recur, and add "N more places".
- Do not draft an explanation for each term; the writer writes it.
- Do not output it for expert readers, when the reader is not decided or only inferred, or when the user wants only the text.
- For internal names in a text for outside readers (when a relationship and the reader level were specified), you may add "the writer decides whether to explain it or leave it out".
- Questions for the writer are about places whose meaning is unclear in the original itself; "Needs an explanation" is for places the writer understands but the reader lacks. Do not list the same word in both. When composing, if the material does not explain a term, do not add an explanation; list it.

## 11. Reader profiles

- A profile gives a specified level only when it says what the readers know or which field they work in (section 3): same field as the document: expert; different field but used to technical or business words: informed; otherwise general. A profile that only names a role ("procurement manager") gives an inferred level, and section 6 applies. Decide which terms need explanation from a specified level.
- The writer-reader relationship is handled in register.md. Politeness changes only within register.md section 7. Do not change structure, contractions, claims or examples.
- Do not pass the profile to check.
- For "make it beginner-friendly" or "make it simple", make the words and the order of explanation easier (sections 8 and 9) and treat the reader as an adult. Do not add a childish or cheerleading tone ("Don't worry!", "You've got this!", "Easy, right?"). When the original already uses that tone, keep it unless asked.

## 12. How to show it

In the check record, the setting is the document type: `Writer: not decided / Reader: general (specified) / Setting: manual (inferred)`. Write "(specified)" or "(inferred)" after each decided value and "not decided" otherwise.

When the user corrects the type or reader after your answer, treat it as a new request: rewrite from the first original and add `--new-run` to the first check run of that request (in the same run, the first line would treat the new findings as a revision and tell you not to change the body). It does not count toward "Revise once only".

## 13. Rules exempted by type

| Type | Lint rules exempted |
|---|---|
| pr | excess_list |
| article | none |
| incident | excess_list |
| proposal | none |
| minutes | bold_label_list, excess_list, fragment_run |
| manual | excess_list |
| slides | bold_label_list, excess_list, fragment_run, self_answered_question, count_announcement, closing_summary |
| essay | fragment_run, exclamation, chat_residue (interjections only) |
| formal | none |
| promo | emoji, exclamation, fragment_run, self_answered_question |
| mail | emoji, exclamation, chat_residue (courtesies and interjections only) |
| paper | none |
| script | fragment_run, exclamation, self_answered_question, chat_residue (interjections only) |

No type exempts metaphor_verb: metaphorical verbs on ordinary events are reviewed in every type, and each doc-type file says which uses to keep.

## 14. Example (synthetic)

Request: "Make this easier to read for customers with no technical background." Reader: general (specified). The original says "Re-authenticate via SSO." The material includes the UI, whose button says "Sign in with SSO". Rewrite: "Sign in again with SSO." and add "re-authenticate → sign in again (reader: general)" under "What changed". "SSO" has no explanation in the original or material: add `- Needs an explanation: "SSO" (step 2; not explained in the original or material)`.
