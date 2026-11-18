# Incident report (incident)

See also: domains/tech.md, domains/business.md
Lint rules exempted: excess_list

## 1. Normal forms (do not change)

- Timelines as lists with timestamps and time zones.
- Impact, root cause, contributing factors, action items with owners and due dates.
- Blameless wording ("the deploy script did not check ...") and passive voice for unknown actors.
- Hedges about causes still under investigation ("appears to", "likely").

## 2. Still fix

- Dramatic words ("catastrophic", "nightmare", "perfect storm") when the impact section gives the facts.
- Added certainty: do not turn "likely caused by" into "caused by".
- Added commitments: do not add "this will never happen again" or "we guarantee".
- Times: never change a timestamp, duration or time zone.

## 3. Length and omissions

- Keep every timeline entry and every action item.

## 4. Examples (synthetic)

| Original | Handling |
|---|---|
| A perfect storm of misconfigurations silently brought down the API. | "Several misconfigurations together made the API unavailable without anyone noticing"; write "without triggering an alert" only if the report says no alert fired, and give a count only if the report gives one |
| Root cause: likely a stale DNS cache (under investigation). | Keep |
