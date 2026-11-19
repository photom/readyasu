# Email and chat (mail)

See also: register.md, domains/business.md
Lint rules exempted: emoji, exclamation, chat_residue (courtesies and interjections only)

## 1. Normal forms (do not change)

- The writer's greeting and sign-off, "Thanks!", "Hope you're well", emoji the writer uses with this reader.
- Short messages, fragments in chat, contractions.
- Courtesies, offers and closings ("Let me know if you have any questions", "Thanks in advance", "Here's a draft of the agenda", "Would you like me to book the room?") and interjections ("Sure!", "Of course!") are normal in mail; lint does not report them for this type.

## 2. Still fix

- Chat residue that comes from an AI, not the writer ("Certainly! Here's a draft email:" above the mail, "I hope this email finds you well" when the writer never writes that way and asks for a natural tone). Lint does not report the interjections and offers in mail, so read the first and last lines yourself.
- Requests buried at the end: move the request and its deadline up only if the order does not change the meaning, and keep them together.
- Over-apologizing that the original does not have. Do not add apologies or thanks.

## 3. Length and omissions

- Keep every date, amount, attachment mention and request.

## 4. Examples (synthetic)

| Original | Handling |
|---|---|
| Sure! Here's a polished version of your email: | Delete (AI residue) |
| Hi Sam, quick one: can you send the Q3 numbers by Thu? Thanks! | Keep |
