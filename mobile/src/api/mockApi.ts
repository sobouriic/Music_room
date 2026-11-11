import { searchItunes } from '../music/catalog';
import { isoForHour } from '../time';
import {
  ApiClient, ApiError, Delegation, EventPlace, Friend, FriendRequest, PendingInvitation, Plan, Playlist, Tokens, User, VoteEvent,
} from './types';

// In-memory demo server. It enforces the SAME rules the real back-end enforces
// (visibility, licenses, one vote per track, optimistic concurrency), so the app can be demoed and tested without a server.

const ME = 'me';
const delay = (ms = 250) => new Promise((r) => setTimeout(r, process.env.NODE_ENV === 'test' ? 0 : ms));
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
let counter = 100;
const nid = () => String(++counter);

const seed = () => ({
  plan: 'free' as Plan,
  me: {
    id: 'u1', email: 'demo@musicroom.dev', verified: true, hasPassword: true, providers: [] as string[],
    profile: { displayName: 'Demo', bio: '', location: '', notes: '', musicPreferences: ['rock', 'electro'] },
  } as User,
  directory: [
    { id: 'x1', name: 'Dana' }, { id: 'x2', name: 'Emma' }, { id: 'x3', name: 'Farid' }, { id: 'x4', name: 'Alice Martin' },
  ] as Friend[],
  friends: [
    { id: 'f1', name: 'Alice' }, { id: 'f2', name: 'Bob' }, { id: 'f3', name: 'Chloe' },
  ] as Friend[],
  requests: [{ userId: 'x1', name: 'Dana', incoming: true }] as FriendRequest[],
  invitations: [{ kind: 'event', resourceId: 'e3', name: 'Rooftop (invited only)' }] as PendingInvitation[],
  events: [
    {
      id: 'e1', name: 'Friday party', visibility: 'public', license: 'open', version: 1, mine: false, invitedIds: [],
      tracks: [
        { id: 't1', title: 'Around the World', artist: 'Daft Punk', votes: 3, votedByMe: false },
        { id: 't2', title: 'Seven Nation Army', artist: 'The White Stripes', votes: 1, votedByMe: false },
      ],
    },
    {
      id: 'e2', name: 'Office lunch (16h-18h, on site)', visibility: 'public', license: 'geo_time', version: 1, mine: false, invitedIds: [],
      place: { lat: 33.5731, lng: -7.5898, radiusM: 200, startsAt: isoForHour(16), endsAt: isoForHour(18) },
      tracks: [{ id: 't3', title: 'Happy', artist: 'Pharrell Williams', votes: 0, votedByMe: false }],
    },
    {
      id: 'e3', name: 'Rooftop (invited only)', visibility: 'private', license: 'invited', version: 1, mine: false, invitedIds: [ME, 'f1'],
      tracks: [{ id: 't4', title: 'Latch', artist: 'Disclosure', votes: 2, votedByMe: false }],
    },
    {
      // private and I am not invited: it must stay invisible to me
      id: 'e4', name: 'Secret party', visibility: 'private', license: 'invited', version: 1, mine: false, invitedIds: ['f2'],
      tracks: [{ id: 't5', title: 'Hidden', artist: 'Nobody', votes: 0, votedByMe: false }],
    },
  ] as VoteEvent[],
  playlists: [
    {
      id: 'p1', name: 'Road trip', visibility: 'public', license: 'open', version: 1, mine: false, invitedIds: [],
      tracks: [
        { id: 'pt1', title: 'Radar Love', artist: 'Golden Earring' },
        { id: 'pt2', title: 'Take On Me', artist: 'a-ha' },
        { id: 'pt3', title: 'Mr. Brightside', artist: 'The Killers' },
      ],
    },
    {
      id: 'p2', name: 'Study mix (invited editors)', visibility: 'public', license: 'invited', version: 1, mine: false, invitedIds: ['f2'],
      tracks: [{ id: 'pt4', title: 'Intro', artist: 'The xx' }],
    },
  ] as Playlist[],
  devices: [
    { deviceId: 'd1', deviceName: 'Living-room speaker', friend: null, mine: true, version: 1, action: 'stop' },
    { deviceId: 'd2', deviceName: 'Kitchen speaker', friend: null, mine: true, version: 1, action: 'stop' },
    { deviceId: 'd3', deviceName: "Alice's party speaker", friend: null, mine: false, version: 1, action: 'stop' }, // delegated to me
  ] as Delegation[],
});

let db = seed();
/** For unit tests. */
export const resetMock = () => { db = seed(); counter = 100; };

const find = <T extends { id: string }>(list: T[], id: string, what: string) => {
  const x = list.find((i) => i.id === id);
  if (!x) throw new ApiError(404, `${what} not found`);
  return x;
};
const sees = (x: { visibility: string; mine: boolean; invitedIds: string[] }) =>
  x.visibility === 'public' || x.mine || x.invitedIds.includes(ME);
const visible = <T extends { id: string; visibility: string; mine: boolean; invitedIds: string[] }>(list: T[], id: string, what: string) => {
  const x = find(list, id, what);
  if (!sees(x)) throw new ApiError(404, `${what} not found`); // hidden, not "forbidden": do not reveal it exists
  return x;
};
const ownerOnly = (x: { mine: boolean }) => { if (!x.mine) throw new ApiError(403, 'Only the organizer can do this'); };

function distanceM(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const R = 6371000, rad = (d: number) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat), dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

const listeners = new Map<string, Set<(m: { type: string }) => void>>();
const emit = (ch: string, type: string) => listeners.get(ch)?.forEach((cb) => cb({ type }));
const fakeTokens = (): Tokens => ({ accessToken: 'mock-access', refreshToken: 'mock-refresh' });

const canEdit = (p: Playlist) => p.license === 'open' || p.mine || p.invitedIds.includes(ME);
const editable = (id: string) => {
  const p = visible(db.playlists, id, 'Playlist');
  if (!canEdit(p)) throw new ApiError(403, 'Only invited users can edit this playlist');
  return p;
};
const mayVote = (e: VoteEvent) => e.license !== 'invited' || e.mine || e.invitedIds.includes(ME);

function checkPlace(e: VoteEvent, location?: { lat: number; lng: number }) {
  if (e.license !== 'geo_time' || !e.place) return;
  const now = Date.now();
  if (now < Date.parse(e.place.startsAt) || now >= Date.parse(e.place.endsAt)) throw new ApiError(403, 'Voting is closed: outside the time window of this event');
  if (!location) throw new ApiError(403, 'Your location is required to vote at this event');
  if (distanceM(location, e.place) > e.place.radiusM) throw new ApiError(403, 'You are too far from the venue to vote');
}

const sortTracks = (e: VoteEvent) => e.tracks.sort((a, b) => b.votes - a.votes); // stable: ties keep suggestion order

export const mockApi: ApiClient = {
  kind: 'mock',
  setTokens() {},
  onTokensChange() {},

  // ---- auth + profile
  async register() { await delay(); },
  async verifyEmail() { await delay(); },
  async resendVerification() { await delay(); },
  async login(email, password) {
    await delay();
    if (!email || !password) throw new ApiError(401, 'Invalid email or password');
    return fakeTokens();
  },
  async logout() { await delay(100); },
  async forgotPassword() { await delay(); },
  async resetPassword() { await delay(); },
  async googleStart() { await delay(); return { authorizationUrl: 'https://accounts.google.com', state: 'mock-state' }; },
  async googleExchange() {
    await delay();
    db.me = { ...db.me, providers: [...new Set([...db.me.providers, 'google'])] };
    return fakeTokens();
  },
  async googleLink() {
    await delay();
    db.me = { ...db.me, providers: [...new Set([...db.me.providers, 'google'])] };
  },
  async getMe() { await delay(100); return clone(db.me); },
  async updateProfile(profile) { await delay(); db.me = { ...db.me, profile }; return clone(db.me); },

  async searchTracks(query) { return searchItunes(query); },

  // ---- Music Track Vote
  async listEvents() { await delay(); return clone(db.events.filter(sees)); },
  async createEvent(name, visibility, license, place?: EventPlace) {
    await delay();
    if (license === 'geo_time' && !place) throw new ApiError(422, 'A place and a time window are required');
    const e: VoteEvent = { id: nid(), name, visibility, license, version: 1, tracks: [], mine: true, invitedIds: [], place };
    db.events.push(e);
    return clone(e);
  },
  async getEvent(id) { await delay(150); return clone(visible(db.events, id, 'Event')); },
  async setEventInvites(id, userIds) {
    await delay();
    const e = visible(db.events, id, 'Event'); ownerOnly(e);
    e.invitedIds = [...new Set(userIds)]; e.version += 1;
    return clone(e);
  },
  async suggestTrack(eventId, track) {
    await delay();
    const e = visible(db.events, eventId, 'Event');
    if (!mayVote(e)) throw new ApiError(403, 'Only invited people can take part');
    e.tracks.push({ ...track, id: nid(), votes: 0, votedByMe: false });
    e.version += 1;
    emit(`event:${eventId}`, 'tracks_changed');
    return clone(e);
  },
  async voteTrack(eventId, trackId, location) {
    await delay();
    const e = visible(db.events, eventId, 'Event');
    if (!mayVote(e)) throw new ApiError(403, 'Only invited people can vote');
    checkPlace(e, location);
    const t = find(e.tracks, trackId, 'Track');
    if (t.votedByMe) throw new ApiError(409, 'You already voted for this track');
    t.votes += 1; t.votedByMe = true;
    sortTracks(e); e.version += 1; // more votes = played earlier, decided by the server
    emit(`event:${eventId}`, 'tracks_changed');
    return clone(e);
  },
  async unvoteTrack(eventId, trackId, location) {
    await delay();
    const e = visible(db.events, eventId, 'Event');
    if (!mayVote(e)) throw new ApiError(403, 'Only invited people can vote');
    checkPlace(e, location);
    const t = find(e.tracks, trackId, 'Track');
    if (!t.votedByMe) throw new ApiError(404, 'You have not voted for this track');
    t.votes -= 1; t.votedByMe = false;
    sortTracks(e); e.version += 1;
    emit(`event:${eventId}`, 'tracks_changed');
    return clone(e);
  },
  async advanceEvent(eventId) {
    await delay();
    const e = visible(db.events, eventId, 'Event'); ownerOnly(e);
    if (e.tracks.length === 0) throw new ApiError(409, 'The queue is empty');
    const [next] = e.tracks.splice(0, 1);
    e.current = { ...next, votes: 0, votedByMe: false };
    e.version += 1;
    emit(`event:${eventId}`, 'tracks_changed');
    return clone(e);
  },

  // ---- Music Playlist Editor
  async listPlaylists() { await delay(); return clone(db.playlists.filter(sees)); },
  async createPlaylist(name, visibility, license) {
    await delay();
    const p: Playlist = { id: nid(), name, visibility, license, tracks: [], version: 1, mine: true, invitedIds: [] };
    db.playlists.push(p);
    return clone(p);
  },
  async getPlaylist(id) { await delay(150); return clone(visible(db.playlists, id, 'Playlist')); },
  async setPlaylistInvites(id, userIds) {
    await delay();
    const p = visible(db.playlists, id, 'Playlist'); ownerOnly(p);
    p.invitedIds = [...new Set(userIds)]; p.version += 1;
    return clone(p);
  },
  async addPlaylistTrack(id, track) {
    await delay();
    const p = editable(id);
    p.tracks.push({ ...track, id: nid() });
    p.version += 1;
    emit(`playlist:${id}`, 'playlist_changed');
    return clone(p);
  },
  async removePlaylistTrack(id, trackId, baseVersion) {
    await delay();
    const p = editable(id);
    if (baseVersion !== p.version) throw new ApiError(409, 'Playlist was modified by someone else, reloaded', 'version_conflict');
    find(p.tracks, trackId, 'Track');
    p.tracks = p.tracks.filter((t) => t.id !== trackId);
    p.version += 1;
    emit(`playlist:${id}`, 'playlist_changed');
    return clone(p);
  },
  async movePlaylistTrack(id, from, to, baseVersion) {
    await delay();
    const p = editable(id);
    if (baseVersion !== p.version) throw new ApiError(409, 'Playlist was modified by someone else, reloaded', 'version_conflict');
    const [t] = p.tracks.splice(from, 1);
    p.tracks.splice(to, 0, t);
    p.version += 1;
    emit(`playlist:${id}`, 'playlist_changed');
    return clone(p);
  },

  // ---- subscription (bonus)
  async getSubscription() { await delay(100); return { plan: db.plan, source: 'server' }; },
  async setSubscription(plan) { await delay(); db.plan = plan; return { plan, source: 'server' }; },

  // ---- friends and invitations
  async searchUsers(query) {
    await delay(150);
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const known = new Set([...db.friends.map((f) => f.id), ...db.requests.map((r) => r.userId)]);
    return clone(db.directory.filter((u) => u.name.toLowerCase().includes(q) && !known.has(u.id)));
  },
  async listFriends() { await delay(100); return clone(db.friends); },
  async listFriendRequests() { await delay(100); return clone(db.requests); },
  async sendFriendRequest(userId) {
    await delay();
    const u = find(db.directory, userId, 'User');
    if (db.friends.some((f) => f.id === userId) || db.requests.some((r) => r.userId === userId)) throw new ApiError(409, 'Already friends or pending');
    db.requests.push({ userId, name: u.name, incoming: false });
  },
  async acceptFriendRequest(userId) {
    await delay();
    const r = db.requests.find((x) => x.userId === userId && x.incoming);
    if (!r) throw new ApiError(404, 'Friend request not found');
    db.requests = db.requests.filter((x) => x !== r);
    db.friends.push({ id: r.userId, name: r.name });
  },
  async removeFriend(userId) {
    await delay();
    db.friends = db.friends.filter((f) => f.id !== userId);
    db.requests = db.requests.filter((r) => r.userId !== userId);
    db.devices = db.devices.map((d) => (d.friend?.id === userId ? { ...d, friend: null } : d)); // revoke their control
  },
  async listInvitations() { await delay(100); return clone(db.invitations); },
  async acceptInvitation(kind, resourceId) {
    await delay();
    db.invitations = db.invitations.filter((i) => !(i.kind === kind && i.resourceId === resourceId));
  },

  // ---- Music Control Delegation
  async listDelegations() { await delay(); return clone(db.devices); },
  async setDelegation(deviceId, friendId) {
    await delay();
    const d = db.devices.find((x) => x.deviceId === deviceId);
    if (!d) throw new ApiError(404, 'Device not found');
    if (!d.mine) throw new ApiError(403, 'Only the owner can delegate this device');
    if (friendId && !db.friends.some((f) => f.id === friendId)) throw new ApiError(403, 'Delegate must be an accepted friend');
    d.friend = db.friends.find((f) => f.id === friendId) ?? null;
    d.version += 1;
    return clone(db.devices);
  },
  async registerDevice(name) {
    await delay();
    if (!db.devices.some((d) => d.deviceName === name && d.mine))
      db.devices.push({ deviceId: nid(), deviceName: name, friend: null, mine: true, version: 1, action: 'stop' });
    return clone(db.devices);
  },
  async controlDevice(deviceId, action, track) {
    await delay();
    const d = db.devices.find((x) => x.deviceId === deviceId);
    if (!d) throw new ApiError(404, 'Device not found');
    if (action === 'play' && !track) throw new ApiError(422, 'Pick a track to play');
    d.action = action;
    if (action === 'play') d.trackTitle = track!.title;
    d.version += 1;
    return clone(db.devices);
  },

  subscribe(channel, onMessage) {
    if (!listeners.has(channel)) listeners.set(channel, new Set());
    listeners.get(channel)!.add(onMessage);
    // simulate another user voting every few seconds
    const timer = setInterval(() => {
      if (!channel.startsWith('event:')) return;
      const e = db.events.find((x) => `event:${x.id}` === channel);
      if (!e || e.tracks.length === 0) return;
      e.tracks[Math.floor(Math.random() * e.tracks.length)].votes += 1;
      sortTracks(e);
      emit(channel, 'tracks_changed');
    }, 6000);
    return () => { clearInterval(timer); listeners.get(channel)?.delete(onMessage); };
  },
};
