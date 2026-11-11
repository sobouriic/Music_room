# AI usage declaration (subject chapter II asks for transparency)

Fill in and keep up to date. You must be able to explain every item below during the defense.

## What AI generated
- First version of the app scaffold (navigation, screens, API layer, mock server), then the merge with the back-end contract,
  the Google PKCE screen, the dark theme, the logo, the music search/preview and the unit tests.
- Tool used: Claude (Anthropic) in a chat.

## What I verified myself (tick when really done)
- [ ] I read `src/api/types.ts`, `mockApi.ts`, `httpApi.ts` and can explain the hybrid real/mock switch.
- [ ] I can explain the PKCE flow and why the final address is pasted manually.
- [ ] I can explain optimistic concurrency (`version`, 409) and the one-vote rule.
- [ ] I ran the app on a phone against the real back-end and tested every screen.
- [ ] I reviewed the code with my teammate and we changed: ______________________

## What I changed or decided
- ______________________
