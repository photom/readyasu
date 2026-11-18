# Email and chat (mail)

See also: register.md, domains/business.md
Lint rules exempted: emoji, exclamation, chat_residue (closing courtesies only)

## 1. Normal forms (do not change)

- The writer's greeting and sign-off, "Thanks!", "Hope you're well", emoji the writer uses with this reader.
- Short messages, fragments in chat, contractions.
- Closing courtesies ("Let me know if you have any questions", "Thanks in advance") are normal in mail; lint does not report them for this type.

## 2. Still fix

- Chat residue that comes from an AI, not the writer ("Certainly! Here's a draft email:", "I hope this email finds you well" when the writer never writes that way and asks for a natural tone).
- Requests buried at the end: move the request and its deadline up only if the order does not change the meaning, and keep them together.
- Over-apologizing that the original does not have. Do not add apologies or thanks.

## 3. Length and omissions

- Keep every date, amount, attachment mention and request.

## 4. Examples (synthetic)

| Original | Handling |
|---|---|
| Sure! Here's a polished version of your email: | Delete (AI residue) |
| Hi Sam, quick one: can you send the Q3 numbers by Thu? Thanks! | Keep |
