import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { recordAction } from '../activity';
import { useAuth } from '../context/AuthContext';
import { Alert } from '../alert';
import { api, ApiError, Playlist, PlaylistTrack, VoteEvent } from '../api';
import { Art, colors, s, Text } from '../ui';
import { getLocalDevice, onLocalDeviceChange } from './localDevice';

type Playable = { id?: string; title: string; artist: string; artwork?: string; previewUrl?: string };
type Mode = { kind: 'playlist'; id: string; tracks: PlaylistTrack[]; played: Set<string> } | { kind: 'event'; id: string };
type Ctx = {
  current: Playable | null; playing: boolean; toggle: (track: Playable) => void; stop: () => void;
  playPlaylist: (playlist: Playlist) => void; updatePlaylist: (playlist: Playlist) => void;
  playEvent: (id: string, advance?: boolean) => Promise<VoteEvent>;
};
const PlayerCtx = createContext<Ctx>(null!);
export const usePlayer = () => useContext(PlayerCtx);

// Previews only. Queue order belongs to the server; the organizer advances events.
export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const { user, online = true } = useAuth();
  const player = useAudioPlayer();
  const status = useAudioPlayerStatus(player);
  const [current, setCurrent] = useState<Playable | null>(null);
  const selected = useRef<Playable | null>(null);
  const mode = useRef<Mode | null>(null);
  const generation = useRef(0);
  const handled = useRef(-1);
  const pending = useRef<number | null>(null);
  useEffect(() => { setAudioModeAsync({ playsInSilentMode: true }).catch(() => {}); }, []);
  const select = (track: Playable) => {
    if (!track.previewUrl) throw new Error('This track has no audio preview.');
    ++generation.current; selected.current = track; setCurrent(track);
    player.replace({ uri: track.previewUrl }); player.play(); recordAction('playback_start');
  };
  const stop = () => {
    ++generation.current; mode.current = null; selected.current = null;
    player.pause(); setCurrent(null); recordAction('playback_stop');
  };
  const toggle = (track: Playable) => {
    if (!track.previewUrl) return Alert.alert('No preview', 'This track has no audio preview.');
    if (selected.current?.previewUrl === track.previewUrl) {
      if (status.playing) { player.pause(); recordAction('playback_pause'); } else { player.play(); recordAction('playback_start'); }
    } else {
      mode.current = null; select(track);
    }
  };
  const playlistNext = () => {
    const queue = mode.current;
    if (queue?.kind !== 'playlist') return;
    const next = queue.tracks.find(track => track.previewUrl && !queue.played.has(track.id));
    if (!next) { stop(); return; }
    queue.played.add(next.id); select(next);
  };
  const playPlaylist = (playlist: Playlist) => {
    mode.current = { kind: 'playlist', id: playlist.id, tracks: playlist.tracks, played: new Set() };
    playlistNext();
  };
  const updatePlaylist = (playlist: Playlist) => {
    if (mode.current?.kind === 'playlist' && mode.current.id === playlist.id) mode.current.tracks = playlist.tracks;
  };
  const playEvent = async (id: string, advance = false): Promise<VoteEvent> => {
    const request = ++generation.current;
    const event = await api.getEvent(id);
    if (!event.mine) throw new Error('Only the organizer can advance event playback.');
    const next = advance || !event.current ? await api.advanceEvent(id) : event;
    if (!next.current?.previewUrl) throw new Error('The selected track has no preview. Choose another track.');
    if (request !== generation.current) return next;
    mode.current = { kind: 'event', id }; select(next.current);
    return next;
  };
  useEffect(() => {
    if (!status.didJustFinish || !mode.current || pending.current === generation.current || handled.current === generation.current) return;
    handled.current = generation.current;
    const queue = mode.current;
    if (queue.kind === 'playlist') { playlistNext(); return; }
    const version = generation.current;
    pending.current = version;
    (async () => {
      try {
        // The expected current ID prevents two organizer devices skipping two tracks.
        let event: VoteEvent;
        try { event = await api.advanceEvent(queue.id, selected.current?.id); }
        catch (e) {
          if (!(e instanceof ApiError) || e.code !== 'version_conflict') throw e;
          event = await api.getEvent(queue.id);
        }
        if (version !== generation.current || mode.current !== queue) return;
        if (event.current?.previewUrl) select(event.current);
        else stop();
      } catch (e) {
        if (version !== generation.current) return;
        stop();
        if (!(e instanceof ApiError) || e.code !== 'empty_queue') Alert.alert('Playback stopped', e instanceof Error ? e.message : 'Reconnect and start playback again.');
      } finally { if (pending.current === version) pending.current = null; }
    })();
  }, [status.didJustFinish]);
  const activePlaylist = current && mode.current?.kind === 'playlist' ? mode.current.id : null;
  useEffect(() => {
    if (!activePlaylist) return;
    let active = true;
    return (() => {
      const unsubscribe = api.subscribe(`playlist:${activePlaylist}`, async () => {
        try {
          const fresh = await api.getPlaylist(activePlaylist);
          if (active) updatePlaylist(fresh);
        } catch (e) {
          if (active && e instanceof ApiError && [401, 403, 404].includes(e.status)) stop();
        }
      });
      return () => { active = false; unsubscribe(); };
    })();
  }, [activePlaylist, user?.id]);
  useEffect(() => { stop(); }, [user?.id, player]);
  useEffect(() => {
    if (!online) player.pause();
  }, [online, player]);
  // Only the device explicitly bound on this installation consumes its commands.
  useEffect(() => {
    if (!user || !online || !api.listDelegations) return;
    let active = true, busy = false, bound: string | null = null;
    let applied = -1;
    let unsubscribe = () => {};
    const refresh = async () => {
      if (!active || busy || !bound) return;
      const target = bound;
      busy = true;
      try {
        const device = (await api.listDelegations()).find(d => d.deviceId === target && d.mine);
        if (!active || bound !== target) return;
        if (!device) { stop(); return; }
        if (device.version <= applied) return;
        applied = device.version;
        mode.current = null;
        if (device.action === 'stop') stop();
        else if (device.action === 'pause') player.pause();
        else if (device.previewUrl) {
          if (selected.current?.previewUrl === device.previewUrl) player.play();
          else select({ title: device.trackTitle ?? 'Device preview', artist: '', previewUrl: device.previewUrl });
        } else Alert.alert('No preview', 'This device track has no audio preview. Choose another track.');
      } catch (e) {
        if (active && e instanceof ApiError && [401, 403, 404].includes(e.status)) stop();
      } finally { busy = false; }
    };
    const bind = async () => {
      const id = await getLocalDevice(user.id);
      if (!active || id === bound) return;
      unsubscribe(); stop(); bound = id; applied = -1;
      if (id) { unsubscribe = api.subscribe(`device:${id}`, refresh); void refresh(); }
    };
    void bind().catch(() => {});
    const remove = onLocalDeviceChange(() => { void bind().catch(() => {}); });
    const timer = setInterval(() => { void refresh(); }, 5000);
    // useAudioPlayer owns native disposal. Its cleanup may run before ours, so
    // only cancel JS work here; calling pause on that released object crashes.
    return () => { active = false; unsubscribe(); remove(); clearInterval(timer); };
  }, [user?.id, online, player]);
  useEffect(() => () => { ++generation.current; mode.current = null; }, []);

  return <PlayerCtx.Provider value={{ current, playing: status.playing, toggle, stop, playPlaylist, updatePlaylist, playEvent }}>{children}</PlayerCtx.Provider>;
}

export function MiniPlayer() {
  const { current, playing, toggle, stop } = usePlayer();
  if (!current) return null;
  return <View style={[s.bar, { marginHorizontal: 8, marginBottom: 6 }]}>
    <Art seed={current.title} uri={current.artwork} size={40} radius={8} />
    <View style={{ flex: 1 }}>
      <Text style={s.rowTitle} numberOfLines={1}>{current.title}</Text>
      <Text style={s.muted} numberOfLines={1}>{current.artist} · preview</Text>
    </View>
    <Pressable onPress={() => toggle(current)} hitSlop={10}><Ionicons name={playing ? 'pause-circle' : 'play-circle'} size={40} color={colors.accent} /></Pressable>
    <Pressable onPress={stop} hitSlop={10}><Ionicons name="stop-circle-outline" size={30} color={colors.muted} /></Pressable>
  </View>;
}
