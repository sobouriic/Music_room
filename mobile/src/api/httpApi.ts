import { Platform } from 'react-native';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import {
  ApiClient, ApiError, Delegation, DeviceAction, EventPlace, Friend, FriendRequest, PendingInvitation, Plan, Playlist, Profile,
  Tokens, Track, TrackInput, User, VoteEvent,
} from './types';

// ---- shapes returned by the back-end (see backend/docs/openapi.json); snake_case there, camelCase in the app
type ApiUser = {
  id: string; email: string; verified: boolean; has_password: boolean; providers: string[];
  public: { display_name: string; bio: string };
  friends_only: { location: string };
  private: { notes: string };
  music_preferences: string[];
};
type ApiTokens = { access_token: string; refresh_token: string };
type ApiTrack = {
  id?: string; deezer_id: number; title: string; artist: string; preview_url?: string | null; artwork_url?: string | null;
  votes?: number; voted_by_me?: boolean;
};
type ApiResource = {
  id: string; owner_id: string; name: string; visibility: 'public' | 'private'; license: 'open' | 'invited' | 'geo_time';
  version: number; tracks: (ApiTrack & { id: string })[]; current_track?: (ApiTrack & { id: string }) | null;
  geo_rule?: { lat: number; lng: number; radius_m: number; starts_at: string; ends_at: string } | null;
};
type ApiDevice = {
  id: string; owner_id: string; name: string; friend_id: string | null; version: number;
  state?: { action?: string; track?: { title?: string; preview_url?: string } | null };
};
type Collection = 'events' | 'playlists';

const toUser = (u: ApiUser): User => ({
  id: u.id, email: u.email, verified: u.verified, hasPassword: u.has_password, providers: u.providers,
  profile: {
    displayName: u.public.display_name, bio: u.public.bio, location: u.friends_only.location,
    notes: u.private.notes, musicPreferences: u.music_preferences,
  },
});
const toTokens = (t: ApiTokens): Tokens => ({ accessToken: t.access_token, refreshToken: t.refresh_token });
const toTrackInput = (t: ApiTrack): TrackInput => ({
  deezerId: t.deezer_id, title: t.title, artist: t.artist,
  artwork: t.artwork_url ?? undefined, previewUrl: t.preview_url ?? undefined,
});
const toTrack = (t: ApiTrack & { id: string }): Track => ({ ...toTrackInput(t), id: t.id, votes: t.votes ?? 0, votedByMe: !!t.voted_by_me });
const toPlace = (g: NonNullable<ApiResource['geo_rule']>): EventPlace =>
  ({ lat: g.lat, lng: g.lng, radiusM: g.radius_m, startsAt: g.starts_at, endsAt: g.ends_at });
const enc = encodeURIComponent;

async function toError(res: Response): Promise<ApiError> {
  let code: string | undefined;
  let message = res.statusText || `HTTP ${res.status}`;
  try {
    const body = await res.json();
    code = body?.error?.code;
    message = body?.error?.message ?? message;
    const fields: { field: string }[] | undefined = body?.error?.fields;
    if (fields?.length) message += ` (${fields.map((f) => f.field.replace(/^body\./, '')).join(', ')})`;
  } catch {}
  if (res.status === 429) message = `Too many attempts. Retry in ${res.headers.get('Retry-After') ?? 'a few'} seconds.`;
  return new ApiError(res.status, message, code);
}

/** Real client: every service goes to the back-end (REST + JSON, WebSocket for invalidations). */
export function createHttpApi(baseUrl: string): ApiClient {
  const root = baseUrl.replace(/\/$/, '') + '/api/v1';
  let tokens: Tokens | null = null;
  let listener: (t: Tokens | null) => void | Promise<void> = () => {};
  let sessionGeneration = 0;
  let resolveTokens: () => Promise<Tokens | null> = async () => null;
  let connectionListener: (online: boolean) => void = () => {};
  let restoring: Promise<void> | null = null;
  async function ensureTokens() {
    if (tokens) return;
    const generation = sessionGeneration;
    if (!restoring) {
      restoring = resolveTokens().then(saved => {
        if (generation === sessionGeneration && saved) tokens = saved;
      }).finally(() => { restoring = null; });
    }
    await restoring;
    if (generation !== sessionGeneration) throw new ApiError(409, 'The account changed. Please try again.', 'session_changed');
    if (!tokens) {
      await listener(null);
      throw new ApiError(401, 'Please log in again to reconnect your account.', 'reauthentication_required');
    }
  }
  let refreshing: Promise<boolean> | null = null;
  let meId: string | null = null;
  const names = new Map<string, string>(); // user id -> display name

  async function send(method: string, path: string, body: unknown, auth: boolean): Promise<Response> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      // metadata the back-end logs for every action (subject V.6)
      'X-App-Platform': Platform.OS,
      'X-App-Device': Device.modelName ?? 'unknown',
      'X-App-Version': Constants.expoConfig?.version ?? '0.0.0',
    };
    if (auth && tokens) headers.Authorization = `Bearer ${tokens.accessToken}`;
    try {
      const response = await fetch(root + path, { method, headers, signal: controller.signal, body: body === undefined ? undefined : JSON.stringify(body) });
      connectionListener(response.status < 500);
      return response;
    } catch {
      connectionListener(false);
      throw new ApiError(0, `Cannot reach the server at ${baseUrl}. Check the address in Settings and the Wi-Fi.`, 'network');
    } finally {
      clearTimeout(timeout);
    }
  }

  // Refresh tokens are single-use and rotate: serialize refreshes, as the back-end asks.
  function refresh(): Promise<boolean> {
    if (!refreshing) {
      refreshing = (async () => {
        if (!tokens) return false;
        const generation = sessionGeneration;
        const res = await send('POST', '/auth/refresh', { refresh_token: tokens.refreshToken }, false);
        if (generation !== sessionGeneration) return false;
        if (!res.ok) {
          if (res.status === 401) { ++sessionGeneration; tokens = null; await listener(null); return false; }
          throw await toError(res); // A transient failure is not session revocation.
        }
        const next = toTokens(await res.json());
        if (generation !== sessionGeneration) return false;
        tokens = next;
        await listener(tokens);
        return true;
      })().finally(() => { refreshing = null; });
    }
    return refreshing;
  }

  async function req<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
    if (auth) await ensureTokens();
    const generation = sessionGeneration;
    let res = await send(method, path, body, auth);
    if (auth && generation !== sessionGeneration) throw new ApiError(409, 'The account changed. Please try again.', 'session_changed');
    if (res.status === 401 && auth && tokens && (await refresh())) res = await send(method, path, body, auth);
    if (!res.ok) {
      if (auth && res.status === 401 && generation === sessionGeneration && tokens) {
        ++sessionGeneration; tokens = null; await listener(null);
      }
      throw await toError(res);
    }
    return res.status === 204 ? (undefined as T) : res.json();
  }

  // ---- helpers
  async function me(): Promise<string> {
    if (!meId) meId = (await req<ApiUser>('GET', '/users/me')).id;
    return meId;
  }
  async function nameOf(id: string): Promise<string> {
    const cached = names.get(id);
    if (cached) return cached;
    let name = `User ${id.slice(0, 4)}`;
    try {
      const u = await req<{ public: { display_name: string } }>('GET', `/users/${id}/public`);
      if (u.public.display_name) name = u.public.display_name;
    } catch {}
    names.set(id, name);
    return name;
  }
  const friendOf = async (id: string): Promise<Friend> => ({ id, name: await nameOf(id) });

  const fresh = (c: Collection, id: string) => req<ApiResource>('GET', `/${c}/${id}`);
  const invitedIds = async (c: Collection, id: string) =>
    (await req<{ user_id: string }[]>('GET', `/${c}/${id}/invitations`)).map((i) => i.user_id);

  // `detail`: also load the invitation list (owner only), which a list view does not need.
  async function toEvent(r: ApiResource, detail: boolean): Promise<VoteEvent> {
    const mine = r.owner_id === (await me());
    return {
      id: r.id, name: r.name, visibility: r.visibility, license: r.license, version: r.version,
      tracks: r.tracks.map(toTrack), current: r.current_track ? toTrack(r.current_track) : null,
      mine, invitedIds: mine && detail ? await invitedIds('events', r.id) : [],
      place: r.geo_rule ? toPlace(r.geo_rule) : undefined,
    };
  }
  async function toPlaylist(r: ApiResource, detail: boolean): Promise<Playlist> {
    const mine = r.owner_id === (await me());
    return {
      id: r.id, name: r.name, visibility: r.visibility, license: r.license === 'invited' ? 'invited' : 'open',
      version: r.version, tracks: r.tracks.map(toTrack), mine,
      invitedIds: mine && detail ? await invitedIds('playlists', r.id) : [],
    };
  }

  // Invitations bump the resource version, so each change is made on the latest version.
  async function syncInvites(c: Collection, id: string, wanted: string[]): Promise<ApiResource> {
    let r = await fresh(c, id);
    const current = await invitedIds(c, id);
    for (const uid of wanted.filter((x) => !current.includes(x))) {
      await req('POST', `/${c}/${id}/invitations`, { user_id: uid, base_version: r.version });
      r = await fresh(c, id);
    }
    for (const uid of current.filter((x) => !wanted.includes(x))) {
      await req('DELETE', `/${c}/${id}/invitations/${uid}?base_version=${r.version}`);
      r = await fresh(c, id);
    }
    return r;
  }

  async function addTrack(c: Collection, id: string, track: TrackInput): Promise<ApiResource> {
    if (track.deezerId === undefined) throw new ApiError(422, 'Pick the track from the search results.');
    const r = await fresh(c, id); // adding is not order-sensitive, so use the latest version
    return req<ApiResource>('POST', `/${c}/${id}/tracks`, { deezer_id: track.deezerId, base_version: r.version });
  }

  async function toDelegation(d: ApiDevice): Promise<Delegation> {
    const action = (['play', 'pause', 'stop'].includes(d.state?.action ?? '') ? d.state!.action : 'stop') as DeviceAction;
    return {
      deviceId: d.id, deviceName: d.name, mine: d.owner_id === (await me()), version: d.version, action,
      friend: d.friend_id ? await friendOf(d.friend_id) : null, trackTitle: d.state?.track?.title ?? undefined,
      previewUrl: d.state?.track?.preview_url ?? undefined,
    };
  }
  const listDevices = async () => Promise.all((await req<ApiDevice[]>('GET', '/devices?limit=100')).map(toDelegation));
  const getDevice = (id: string) => req<ApiDevice>('GET', `/devices/${id}`);

  const asPlan = (p: unknown): Plan => (p === 'premium' ? 'premium' : 'free');

  const voteBody = (l?: { lat: number; lng: number }) => (l ? { lat: l.lat, lng: l.lng } : {});

  return {
    kind: 'http',
    logActions: async (events) => { await req('POST', '/activity', { events }); },
    getFriendProfile: async (id) => {
      const u = await req<{ public: { display_name: string; bio: string }; friends_only: { location: string } }>('GET', `/users/${id}/friends-only`);
      return { name: u.public.display_name, bio: u.public.bio, location: u.friends_only.location };
    },
    updateEvent: async (e) => toEvent(await req<ApiResource>('PUT', `/events/${e.id}`, {
      name: e.name, visibility: e.visibility, license: e.license, base_version: e.version,
      geo_rule: e.license === 'geo_time' && e.place ? { lat: e.place.lat, lng: e.place.lng, radius_m: e.place.radiusM, starts_at: e.place.startsAt, ends_at: e.place.endsAt } : null,
    }), true),
    updatePlaylist: async (p) => toPlaylist(await req<ApiResource>('PUT', `/playlists/${p.id}`, {
      name: p.name, visibility: p.visibility, license: p.license, base_version: p.version,
    }), true),
    setTokens: (t) => { ++sessionGeneration; tokens = t; meId = null; },
    onTokensChange: (cb) => { listener = cb; },
    onTokensNeeded: (cb) => { resolveTokens = cb; },
    onConnectionChange: (cb) => { connectionListener = cb; },

    // ---- auth + profile
    register: async (email, password) => { await req('POST', '/auth/register', { email, password }, false); },
    verifyEmail: async (token, password) => { await req('POST', '/auth/verify-email', { token, password }, false); },
    resendVerification: async (email) => { await req('POST', '/auth/resend-verification', { email }, false); },
    login: async (email, password) => toTokens(await req<ApiTokens>('POST', '/auth/login', { email, password }, false)),
    logout: async (refreshToken) => { await req('POST', '/auth/logout', { refresh_token: refreshToken }); },
    forgotPassword: async (email) => { await req('POST', '/auth/forgot-password', { email }, false); },
    resetPassword: async (token, password) => { await req('POST', '/auth/reset-password', { token, password }, false); },
    googleStart: async (codeChallenge, intent) => {
      const r = await req<{ authorization_url: string; state: string }>(
        'POST', '/auth/google/start', { code_challenge: codeChallenge, intent,
          platform: Platform.OS === 'web' ? 'web' : 'native' }, intent === 'link');
      return { authorizationUrl: r.authorization_url, state: r.state };
    },
    googleExchange: async (state, code, codeVerifier) =>
      toTokens(await req<ApiTokens>('POST', '/auth/google/exchange', { state, code, code_verifier: codeVerifier }, false)),
    googleLink: async (state, code, codeVerifier) => {
      await req('POST', '/auth/google/link', { state, code, code_verifier: codeVerifier });
    },
    getMe: async () => {
      const u = await req<ApiUser>('GET', '/users/me');
      meId = u.id;
      return toUser(u);
    },
    updateProfile: async (p: Profile) =>
      toUser(await req<ApiUser>('PATCH', '/users/me', {
        public: { display_name: p.displayName, bio: p.bio },
        friends_only: { location: p.location },
        private: { notes: p.notes },
        music_preferences: p.musicPreferences,
      })),

    // ---- catalog (Deezer through the back-end: no Deezer secret or key in the app)
    searchTracks: async (q) =>
      q.trim() ? (await req<ApiTrack[]>('GET', `/tracks/search?q=${enc(q.trim())}&limit=20`)).map(toTrackInput) : [],

    // ---- Music Track Vote
    listEvents: async () => Promise.all((await req<ApiResource[]>('GET', '/events?limit=100')).map((r) => toEvent(r, false))),
    createEvent: async (name, visibility, license, place) => {
      const geo_rule = license === 'geo_time' && place
        ? { lat: place.lat, lng: place.lng, radius_m: place.radiusM, starts_at: place.startsAt, ends_at: place.endsAt } : undefined;
      return toEvent(await req<ApiResource>('POST', '/events', { name, visibility, license, geo_rule }), true);
    },
    getEvent: async (id) => toEvent(await fresh('events', id), true),
    nearbyEvents: async ({ lat, lng }) => Promise.all((await req<ApiResource[]>('GET', `/events/nearby?lat=${lat}&lng=${lng}`)).map(event => toEvent(event, false))),
    setEventInvites: async (id, userIds) => toEvent(await syncInvites('events', id, userIds), true),
    suggestTrack: async (id, track) => toEvent(await addTrack('events', id, track), true),
    voteTrack: async (id, trackId, location) =>
      toEvent(await req<ApiResource>('POST', `/events/${id}/tracks/${trackId}/votes`, voteBody(location)), true),
    unvoteTrack: async (id, trackId, location) =>
      toEvent(await req<ApiResource>('DELETE', `/events/${id}/tracks/${trackId}/votes`, voteBody(location)), true),
    advanceEvent: async (id, currentTrackId) => {
      const r = await fresh('events', id);
      return toEvent(await req<ApiResource>('POST', `/events/${id}/advance`, { base_version: r.version,
        ...(currentTrackId ? { expected_current_track_id: currentTrackId } : {}) }), true);
    },

    // ---- Music Playlist Editor
    listPlaylists: async () => Promise.all((await req<ApiResource[]>('GET', '/playlists?limit=100')).map((r) => toPlaylist(r, false))),
    createPlaylist: async (name, visibility, license) =>
      toPlaylist(await req<ApiResource>('POST', '/playlists', { name, visibility, license }), true),
    getPlaylist: async (id) => toPlaylist(await fresh('playlists', id), true),
    setPlaylistInvites: async (id, userIds) => toPlaylist(await syncInvites('playlists', id, userIds), true),
    addPlaylistTrack: async (id, track) => toPlaylist(await addTrack('playlists', id, track), true),
    // moves and removals use the version the user SAW: a stale one is refused with 409
    removePlaylistTrack: async (id, trackId, baseVersion) =>
      toPlaylist(await req<ApiResource>('DELETE', `/playlists/${id}/tracks/${trackId}?base_version=${baseVersion}`), true),
    movePlaylistTrack: async (id, from, to, baseVersion) =>
      toPlaylist(await req<ApiResource>('POST', `/playlists/${id}/tracks/move`,
        { base_version: baseVersion, from_index: from, to_index: to }), true),

    syncOfflinePlaylist: async (id, edit) => toPlaylist(await req<ApiResource>('POST', `/playlists/${id}/offline`, {
      mutation_id: edit.mutationId, base_version: edit.baseVersion, track_ids: edit.trackIds,
    }), false),

    // ---- subscription (bonus)
    getSubscription: async () => {
      return { plan: asPlan((await req<{ plan: string }>('GET', '/subscription')).plan), source: 'server' as const };
    },
    setSubscription: async (plan) => {
      return { plan: asPlan((await req<{ plan: string }>('PUT', '/subscription', { plan })).plan), source: 'server' as const };
    },

    // ---- friends and invitations
    searchUsers: async (q) => {
      if (q.trim().length < 2) return [];
      const found = await req<{ id: string; public: { display_name: string } }[]>('GET', `/users/search?q=${enc(q.trim())}&limit=20`);
      return found.map((u) => { names.set(u.id, u.public.display_name); return { id: u.id, name: u.public.display_name }; });
    },
    listFriends: async () =>
      Promise.all((await req<{ user_id: string }[]>('GET', '/friends?limit=100')).map((f) => friendOf(f.user_id))),
    listFriendRequests: async () => {
      const myId = await me();
      const rows = await req<{ user_id: string; requester_id: string }[]>('GET', '/friends/requests?limit=100');
      return Promise.all(rows.map(async (r): Promise<FriendRequest> =>
        ({ userId: r.user_id, name: await nameOf(r.user_id), incoming: r.requester_id !== myId })));
    },
    sendFriendRequest: async (userId) => { await req('POST', '/friends/requests', { user_id: userId }); },
    acceptFriendRequest: async (userId) => { await req('POST', `/friends/${userId}/accept`); },
    removeFriend: async (userId) => { await req('DELETE', `/friends/${userId}`); },
    listInvitations: async () =>
      (await req<{ kind: 'event' | 'playlist'; resource_id: string; name: string }[]>('GET', '/invitations?status=pending&limit=50'))
        .map((i): PendingInvitation => ({ kind: i.kind, resourceId: i.resource_id, name: i.name })),
    acceptInvitation: async (kind, resourceId) => { await req('POST', `/${kind}s/${resourceId}/invitations/accept`); },

    // ---- Music Control Delegation
    listDelegations: listDevices,
    setDelegation: async (deviceId, friendId) => {
      const d = await getDevice(deviceId);
      await req('PUT', `/devices/${deviceId}/delegation`, { friend_id: friendId, base_version: d.version });
      return listDevices();
    },
    registerDevice: async (name) => { await req('POST', '/devices', { name }); return listDevices(); },
    controlDevice: async (deviceId, action, track) => {
      if (action === 'play' && track?.deezerId === undefined) throw new ApiError(422, 'Pick a track from the search results to play.');
      const d = await getDevice(deviceId);
      await req('POST', `/devices/${deviceId}/control`,
        { base_version: d.version, action, ...(action === 'play' ? { deezer_id: track!.deezerId } : {}) });
      return listDevices();
    },

    // ---- real time: the socket only says "something changed"; the screen refetches through REST
    subscribe(channel, onMessage) {
      const [kind, id] = channel.split(':');
      const url = `${root.replace(/^http/, 'ws')}/ws/${kind}/${id}`;
      let ws: WebSocket | null = null;
      let closed = false;
      let attempts = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const open = () => {
        if (closed || !tokens) return;
        ws = new WebSocket(url);
        // the token goes in the first frame, never in the URL
        ws.onopen = () => ws?.send(JSON.stringify({ access_token: tokens?.accessToken, metadata: { platform: Platform.OS, device: Device.modelName ?? 'unknown', app_version: Constants.expoConfig?.version ?? '0.0.0' } }));
        ws.onmessage = (e) => {
          try {
            const m = JSON.parse(String(e.data));
            if (m.type === 'heartbeat') return;
            attempts = 0;
            onMessage(m); // includes "ready": refetch once the subscription is live
          } catch {} // "pong" and other non-JSON frames
        };
        ws.onclose = async (e) => {
          if (closed || attempts++ >= 5) return;
          // Refetch the list so that inaccessible devices disappear from the screen.
          if (kind === 'device' && e.code === 1008) onMessage({ type: 'device_access_changed' });
          if (e.code === 1008 && !(await refresh().catch(() => false))) return; // token expired: renew, else give up
          if (closed) return;
          timer = setTimeout(open, e.code === 1008 ? 0 : Math.min(1000 * 2 ** attempts, 15000));
        };
      };
      open();
      return () => { closed = true; if (timer) clearTimeout(timer); ws?.close(); };
    },
  };
}
