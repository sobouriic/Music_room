import React, { useState } from 'react';
import { Alert } from '../alert';
import { api } from '../api';
import { Button, H, Input, Screen, Text, errMsg, s } from '../ui';

export default function RegisterScreen({ navigation }: any) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const submit = async () => {
    if (!email.includes('@')) return Alert.alert('Enter a valid email');
    if (password.length < 12) return Alert.alert('Password must have at least 12 characters');
    try {
      await api.register(email.trim(), password);
      // The back-end never says whether the address already exists, so the message is always the same.
      Alert.alert('Check your email', 'If the address is eligible, we sent a verification code.', [
        { text: 'Enter the code', onPress: () => navigation.replace('VerifyEmail', { email: email.trim() }) },
      ]);
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen>
      <H>Create an account</H>
      <Input placeholder="Email" keyboardType="email-address" value={email} onChangeText={setEmail} />
      <Input placeholder="Password (12+ characters)" secureTextEntry value={password} onChangeText={setPassword} />
      <Button title="Sign up" onPress={submit} />
      {__DEV__ && <Text style={s.muted}>Dev tip: the verification email is a file in backend/.dev-mail/ (copy the "Token:" value).</Text>}
    </Screen>
  );
}
