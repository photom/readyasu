# Document types and readers

Read this when the reader is specified as informed or general (SKILL.md section 2, Step 1), or when you are unsure how to decide the type or reader.

## 1. Clues for the type

| Type | Clues |
|---|---|
| pr | "Summary / Changes / Testing" headings, checklists, references to files, commits or issues |
| article | Title, introduction, sections, code samples, written for the public or a team blog |
| incident | Timeline with timestamps, impact, root cause, action items, "postmortem" |
| proposal | Problem, options, recommendation, cost, decision requested |
| minutes | Date, attendees, agenda, decisions, action items with owners |
| manual | Numbered steps, prerequisites, "click", "run", troubleshooting |
| slides | Short lines, one idea per heading, `---` separators, speaker notes |
| essay | First person, reflection, narrative, fiction, no instructions to the reader |
| formal | "shall", defined terms, numbered clauses, policies, contracts, specifications |
| promo | Product benefits, calls to action, taglines, launch announcements |
| mail | Greeting, sign-off, "Hi", "Thanks", chat messages |
| paper | Abstract, related work, method, results, citations |
| script | Character names before lines, stage directions, scene headings |

## 2. Clues for the reader

- expert: the same field as the writer; terms used without explanation are fine.
- informed: technical, but from a different field (a backend engineer reading about ML, a product manager reading a design document).
- general: no specialist knowledge (customers, the public, other departments).

## 3. When you may proceed on an inference

Infer the type when the text has two or more clues from section 1 and no clue for another type. Write "(inferred)" in the check record. Do not infer the reader from the type alone.

## 4. Ask or proceed without deciding

Ask once, before rewriting, only when the answer changes the rewrite (for example, a general reader would need ten terms explained) and you can ask. Otherwise proceed without deciding.

## 5. When you do not decide

Apply all of SKILL.md section 1 and no doc-type exemptions. Do not add explanations for any reader.

## 6. Adjustments allowed on an inference

On an inferred type, apply only the exemptions in the type's file; do not change register or add explanations.

## 7. The three readers

| Reader | Do | Do not |
|---|---|---|
| expert | Keep terms, identifiers and abbreviations | Add explanations |
| informed | Expand an abbreviation at first use when the original or material gives the expansion; keep terms but mark unexplained ones with "Needs an explanation" | Explain with general knowledge |
| general | Same as informed; prefer the plain word when the original or material offers one ("sign in" over "authenticate" when the UI says "Sign in") | Replace a term whose plain form changes the meaning |

## 8. Terms

- Keep identifiers, product names, UI labels and API names as they are.
- When the original uses two words for the same thing ("instance" and "server"), keep both unless the material says they are the same.
- Do not explain a term with your own knowledge; write "Needs an explanation: term (location)" instead.

## 9. Sentence length and omissions

- For general readers, split a sentence that carries three or more conditions only when each condition can keep its scope.
- Do not drop steps that experts would skip; the original decided what to include.

## 10. How to write "Needs an explanation"

One line per term, after "Questions for the writer" items, not counted toward the three: `- Needs an explanation: idempotent (step 3)`.

## 11. Reader profiles

When the request names a reader ("for new hires", "for the finance team"), use it as given. Do not add assumptions about their knowledge beyond the three levels.

## 12. How to show it

In the check record: `Writer: not decided / Reader: general (specified) / Setting: not decided`.

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
| essay | metaphor_verb, fragment_run, exclamation |
| formal | none |
| promo | emoji, exclamation, fragment_run, metaphor_verb, self_answered_question |
| mail | emoji, exclamation, chat_residue (closing courtesies only) |
| paper | none |
| script | fragment_run, exclamation, self_answered_question, metaphor_verb |

## 14. Example (synthetic)

Request: "Make this easier to read for our customers." Reader: general (specified). The original says "Re-authenticate via SSO." The UI label is "Sign in with SSO". Rewrite: "Sign in again with SSO." The term "SSO" has no explanation in the original or material: add `- Needs an explanation: SSO (step 2)`.
