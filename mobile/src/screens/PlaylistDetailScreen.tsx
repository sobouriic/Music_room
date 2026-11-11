import React, { useCallback, useEffect, useState } from 'react';
import { Alert } from '../alert';
import { api, Playlist } from '../api';
import { useAuth } from '../context/AuthContext';
import { useSubscription } from '../context/SubscriptionContext';
import { InvitePicker } from '../InvitePicker';
import { TrackSearch } from '../music/TrackSearch';
import { usePlayer } from '../music/player';
import { offline } from '../offline';
import { Button, H, Pill, Row, Screen, Text, Title, errMsg, s } from '../ui';

export default function PlaylistDetailScreen({ route, navigation }: any) {
  const { id } = route.params;
  const { user, online = true, cachePlan } = useAuth();
  const { isPremium } = useSubscription();
  const { toggle, playPlaylist, updatePlaylist } = usePlayer();
  const [message, setMessage] = useState('');
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const load = useCallback(async () => {
    if (!user) return;
    try {
      const saved = await offline.get(user.id, id).catch(() => null);
      if (saved) setPlaylist(saved);
      if (!online) {
        setMessage(saved ? 'Saved offline copy. Open Offline playlists to edit and sync. Audio previews need internet.' : 'This playlist has not been saved on this device. Connect to download it.');
        return;
      }
      const p = await api.getPlaylist(id); setPlaylist(p); updatePlaylist(p); setMessage('');
    } catch (e) {
      setMessage('Showing the saved copy if available. Reconnect to refresh this playlist.');
    }
  }, [id, user?.id, online]);
  useEffect(() => { load(); return online ? api.subscribe(`playlist:${id}`, () => load()) : undefined; }, [id, load, online]);
  const run = async (operation: () => Promise<Playlist>) => {
    try { const p = await operation(); setPlaylist(p); updatePlaylist(p); } catch (e) { Alert.alert('Playlist', errMsg(e)); }
  };
  const saveOffline = async () => {
    if (!playlist || !user) return;
    try {
      const sub = await api.getSubscription();
      if (sub.plan !== 'premium') throw new Error('Premium is needed to save offline playlists.');
      await cachePlan(sub.plan);
      const fresh = await api.getPlaylist(id);
      await offline.save(user.id, fresh);
      setPlaylist(fresh);
      Alert.alert('Saved offline', 'The playlist metadata is saved. Open Offline playlists to reorder or remove tracks without internet. Audio previews need a connection.');
    } catch (e) { Alert.alert('Offline', errMsg(e)); }
  };
  return <Screen scroll>
    <Title>{playlist?.name ?? 'Playlist'}</Title>
    <Text style={s.muted}>{playlist?.tracks.length ?? 0} tracks · {playlist?.visibility}</Text>
    {!!message && <Text style={s.muted}>{message}</Text>}
    <Button title="Play playlist previews" disabled={!online || !playlist?.tracks.length} onPress={() => playlist && playPlaylist(playlist)} />
    {playlist?.tracks.map((track, index) => <Row key={track.id} title={track.title} subtitle={track.artist}
      right={<>
        {track.previewUrl && <Pill title="▶" onPress={() => toggle(track)} />}
        <Pill title="↑" disabled={!online || index === 0} onPress={() => run(() => api.movePlaylistTrack(id, index, index - 1, playlist.version))} />
        <Pill title="×" disabled={!online} onPress={() => run(() => api.removePlaylistTrack(id, track.id, playlist.version))} />
      </>} />)}
    {online && <><H>Add a track</H>
    <TrackSearch actionLabel="Add" onPick={track => run(() => api.addPlaylistTrack(id, track))} /></>}
    {playlist?.mine && online && <InvitePicker selected={playlist.invitedIds} onChange={ids => run(() => api.setPlaylistInvites(id, ids))} />}
    <Button title={isPremium ? 'Save for offline editing' : 'Get Premium for offline editing'} kind="secondary" disabled={!playlist || !online}
      onPress={() => isPremium ? saveOffline() : navigation.navigate('Plans')} />
    {playlist?.mine && <Button title="Playlist settings" kind="secondary" onPress={() => navigation.navigate('ResourceSettings', { kind: 'playlist', id })} />}
    <Button title="Offline playlists" kind="secondary" onPress={() => navigation.navigate('Offline')} />
  </Screen>;
}
