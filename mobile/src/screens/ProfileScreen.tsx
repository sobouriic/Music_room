import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { View } from 'react-native';
import { Alert } from '../alert';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';
import { useSubscription } from '../context/SubscriptionContext';
import { Banner, Button, H, Input, Screen, Text, colors, errMsg, s } from '../ui';

export default function ProfileScreen({ navigation }: any) {
  const { user, setUser, logout, reloadUser } = useAuth();
  const { plan } = useSubscription();
  // Google sign-ups arrive with an empty display name, so fall back to the part of the email before the @.
  const shownName = user!.profile.displayName || user!.email.split('@')[0];
  const [p, setP] = useState({ ...user!.profile, displayName: shownName });
  const [prefs, setPrefs] = useState(user!.profile.musicPreferences.join(', '));
  const [editable, setEditable] = useState(false);
  useFocusEffect(useCallback(() => {
    let active = true;
    setEditable(false);
    reloadUser().then(fresh => {
      if (!active) return;
      setP(fresh.profile); setPrefs(fresh.profile.musicPreferences.join(', ')); setEditable(true);
    }).catch(() => {});
    return () => { active = false; setEditable(false); };
  }, [user?.id]));
  const googleLinked = user!.providers.includes('google');

  const save = async () => {
    try {
      if (!editable) throw new Error('Reconnect and reopen Profile before editing.');
      const musicPreferences = prefs.split(',').map((x) => x.trim()).filter(Boolean);
      setUser(await api.updateProfile({ ...p, musicPreferences }));
      Alert.alert('Saved');
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen scroll>
      {!user!.verified && <Banner text="Your email is not validated yet." />}
      <View style={{ alignItems: 'center', gap: 6, marginVertical: 8 }}>
        <View style={{ width: 84, height: 84, borderRadius: 42, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontSize: 36, fontWeight: '900' }}>{shownName.charAt(0).toUpperCase()}</Text>
        </View>
        <Text style={{ fontSize: 24, fontWeight: '800' }}>{shownName}</Text>
        <Text style={s.muted}>{user!.email}</Text>
        {googleLinked && <Text style={s.muted}>{user!.hasPassword ? 'Google account linked' : 'Signed in with Google'}</Text>}
      </View>

      {!editable && <Banner text="Reconnect and reopen this screen to edit your current profile." />}
      <H>Public (everyone can see)</H>
      <Input placeholder="Display name" autoCapitalize="words" value={p.displayName} onChangeText={(v) => setP({ ...p, displayName: v })} />
      <Input placeholder="Bio" multiline value={p.bio} onChangeText={(v) => setP({ ...p, bio: v })} />
      <H>Friends only</H>
      <Input placeholder="Location" value={p.location} onChangeText={(v) => setP({ ...p, location: v })} />
      <H>Private (only me)</H>
      <Input placeholder="Notes" multiline value={p.notes} onChangeText={(v) => setP({ ...p, notes: v })} />
      <H>Music preferences (comma separated)</H>
      <Input value={prefs} onChangeText={setPrefs} />
      <Button title="Save profile" disabled={!editable} onPress={save} />

      <H>Linked accounts</H>
      <Button title={googleLinked ? 'Google linked ✓' : 'Link Google'} kind="secondary" disabled={googleLinked} onPress={() => navigation.navigate('LinkGoogle', { intent: 'link' })} />

      <H>Subscription</H>
      <Text>Current plan: {plan === 'premium' ? 'Premium' : 'Free'}</Text>
      <Button title="Manage subscription" kind="secondary" onPress={() => navigation.navigate('Plans')} />

      <Button title="Log out" kind="secondary" onPress={logout} />
      <Button title="Connection settings" kind="secondary" onPress={() => navigation.navigate('Settings')} />
    </Screen>
  );
}
