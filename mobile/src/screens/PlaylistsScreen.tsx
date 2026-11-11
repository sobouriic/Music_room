import React, { useCallback, useState } from 'react';
import { Switch, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { Alert } from '../alert';
import { useAuth } from '../context/AuthContext';
import { offline, savedView } from '../offline';
import { api, Playlist } from '../api';
import { Button, colors, errMsg, H, Input, Row, Screen, Text, Title, s } from '../ui';

export default function PlaylistsScreen({ navigation }: any) {
  const { user, online = true } = useAuth();
  const [message, setMessage] = useState('');
  const [items, setItems] = useState<Playlist[]>([]);
  const [name, setName] = useState('');
  const [isPrivate, setPrivate] = useState(false);
  const [invitedOnly, setInvitedOnly] = useState(false); // license: default everyone can edit

  const load = useCallback(async () => {
    if (!user) return;
    const cached = await offline.list(user.id).catch(() => []);
    if (cached.length || !online) setItems(cached.map(savedView));
    if (!online) { setMessage('Offline — showing playlists saved on this device.'); return; }
    try { setItems(await api.listPlaylists()); setMessage(''); }
    catch { setMessage('Could not refresh. Saved offline playlists remain available.'); }
  }, [user?.id, online]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const create = async () => {
    if (!name.trim()) return;
    try {
      await api.createPlaylist(name.trim(), isPrivate ? 'private' : 'public', invitedOnly ? 'invited' : 'open');
      setName(''); load();
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen scroll>
      <Title>Library</Title>
      <Text style={s.muted}>Playlists you can build together, in real time.</Text>
      {!!message && <Text style={s.muted}>{message}</Text>}
      <Button title="Offline playlists" kind="secondary" onPress={() => navigation.navigate('Offline')} />
      {items.map((p) => (
        <Row key={p.id} title={p.name} subtitle={`${p.tracks.length} tracks · ${p.visibility}`}
          onPress={() => navigation.navigate('PlaylistDetail', { id: p.id })}
          right={<Ionicons name="chevron-forward" size={18} color={colors.muted} />} />
      ))}
      <H>New playlist</H>
      <Input placeholder="Playlist name" value={name} onChangeText={setName} />
      <View style={[s.row, { justifyContent: 'space-between' }]}>
        <Text>Private</Text><Switch value={isPrivate} onValueChange={setPrivate} trackColor={{ true: colors.accent }} />
      </View>
      <View style={[s.row, { justifyContent: 'space-between' }]}>
        <Text>Only invited users can edit</Text><Switch value={invitedOnly} onValueChange={setInvitedOnly} trackColor={{ true: colors.accent }} />
      </View>
      <Button title="+ New playlist" disabled={!online} onPress={create} />
    </Screen>
  );
}
