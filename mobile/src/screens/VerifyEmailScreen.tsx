import React, { useState } from 'react';
import { Alert } from '../alert';
import { api } from '../api';
import { Button, H, Input, Screen, Text, errMsg, s } from '../ui';

export default function VerifyEmailScreen({ route, navigation }: any) {
  const [email, setEmail] = useState<string>(route.params?.email ?? '');
  const [token, setToken] = useState(route.params?.token ?? '');
  const [password, setPassword] = useState('');

  const verify = async () => {
    try {
      await api.verifyEmail(token.trim(), password);
      Alert.alert('Email verified', 'You can now log in.', [{ text: 'OK', onPress: () => navigation.navigate('Login') }]);
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  const resend = async () => {
    if (!email) return Alert.alert('Enter your email first');
    try { await api.resendVerification(email.trim()); Alert.alert('Sent', 'If the account is eligible, a new code was sent.'); }
    catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen>
      <H>Verify your email</H>
      <Text style={s.muted}>Paste the token from the verification email.</Text>
      <Input placeholder="Verification token" value={token} onChangeText={setToken} />
      <Text style={s.muted}>Set the password for your verified account. This replaces any unverified signup password.</Text>
      <Input placeholder="Your password (12+ characters)" secureTextEntry value={password} onChangeText={setPassword} />
      <Button title="Verify" onPress={verify} />
      <Input placeholder="Email (to resend)" keyboardType="email-address" value={email} onChangeText={setEmail} />
      <Button title="Resend the email" kind="secondary" onPress={resend} />
    </Screen>
  );
}
