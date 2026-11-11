# Testing on iOS and Android simulators

From the repository root, keep `make backend` running in one terminal. You can
also keep `make dev` running if you want the browser app on port 8081.

Start your virtual iPhone before using the iOS commands below. Android commands
reuse one connected device or start the only saved emulator and wait for boot.
If multiple virtual phones exist, choose one with
`make android ANDROID_AVD=YOUR_AVD_NAME` (or `make android-build` with the same option).
If multiple devices are connected, use `ANDROID_SERIAL=emulator-5554` to select one.
Offline/unauthorized devices need to be restarted or unlocked/authorized first.

| Command | Purpose |
| --- | --- |
| `make ios` / `make ios-dev` | Open the installed development app on iOS, localhost port 8082; no rebuild. |
| `make android` / `make android-dev` | Open the installed development app on Android, port 8083 forwarded through ADB; no rebuild. |
| `make ios-build` | Build/install the native iOS development app and start Metro. |
| `make android-build` | Build/install the native Android development app and start Metro. |

`make` / `make help` shows the command list. `make ios-go` and `make android-go`
explicitly open Expo Go; they cannot test this app's Google callback. The Makefile
inside `mobile/` forwards to the root commands so the names have the same meaning.
Android native builds select installed JDK 21 instead of unsupported Java 27;
on other machines set `ANDROID_JAVA_HOME` to the JDK 21 directory.
Make also supplies `ANDROID_HOME` and `ANDROID_SDK_ROOT` to Expo/Gradle; defaults
are `~/Library/Android/sdk` on macOS and `~/Android/Sdk` on Linux. For a different
installation, use `make android-build ANDROID_HOME=/path/to/Android/sdk`.
The first build may download the SDK platform/build-tools/NDK requested by Expo;
having an API-37 emulator alone does not install all API-36 build components.

Run iOS and Android commands in separate terminals. Both use the same API and
database. Android forwards API port 8001 through ADB, so both apps can use
`http://localhost:8001` in Backend settings with mock data off. Previously saved
settings override the defaults supplied by Make. These commands target local
simulators/emulators, not a phone on another computer or network.

## Google sign-in

Use `make ios-build` or `make android-build` for Google authentication. Expo Go
cannot register the app's `musicroom://oauth` callback. Initial builds download
native dependencies and take longer than opening Expo Go. Xcode with an iOS
runtime is required for iOS; Android Studio/SDK and a JDK are required for Android.

Google opens a system browser authentication session. After sign-in, the backend
callback sends an HTTP redirect for native attempts to `musicroom://oauth?code=...&state=...`.
The app validates state, exchanges the code with its PKCE verifier, and starts
the same authenticated session used by password login. Cancellation leaves the
user signed out and allows retry. If the OS terminates the app during sign-in,
start a new attempt.

The Google Console redirect URI must still match backend `GOOGLE_REDIRECT_URI`,
locally `http://localhost:8001/api/v1/auth/google/callback`. Do not register
`musicroom://oauth` as the Google web-client redirect: it is the backend-to-app
return link. Localhost works here on iOS Simulator and on Android with the ADB
forwarding set by Make. Physical devices need a reachable backend callback,
normally HTTPS, configured on both the server and Google Console.

Browser attempts keep returning to the website configured by
`GOOGLE_WEB_RETURN_URL` (default `http://localhost:8081/`).

## Verify with two accounts

1. Log in as different users on iOS and Android.
2. Send and accept a friend request.
3. Invite the other user to a private playlist or event.
4. Open the resource on both devices and verify live updates.
5. In a development build, verify Google login returns to the app's main screen,
   cancellation works, and Google account linking returns to the profile.

The callback flow has automated regression coverage. A real Google account
sign-in on each native platform must still be tested after building.

## Location voting

Rebuild with `make ios-build` / `make android-build` after changing location
permissions in app.json. Reloading JavaScript does not update native permissions.
Only foreground location is requested; background location is disabled.

- iOS Simulator: select Features → Location → Custom Location.
- Android Emulator: open the … extended controls → Location → set a point.
- Use the same coordinates on both devices, for example latitude 33.57,
  longitude -7.59. Allow location permission when the app requests it.
- Create a Place & time event with a currently active voting window and use
  the creator's location as its venue. Add a track and vote from the other account.
- Move the second simulated location outside the event's 200 m radius: voting
  must fail. Also test denied permission, disabled location services, and a closed
  voting window.

The server enforces distance and time against submitted coordinates. It cannot
prove physical presence from client GPS alone: a modified client can submit
different coordinates. Simulator coordinates are intentionally supported for
development. This is not an anti-spoofing or device-attestation implementation.

## Bonus acceptance checks

### Device audio and delegation

On the phone/browser that should produce sound, open Control, add a device if
needed, then select **Use on this device** on exactly its own row. The binding
is saved per installation, backend and account; existing duplicate device rows
are not automatically assigned to the same phone. Keep the target app open and
online. **Play a track** opens search: choose a result with a Deezer preview.
**Pause** pauses that target; **Stop** clears its playback. Select the track again
to start after pausing/stopping. Audio is a preview, not the full song.

Select an accepted friend's name to delegate that row. The friend can then send
commands from their Control tab while sound comes from the owner's bound target.
**Revoke** removes the friend's permission; it does not stop audio or delete the
device. With no delegate it is disabled. Device commands arrive through WebSocket
updates, with a five-second REST fallback. Browser autoplay restrictions may
require interacting with playback in the target browser first. Validate audible
output on the actual phone/browser separately from mocked audio-player tests.

- Plans: choose Premium in Profile → Manage subscription. No payment is taken.
  Create/edit a playlist, switch to Free, and confirm online editing still works.
  Offline saving/synchronization must be refused and cached copies cleared.
- Offline: while online on Premium, open a playlist and Save for offline editing.
  Open Offline playlists, disconnect network, reorder/remove tracks, and restart
  the app. Restore connectivity and Sync changes. Repeat with another user editing
  the server playlist while offline: a conflict must preserve the draft and must
  not overwrite their changes. Logout/downgrade clears local saved copies.
  Verify that the cached Premium plan and saved tracks survive an offline
  restart. Device control should explain that a connection is required. A failed
  sync must keep the draft; reconnect and use Refresh connection before retrying.
- Nearby notifications: rebuild with the notification plugin. Create a public
  Place & time event with a current time window and matching venue coordinates.
  Open Live → Nearby event alerts → Enable nearby alerts and allow permissions.
  Confirm a local phone alert. Check that a private/far-away/closed event does not
  appear and repeats do not notify again for 30 minutes. Simulator GPS can test
  filtering; validate the native banner on a phone too. This is foreground-only,
  with no Bluetooth or remote push service.
  Android uses a high-importance channel for visible banners; iOS enables
  foreground banners and sound. Allow system notifications and disable Focus /
  Do Not Disturb during this check. Web requests browser notification permission
  from Enable nearby alerts; use localhost or HTTPS (a plain LAN HTTP address
  cannot request browser notifications). All three platforms also show an
  actionable in-app alert if system notifications are denied or unavailable.
  Repeated system alerts for the same event are suppressed for 30 minutes.
  After enabling, navigate to Library or Profile: the global nearby banner and
  minute-by-minute checks must continue while the app is active. The enabled
  setting is saved per account/backend and restored on restart; permission is
  requested only from the enable button, not automatically on startup.

Audio remains Deezer previews. Offline mode saves playlist metadata/drafts, not
full songs. These hands-on tests are separate from the automated test results.

## Missing native module at startup

If a client reports `Cannot find native module ExpoTopicSubscriptionModule`, its
installed native runtime does not match the current notification dependency.
The app loads only the local-notification functions when alerts are enabled;
it avoids the SDK-57 package entry point that eagerly loads remote topics.
If local native APIs are unavailable, nearby discovery still runs without banners. Rebuild the development app once to use
notifications. Restart Metro if it still serves the old crash, then open the
installed **Music Room** app, not Expo Go. Afterwards use the fast `make android`
or `make ios` command. Do not rebuild for ordinary TypeScript/UI changes.

Google login updates the active session immediately; optional offline-cache writes
do not delay entering the main screen. Browser callbacks arriving after startup
are processed on hash/page return too. The anonymous login route is absent from
the signed-in navigator, so it cannot remain open after login; account linking
uses its own route. No manual refresh or native rebuild is needed for these JS changes.

## Real phone with Expo Go

1. Connect the phone and computer to the same Wi-Fi and install Expo Go on the phone.
2. Keep `make backend` running in terminal 1.
3. In terminal 2 run `make phone`. It starts Metro in LAN mode on port 8084, detects
   the computer IP and supplies that address to the API client. If detection fails,
   run `make phone PHONE_IP=YOUR_COMPUTER_LAN_IP`.
4. Scan the QR code using Expo Go on Android or Camera on iPhone. Use an Expo Go
   version compatible with this project's Expo SDK.
5. If saved Connection settings still point to localhost, set the API address to
   the one printed by Make (for example `http://192.168.1.10:8001`) with mock mode off.
   From the phone browser, that address plus `/api/v1/health` should return `ok`.

Phone commands do not launch an emulator or use ADB port forwarding. Expo Go can
test password login, profiles and service screens, subject to its bundled native
module support. Google sign-in needs the Music Room development app installed
on the physical phone, then `make phone-dev` (also on port 8084). An iOS Simulator
build cannot be installed on an iPhone; a device build/signing is needed there.

For native Google on a physical phone, the backend Google redirect must be
reachable from that phone's browser and registered in Google Console. A callback
using localhost points to the phone itself over Wi-Fi. Use a configured HTTPS
callback for this flow; changing the Metro QR/API URL does not change Google's
registered redirect URI. `make phone-dev` by itself does not install a native app
or configure a Google callback.

If the local network isolates Wi-Fi clients, neither LAN Metro nor the API can
be reached directly; use a network allowing device-to-device access. An Expo-only
tunnel would expose Metro, not automatically your backend.
