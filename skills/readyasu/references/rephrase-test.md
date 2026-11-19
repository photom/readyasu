# The rephrase test

Details of the rephrase test in SKILL.md section 2, Step 2. Read this when you are unsure whether to fix or keep a place that matched a section 1 pattern, when you fix a negative contrast, and when you are unsure how to report what you kept.

## 1. Procedure

For each place that matched a pattern, decide in this order.

1. Write one candidate rewrite.
2. Compare the original and the candidate on the six points in section 2. Also check that the sentence's function (fact, opinion, request and so on; SKILL.md "Top rule: keep the meaning") is the same.
3. If any point changes, discard the candidate and keep the original. Do not keep rewriting until a candidate passes.
4. If all six are the same, take the candidate.

Exception: a fill or correction that meets the conditions in fact-recovery.md section 3 adds to "numbers, names and timing" or "who does what", but is not discarded for that alone. The other five points must stay the same.

For a candidate that deletes a sentence or phrase, do not compare sentence by sentence; check whether the deleted part holds a claim, condition, number or deadline found nowhere else. If it does, keep it or move it into the body with the same meaning. Instructions to an AI, restating closings and stock sign-offs left in the body can go when they hold nothing for the reader (slop-catalog.md section 6).

## 2. The six points

| Point | Same when | Example of a candidate that changes it (synthetic; discard it) |
|---|---|---|
| What it is about | Same topic and point; not swapped for another concept | The heart of this design is simplicity → The goal of this design is simplicity |
| What it affirms and denies | Nothing affirmed becomes denied or the reverse; no negation appears or disappears (for removing X from "not X but Y", see section 3) | The new process did not eliminate rework → The new process eliminated rework |
| Who does what to whom | Same actor, same recipient, same direction (asking vs explaining) | Dana asked Lee to review it → Dana reviewed it |
| Scope and conditions | Limits such as "some", "only when", "up to" and the action they attach to are the same | Only admins can delete → Users can delete |
| Strength of assertion, hedge and hearsay | Same assertion, hedge, hearsay, ability, permission and obligation | The cause appears to be a misconfiguration → The cause is a misconfiguration |
| Numbers, names and timing | Same numbers, units, names, dates and periods such as "since last month" | About 30 inquiries → 30 inquiries |

- A candidate that only swaps a word and keeps all six points passes ("I burned the whole afternoon" → "I wasted the whole afternoon", keeping the regret).
- A candidate that replaces plain verbs with Latinate nouns ("we checked" → "verification was performed") becomes stiffer even when the six points hold. Do not add zombie nouns or Latinate words in places you rewrite (slop-catalog.md section 7). Conversely, keep the words the document normally uses ("configure", "deploy"); do not swap them for casual verbs that broaden meaning ("verify" → "look at").

## 3. Negative contrast (not X, but Y)

Negative contrast flips the claim more easily than other patterns. For a candidate that removes X, check these instead of "what it affirms and denies" (the other five points as in section 2).

1. Write a sentence that says only Y and see whether the claim is the same.
2. If it changes, keep X. Here X corrects a reader's assumption or a hypothesis that testing ruled out. Keep the original, and only smooth the wording when you can name a misreading or difficulty. A negation and affirmation split into two sentences ("It wasn't X. It was Y.") becomes one sentence that keeps X ("It was Y, not X"); since X stays, the claim does not change.
3. If it does not change, write only Y.
4. After fixing, check that the removed X did not move into an affirmative sentence. If X shows up as a purpose or priority ("for X and Y", "X as well as Y", "first, X"), the fix is wrong. The diff reports this when the denied word appears in an affirmative sentence with words such as "focus", "priority", "first", or joined to Y with "and", "as well as", "both" (see review-points.md). Some correct rewrites also trigger it ("First, reduce X"), so read whether X moved to the side of the goal. Not every form is caught; compare the sentences even without a finding.
5. If you cannot decide, keep it.

Technical write-ups often say "We suspected X, but it was Y". Removing negative contrast everywhere makes such write-ups worse.

### Keep (synthetic)

| Original | Why keep |
|---|---|
| The slowdown came from the office network, not the database. | Corrects the cause readers are likely to suspect |
| We first suspected a memory leak, but the process had hit the open-file limit. | States a hypothesis that testing ruled out and the real cause |
| I'm not trying to assign blame; I want to understand what happened. | Sets how the reader should take the message |
| These numbers are orders received, not revenue. | Corrects an easily misread meaning |
| The new version isn't faster; we only changed how the wait is displayed. | Denies a likely misunderstanding of the effect |
| It's not only a failure; it's also a test of one condition. | "Not only ... also" sentence; keep as one sentence |
| This delay isn't our office connection. Teams in other offices saw the same delay at the same time. | The second sentence gives evidence for the denial, not a "then what"; do not merge |

### Fix (synthetic)

| Original | Fixed | Why |
|---|---|---|
| What you need isn't magic, it's a morning checklist. | What you need is a morning checklist. | No reader expects magic; removing it keeps the claim |
| This tool doesn't collect opinions — it collects operation logs. | This tool collects operation logs. | Only when nothing nearby suggests it collects opinions; otherwise keep |
| We didn't need a new tool. We needed a shared way to use the old one. | We didn't need a new tool; we needed a shared way to use the old one. | Two-sentence contrast; keep X and join (also in essays; not in fiction narration or dialogue, or short promo runs) |
| It's not just a library. It's a philosophy. | (ask) | What "philosophy" means is not in the text; ask instead of guessing |
| (The previous sentence is about the load balancer's connection limit.) Once the limit was exceeded, 503 errors were returned. | Once the limit was exceeded, the load balancer returned 503 errors. | Fills in a subject the surrounding sentences establish; the six points stay the same |

### Wrong fixes (synthetic)

| Original | Wrong fix | What went wrong |
|---|---|---|
| We chose clarity over cleverness. | We chose both clarity and cleverness. | The denied side became an addition |
| The fix is not a workaround but a root-cause fix. | The fix addresses the workaround and the root cause. | X moved to the affirmative side |
| Don't optimize first; measure first. | First, optimize and measure. | The order and the denial both flipped |

## 4. How to report

- Under "What changed", write the original wording, the revised wording and the reason.
- Under "AI-like wording kept", write the wording and which point would have changed ("kept 'not the cache': it corrects the likely suspicion").
- Do not list a discarded candidate under "What changed", and do not report a change you did not make.
- Do not report every pattern you looked at; report only those a reader might expect you to have changed.
