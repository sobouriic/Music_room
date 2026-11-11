import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { Alert } from '../alert';
import { api, Friend, FriendRequest, PendingInvitation } from '../api';
import { useAuth } from '../context/AuthContext';
import { Banner, Button, errMsg, H, Input, Pill, Row, Screen, Text, Title, s } from '../ui';

export default function FriendsScreen({ navigation }: any) {
  const { user } = useAuth();
  const [friends, setFriends] = useState<Friend[]>([]);
  const [requests, setRequests] = useState<FriendRequest[]>([]);
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<Friend[] | null>(null);

  const load = useCallback(async () => {
    try {
      setFriends(await api.listFriends());
      setRequests(await api.listFriendRequests());
      setInvitations(await api.listInvitations());
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); await load(); } catch (e) { Alert.alert('Error', errMsg(e)); }
  };
  const search = async () => {
    try { setFound(await api.searchUsers(query)); } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen scroll>
      <Title>Friends</Title>
      <Text style={s.muted}>Friends can see your "friends only" info, be invited to events and playlists, and control your devices.</Text>
      {!user?.profile.displayName && <Banner text="Set a display name in your Profile so other people can find you." />}

      {invitations.length > 0 && <H>Invitations</H>}
      {invitations.map((i) => (
        <Row key={i.kind + i.resourceId} title={i.name} subtitle={`${i.kind} invitation`}
          right={<Pill title="Accept" active onPress={() => act(() => api.acceptInvitation(i.kind, i.resourceId))} />} />
      ))}

      {requests.length > 0 && <H>Requests</H>}
      {requests.map((r) => (
        <Row key={r.userId} title={r.name} subtitle={r.incoming ? 'wants to be your friend' : 'request sent'}
          right={<>
            {r.incoming && <Pill title="Accept" active onPress={() => act(() => api.acceptFriendRequest(r.userId))} />}
            <Pill title={r.incoming ? 'Decline' : 'Cancel'} onPress={() => act(() => api.removeFriend(r.userId))} />
          </>} />
      ))}

      <H>My friends</H>
      {friends.length === 0 && <Text style={s.muted}>No friends yet.</Text>}
      {friends.map((f) => <Row key={f.id} title={f.name} right={<><Pill title="Profile" onPress={() => navigation.navigate('FriendProfile', { id: f.id })} /><Pill title="Remove" onPress={() => act(() => api.removeFriend(f.id))} /></>} />)}

      <H>Find people</H>
      <Input placeholder="Search by display name (2+ letters)" value={query} onChangeText={setQuery} onSubmitEditing={search} returnKeyType="search" />
      <Button title="Search" kind="secondary" onPress={search} disabled={query.trim().length < 2} />
      {found?.length === 0 && <Text style={s.muted}>Nobody found.</Text>}
      {found?.map((u) => (
        <Row key={u.id} title={u.name}
          right={<Pill title="Add" active onPress={() => act(async () => { await api.sendFriendRequest(u.id); setFound(found.filter((x) => x.id !== u.id)); })} />} />
      ))}
    </Screen>
  );
}
