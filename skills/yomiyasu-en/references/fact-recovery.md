# Fact check (filling from context and verifying)

## 1. When to read this

Read this from SKILL.md section 2, Step 2 when:

- a metaphor or exaggeration hides the content ("performance went through the roof"),
- a subject, number or condition is missing and readers cannot act without it,
- values conflict (the text says 3 days in one place and 72 hours in another, or the text and the material disagree),
- a value has no source,
- you are about to put a value from the conversation or material into the body,
- you got only a draft (no material) and a value readers need to act is missing.

## 2. Procedure

1. List the gaps: missing actor, missing number, missing condition, missing deadline, conflicting values, unsourced values. Ignore gaps that do not stop the reader.
2. For each gap, search in this order: the original, the request, the material, what the user said in this conversation, files that were opened, command output. Your own earlier answers, other AIs' answers and general knowledge do not count.
3. Fill a gap only when you find a sentence that states the value. Copy the value with its strength: "about 30" stays "about 30", "planned for May" stays planned.
4. When values conflict, do not pick one. Keep the original wording and ask, quoting both sources. Correct the body only when the material clearly supersedes the draft (a newer version of the same spec, or the user's own correction in this conversation); then report the correction.
5. When nothing states the value, keep the body as it is and ask under "Questions for the writer", only when a reader could not act without the answer.
6. When the user wants only the text, fill and correct as above but add no notes.

## 3. Conditions for filling, adding and correcting

- Fill: the value is stated in a source and the sentence clearly needs it ("Deploy by Friday" when the request says "the deadline is Friday, May 9" → "Deploy by Friday, May 9").
- Add: you may add a short clarification from the material ("the staging cluster (stg-2)") only when the reader would otherwise not know which one is meant.
- Correct: only when a source states a different value and that source wins (see step 4). Never correct to a value you believe from general knowledge.
- Never: invent an owner because someone "usually" does it, convert units unless asked, round numbers, add a cause, or turn "under investigation" into a finding.

## 4. How to report

```markdown
### Fact check
- Filled: "by Friday" → "by Friday, May 9" (source: request, "the deadline is Friday, May 9")
- Corrected: "3 days" → "72 hours" (source: material spec-v2.md, "Logs are kept for 72 hours"; the draft's "3 days" came from spec-v1)
- Not confirmed: "about 200 users" has no source in the material
```

- Quote the source sentence, not a paraphrase.
- Use the heading "Fact check" exactly.
- When the check output has a "Fact gaps" section (`--fact-gaps`), read each item and decide whether it is a gap readers need filled. The section lists vague placeholders ("soon", "several", "TBD", "a few") and numbers without units; it does not decide anything.

## 5. Other situations

- Composing from material: every number, name and strength word in the final draft must appear in the material. The check's material match lists numbers and names that do not.
- Revising your own draft: treat your draft as the original, and the conversation and material as sources. Values you wrote earlier are not sources by themselves.
- Mail and chat replies: do not fill dates and amounts from earlier messages unless those messages were given to you in this conversation.
