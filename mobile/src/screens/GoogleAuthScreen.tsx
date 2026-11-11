import React, { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as WebBrowser from 'expo-web-browser';
import { Alert } from '../alert';
import * as Crypto from 'expo-crypto';
import { api, ApiError } from '../api';
import { b64url, parseCallback } from '../pkceUtils';
import { useAuth } from '../context/AuthContext';
import { Button, H, Screen, Text, errMsg, s } from '../ui';

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
// PKCE (RFC 7636, S256): the verifier never leaves the phone until the final exchange.
async function makePkce() {
  const bytes = await Crypto.getRandomBytesAsync(64);
  const verifier = Array.from(bytes, (b) => CHARS[b % CHARS.length]).join('');
  const digest = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier, {
    encoding: Crypto.CryptoEncoding.BASE64,
  });
  return { verifier, challenge: b64url(digest) };
}

function friendly(e: unknown) {
  if (e instanceof ApiError) {
    if (e.code === 'google_not_configured') return 'Google sign-in is not configured on the server (see GOOGLE_* in backend/.env).';
    if (e.code === 'invalid_oauth_state' || e.code === 'invalid_pkce') return 'This attempt expired or was already used. Start again.';
  }
  return errMsg(e);
}

export default function GoogleAuthScreen({ route, navigation }: any) {
  const needsBuild = Platform.OS !== 'web' && Constants.executionEnvironment === 'storeClient';
  const intent: 'login' | 'link' = route.params?.intent ?? 'login';
  const { start, setUser } = useAuth();
  const pkce = useRef<{ verifier: string; state: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const autoOpened = useRef(false);
  const exchanging = useRef(false);

  const openGoogle = async () => {
    if (busy) return;
    if (api.kind === 'mock') {
      Alert.alert('Connect to the backend',
        'Google sign-in is unavailable in demo mode.');
      return;
    }
    if (needsBuild) {
      Alert.alert('Development build needed',
        'Google sign-in returns to the Music Room app using its own link. Run make ios-build or make android-build, then test in that app instead of Expo Go.');
      return;
    }
    try {
      setBusy(true);
      const { verifier, challenge } = await makePkce();
      const { authorizationUrl, state } = await api.googleStart(challenge, intent);
      pkce.current = { verifier, state };
      if (Platform.OS === 'web') {
        // Web: keep the attempt in this tab, go to Google in the same tab. The back-end sends the browser back to the app
        // with the result in the URL fragment, and AuthContext finishes the sign-in (no pasting needed).
        sessionStorage.setItem('music-room-google-attempt', JSON.stringify({ verifier, state, intent, createdAt: Date.now() }));
        window.location.assign(authorizationUrl);
      } else {
        const result = await WebBrowser.openAuthSessionAsync(authorizationUrl, 'musicroom://oauth');
        if (result.type === 'success') await finish(result.url);
        else pkce.current = null;
      }
    } catch (e) { Alert.alert('Error', friendly(e)); }
    finally { setBusy(false); }
  };

  // Same-tab browser navigation needs no popup click. Start once on each platform.
  useEffect(() => {
    if (autoOpened.current) return;
    autoOpened.current = true;
    openGoogle();
  }, []);

  const finish = async (callbackUrl: string) => {
    if (exchanging.current) return;
    if (!callbackUrl.startsWith('musicroom://oauth?') || !pkce.current) return;
    const { code, state, error } = parseCallback(callbackUrl);
    if (state !== pkce.current.state) return Alert.alert('Security check failed', 'The state does not match. Start again.');
    if (error) { pkce.current = null; return Alert.alert('Google refused', error); }
    if (!code || !state) return Alert.alert('Google sign-in', 'The callback did not include a sign-in code. Start again.');
    try {
      setBusy(true);
      exchanging.current = true;
      if (intent === 'login') {
        await start(await api.googleExchange(state, code, pkce.current.verifier));
      } else {
        await api.googleLink(state, code, pkce.current.verifier);
        setUser(await api.getMe());
        Alert.alert('Google linked');
        navigation.goBack();
      }
      pkce.current = null;
    } catch (e) { Alert.alert('Error', friendly(e)); }
    finally { exchanging.current = false; setBusy(false); }
  };

  return (
    <Screen scroll>
      <H>{intent === 'login' ? 'Sign in with Google' : 'Link your Google account'}</H>
      {needsBuild ? <>
        <Text>Google login needs the installed Music Room development app. You are currently using Expo Go.</Text>
        <Text style={s.muted}>Build once with make ios-build or make android-build. Afterwards use make ios or make android to open Music Room without rebuilding.</Text>
      </> : <>
        <Text>Continue with Google in the browser, then return to Music Room automatically.</Text>
        <Button title={busy ? 'Signing in…' : 'Open Google'} onPress={openGoogle} disabled={busy} />
      </>}
    </Screen>
  );
}
