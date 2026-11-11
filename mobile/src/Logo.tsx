import React from 'react';
import { View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors, Text } from './ui';

// A sound wave inside a rounded badge. Same shape as assets/logo.svg and the app icon.
const BARS = [0.34, 0.6, 0.92, 0.52, 1, 0.68, 0.4];

export function LogoMark({ size = 56 }: { size?: number }) {
  const bar = size * 0.065;
  return (
    <LinearGradient colors={[colors.purple, colors.accent]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
      style={{ width: size, height: size, borderRadius: size * 0.26, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: size * 0.05 }}>
      {BARS.map((h, i) => (
        <View key={i} style={{ width: bar, height: size * 0.56 * h, borderRadius: bar / 2, backgroundColor: '#fff' }} />
      ))}
    </LinearGradient>
  );
}

export function Logo({ size = 48, stacked }: { size?: number; stacked?: boolean }) {
  if (stacked) {
    return (
      <View style={{ alignItems: 'center', gap: size * 0.22 }}>
        <LogoMark size={size} />
        <Text style={{ fontSize: size * 0.5, fontWeight: '900' }}>
          Music <Text style={{ color: colors.accent, fontSize: size * 0.5, fontWeight: '900' }}>Room</Text>
        </Text>
      </View>
    );
  }
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: size * 0.28 }}>
      <LogoMark size={size} />
      <View>
        <Text style={{ fontSize: size * 0.5, fontWeight: '900', lineHeight: size * 0.56 }}>Music</Text>
        <Text style={{ fontSize: size * 0.5, fontWeight: '900', lineHeight: size * 0.56, color: colors.accent }}>Room</Text>
      </View>
    </View>
  );
}
