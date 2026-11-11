import React, { useCallback, useState } from 'react';
import { FlatList, Switch, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Alert } from '../alert';
import { api, EventPlace, VoteEvent, VoteLicense } from '../api';
import { currentPosition } from '../location';
import { isoForHour } from '../time';
import { Button, colors, errMsg, H, Input, Pill, Screen, Text, Tile, Title, s } from '../ui';

const LICENSES: { key: VoteLicense; label: string }[] = [
  { key: 'open', label: 'Everyone' },
  { key: 'invited', label: 'Invited only' },
  { key: 'geo_time', label: 'Place & time' },
];

export default function EventsScreen({ navigation }: any) {
  const [events, setEvents] = useState<VoteEvent[]>([]);
  const [name, setName] = useState('');
  const [isPrivate, setPrivate] = useState(false); // default: public
  const [license, setLicense] = useState<VoteLicense>('open'); // default: everyone can vote
  const [startHour, setStartHour] = useState('16');
  const [endHour, setEndHour] = useState('18');
  const [position, setPosition] = useState<{ lat: number; lng: number } | null>(null);

  const load = useCallback(async () => {
    try { setEvents(await api.listEvents()); } catch (e) { Alert.alert('Error', errMsg(e)); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const useMyLocation = async () => {
    try { setPosition(await currentPosition()); } catch (e) { Alert.alert('Location', errMsg(e)); }
  };

  const create = async () => {
    if (!name.trim()) return;
    let place: EventPlace | undefined;
    if (license === 'geo_time') {
      const from = Number(startHour), to = Number(endHour);
      if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to > 24 || from >= to)
        return Alert.alert('Time window', 'Enter whole hours, for example 16 and 18.');
      if (!position) return Alert.alert('Place', 'Tap "Use my location" to set the venue.');
      place = { ...position, radiusM: 200, startsAt: isoForHour(from), endsAt: isoForHour(to) };
    }
    try {
      await api.createEvent(name.trim(), isPrivate ? 'private' : 'public', license, place);
      setName(''); setPosition(null);
      load();
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen scroll>
      <Title>Live events</Title>
      <Text style={s.muted}>Pick an event and vote for what plays next.</Text>
      <FlatList horizontal data={events} keyExtractor={(e) => e.id} showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 14, paddingVertical: 8 }}
        ListEmptyComponent={<Text style={s.muted}>No event yet. Create the first one below.</Text>}
        renderItem={({ item }) => (
          <Tile title={item.name} subtitle={`${item.visibility} · ${item.tracks.length} tracks`}
            onPress={() => navigation.navigate('EventDetail', { id: item.id, name: item.name })} />
        )} />

      <Button title="Nearby event alerts" kind="secondary" onPress={() => navigation.navigate('Nearby')} />
      <H>Create an event</H>
      <Input placeholder="Event name" value={name} onChangeText={setName} />
      <View style={[s.row, { justifyContent: 'space-between' }]}>
        <Text>Private event (invited friends only can see it)</Text>
        <Switch value={isPrivate} onValueChange={setPrivate} trackColor={{ true: colors.accent }} />
      </View>
      <Text style={s.muted}>Who can vote?</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {LICENSES.map((l) => <Pill key={l.key} title={l.label} active={license === l.key} onPress={() => setLicense(l.key)} />)}
      </View>
      {license === 'geo_time' && (
        <>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <Input style={{ flex: 1 }} placeholder="From (hour)" keyboardType="number-pad" value={startHour} onChangeText={setStartHour} />
            <Input style={{ flex: 1 }} placeholder="To (hour)" keyboardType="number-pad" value={endHour} onChangeText={setEndHour} />
          </View>
          <Button title={position ? 'Location set ✓ (200 m radius)' : 'Use my location as the venue'} kind="secondary" onPress={useMyLocation} />
        </>
      )}
      <Button title="+ New event" onPress={create} />
    </Screen>
  );
}
