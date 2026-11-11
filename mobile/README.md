# Music Room: mobile app

React Native (Expo) + TypeScript. Android and iOS from one codebase, plus a browser build for testing.
The app is only a **remote control**: every rule and every piece of data lives on the back-end (subject V.5).

## Run
    cp .env.example .env      # never commit .env
    make install
    make help                 # commands forwarded to the root Makefile
    make android              # installed Android development app, no rebuild
    make ios                  # installed iOS development app, no rebuild
    make test                 # unit tests (demo server rules, PKCE helpers)
    # with the back-end running: API_URL=http://localhost:8001 MAIL_DIR=../backend/.dev-mail npm test -- integration

Back-end address: Login screen > "Backend settings" (or Profile > "Backend settings"). "Use mock data" runs without a server.

## What is implemented (subject chapter V)
| Subject | In the app |
|---|---|
| V.1 User | e-mail/password sign-up, e-mail verification, forgot/reset password, Google sign-in (PKCE), link Google, profile with public / friends-only / private / music-preferences sections |
| V.2.1 Music Track Vote | public/private events, licenses (everyone / invited only / place and time), suggest + vote, ranking by votes, real-time refresh, invitations |
| V.2.2 Music Control Delegation | per-device list, give or revoke control for each friend, register this phone |
| V.2.3 Music Playlist Editor | public/private playlists, licenses (everyone / invited editors), add / move / remove tracks, version check against concurrent edits, invitations |
| Bonus: Free vs Paid | two server-managed offers: online playlist creation/editing is Free; only offline saving, editing and sync require Premium. See `docs/SUBSCRIPTION_BACKEND.md` |
| V.5 Mobile application | configurable back-end address, Google authentication, no business rule in the client |
| V.6 Securing | tokens in the device secure store, automatic single-flight refresh, every request carries platform / device / app version headers for the server logs |
| External SDK | Deezer catalog (searched through the back-end) for search, artwork and 30 s previews, played with `expo-audio`. Demo mode uses the iTunes Search API |

## Real back-end vs demo mode
`src/api/httpApi.ts` sends **every** service to the real back-end (see `docs/API_MAPPING.md`). `src/api/mockApi.ts` is an in-memory
demo server that enforces the same rules (visibility, licenses, one vote per track, version conflicts) and is covered by unit tests.
Settings > "Use mock data" switches between them. Because the app only talks through the `ApiClient` interface, the screens do not know which one they use.

## Structure
    src/api/types.ts      the contract (ApiClient interface)
    src/api/mockApi.ts    in-memory demo server with the business rules
    src/api/httpApi.ts    real client (REST + JSON, token refresh, WebSocket invalidations)
    src/music/            catalog search, preview player, search UI
    src/screens/          one file per screen
    src/__tests__/        unit tests + end-to-end test against the real back-end

## Decisions to be able to defend
- **React Native / Expo**: one TypeScript codebase for Android and iOS, no emulator needed (Expo Go), web build for the responsive bonus.
- **REST + JSON**: simple, cacheable, documented with Swagger on the back-end, easy to mock. Real-time uses a WebSocket per channel; the app only refetches when told something changed.
- **Server is the truth**: the app never decides who may vote or edit. It sends what the phone knows (position, version it saw) and shows the server's answer.
- **Concurrency**: playlist edits carry the version the user saw; a stale edit gets 409 and the app reloads. A track can be voted once per user, enforced server-side (409).
- **Contract first + mock**: the front-end was built before the server existed, against an explicit interface. The mock rules are covered by unit tests.
- **Security on the client**: tokens in `expo-secure-store` (localStorage on web only), refresh tokens are single-use so refreshes are serialized, no secret is stored in the repo (`.env` is ignored).
- **External SDK**: Deezer is called by the server only (no Deezer key or secret in the app); the catalog only provides metadata and previews. Voting, ordering, permissions and storage are ours (subject warning, chapter III).

## Known limits (be upfront in the defense)
- Google login returns automatically on the website. On a phone it is semi-manual, because the back-end redirect is `http://localhost:8001/...`, which a phone cannot reach, so the user pastes the final address. An HTTPS redirect that opens the app is the production fix.
- Previews play on the local phone only; the shared queue is on the server. There is no full-length playback.
- Facebook sign-in is not implemented (the subject says "Facebook or Google").
- Bonuses are not implemented (offline mode, subscription, iBeacon).
