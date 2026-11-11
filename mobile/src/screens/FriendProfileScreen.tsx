import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { api } from '../api';
import { H, Screen, Text, errMsg } from '../ui';
export default function FriendProfileScreen({ route }: any) {
  const [profile, setProfile] = useState<{ name: string; bio: string; location: string } | null>(null);
  const [error, setError] = useState('');
  useFocusEffect(useCallback(() => {
    let active = true;
    setProfile(null);
    (async () => {
      try {
        if (!api.getFriendProfile) throw new Error('Use the real backend to view friends-only profiles.');
        const p = await api.getFriendProfile(route.params.id);
        if (active) { setProfile(p); setError(''); }
      } catch (e) { if (active) setError(errMsg(e)); }
    })();
    return () => { active = false; setProfile(null); };
  }, [route.params.id]));
  return <Screen><H>{profile?.name ?? 'Friend profile'}</H><Text>{error || profile?.bio}</Text>
    {profile && <><H>Friends-only location</H><Text>{profile.location || 'Not shared'}</Text></>}
  </Screen>;
}
