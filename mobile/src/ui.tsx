import React from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text as RNText, TextInput, TextInputProps, TextProps, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';

// Dark navy base, a pink accent, and a purple/pink glow rising from the bottom of each screen.
export const colors = {
  bg: '#0a0a18',
  surface: '#14142b',
  surface2: '#24243f',
  text: '#ffffff',
  muted: '#9a9ab5',
  accent: '#ee3a74',
  purple: '#7b3fe4',
  danger: '#ff6b6b',
};

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

// Themed Text: all screens import this instead of react-native's Text (default there is black).
export const Text = ({ style, ...p }: TextProps) => <RNText {...p} style={[{ color: colors.text }, style]} />;

export function Button({ title, onPress, kind = 'primary', disabled }: {
  title: string; onPress: () => void; kind?: 'primary' | 'secondary'; disabled?: boolean;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled}
      style={({ pressed }) => [s.btn, kind === 'secondary' && s.btn2, pressed && { opacity: 0.8 }, disabled && { opacity: 0.4 }]}>
      <Text style={s.btnText}>{title}</Text>
    </Pressable>
  );
}

export const Input = (p: TextInputProps) => (
  <TextInput placeholderTextColor={colors.muted} autoCapitalize="none" selectionColor={colors.accent}
    {...p} style={[s.input, p.style]} />
);

/** Page container with the glow background. `scroll` makes the content scrollable. */
export function Screen({ children, scroll }: { children: React.ReactNode; scroll?: boolean }) {
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <LinearGradient pointerEvents="none" style={StyleSheet.absoluteFill}
        colors={[colors.bg, colors.bg, '#1c1140', '#4b1b5e', '#7a2a60']} locations={[0, 0.4, 0.72, 0.9, 1]} />
      {scroll
        ? <ScrollView contentContainerStyle={s.screen} keyboardShouldPersistTaps="handled">{children}</ScrollView>
        : <View style={[s.screen, { flex: 1 }]}>{children}</View>}
    </View>
  );
}

export const Title = ({ children }: { children: React.ReactNode }) => <Text style={s.title}>{children}</Text>;
export const H = ({ children }: { children: React.ReactNode }) => <Text style={s.h}>{children}</Text>;
export const Banner = ({ text }: { text: string }) => <View style={s.banner}><Text>{text}</Text></View>;

// Square "cover" placeholder: a stable colour pair per title, since there is no real artwork yet.
const hue = (seed: string) => [...seed].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
export function Art({ seed, size = 52, radius = 10, uri }: { seed: string; size?: number; radius?: number; uri?: string }) {
  if (uri) return <Image source={{ uri }} style={{ width: size, height: size, borderRadius: radius, backgroundColor: colors.surface2 }} />;
  const h = hue(seed);
  return (
    <LinearGradient colors={[`hsl(${h}, 62%, 46%)`, `hsl(${(h + 50) % 360}, 60%, 24%)`]}
      start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
      style={{ width: size, height: size, borderRadius: radius, alignItems: 'center', justifyContent: 'center' }}>
      <Ionicons name="musical-notes" size={size * 0.42} color="rgba(255,255,255,0.85)" />
    </LinearGradient>
  );
}

/** Big cover with caption, for horizontal carousels. */
export function Tile({ title, subtitle, onPress }: { title: string; subtitle?: string; onPress?: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [{ width: 132, gap: 6 }, pressed && { opacity: 0.75 }]}>
      <Art seed={title} size={132} radius={14} />
      <Text style={s.rowTitle} numberOfLines={2}>{title}</Text>
      {!!subtitle && <Text style={s.muted} numberOfLines={1}>{subtitle}</Text>}
    </Pressable>
  );
}

/** One list row: cover, two lines of text, optional right-hand content. */
export function Row({ title, subtitle, right, onPress, index, artwork }: {
  title: string; subtitle?: string; right?: React.ReactNode; onPress?: () => void; index?: number; artwork?: string;
}) {
  return (
    <Pressable onPress={onPress} disabled={!onPress} style={({ pressed }) => [s.row, pressed && { opacity: 0.7 }]}>
      {index !== undefined && <Text style={s.index}>{index}</Text>}
      <Art seed={title} uri={artwork} />
      <View style={{ flex: 1 }}>
        <Text style={s.rowTitle} numberOfLines={1}>{title}</Text>
        {!!subtitle && <Text style={s.muted} numberOfLines={1}>{subtitle}</Text>}
      </View>
      {right}
    </Pressable>
  );
}

export const Pill = ({ title, onPress, active, disabled }: { title: string; onPress: () => void; active?: boolean; disabled?: boolean }) => (
  <Pressable onPress={onPress} disabled={disabled}
    style={[s.pill, active && { backgroundColor: colors.accent, borderColor: colors.accent }, disabled && { opacity: 0.6 }]}>
    <Text style={{ fontWeight: '700', fontSize: 13 }}>{title}</Text>
  </Pressable>
);

/** "Up next" bar: shows the track that will be played first (top of the vote ranking). */
export function UpNextBar({ title, artist, votes, artwork, onPlay, playing, label = 'UP NEXT' }: {
  title: string; artist: string; votes: number; artwork?: string; onPlay?: () => void; playing?: boolean; label?: string;
}) {
  return (
    <View style={s.bar}>
      <Art seed={title} uri={artwork} size={44} radius={8} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '800', letterSpacing: 1 }}>{label}</Text>
        <Text style={s.rowTitle} numberOfLines={1}>{title}</Text>
        <Text style={s.muted} numberOfLines={1}>{artist} · {votes} votes</Text>
      </View>
      {onPlay && (
        <Pressable onPress={onPlay} hitSlop={10}>
          <Ionicons name={playing ? 'pause-circle' : 'play-circle'} size={44} color={colors.accent} />
        </Pressable>
      )}
    </View>
  );
}

/** Shown in place of a Premium-only feature. */
export function UpgradeCard({ title, text, onPress }: { title: string; text: string; onPress: () => void }) {
  return (
    <View style={[s.banner, { gap: 8, borderWidth: 1, borderColor: colors.accent }]}>
      <Text style={{ fontWeight: '800', fontSize: 16 }}>🔒 {title}</Text>
      <Text style={s.muted}>{text}</Text>
      <Button title="See plans" onPress={onPress} />
    </View>
  );
}

export const s = StyleSheet.create({
  screen: { padding: 16, gap: 12 },
  title: { fontSize: 34, fontWeight: '900', color: colors.text, marginTop: 4 },
  h: { fontSize: 19, fontWeight: '800', marginTop: 10, color: colors.text },
  btn: { backgroundColor: colors.accent, paddingVertical: 14, paddingHorizontal: 20, borderRadius: 999, alignItems: 'center' },
  btn2: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.surface2 },
  btnText: { color: colors.text, fontWeight: '700' },
  input: { backgroundColor: colors.surface, color: colors.text, borderRadius: 14, padding: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6 },
  rowTitle: { fontWeight: '700', fontSize: 15 },
  index: { width: 18, color: colors.muted, textAlign: 'center' },
  banner: { backgroundColor: colors.surface2, padding: 12, borderRadius: 12 },
  muted: { color: colors.muted, fontSize: 13 },
  pill: { paddingVertical: 7, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: colors.surface2 },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: 'rgba(20,20,43,0.92)', padding: 12, borderRadius: 16 },
});
