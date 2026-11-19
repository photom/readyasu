# Technical writing

## 1. Decoration and lists

### Bold and lists
- Bold only what the reader must not miss: a destructive command, a value to type, a breaking change.
- A list is for parallel items. Do not turn an explanation with reasons and conditions into bullets.
- Do not start every bullet with a bold label and colon.

### Decoration and stock structure
- No emoji in headings or bullets of technical documents.
- A closing "Conclusion" or "Key takeaways" section that only repeats a short how-to can go (SKILL.md "Headings that guide"); keep "Introduction" and any number, condition or next step found only there.

## 2. Steps and settings
- One action per step, in the order performed. Prerequisites first.
- Put values, file names, commands and identifiers in inline code as the original does; do not add or remove code formatting.
- Keep the exact error messages and log lines.

## 3. Style
- Write what the code does ("returns null when the key is missing"), not what it feels or knows.
- Use the field's terms ("race condition", "idempotent"); do not swap them for vague words ("timing issue") unless the original is vague.
- Keep "we" and "you" as the original uses them.
