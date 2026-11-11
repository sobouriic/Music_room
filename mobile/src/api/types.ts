export type Visibility = 'public' | 'private';
export type VoteLicense = 'open' | 'invited' | 'geo_time';
export type EditLicense = 'open' | 'invited';

// Mirrors the 4 profile categories of the back-end:
// public (displayName, bio), friends only (location), private (notes), music preferences.
export type Profile = {
  displayName: string;
  bio: string;
  location: string;
  notes: string;
  musicPreferences: string[];
};

export type User = {
  id: string;
  email: string;
  verified: boolean;
  hasPassword: boolean;
  providers: string[];
  profile: Profile;
};

export type Tokens = { accessToken: string; refreshToken: string };

// A song. artwork/previewUrl/deezerId come from the music catalog; the server resolves the metadata from deezerId.
export type TrackInput = { title: string; artist: string; artwork?: string; previewUrl?: string; deezerId?: number };
export type Track = TrackInput & { id: string; votes: number; votedByMe: boolean };

// "place and time" license: only people within radiusM of (lat,lng) between startsAt and endsAt (ISO) can vote.
export type EventPlace = { lat: number; lng: number; radiusM: number; startsAt: string; endsAt: string };
export type VoteEvent = {
  id: string; name: string; visibility: Visibility; license: VoteLicense; version: number;
  tracks: Track[];        // the queue, best-ranked first (ordering is done by the server)
  current?: Track | null; // the track the organizer last advanced to
  mine: boolean;          // I am the organizer
  invitedIds: string[];   // user ids invited (only known to the organizer)
  place?: EventPlace;
};

export type PlaylistTrack = TrackInput & { id: string };
// `version` lets the SERVER detect concurrent edits (optimistic concurrency).
export type Playlist = {
  id: string; name: string; visibility: Visibility; license: EditLicense; tracks: PlaylistTrack[]; version: number;
  mine: boolean; invitedIds: string[];
};

// Subscription bonus: two offers. Premium unlocks offline playlist saving/editing/sync; online editing is Free.
// source 'device' = an offline, previously verified entitlement or mock client state.
export type Plan = 'free' | 'premium';
export type Subscription = { plan: Plan; source: 'server' | 'device' };

export type Friend = { id: string; name: string };
export type FriendRequest = { userId: string; name: string; incoming: boolean };
export type PendingInvitation = { kind: 'event' | 'playlist'; resourceId: string; name: string };

export type DeviceAction = 'play' | 'pause' | 'stop';
export type Delegation = {
  deviceId: string; deviceName: string;
  friend: Friend | null;   // who may control it besides me
  mine: boolean;           // false: a friend delegated this device to me
  version: number;
  action: DeviceAction;    // desired control state kept by the server
  trackTitle?: string;
  previewUrl?: string;
};

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

/** Contract between the app and the back-end. */
export interface ApiClient {
  /** 'mock' = in-memory demo server, 'http' = the real back-end. */
  readonly kind: 'mock' | 'http';
  logActions?(events: { event_id: string; action: string; occurred_at: string }[]): Promise<void>;
  getFriendProfile?(id: string): Promise<{ name: string; bio: string; location: string }>;
  updateEvent?(event: VoteEvent): Promise<VoteEvent>;
  updatePlaylist?(playlist: Playlist): Promise<Playlist>;
  onTokensNeeded?(cb: () => Promise<Tokens | null>): void;
  onConnectionChange?(cb: (online: boolean) => void): void;
  // --- session plumbing
  setTokens(tokens: Tokens | null): void;
  /** Called when the client refreshed its tokens (new pair) or lost the session (null). */
  onTokensChange(cb: (tokens: Tokens | null) => void | Promise<void>): void;

  // --- REAL on the back-end today (auth + profile)
  register(email: string, password: string): Promise<void>;
  verifyEmail(token: string, password: string): Promise<void>;
  resendVerification(email: string): Promise<void>;
  login(email: string, password: string): Promise<Tokens>;
  logout(refreshToken: string): Promise<void>;
  forgotPassword(email: string): Promise<void>;
  resetPassword(token: string, password: string): Promise<void>;
  // Google (PKCE): start -> user signs in in the browser -> exchange (login) or link (profile)
  googleStart(codeChallenge: string, intent: 'login' | 'link'): Promise<{ authorizationUrl: string; state: string }>;
  googleExchange(state: string, code: string, codeVerifier: string): Promise<Tokens>;
  googleLink(state: string, code: string, codeVerifier: string): Promise<void>;
  getMe(): Promise<User>;
  updateProfile(profile: Profile): Promise<User>;

  // --- music catalog (Deezer, searched through the back-end)
  searchTracks(query: string): Promise<TrackInput[]>;

  // --- Music Track Vote
  listEvents(): Promise<VoteEvent[]>;
  createEvent(name: string, visibility: Visibility, license: VoteLicense, place?: EventPlace): Promise<VoteEvent>;
  getEvent(id: string): Promise<VoteEvent>;
  nearbyEvents?(location: { lat: number; lng: number }): Promise<VoteEvent[]>;
  setEventInvites(eventId: string, userIds: string[]): Promise<VoteEvent>;
  suggestTrack(eventId: string, track: TrackInput): Promise<VoteEvent>;
  voteTrack(eventId: string, trackId: string, location?: { lat: number; lng: number }): Promise<VoteEvent>;
  unvoteTrack(eventId: string, trackId: string, location?: { lat: number; lng: number }): Promise<VoteEvent>;
  advanceEvent(eventId: string, currentTrackId?: string): Promise<VoteEvent>;

  // --- Music Playlist Editor
  listPlaylists(): Promise<Playlist[]>;
  createPlaylist(name: string, visibility: Visibility, license: EditLicense): Promise<Playlist>;
  getPlaylist(id: string): Promise<Playlist>;
  setPlaylistInvites(id: string, userIds: string[]): Promise<Playlist>;
  addPlaylistTrack(id: string, track: TrackInput): Promise<Playlist>;
  removePlaylistTrack(id: string, trackId: string, baseVersion: number): Promise<Playlist>;
  movePlaylistTrack(id: string, from: number, to: number, baseVersion: number): Promise<Playlist>;
  syncOfflinePlaylist?(id: string, edit: { mutationId: string; baseVersion: number; trackIds: string[] }): Promise<Playlist>;

  // --- subscription (bonus)
  getSubscription(): Promise<Subscription>;
  setSubscription(plan: Plan): Promise<Subscription>;

  // --- friends and invitations
  searchUsers(query: string): Promise<Friend[]>;
  listFriends(): Promise<Friend[]>;
  listFriendRequests(): Promise<FriendRequest[]>;
  sendFriendRequest(userId: string): Promise<void>;
  acceptFriendRequest(userId: string): Promise<void>;
  removeFriend(userId: string): Promise<void>; // cancels, declines or removes
  listInvitations(): Promise<PendingInvitation[]>;
  acceptInvitation(kind: 'event' | 'playlist', resourceId: string): Promise<void>;

  // --- Music Control Delegation
  listDelegations(): Promise<Delegation[]>;
  setDelegation(deviceId: string, friendId: string | null): Promise<Delegation[]>;
  registerDevice(name: string): Promise<Delegation[]>;
  controlDevice(deviceId: string, action: DeviceAction, track?: TrackInput): Promise<Delegation[]>;

  /** Real-time invalidations for "event:ID", "playlist:ID" or "device:ID". Returns an unsubscribe function. */
  subscribe(channel: string, onMessage: (msg: { type: string }) => void): () => void;
}
