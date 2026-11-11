import React, { useCallback, useEffect, useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Alert } from '../alert';
import { api, TrackInput, VoteEvent } from '../api';
import { InvitePicker } from '../InvitePicker';
import { currentPosition } from '../location';
import { TrackSearch } from '../music/TrackSearch';
import { usePlayer } from '../music/player';
import { fmtTime } from '../time';
import { Button, colors, errMsg, H, Input, Pill, Row, Screen, Text, Title, UpNextBar, s } from '../ui';

const licenseLabel = (e: VoteEvent) =>
  e.license === 'invited' ? 'Only invited friends can vote'
  : e.license === 'geo_time' ? `Vote on site, ${e.place ? fmtTime(e.place.startsAt) : '?'} to ${e.place ? fmtTime(e.place.endsAt) : '?'}`
  : 'Everyone can vote';

export default function EventDetailScreen({ route, navigation }: any) {
  const { id, name } = route.params;
  const { toggle, current, playing, playEvent } = usePlayer();
  const [event, setEvent] = useState<VoteEvent | null>(null);
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');

  const load = useCallback(async () => {
    try { setEvent(await api.getEvent(id)); } catch (e) { Alert.alert('Error', errMsg(e)); }
  }, [id]);

  // The server is the source of truth: on every pushed message we just refetch.
  useEffect(() => {
    load();
    return api.subscribe(`event:${id}`, () => load());
  }, [id, load]);

  const run = async (fn: () => Promise<VoteEvent>, errTitle = 'Error') => {
    try { setEvent(await fn()); } catch (e) { Alert.alert(errTitle, errMsg(e)); }
  };

  // The "place and time" license is checked by the SERVER; the app only reports where the phone is.
  const withLocation = async () => (event?.license === 'geo_time' ? await currentPosition() : undefined);
  const vote = (trackId: string, voted: boolean) => run(async () => {
    const location = await withLocation();
    return voted ? api.unvoteTrack(id, trackId, location) : api.voteTrack(id, trackId, location);
  }, 'Cannot vote');

  const suggest = (track: TrackInput) => run(async () => { const e = await api.suggestTrack(id, track); setTitle(''); setArtist(''); return e; }, 'Cannot suggest');
  const invite = (ids: string[]) => run(() => api.setEventInvites(id, ids));

  const tracks = event?.tracks ?? [];
  const totalVotes = tracks.reduce((n, t) => n + t.votes, 0);
  const top = tracks[0];
  const playingNow = (t?: { previewUrl?: string } | null) => !!t?.previewUrl && current?.previewUrl === t.previewUrl && playing;

  return (
    <Screen scroll>
      <Title>{name}</Title>
      <Text style={s.muted}>{tracks.length} tracks · {totalVotes} votes · {event?.visibility} · {event ? licenseLabel(event) : ''}</Text>

      {event?.current && (
        <UpNextBar label="NOW PLAYING" title={event.current.title} artist={event.current.artist} votes={0}
          artwork={event.current.artwork} playing={playingNow(event.current)} onPlay={() => toggle(event.current!)} />
      )}
      {top && (
        <UpNextBar title={top.title} artist={top.artist} votes={top.votes} artwork={top.artwork}
          playing={playingNow(top)} onPlay={() => toggle(top)} />
      )}
      {event?.mine && tracks.length > 0 && (
        <>
          <Button title="Start event playback" onPress={() => run(() => playEvent(id))} />
          <Button title="Play the next track (organizer)" kind="secondary" onPress={() => run(() => playEvent(id, true))} />
        </>
      )}

      <H>All songs</H>
      {tracks.length === 0 && <Text style={s.muted}>No track yet. Suggest the first one below.</Text>}
      {tracks.map((t, i) => (
        <Row key={t.id} index={i + 1} title={t.title} artwork={t.artwork} subtitle={`${t.artist} · ${t.votes} votes`}
          right={<>
            {t.previewUrl && <Ionicons name="play-circle-outline" size={28} color={colors.muted} onPress={() => toggle(t)} />}
            <Pill title={t.votedByMe ? 'Voted ✓' : 'Vote'} active={t.votedByMe} onPress={() => vote(t.id, t.votedByMe)} />
          </>} />
      ))}

      <H>Suggest a track</H>
      <TrackSearch actionLabel="Suggest" onPick={(t) => suggest(t)} />
      {api.kind === 'mock' && (
        <>
          <Text style={s.muted}>Demo mode: you can also add a track by hand.</Text>
          <Input placeholder="Title" value={title} onChangeText={setTitle} />
          <Input placeholder="Artist" value={artist} onChangeText={setArtist} />
          <Button title="Suggest" kind="secondary" disabled={!title.trim()} onPress={() => suggest({ title: title.trim(), artist: artist.trim() })} />
        </>
      )}

      {event?.mine && <Button title="Event settings" kind="secondary" onPress={() => navigation.navigate('ResourceSettings', { kind: 'event', id })} />}
      {event?.mine && (
        <InvitePicker selected={event.invitedIds} onChange={invite} />
      )}
    </Screen>
  );
}
