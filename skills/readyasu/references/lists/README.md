# Word lists

The lint and diff scripts read these files. One phrase per line; an optional TAB is followed by a note that lint shows with the finding. Lines starting with `#` are comments.

- Matching ignores case. A space matches any run of whitespace, including a line break inside a paragraph.
- A word ending with `*` matches any word ending (`delv*` matches delve, delves, delving, delved).
- An apostrophe matches both ' and ’. Other punctuation must follow exactly (`happy hacking!` needs the exclamation mark right after "hacking").
- A phrase matches inside underscore emphasis (`_seamless_`, `__leverage__`), but not inside a snake_case name (`enable_seamless_mode`).
- Matches inside code and URLs are ignored. Block quotations are ignored too, except callouts (`> **Note:**`, `> [!WARNING]`, `> 💡 **Tip:**`, `> **⚠️ Warning:**`, `> *Note:*`), which are the writer's own text.
- When matches overlap, lint reports one of them: the more severe one, then a project word, then the longer phrase ("plays a crucial role" rather than "crucial" inside it). A match exempted by `--doc-type` does not hide an overlapping match that is reported.
- The document title (the first level-1 heading) is not checked against these lists.
- A few single entries are exempt in some doc types, set in `ENTRY_EXEMPT` in `readyasu_lint.py`: "thank you for your attention" (closing-courtesies.txt) in slides and script, and "key takeaways" (ai-vocabulary.txt) in slides. `--help` lists them.

| File | Rule | Severity |
|---|---|---|
| ai-vocabulary.txt | ai_vocabulary ("key takeaways" not reported for `--doc-type slides`) | info |
| stock-phrases.txt | stock_phrase | warn |
| chat-residue.txt | chat_residue (AI disclaimers such as "As an AI language model, I"; an assistant's preamble before a drafted or revised text is found by a pattern in `readyasu_lint.py`, see review-points.md section 3) | warn |
| closing-courtesies.txt | chat_residue (courtesies, offers and closings such as "I hope this helps" and "Happy coding"; not reported for `--doc-type mail`; "thank you for your attention" also not for slides and script; "Here's a draft:" is found by the preamble pattern, which reports it in mail too when a drafted mail follows) | warn |
| chat-interjections.txt | chat_residue (Sure!, Of course!, Hey there; reported only at the start of a block, a table cell, a sentence or a capitalized line; not reported for `--doc-type` essay, mail or script, or inside double quotation marks) | warn |
| wordy-phrases.txt | wordy_phrase | info |
| metaphor-verbs.txt | metaphor_verb | info |
| intensifiers.txt | intensifier | info |
| jargon.txt | jargon | info |
| fact-gaps.txt | fact gaps in `readyasu_check.py run --fact-gaps` (format: kind<TAB>regex; see the file) | (not lint) |
| stiff-words.txt | stiffness check in diff | (not lint) |
| feelings.txt | feelings added, in diff | (not lint) |
| roles.txt | actors added, in diff | (not lint) |

These lists are clues, not a ban list. See slop-catalog.md for how to judge each word.
