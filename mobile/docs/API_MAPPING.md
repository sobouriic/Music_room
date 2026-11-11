# How the app talks to the back-end

The contract is the `ApiClient` interface in `src/api/types.ts`. `src/api/httpApi.ts` implements it against the real API
(authoritative docs: `backend/docs/openapi.json`, `backend/docs/MUSIC_INTEGRATION.md`). `src/api/mockApi.ts` implements the same
interface in memory for demos and unit tests. Settings > "Use mock data" switches between them.

| App method | Back-end |
|---|---|
| register / verifyEmail / login / logout / forgotPassword / resetPassword | `/auth/...` |
| googleStart / googleExchange / googleLink | `/auth/google/start`, `/exchange`, `/link` (PKCE) |
| getMe / updateProfile | `GET`/`PATCH /users/me` |
| searchTracks | `GET /tracks/search` (Deezer, searched by the server) |
| listEvents / getEvent / createEvent | `GET /events`, `GET /events/{id}`, `POST /events` (`geo_rule` for the place and time license) |
| suggestTrack | `POST /events/{id}/tracks {deezer_id, base_version}` (latest version fetched first) |
| voteTrack / unvoteTrack | `POST` / `DELETE /events/{id}/tracks/{track}/votes` (`{lat,lng}` for geo events) |
| advanceEvent | `POST /events/{id}/advance` (organizer) |
| setEventInvites / setPlaylistInvites | `POST`/`DELETE /{collection}/{id}/invitations` (each change on the latest version) |
| listPlaylists / createPlaylist / getPlaylist | `/playlists` |
| addPlaylistTrack | `POST /playlists/{id}/tracks {deezer_id, base_version}` |
| movePlaylistTrack / removePlaylistTrack | `POST .../tracks/move`, `DELETE .../tracks/{id}` with the version the user SAW (stale = 409) |
| searchUsers / listFriends / listFriendRequests | `/users/search`, `/friends`, `/friends/requests` |
| sendFriendRequest / acceptFriendRequest / removeFriend | `POST /friends/requests`, `POST /friends/{id}/accept`, `DELETE /friends/{id}` |
| listInvitations / acceptInvitation | `GET /invitations`, `POST /{collection}/{id}/invitations/accept` |
| listDelegations / registerDevice / setDelegation / controlDevice | `GET`/`POST /devices`, `PUT /devices/{id}/delegation`, `POST /devices/{id}/control` |
| subscribe | WebSocket `/ws/event|playlist|device/{id}`: first frame `{"access_token"}`, server answers `ready`, then `*_changed`; the screen refetches over REST |

Notes
- Track ids in the app are the server's queue-entry UUIDs; `deezerId` is the catalog id. Free-text tracks only exist in demo mode.
- Names of friends come from `/users/{id}/public` (cached). People find each other by display name, so set one in the profile.
- The place and time rule is checked by the server clock and distance. The phone only reports its position (it can be spoofed, as the back-end docs say).
