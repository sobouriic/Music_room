import React, { useCallback, useState } from 'react';
import { View } from 'react-native';
import * as Device from 'expo-device';
import { useFocusEffect } from '@react-navigation/native';
import { Alert } from '../alert';
import { useAuth } from '../context/AuthContext';
import { api, ApiError, Delegation, Friend, TrackInput } from '../api';
import { TrackSearch } from '../music/TrackSearch';
import { bindLocalDevice, getLocalDevice } from '../music/localDevice';
import { Button, errMsg, Pill, Screen, Text, Title, s } from '../ui';

export default function DelegationScreen({ navigation }: any = {}) {
  const { user, online = true } = useAuth();
  const [localId, setLocalId] = useState<string | null>(null);
  const [devices, setDevices] = useState<Delegation[]>([]);
  const [friends, setFriends] = useState<Friend[]>([]);
  const [pickFor, setPickFor] = useState<string | null>(null); // device whose "play a track" search is open

  const load = useCallback(async () => {
    if (!online) return;
    try { setDevices(await api.listDelegations()); setFriends(await api.listFriends()); if (user) setLocalId(await getLocalDevice(user.id)); }
    catch (e) { if (!(e instanceof ApiError && [0, 401].includes(e.status))) Alert.alert('Error', errMsg(e)); }
  }, [online, user?.id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  // Keep subscriptions stable across state/version changes; rebuild only when device IDs change.
  const deviceChannels = devices.map((d) => d.deviceId).sort().join(',');
  useFocusEffect(useCallback(() => {
    if (!deviceChannels || !online) return;
    let active = true;
    const unsubscribes = deviceChannels.split(',').map((id) =>
      api.subscribe(`device:${id}`, () => {
        if (!active) return;
        void (async () => {
          try {
            const updated = await api.listDelegations();
            if (active) setDevices(updated);
          } catch (e) {
            if (active) Alert.alert('Error', errMsg(e));
          }
        })();
      }),
    );
    return () => {
      active = false;
      unsubscribes.forEach((unsubscribe) => unsubscribe());
    };
  }, [deviceChannels, online]));

  const run = async (fn: () => Promise<Delegation[]>) => {
    try { setDevices(await fn()); } catch (e) { Alert.alert('Error', errMsg(e)); }
  };
  const play = (d: Delegation, t: TrackInput) => { setPickFor(null); run(() => api.controlDevice(d.deviceId, 'play', t)); };

  if (!online) return <Screen>
    <Title>Control</Title>
    <Text>Device control needs a connection. Your saved playlists can still be edited offline.</Text>
    <Button title="Offline playlists" onPress={() => navigation?.navigate('Offline')} />
  </Screen>;
  return (
    <Screen scroll>
      <Title>Control</Title>
      <Text style={s.muted}>Choose which friend controls the music on each of your devices. The license is per device.</Text>
      <Text style={s.muted}>Select “Use on this device” for the phone or browser that should play audio. Keep that app open and connected. Revoke removes your friend's permission; Stop stops music.</Text>
      {devices.length === 0 && <Text style={s.muted}>No device yet. Add this phone below.</Text>}
      {devices.map((d) => (
        <View key={d.deviceId} style={{ gap: 8, marginVertical: 8 }}>
          <Text style={{ fontWeight: '700', fontSize: 16 }}>{d.deviceName}{d.deviceId === localId ? ' (this device)' : d.mine ? '' : '  (shared with me)'}</Text>
          {d.mine && d.deviceId !== localId && <Pill title="Use on this device" onPress={async () => {
            if (!user) return;
            try { await bindLocalDevice(user.id, d.deviceId); setLocalId(d.deviceId); }
            catch (e) { Alert.alert('Device setup failed', errMsg(e)); }
          }} />}
          <Text style={s.muted}>
            {d.action === 'stop' ? 'Stopped' : d.action === 'pause' ? 'Paused' : 'Playing'}{d.trackTitle ? `: ${d.trackTitle}` : ''}
            {d.mine ? ` · Controlled by: ${d.friend?.name ?? 'only me'}` : ''}
          </Text>
          {d.mine && (
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {friends.map((f) => (
                <Pill key={f.id} title={f.name} active={d.friend?.id === f.id} onPress={() => run(() => api.setDelegation(d.deviceId, f.id))} />
              ))}
              <Pill title="Revoke" disabled={!d.friend} onPress={() => run(() => api.setDelegation(d.deviceId, null))} />
            </View>
          )}
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <Pill title="▶ Play a track" active={pickFor === d.deviceId} onPress={() => setPickFor(pickFor === d.deviceId ? null : d.deviceId)} />
            <Pill title="⏸ Pause" onPress={() => run(() => api.controlDevice(d.deviceId, 'pause'))} />
            <Pill title="⏹ Stop" onPress={() => run(() => api.controlDevice(d.deviceId, 'stop'))} />
          </View>
          {pickFor === d.deviceId && <TrackSearch actionLabel="Play" onPick={(t) => play(d, t)} />}
        </View>
      ))}
      <Button title="+ Add this phone as a device" kind="secondary"
        onPress={() => run(() => api.registerDevice(Device.deviceName ?? Device.modelName ?? 'This device'))} />
    </Screen>
  );
}
