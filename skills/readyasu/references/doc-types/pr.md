# Pull request description (pr)

See also: domains/tech.md
Lint rules exempted: excess_list

## 1. Normal forms (do not change)

- Bullet lists of changes and tests, checklists (`- [x] Added tests`), and fragments without a subject ("Add cache eviction for expired keys").
- Template headings (Summary, Changes, Testing, Notes). Keep their number and order.
- Sentences whose subject is an identifier ("`retry_limit` sets the maximum number of retries"). Keep them for expert and informed readers (audience.md section 7).
- The default reader is expert (the reviewer).
- Imperative mood in titles and bullets ("Fix", "Add"), past tense in descriptions ("Fixed"). Keep whichever the original uses.

## 2. Still fix

- Change reports without a verb and confusion between done and planned (SKILL.md "Stance and sentence form").
- Sentences that mix what was tested with what was not. Do not write untested behavior as tested.
- Lists that only pair a label with an explanation (`- **Improvement**: Improved the list view`, bold or not). bold_label_list is not exempted for this type.
- Chat residue ("I hope this helps reviewers", "Let me know if you have any questions!"). Keep "This PR aims to": removing "aims to" turns a purpose into a claim that the change works.

## 3. Length and omissions

- Keep one change per bullet. Do not merge bullets into prose.
- Do not expand fragments into full sentences.

## 4. Examples (synthetic)

| Original | Handling |
|---|---|
| - Add eviction for expired cache keys | Keep (fragment) |
| - **Improvement**: Improved the list view | Remove the label: "- Improved the list view". Say what changed only if the original or material says |
| This PR seamlessly enhances the robustness of the retry logic. | "This PR makes the retry logic withstand ..." with what the diff or material shows, keeping the improvement claim and "seamlessly" unless the diff shows what the reader no longer has to do; ask if unknown |
