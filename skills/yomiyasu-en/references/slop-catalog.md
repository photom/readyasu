# Catalog of unnatural AI vocabulary and constructions in English

This catalog lists words and constructions worth reviewing in AI-generated English, with candidate rewrites. The candidates are not a replacement table. Use one only when it keeps the same kind of state, the same strength and the same scope as the original in its context. Do not swap a word whose meaning you cannot pin down for one that merely sounds close; when you cannot tell whether a verb or relation means the same thing, keep the original. A word listed here is not banned: when you cannot rewrite it naturally while keeping the meaning, keep it. Keep "undecided" and "under investigation" states the original tells the reader; put your own uncertainty in "What changed" or "Questions for the writer", never in the body.

The test for every entry: would a careful human writer in this field have used this word before AI text became common? If yes, keep it.

The lint lists in `lists/` hold the words each rule matches. This file explains how to judge them.

---

## 1. Metaphorical verbs

Rewrite events and technical operations described with a metaphor into plain words that fit the context. Keep idioms that ordinary English used before AI ("take a toll", "bite the bullet", "a long shot", "learn the ropes"); in specifications, keep them too when they cannot be misread.

| Verb | Example to review | Candidates and cautions |
|---|---|---|
| unlock | "unlock new possibilities", "unlock the full potential" | Say what becomes possible ("lets you export to CSV"). If the original does not say, keep and ask. Literal unlocking (a door, an account, a phone) stays. |
| supercharge, turbocharge | "supercharge your workflow" | Say what got faster or larger and by how much, only from the original. Do not invent a number. |
| unleash | "unleash the power of" | Usually delete the frame: "the power of X lets you" → "X lets you". |
| harness | "harness the power of data" | "use data to ...". Keep the literal sense (a harness for a horse, a test harness). |
| navigate | "navigate the complexities of", "navigate the landscape" | "deal with", "work through", or name the actual difficulties if the original lists them. Literal navigation (a website, a ship) stays. |
| dive into, deep dive | "Let's dive into", "a deep dive into" | Delete the announcement or write "This section explains". "Deep dive" as a fixed meeting name stays. |
| delve | "delve into the details" | "look at", "examine", "go through". |
| weave | "weaves together data from" | "combines", "merges". |
| fuel | "fuels innovation" | Say what it makes possible, or "drives" only if a causal claim is in the original. |
| tame | "tame your inbox" | "reduce", "sort", "control" as the original supports. |
| shine | "where X truly shines" | "where X works best", "X is most useful when". Keep the hedge "truly" only if the original has emphasis worth keeping; otherwise drop it. |
| kill, crush, nail | "kill the bottleneck", "crush your goals" | "remove", "fix", "meet". Keep "kill a process" (a technical term). |
| empower | "empowers teams to" | "lets teams", "allows teams to". Keep the formal sense of granting legal power. |
| skyrocket | "sales skyrocketed" | "rose sharply" with the number if given. |
| elevate | "elevate your writing" | "improve", or say what changes. |
| bridge the gap | "bridges the gap between design and code" | Say what connects to what ("generates code from design files"). |
| silently fail / quietly break | "the job silently fails" | "fails without an error message" only when the mechanism is clear; otherwise "fails without anyone noticing". Keep the breadth of "silently": do not claim there is no log if the original does not say so. |

---

## 2. Stock constructions

| Construction | Example | Natural form |
|---|---|---|
| It's not X, it's Y | "It's not just a tool, it's a philosophy." | When nobody would think X, delete X: "It's a way of working." When X corrects a likely misreading, keep the negation in one sentence: "The cause was DNS, not the cache." Never turn X into an addition ("both X and Y"). |
| Not only X, but also Y | "not only faster but also more reliable" | Fine when both halves carry weight. When "not only" only inflates, "faster and more reliable". |
| The X? Y. | "The result? A 40% drop in errors." | "Errors dropped by 40%." Keep in promo, slides and scripts. |
| Here's the thing / Here's why / Here's what you need to know | "Here's the thing: caching is hard." | Delete the announcement: "Caching is hard." |
| What makes X Y is Z | "What makes this approach powerful is its simplicity." | "This approach works because it is simple" only if the original makes that causal claim; otherwise "This approach is simple." |
| X is more than just Y | "This is more than just a library." | Say what more it is, from the original; if nothing, delete. |
| Whether you're X or Y | "Whether you're a beginner or an expert, ..." | Delete when the sentence works for everyone anyway. |
| From X to Y | "from startups to enterprises" | Keep if both ends are real; delete if it only signals breadth. |
| Triplets of adjectives | "fast, reliable, and scalable" | Keep only the adjectives the original supports with facts. Do not delete facts. |
| em dash splice | "The fix — which took two days — was simple." | "The fix, which took two days, was simple." Choose punctuation that keeps the same scope. Ranges (2019–2021) stay. |
| Colon reveal | "The answer: simplicity." | "The answer is simplicity", or fold into the previous sentence. |
| Rhetorical question opener | "But what does this mean for developers?" | Delete and state the answer, unless the document type keeps it. |
| Cleft list | "What changed was the UI, the reports, and the alerts." | "The UI, the reports, and the alerts changed", unless an earlier sentence set up "something changed". |

---

## 3. AI vocabulary

Words that appear far more often in AI text than in human text of the same kind. Review them in context; keep any that the field uses as a term.

| Word | Example | Candidates |
|---|---|---|
| delve, tapestry, testament | "a testament to the team's dedication" | "shows the team's dedication", or state the evidence. |
| pivotal, crucial, vital, paramount | "plays a pivotal role" | "is central to", "matters for", or say what depends on it. Keep "crucial" when the original says it is required. |
| seamless(ly) | "seamless integration" | Say what the user does not have to do ("works without extra configuration"), only from the original. |
| robust | "a robust solution" | Say what it withstands. Keep "robust" in statistics and control engineering. |
| leverage (verb) | "leverage our expertise" | "use". Keep the financial noun. |
| realm, landscape, sphere | "in the realm of AI", "the evolving landscape" | Usually delete: "in AI". Keep "threat landscape" if the field uses it. |
| embark, journey | "embark on a journey" | "start". Keep literal journeys. |
| foster, cultivate | "foster collaboration" | Say what people do. |
| underscore, highlight, showcase | "underscores the importance of" | "shows", or state the importance directly. |
| intricate, nuanced, multifaceted | "an intricate interplay" | Name the parts. |
| holistic, comprehensive | "a holistic approach" | Say what it covers. |
| ever-evolving, fast-paced, cutting-edge, state-of-the-art | "in today's fast-paced world" | Delete the opener. Keep "state of the art" in research papers comparing with prior results. |
| game-changer, revolutionary, groundbreaking | "a game-changing feature" | State the change. In promo, keep energy but ask about unsupported claims. |
| boast | "the app boasts a clean UI" | "has". |
| meticulous(ly) | "meticulously crafted" | Delete or say what care was taken. |
| synergy, alignment (as goal), stakeholders (as everyone) | "drive alignment across stakeholders" | Name the people and what they agree on. Keep "stakeholders" when it is the organization's term. |

---

## 4. Inflated words for ordinary experiences

Do not describe small personal experiences or routine technical choices with grand words: "profound", "transformative", "epiphany", "masterpiece", "symphony", "odyssey", "saga", "quest", "magic", "alchemy", "elegant dance". "Removing the noise of daily life revealed the tool's true essence" → "Away from the usual rush, I could see what the tool is good at." Do not add proper nouns or big lessons that the original does not have.

---

## 5. Words that look concrete but say little

| Word | Example | What to do |
|---|---|---|
| various, numerous, a variety of, a wide range of | "offers various features" | Keep when the original lists none; do not invent examples. If the list follows, delete the word. |
| significant(ly), substantial(ly) | "significantly improved" | Use the number if the original gives one. In papers, keep "significant" only for statistical significance. |
| key, core, essential | "key features", "core concepts" | Delete when every item is called key. |
| valuable insights, actionable insights | "provides valuable insights" | Say what the reader learns. |
| best practices | "follow best practices" | Name the practice if the original does; otherwise keep. |
| optimize, streamline, enhance | "streamline your process" | Say which step got shorter or what changed. |
| empower, enable | "enables teams to scale" | Say what teams can now do. |

---

## 6. Announcements, filler and stock closings

| Pattern | Example | What to do |
|---|---|---|
| Opening frames | "In today's digital age,", "In the ever-evolving world of" | Delete. |
| Signposting | "Let's take a closer look.", "In this article, we will explore" | Delete or merge into the next sentence. Keep a table of contents in long manuals. |
| "It's worth noting that", "It is important to note that" | "It's worth noting that the API is rate-limited." | "The API is rate-limited." If the note marks a warning, use "Note:" only where the document already uses notes. |
| Stock closings | "In conclusion,", "Overall,", "Ultimately,", "At the end of the day," | Delete the phrase; delete the whole closing when it only repeats. |
| Chat residue | "Great question!", "Certainly!", "I hope this helps!", "Feel free to reach out", "Let me know if you have any questions", "As an AI language model" | Delete from documents. In mail, keep a closing the writer would normally use, and keep the original's sign-off. |
| Instructions to the AI left in the text | "Here's a revised version:", "Sure, here is the article:" | Delete. |
| Closing restatements | "By following these steps, you can ensure a smooth deployment." | Delete when the steps already said it; keep a next step or a condition that appears only there. |

---

## 7. Wordy phrases and zombie nouns

| Phrase | Shorter | Caution |
|---|---|---|
| in order to | to | Keep "in order to" when it separates two "to"s. |
| due to the fact that, owing to the fact that | because | |
| at this point in time, at the present time | now, currently | |
| has the ability to, is able to | can | Keep permission vs ability: "is allowed to" is not "can" in a policy. |
| make a decision, reach a conclusion | decide, conclude | |
| conduct an investigation of, perform an analysis of | investigate, analyze | Keep "conduct" when the document is a formal procedure with that wording. |
| provide assistance, offer support | help, support | |
| utilize, utilization | use | Keep "utilization" as a metric (CPU utilization). |
| facilitate | help, make easier, run (a meeting) | |
| a large number of, a majority of | many, most | Keep a number when given. |
| in the event that | if | Keep in contracts that use it consistently. |
| prior to, subsequent to | before, after | Keep in formal documents that use them consistently. |
| with regard to, in terms of | about, for | |
| it should be noted that | (delete) | |

Do not add these phrases yourself in places you rewrite. Keep the document's register: in formal documents, "prior to" may be the house style.

---

## 8. Metaphors that do not hold, and metaphors to keep

In essays and fiction, a metaphor is fine when the reader can tell what is compared with what. Rewrite a metaphor only when pulling out its subject and verb gives a statement that makes no sense and suggests nothing ("the afternoon hugged its knees", "silence tasted of blue static"), or when it stacks two images that conflict ("a tapestry of journeys"). Keep a metaphor that a later sentence explains. In essays, still rewrite metaphorical verbs on technical operations (section 1).

---

## 9. Punctuation habits

- Em dashes (—) and spaced en dashes ( – ) used to splice clauses, especially more than one per paragraph. Replace with commas, parentheses, colons or a period while keeping scope. Keep ranges, keep them in quotations and code, and keep them in fiction where they are the writer's voice.
- Exclamation marks in documentation and reports. Keep them in mail where the writer uses them, in promo, and in dialogue.
- Semicolon chains joining three or more clauses.
- Colons at the end of headings and before a single word ("The answer: simplicity").
- Title Case or sentence case: keep whichever the document uses.

---

## 10. Questions for flagged stock phrases

When lint reports `ai_vocabulary`, `stock_phrase` or `wordy_phrase`, ask:

1. Does the word carry content the sentence needs? If the sentence loses a fact without it, keep it.
2. Is it the field's term? If yes, keep it.
3. Is there a plain word with the same scope and strength? If yes, use it. If the plain word is broader ("check" for "verify against the spec") or weaker, keep the original.
4. Does removing it leave a sentence that only repeats the previous one? Then delete the sentence, after checking that no number or condition appears only there.
5. If you rewrite, does the rewrite add a fact, actor or cause? If yes, do not rewrite; ask.
