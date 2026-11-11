import React from 'react';
import { useNearby } from '../context/NearbyContext';
import { recordAction } from '../activity';
import { Alert } from '../alert';
import { Button, Row, Screen, Text, Title, errMsg, s } from '../ui';

export default function NearbyScreen({ navigation }: any) {
  const { enabled, notifications, checking, message, events, enable, disable } = useNearby();
  return <Screen scroll>
    <Title>Nearby event alerts</Title>
    <Text style={s.muted}>Find active public Place & time events within 1 km. Allow location and notifications to receive nearby alerts. Checks run once a minute across the app while it is open and active. Alerts appear at the top of the app and in system notifications when allowed.</Text>
    <Button title={enabled ? 'Stop nearby alerts' : 'Enable nearby alerts'} onPress={() => { if (enabled) { disable(); recordAction('nearby_alerts_disabled'); } else void enable().catch(e => Alert.alert('Nearby alerts', errMsg(e))); }} />
    {enabled && <Text>{checking ? 'Checking your location…' : 'Nearby checks enabled.'} {!notifications && 'System notifications are unavailable or denied; nearby alerts appear here. Allow notifications in your device or browser settings for system banners.'}</Text>}
    {!!message && <Text>{message}</Text>}
    {events.map(event => <Row key={event.id} title={event.name} subtitle={`${event.tracks.length} tracks · public event`}
      onPress={() => navigation.navigate('EventDetail', { id: event.id, name: event.name })} />)}
  </Screen>;
}
