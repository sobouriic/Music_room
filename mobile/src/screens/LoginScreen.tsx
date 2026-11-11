import React, { useState } from 'react';
import { View } from 'react-native';
import { Alert } from '../alert';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';
import { Logo } from '../Logo';
import { Button, colors, errMsg, H, Input, Screen, Text } from '../ui';

export default function LoginScreen({ navigation }: any) {
  const { start } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const run = async (fn: () => Promise<any>) => {
    try { await start(await fn()); } catch (e) { Alert.alert('Error', errMsg(e)); }
  };

  return (
    <Screen scroll>
      <View style={{ alignItems: 'center', marginTop: 40, marginBottom: 16, gap: 10 }}>
        <Logo size={88} stacked />
        <Text style={{ color: colors.muted, textAlign: 'center' }}>Your music, with your friends.</Text>
      </View>
      <H>Log in</H>
      <Input placeholder="Email" keyboardType="email-address" value={email} onChangeText={setEmail} />
      <Input placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
      <Button title="Log in" onPress={() => run(() => api.login(email.trim(), password))} />
      <Button title="Continue with Google" kind="secondary" onPress={() => navigation.navigate('GoogleAuth', { intent: 'login' })} />
      <Button title="Create an account" kind="secondary" onPress={() => navigation.navigate('Register')} />
      <Button title="Forgot password?" kind="secondary" onPress={async () => {
        if (!email) return Alert.alert('Enter your email first');
        try {
          await api.forgotPassword(email.trim());
          Alert.alert('Check your inbox', 'If the account exists, a reset code was sent.', [
            { text: 'Enter the code', onPress: () => navigation.navigate('ResetPassword') },
            { text: 'Later' },
          ]);
        } catch (e) { Alert.alert('Error', errMsg(e)); }
      }} />
      <Button title="I have an email verification code" kind="secondary" onPress={() => navigation.navigate('VerifyEmail', { email })} />
      <Button title="Connection settings" kind="secondary" onPress={() => navigation.navigate('Settings')} />
    </Screen>
  );
}
