import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { AppState, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, VoteEvent } from '../api';
import { useAuth } from './AuthContext';
import { loadConfig } from '../config';
import { currentPosition } from '../location';
import { enableNearbyNotifications, showNearbyAlerts } from '../nearbyNotifications';
import { Button, Text, colors, errMsg } from '../ui';

type State = {
  enabled: boolean; notifications: boolean; checking: boolean; message: string;
  events: VoteEvent[]; notice: VoteEvent | null;
  enable: () => Promise<void>; disable: () => void; dismiss: () => void;
};
const NearbyContext = createContext<State>(null!);
export const useNearby = () => useContext(NearbyContext);
export function NearbyProvider({ children }: { children: React.ReactNode }) {
  const { user, online = true } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState('');
  const [events, setEvents] = useState<VoteEvent[]>([]);
  const [notice, setNotice] = useState<VoteEvent | null>(null);
  const seen = useRef<Record<string, number>>({});
  const key = useRef<string | null>(null);
  const actor = useRef(user?.id); actor.current = user?.id;
  useEffect(() => {
    let active = true;
    setEnabled(false); setNotifications(false); setEvents([]); setNotice(null);
    setMessage(''); seen.current = {}; key.current = null;
    if (user) void (async () => {
      const storageKey = `music-room-nearby-enabled:${(await loadConfig()).baseUrl}:${user.id}`;
      const value = await AsyncStorage.getItem(storageKey);
      if (!active) return;
      key.current = storageKey;
      if (value === 'true') {
        const allowed = await enableNearbyNotifications(false);
        if (active) { setNotifications(allowed); setEnabled(true); }
      }
    })().catch(() => {});
    return () => { active = false; };
  }, [user?.id]);
  useEffect(() => {
    if (!enabled || !user || !online) return;
    let active = true, inFlight = false;
    const check = async () => {
      if (!active || inFlight || (AppState.currentState && AppState.currentState !== 'active')) return;
      inFlight = true; setChecking(true);
      try {
        if (!api.nearbyEvents) throw new Error('Use the real backend for nearby events.');
        const position = await currentPosition();
        if (!active) return;
        const results = await api.nearbyEvents(position);
        if (!active) return;
        setEvents(results); setMessage(results.length ? '' : 'No active public events within 1 km.');
        const now = Date.now();
        const fresh = results.filter(event => !seen.current[event.id] || now - seen.current[event.id] > 1800000);
        if (fresh.length) {
          setNotice(fresh[0]);
          fresh.forEach(event => { seen.current[event.id] = now; });
        }
        if (notifications) await showNearbyAlerts(user.id, results);
      } catch (e) { if (active) setMessage(errMsg(e)); }
      finally { inFlight = false; if (active) setChecking(false); }
    };
    void check();
    const timer = setInterval(check, 60000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') void check(); });
    return () => { active = false; clearInterval(timer); listener.remove(); setChecking(false); };
  }, [enabled, notifications, online, user?.id]);
  const enable = async () => {
    const id = user?.id;
    // Keep the browser permission request directly in the button's user gesture.
    const allowed = await enableNearbyNotifications();
    if (actor.current !== id) return;
    setNotifications(allowed); setEnabled(true);
    if (key.current) await AsyncStorage.setItem(key.current, 'true');
  };
  const disable = () => {
    setEnabled(false); setNotice(null); setMessage('');
    if (key.current) void AsyncStorage.setItem(key.current, 'false').catch(() => {});
  };
  return <NearbyContext.Provider value={{ enabled, notifications, checking, message, events, notice, enable, disable, dismiss: () => setNotice(null) }}>{children}</NearbyContext.Provider>;
}
export function NearbyBanner({ open }: { open: (event: VoteEvent) => void }) {
  const { enabled, notice, dismiss } = useNearby();
  if (!enabled || !notice) return null;
  return <View style={{ backgroundColor: colors.surface2, padding: 14, gap: 8, borderBottomWidth: 2, borderBottomColor: colors.accent }}>
    <Text accessibilityRole="alert" style={{ fontWeight: '700' }}>♫ Event nearby: {notice.name}</Text>
    <View style={{ flexDirection: 'row', gap: 8 }}>
      <Button title="Open nearby event" onPress={() => { open(notice); dismiss(); }} />
      <Button title="Dismiss alert" kind="secondary" onPress={dismiss} />
    </View>
  </View>;
}
