# Bonus features and validation

All API paths below have the `/api/v1` prefix and require a Bearer access token.
Shared database migrations live in `backend/alembic/versions/`.

## Free / Premium demo

| Endpoint | Request | Response / behavior |
| --- | --- | --- |
| `GET /subscription` | None | `{ "plan": "free", "billing_mode": "demo" }` |
| `PUT /subscription` | `{ "plan": "premium" }` or `free` | Persists the caller's plan; no payment is collected. |

New accounts start Free. Online playlist creation/editing, voting, device control,
friendships and invitations are available on both plans. Playlist access/edit
licenses still apply: private playlists require an invitation and invited-only
editing excludes users without permission.

Only offline saving, editing cached drafts and offline synchronization require
Premium. Downgrading preserves online editing but removes local offline copies
when the app learns of the downgrade. User-row locks serialize plan changes
with offline synchronization. In `APP_ENV=production`, the demo switch is disabled
(`403 billing_required`); no billing provider is implemented.

## Offline playlists

Premium users can save up to 20 playlist snapshots in the app and reorder/remove
existing tracks offline. There is no offline catalog search, account creation,
new-track download or full-song audio cache. Deezer preview playback remains online.

`POST /playlists/{resource_id}/offline`:

```json
{
  "mutation_id": "22222222-2222-4222-8222-222222222222",
  "base_version": 3,
  "track_ids": ["33333333-3333-4333-8333-333333333333"]
}
```

Returns the updated playlist. `track_ids` contains the desired ordering/subset of
the tracks from the snapshot. The server validates Premium, visibility, edit
permission and version, then applies the entire edit in one transaction.

- Retry the same mutation ID/body after a lost response: the original result is
  returned without another version change.
- `409 version_conflict`: server data changed. Keep the local draft for review;
  never silently overwrite or automatically rebase it.
- `409 mutation_conflict`: that ID was reused for a different request.
- `401`: authentication must be restored; keep pending drafts while recovering
  the session. A confirmed invalid refresh session logs the user out.
- `403`, `404`: subscription or resource access has been rejected;
  the client discards the saved resource on confirmed rejection.
- `422`: invalid/duplicate/unknown track IDs.

Offline login restoration requires the same locally saved refresh-token
fingerprint and a Premium entitlement verified within seven days. Cache entries
are scoped to server/account and deleted on logout/account changes. Tokens remain
in the existing token store; this metadata cache contains no raw credentials.
Immediate remote revocation cannot be detected while fully offline. Private
metadata can remain on a disconnected device until reconnect, expiry or logout.

## Nearby-event phone notifications

`GET /api/v1/events/nearby?lat=33.57&lng=-7.59&radius_m=1000`
returns up to 30 public Place & time events inside the search radius, nearest
first. Only events with an active time window and an enabled owner are returned.
Private events are never disclosed, even to invited users. Radius is between
50 m and 100 km; the default is 1 km. Coordinates are validated and not persisted.
The lookup checks at most 500 latitude-bounded candidates per request; this is a
bounded prototype query, not a global geospatial search index.

In the app, open **Live → Nearby event alerts → Enable nearby alerts**. The
app requests foreground location and local-notification permission, checks once
per minute across the application while it is open and active, and schedules an immediate
local phone notification for matching events. Repeats are suppressed for 30 minutes
per account/server. If notifications are denied, nearby events still appear in
the global in-app banner and event list. Web also requests browser notifications
on localhost/HTTPS. The enabled preference is saved per account/server and
restored without prompting again on startup.

No Bluetooth hardware, second phone, Firebase or APNs setup is required. There is
no background location tracking and no server push while the app is closed.
GPS notifications are a convenience feature, not Bluetooth/IoT integration or
proof of physical presence. The speaker client below is the separate IoT option.
The experimental Bluetooth registry was removed; its historical migration and
cleanup migration are kept so databases that already applied it can upgrade.

### Test

1. Rebuild using `make ios-build` or `make android-build` to include native
   notification configuration. The targets now prebuild before compiling.
2. Create a public Place & time event with an active time window and venue set
   using your current location.
3. Open Nearby event alerts, enable them and allow location/notifications.
4. Verify a nearby result and phone notification. Repeated checks within 30
   minutes must not create duplicate alerts for that event.
5. Move the simulated location more than 1 km away: the event must disappear.
   A private event, closed time window or disabled event owner must not appear.

You can test lookup using simulator GPS coordinates. Test actual notification
presentation and permission denial on the phone too; OS notification settings
may suppress banners.

## Current evidence

Automated tests cover plans, Free online editing, Premium-only offline replay/conflicts/revoked
access, nearby privacy/time/distance filtering, notification permissions and
repeat suppression, native permission generation and offline cache isolation.
Native builds, airplane-mode restart/sync, notification presentation and audible
speaker playback still need hands-on validation. Automated checks do not establish
that the entire subject has passed evaluation.

## Speaker client for delegated playback

`bonus/device_player.py` executes the server's device state on a computer or
Raspberry Pi with speakers and FFmpeg's `ffplay` installed. It signs in as the
owner, creates or reuses a playback device, authenticates its WebSocket with the
first frame, fetches authoritative state, and applies play/pause/stop locally.
It refreshes the session when needed and stops playback on disconnection or
revoked access. It accepts only HTTPS Deezer preview CDN URLs and never invokes
a shell. It plays previews, not full songs.

```sh
cd backend
.venv/bin/python -m bonus.device_player --email your-account@example.com
# Reuse the printed device ID on later runs:
.venv/bin/python -m bonus.device_player --email your-account@example.com --device-id DEVICE_UUID
```

Enter the password at the hidden prompt; credentials are not saved by this
client. Keep it running, delegate the device to an accepted friend in the app,
and test that friend's play/pause/stop commands. Use `--api https://...` for a
remote server. Physical speaker playback still requires a hands-on test because
ffplay/audio hardware are not available in this validation environment.

Voting, playlist editing and per-device delegation have backend routes and tests;
the speaker client supplies command execution for the third service. All three
still need the final multi-user/device acceptance test before grading sign-off.
