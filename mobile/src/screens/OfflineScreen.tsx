import React, { useCallback, useState } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api, ApiError } from '../api';
import { Alert } from '../alert';
import { useSubscription } from '../context/SubscriptionContext';
import { useAuth } from '../context/AuthContext';
import { offline, SavedPlaylist } from '../offline';
import { Button, H, Pill, Row, Screen, Text, Title, errMsg, s } from '../ui';

export default function OfflineScreen() {
  const { user, online = true, reloadUser } = useAuth();
  const { refresh: refreshPlan } = useSubscription();
  const [entries, setEntries] = useState<SavedPlaylist[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (revalidate = true) => {
    if (!user) return;
    try {
      const cached = await offline.list(user.id);
      setEntries(cached); // Render tracks before any network requests/timeouts.
      setMessage(online ? '' : 'Offline — your saved tracks and drafts are available.');
      if (!online || !revalidate) return;
      try {
        await offline.revalidate(user.id, id => api.getPlaylist(id));
        setEntries(await offline.list(user.id));
      } catch (e) {
        setMessage(e instanceof ApiError && e.status === 401
          ? 'Reconnect and sign in to synchronize. Your draft has not been overwritten.'
          : 'Could not refresh online. Your saved tracks and draft are kept.');
      }
    } catch (e) { setEntries([]); setMessage(errMsg(e)); }
  }, [user?.id, online]);
  useFocusEffect(useCallback(() => {
    let checking = false;
    const check = async () => {
      if (checking) return;
      checking = true;
      try { await load(AppState.currentState === 'active'); } finally { checking = false; }
    };
    check();
    const timer = setInterval(check, 60000);
    const listener = AppState.addEventListener('change', state => { if (state === 'active') check(); });
    return () => { clearInterval(timer); listener.remove(); };
  }, [load]));
  const edit = async (entry: SavedPlaylist, ids: string[]) => {
    try { await offline.edit(user!.id, entry.snapshot.id, ids); await load(false); }
    catch (e) { Alert.alert('Offline', errMsg(e)); }
  };
  const sync = async (entry: SavedPlaylist) => {
    if (!online) return Alert.alert('Offline', 'Your draft is saved. Reconnect before synchronizing.');
    if (!api.syncOfflinePlaylist) return Alert.alert('Offline', 'Use the real backend for offline synchronization.');
    setBusy(true);
    try {
      await offline.sync(user!.id, entry.snapshot.id, edit => api.syncOfflinePlaylist!(entry.snapshot.id, edit));
      Alert.alert('Synced', 'Your changes are saved on the server.');
    } catch (e) {
      Alert.alert('Not synced', e instanceof ApiError && e.status === 409
        ? 'Someone changed this playlist. Your draft is kept. Review it, then discard the saved copy and download the latest version. Server changes were not overwritten.'
        : errMsg(e));
    } finally { await load(false); setBusy(false); }
  };
  const discard = (entry: SavedPlaylist) => Alert.alert('Remove saved copy?',
    'This removes the offline copy and any unsynced draft. The server playlist stays unchanged.', [
      { text: 'Remove', onPress: async () => { await offline.remove(user!.id, entry.snapshot.id); await load(); } },
      { text: 'Cancel' },
    ]);
  return <Screen scroll>
    <Title>Offline playlists</Title>
    <Button title="Refresh connection" kind="secondary" disabled={busy} onPress={async () => {
      setBusy(true);
      try { await reloadUser(); await refreshPlan(); await load(); }
      catch { Alert.alert('Offline', 'No connection yet. Your saved playlists and drafts are kept.'); }
      finally { setBusy(false); }
    }} />
    <Text style={s.muted}>Saved metadata and drafts only. Audio previews need internet. Connect to sync; conflicts require review. Offline access expires seven days after the last Premium verification.</Text>
    {!!message && <Text>{message}</Text>}
    {entries.length === 0 && !message && <Text>Save a playlist online first.</Text>}
    {entries.map(entry => <React.Fragment key={entry.snapshot.id}>
      <H>{entry.snapshot.name}</H>
      <Text>{entry.mutationId ? 'Pending changes' : 'Saved'} · {new Date(entry.savedAt).toLocaleString()}</Text>
      {entry.trackIds.map((id, index) => {
        const track = entry.snapshot.tracks.find(t => t.id === id);
        if (!track) return null;
        return <Row key={id} title={track.title} subtitle={track.artist} right={<>
          <Pill title="↑" disabled={busy || index === 0} onPress={() => {
            const ids = [...entry.trackIds]; [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]; edit(entry, ids);
          }} />
          <Pill title="×" disabled={busy} onPress={() => edit(entry, entry.trackIds.filter(value => value !== id))} />
        </>} />;
      })}
      <Button title="Sync changes" disabled={busy || !online || !entry.mutationId} onPress={() => sync(entry)} />
      <Button title="Discard saved copy" kind="secondary" disabled={busy} onPress={() => discard(entry)} />
    </React.Fragment>)}
  </Screen>;
}
