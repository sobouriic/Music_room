import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { recordAction } from './activity';
import { loadConfig } from './config';
import { ApiError, Playlist, Tokens, User } from './api/types';

export type SavedPlaylist = { snapshot: Playlist; trackIds: string[]; mutationId?: string; savedAt: number };
type Library = { fingerprint: string; user: User; plan: 'free' | 'premium'; verifiedAt: number; playlists: SavedPlaylist[] };
const MAX_AGE = 7 * 86400000;
let tail: Promise<unknown> = Promise.resolve();
const key = async () => `music-room-offline:${(await loadConfig()).baseUrl}`;
const fingerprint = (tokens: Tokens) => Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, tokens.refreshToken);
const valid = (library: Library | null): library is Library => !!library && library.plan === 'premium'
  && Date.now() - library.verifiedAt < MAX_AGE && Date.now() >= library.verifiedAt;
async function read(): Promise<Library | null> {
  const raw = await AsyncStorage.getItem(await key());
  try { return raw ? JSON.parse(raw) : null; } catch { return null; }
}
async function write(library: Library | null) {
  const k = await key();
  if (library) await AsyncStorage.setItem(k, JSON.stringify(library));
  else await AsyncStorage.removeItem(k);
}
function serial<T>(operation: () => Promise<T>): Promise<T> {
  const result = tail.then(operation);
  tail = result.catch(() => {});
  return result;
}
async function requireLibrary(userId: string) {
  const library = await read();
  if (!valid(library) || library.user.id !== userId) throw new Error('Connect online with Premium before using offline playlists.');
  return library;
}

const safeProfile = (user: User): User => ({ ...user, profile: { ...user.profile, notes: '', location: '', musicPreferences: [] } });
export const savedView = (entry: SavedPlaylist): Playlist => ({ ...entry.snapshot,
  tracks: entry.trackIds.map(id => entry.snapshot.tracks.find(t => t.id === id)).filter((track): track is Playlist['tracks'][number] => !!track),
});

// Account/server scoped metadata only: no audio downloads, tokens, private profile,
// location, or passwords are stored in this cache. Logout deletes snapshots/drafts.
export const offline = {
  confirm: (user: User, tokens: Tokens, plan: 'free' | 'premium') => serial(async () => {
    const previous = await read();
    await write({ fingerprint: await fingerprint(tokens), user: safeProfile(user), plan,
      verifiedAt: Date.now(), playlists: plan === 'premium' && previous?.user.id === user.id ? previous.playlists : [] });
  }),
  get: (userId: string, id: string) => serial(async () => {
    const entry = (await requireLibrary(userId)).playlists.find(p => p.snapshot.id === id);
    return entry ? savedView(entry) : null;
  }),
  revalidate: async (userId: string, fetch: (id: string) => Promise<Playlist>) => {
    const entries = await offline.list(userId);
    for (const entry of entries) {
      try {
        const fresh = await fetch(entry.snapshot.id);
        // Preserve the base version and pending draft so conflicts require explicit review.
        if (!entry.mutationId) await offline.save(userId, fresh);
      } catch (e) {
        if (e instanceof ApiError && [403, 404].includes(e.status)) await offline.remove(userId, entry.snapshot.id);
        else if (e instanceof ApiError && (e.status === 0 || e.status === 429 || e.status >= 500)) break;
        else throw e;
      }
    }
  },
  remember: (user: User, tokens: Tokens) => serial(async () => {
    const previous = await read();
    const safeUser = safeProfile(user);
    await write({ fingerprint: await fingerprint(tokens), user: safeUser,
      plan: previous?.user.id === user.id ? previous.plan : 'free',
      verifiedAt: previous?.user.id === user.id ? previous.verifiedAt : 0,
      playlists: previous?.user.id === user.id ? previous.playlists : [] });
  }),
  rotate: (tokens: Tokens) => serial(async () => {
    const library = await read();
    if (library) { library.fingerprint = await fingerprint(tokens); await write(library); }
  }),
  restore: (tokens: Tokens) => serial(async () => {
    const library = await read();
    return valid(library) && library.fingerprint === await fingerprint(tokens) ? library.user : null;
  }),
  entitlement: (userId: string, plan: 'free' | 'premium') => serial(async () => {
    const library = await read();
    if (!library || library.user.id !== userId) return;
    library.plan = plan; library.verifiedAt = Date.now();
    if (plan === 'free') library.playlists = [];
    await write(library);
  }),
  clear: () => serial(() => write(null)),
  list: (userId: string) => serial(async () => (await requireLibrary(userId)).playlists),
  save: (userId: string, snapshot: Playlist) => serial(async () => {
    const library = await requireLibrary(userId);
    const existing = library.playlists.find(p => p.snapshot.id === snapshot.id);
    if (existing?.mutationId) throw new Error('Sync or discard your pending changes before replacing this download.');
    if (!existing && library.playlists.length >= 20) throw new Error('Remove a saved playlist first (maximum 20).');
    library.playlists = library.playlists.filter(p => p.snapshot.id !== snapshot.id);
    library.playlists.push({ snapshot, trackIds: snapshot.tracks.map(t => t.id), savedAt: Date.now() });
    await write(library); recordAction('offline_saved');
  }),
  edit: (userId: string, id: string, trackIds: string[]) => serial(async () => {
    const library = await requireLibrary(userId);
    const entry = library.playlists.find(p => p.snapshot.id === id);
    if (!entry) throw new Error('Save this playlist online first.');
    if (new Set(trackIds).size !== trackIds.length || trackIds.some(id => !entry.snapshot.tracks.some(t => t.id === id))) {
      throw new Error('Offline edits can reorder or remove saved tracks only.');
    }
    entry.trackIds = trackIds; entry.mutationId = Crypto.randomUUID(); recordAction('offline_edit');
    await write(library);
  }),
  remove: (userId: string, id: string) => serial(async () => {
    const library = await read();
    if (!library || library.user.id !== userId) return;
    library.playlists = library.playlists.filter(p => p.snapshot.id !== id); await write(library);
  }),
  // Keep the same mutation ID until the server acknowledges. A 409 preserves the
  // draft for review; do not automatically rebase it over somebody else's edits.
  sync: async (userId: string, id: string, send: (body: { mutationId: string; baseVersion: number; trackIds: string[] }) => Promise<Playlist>) => {
    const entry = await serial(async () => {
      const library = await requireLibrary(userId);
      const entry = library.playlists.find(p => p.snapshot.id === id);
      if (!entry?.mutationId) throw new Error('No pending changes.');
      return JSON.parse(JSON.stringify(entry)) as SavedPlaylist;
    });
    let result: Playlist;
    try { result = await send({ mutationId: entry.mutationId!, baseVersion: entry.snapshot.version, trackIds: entry.trackIds }); }
    catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        // No retaining access after a server-confirmed revocation or downgrade.
        await offline.remove(userId, id);
      }
      throw e;
    }
    recordAction('offline_sync');
    await serial(async () => {
      const library = await requireLibrary(userId);
      const current = library.playlists.find(p => p.snapshot.id === id);
      if (!current) return;
      if (current.mutationId === entry.mutationId) {
        current.snapshot = result; current.savedAt = Date.now();
        current.trackIds = result.tracks.map(t => t.id); delete current.mutationId;
      } else if (current.trackIds.every(id => result.tracks.some(t => t.id === id))) {
        current.snapshot = result; current.savedAt = Date.now();
      } // Unreconcilable edits made during sync keep their original snapshot/draft.
      await write(library);
    });
  },
};
