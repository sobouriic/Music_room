import React, { useCallback, useState } from 'react';
import { View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api, Friend } from './api';
import { H, Pill, Text, colors, s } from './ui';

/** Organizer-only: choose which friends are invited. Friends are re-fetched every time the screen is shown. */
export function InvitePicker({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  useFocusEffect(useCallback(() => {
    let live = true;
    api.listFriends().then((f) => { if (live) { setFriends(f); setState('ready'); } }).catch(() => { if (live) setState('error'); });
    return () => { live = false; };
  }, []));
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <>
      <H>Invite friends</H>
      {state === 'loading' && <Text style={s.muted}>Loading your friends...</Text>}
      {state === 'error' && <Text style={[s.muted, { color: colors.danger }]}>Could not load your friends. Pull back to this screen to retry.</Text>}
      {state === 'ready' && friends.length === 0 && (
        <Text style={s.muted}>No friends yet. Find people in the Friends tab; they appear here once they accept.</Text>
      )}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {friends.map((f) => <Pill key={f.id} title={f.name} active={selected.includes(f.id)} onPress={() => toggle(f.id)} />)}
      </View>
    </>
  );
}
