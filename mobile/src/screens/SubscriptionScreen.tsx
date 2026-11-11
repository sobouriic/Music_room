import React from 'react';
import { View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Alert } from '../alert';
import { Plan } from '../api';
import { useSubscription } from '../context/SubscriptionContext';
import { Button, colors, errMsg, Screen, Text, Title, s } from '../ui';

// The two offers, defined once. The server decides what each plan is really allowed to do.
const OFFERS: { plan: Plan; name: string; price: string; tagline: string; features: [string, boolean][] }[] = [
  {
    plan: 'free', name: 'Free', price: '€0', tagline: 'Vote, control music and edit playlists together.',
    features: [
      ['Track Vote: suggest and vote', true],
      ['Music Control Delegation', true],
      ['Browse playlists', true],
      ['Playlist Editor: create and co-edit', true],
      ['Offline Access', false],
    ],
  },
  {
    plan: 'premium', name: 'Premium', price: 'Demo — no payment', tagline: 'Everything in Free, plus saved offline drafts.',
    features: [
      ['Track Vote: suggest and vote', true],
      ['Music Control Delegation', true],
      ['Browse playlists', true],
      ['Playlist Editor: create and co-edit', true],
      ['Save playlists and edit track order offline', true],
    ],
  },
];

export default function SubscriptionScreen() {
  const { plan, source, change } = useSubscription();

  const choose = (target: Plan, name: string) => {
    Alert.alert(`Switch to ${name}?`, target === 'premium'
      ? 'Demo subscription: no payment is taken. You unlock offline saving, editing and synchronization.'
      : 'Shared playlists stay on the server. Offline copies are cleared. Online playlist creation and editing remain available.', [
      { text: 'Confirm', onPress: async () => {
        try { await change(target); Alert.alert('Done', `You are now on the ${name} plan.`); }
        catch (e) { Alert.alert('Error', errMsg(e)); }
      } },
      { text: 'Cancel' },
    ]);
  };

  return (
    <Screen scroll>
      <Title>Plans</Title>
      <Text style={s.muted}>Switch between the two offers at any time.</Text>
      {OFFERS.map((o) => {
        const current = o.plan === plan;
        return (
          <View key={o.plan} style={{ backgroundColor: colors.surface, borderRadius: 18, padding: 16, gap: 10,
            borderWidth: 2, borderColor: current ? colors.accent : colors.surface2 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ fontSize: 22, fontWeight: '900' }}>{o.name}</Text>
              {current && <Text style={{ color: colors.accent, fontWeight: '800', fontSize: 12, letterSpacing: 1 }}>CURRENT PLAN</Text>}
            </View>
            <Text style={{ fontSize: 18, fontWeight: '700' }}>{o.price}</Text>
            <Text style={s.muted}>{o.tagline}</Text>
            {o.features.map(([label, included]) => (
              <View key={label} style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
                <Ionicons name={included ? 'checkmark-circle' : 'lock-closed'} size={20} color={included ? colors.accent : colors.muted} />
                <Text style={{ color: included ? colors.text : colors.muted }}>{label}</Text>
              </View>
            ))}
            <Button title={current ? 'Your current plan' : o.plan === 'premium' ? 'Choose Premium' : 'Switch to Free'}
              kind={o.plan === 'premium' ? 'primary' : 'secondary'} disabled={current} onPress={() => choose(o.plan, o.name)} />
          </View>
        );
      })}
      <Text style={s.muted}>
        {source === 'device'
          ? 'Using a locally saved plan. Connect to confirm your current subscription.'
          : 'Demo subscriptions are managed by the server. No payment is taken.'}
      </Text>
    </Screen>
  );
}
