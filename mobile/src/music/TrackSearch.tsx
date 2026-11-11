import React, { useState } from 'react';
import { ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Button, colors, Input, Pill, Row, Text, s } from '../ui';
import { api, TrackInput } from '../api';
import { usePlayer } from './player';

/** Search the music catalog, preview a result, and pick it (suggest to an event / add to a playlist). */
export function TrackSearch({ actionLabel, onPick }: { actionLabel: string; onPick: (t: TrackInput) => void }) {
  const { current, playing, toggle } = usePlayer();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<TrackInput[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const search = async () => {
    setBusy(true); setError('');
    try { setResults(await api.searchTracks(q)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); setResults([]); }
    finally { setBusy(false); }
  };

  return (
    <>
      <Input placeholder="Search a song or an artist" value={q} onChangeText={setQ} onSubmitEditing={search} returnKeyType="search" />
      <Button title="Search" kind="secondary" onPress={search} disabled={busy || !q.trim()} />
      {busy && <ActivityIndicator color={colors.accent} />}
      {!!error && <Text style={[s.muted, { color: colors.danger }]}>{error}</Text>}
      {results.map((t, i) => (
        <Row key={`${t.deezerId ?? t.title}-${i}`} title={t.title} subtitle={t.artist} artwork={t.artwork}
          right={<>
            {t.previewUrl && (
              <Ionicons name={current?.previewUrl === t.previewUrl && playing ? 'pause-circle' : 'play-circle-outline'}
                size={30} color={colors.muted} onPress={() => toggle(t)} />
            )}
            <Pill title={actionLabel} onPress={() => onPick(t)} />
          </>} />
      ))}
    </>
  );
}
