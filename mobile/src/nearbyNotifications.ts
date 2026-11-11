import { VoteEvent } from './api/types';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { loadConfig } from './config';

// Browsers require HTTPS (or localhost) and a permission request from a user gesture.
export async function enableNearbyNotifications(request = true): Promise<boolean> {
  if (typeof Notification === 'undefined' || !globalThis.isSecureContext) return false;
  try { return (Notification.permission === 'granted' || (request && await Notification.requestPermission() === 'granted')); }
  catch { return false; }
}
export async function showNearbyAlerts(userId: string, events: VoteEvent[]): Promise<void> {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  const key = `music-room-nearby-alerts:${(await loadConfig()).baseUrl}:${userId}`;
  let seen: Record<string, number> = {};
  try { seen = JSON.parse(await AsyncStorage.getItem(key) ?? '{}'); } catch {}
  const now = Date.now();
  seen = Object.fromEntries(Object.entries(seen).filter(([, time]) => time > now - 1800000));
  for (const event of events.slice(0, 30)) {
    if (seen[event.id]) continue;
    try {
      const alert = new Notification('Music Room event nearby', { body: event.name, tag: `event-${event.id}` });
      alert.onclick = () => { window.focus(); alert.close(); };
      seen[event.id] = now;
      await AsyncStorage.setItem(key, JSON.stringify(seen));
    } catch { throw new Error('Browser notifications are unavailable. Nearby alerts still appear inside Music Room.'); }
  }
}
