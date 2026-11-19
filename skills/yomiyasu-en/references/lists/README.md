# Word lists

The lint and diff scripts read these files. One phrase per line; an optional TAB is followed by a note that lint shows with the finding. Lines starting with `#` are comments.

- Matching ignores case. A space matches any run of whitespace, including a line break inside a paragraph.
- A word ending with `*` matches any word ending (`delv*` matches delve, delves, delving, delved).
- An apostrophe matches both ' and ’.
- Matches inside code and URLs are ignored. Block quotations are ignored too, except callouts (`> **Note:**`, `> [!WARNING]`, `> 💡 **Tip:**`, `> *Note:*`), which are the writer's own text.
- When matches overlap, lint reports one of them: the more severe one, then a project word, then the longer phrase ("plays a crucial role" rather than "crucial" inside it).

| File | Rule | Severity |
|---|---|---|
| ai-vocabulary.txt | ai_vocabulary | info |
| stock-phrases.txt | stock_phrase | warn |
| chat-residue.txt | chat_residue | warn |
| closing-courtesies.txt | chat_residue (courtesies, offers and closings; not reported for `--doc-type mail`) | warn |
| chat-interjections.txt | chat_residue (Sure!, Of course!; not reported for `--doc-type` essay, mail or script, or inside double quotation marks) | warn |
| wordy-phrases.txt | wordy_phrase | info |
| metaphor-verbs.txt | metaphor_verb | info |
| intensifiers.txt | intensifier | info |
| jargon.txt | jargon | info |
| fact-gaps.txt | fact gaps in `yomiyasu_en_check.py run --fact-gaps` (format: kind<TAB>regex; see the file) | (not lint) |
| stiff-words.txt | stiffness check in diff | (not lint) |
| feelings.txt | feelings added, in diff | (not lint) |
| roles.txt | actors added, in diff | (not lint) |

These lists are clues, not a ban list. See slop-catalog.md for how to judge each word.
