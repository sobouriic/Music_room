import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { api } from './api';
import { loadConfig } from './config';

type Entry = { event_id: string; action: string; occurred_at: string };
let actor: string | null = null;
let generation = 0;
let tail = Promise.resolve();
const key = async (id: string) => `music-room-actions:${(await loadConfig()).baseUrl}:${id}`;
export function setActivityUser(id: string | null) { actor = id; ++generation; }
// Bounded best-effort logs, account/server scoped. No arbitrary strings or private data.
export function recordAction(action: 'screen_view' | 'playback_start' | 'playback_pause' | 'playback_stop' | 'queue_next' | 'offline_saved' | 'offline_edit' | 'offline_sync' | 'nearby_alerts_enabled' | 'nearby_alerts_disabled') {
  const id = actor;
  const attempt = generation;
  if (!id) return;
  tail = tail.then(async () => {
    if (attempt !== generation) return;
    const k = await key(id);
    let entries: Entry[] = [];
    try { entries = JSON.parse(await AsyncStorage.getItem(k) ?? '[]'); } catch {}
    if (!Array.isArray(entries)) entries = [];
    entries.push({ event_id: Crypto.randomUUID(), action, occurred_at: new Date().toISOString() });
    entries = entries.slice(-200);
    await AsyncStorage.setItem(k, JSON.stringify(entries));
    if (attempt !== generation || actor !== id || !api.logActions) return;
    while (entries.length && actor === id && attempt === generation) {
      await api.logActions(entries.slice(0, 50));
      entries = entries.slice(50);
      await AsyncStorage.setItem(k, JSON.stringify(entries));
    }
  }).catch(() => {});
}
