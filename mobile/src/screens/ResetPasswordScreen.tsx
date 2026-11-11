import React, { useState } from 'react';
import { Alert } from '../alert';
import { api } from '../api';
import { Button, H, Input, Screen, Text, errMsg, s } from '../ui';

export default function ResetPasswordScreen({ route, navigation }: any) {
  const [token, setToken] = useState(route.params?.token ?? '');
  const [password, setPassword] = useState('');

  const submit = async () => {
    if (password.length < 12) return Alert.alert('Password must have at least 12 characters');
    try {
      await api.resetPassword(token.trim(), password);
      Alert.alert('Password changed', 'Please log in with your new password.', [{ text: 'OK', onPress: () => navigation.navigate('Login') }]);
    } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen>
      <H>Reset your password</H>
      <Text style={s.muted}>Paste the token from the reset email (valid 1 hour).</Text>
      <Input placeholder="Reset token" value={token} onChangeText={setToken} />
      <Input placeholder="New password (12+ characters)" secureTextEntry value={password} onChangeText={setPassword} />
      <Button title="Change password" onPress={submit} />
    </Screen>
  );
}
