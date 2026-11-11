import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import { api, Playlist, VoteEvent } from '../api';
import { Alert } from '../alert';
import { Button, H, Input, Pill, Screen, Text, errMsg } from '../ui';
export default function ResourceSettingsScreen({ route, navigation }: any) {
  const { kind, id } = route.params;
  const [resource, setResource] = useState<Playlist | VoteEvent | null>(null);
  const [lat, setLat] = useState(''); const [lng, setLng] = useState('');
  const [radius, setRadius] = useState('100');
  const [start, setStart] = useState(''); const [end, setEnd] = useState('');
  const load = useCallback(async () => {
    try {
      const r = kind === 'event' ? await api.getEvent(id) : await api.getPlaylist(id);
      if (!r.mine) throw new Error('Only the owner can change these settings.');
      setResource(r);
      const p = (r as VoteEvent).place;
      setLat(p ? String(p.lat) : ''); setLng(p ? String(p.lng) : '');
      setRadius(p ? String(p.radiusM) : '100'); setStart(p?.startsAt ?? ''); setEnd(p?.endsAt ?? '');
    } catch (e) { setResource(null); Alert.alert('Settings', errMsg(e)); }
  }, [id, kind]);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const save = async () => {
    if (!resource) return;
    try {
      if (kind === 'event') {
        if (!api.updateEvent) throw new Error('Use the real backend.');
        let place = undefined;
        if (resource.license === 'geo_time') {
          if (!lat.trim() || !lng.trim() || !radius.trim()) throw new Error('Enter latitude, longitude and radius.');
          const startsAt = new Date(start).toISOString(), endsAt = new Date(end).toISOString();
          place = { lat: Number(lat), lng: Number(lng), radiusM: Number(radius), startsAt, endsAt };
        }
        await api.updateEvent({ ...resource, place } as VoteEvent);
      } else {
        if (!api.updatePlaylist) throw new Error('Use the real backend.');
        await api.updatePlaylist(resource as Playlist);
      }
      navigation.goBack();
    } catch (e) { Alert.alert('Settings not saved', errMsg(e) + ' Reload before retrying a conflicting edit.'); }
  };
  if (!resource) return <Screen><Text>Loading settings…</Text></Screen>;
  return <Screen scroll><H>Name</H><Input value={resource.name} onChangeText={name => setResource({ ...resource, name })} />
    <H>Visibility</H>{(['public', 'private'] as const).map(visibility => <Pill key={visibility} title={visibility} active={resource.visibility === visibility} onPress={() => setResource({ ...resource, visibility })} />)}
    <H>{kind === 'event' ? 'Who can vote?' : 'Who can edit?'}</H>
    {(kind === 'event' ? ['open', 'invited', 'geo_time'] : ['open', 'invited']).map(license => <Pill key={license} title={license} active={resource.license === license} onPress={() => setResource({ ...resource, license } as VoteEvent)} />)}
    {resource.license === 'geo_time' && <><H>Place and time (ISO dates with timezone)</H>
      <Input placeholder="Latitude" value={lat} onChangeText={setLat} /><Input placeholder="Longitude" value={lng} onChangeText={setLng} />
      <Input placeholder="Radius in meters" value={radius} onChangeText={setRadius} />
      <Input placeholder="Start: 2026-11-05T16:00:00Z" value={start} onChangeText={setStart} />
      <Input placeholder="End: 2026-11-05T18:00:00Z" value={end} onChangeText={setEnd} /></>}
    <Button title="Save settings" onPress={save} /><Button title="Reload latest settings" kind="secondary" onPress={load} />
  </Screen>;
}
