import React, { useEffect, useState } from 'react';
import { Switch, View } from 'react-native';
import { Alert } from '../alert';
import { loadConfig } from '../config';
import { useAuth } from '../context/AuthContext';
import { Button, H, Input, Screen, Text, s } from '../ui';

// The subject requires the back-end address to be configurable inside the app.
export default function SettingsScreen() {
  const { configure } = useAuth();
  const [baseUrl, setBaseUrl] = useState('');
  const [useMock, setUseMock] = useState(true);

  useEffect(() => { loadConfig().then((c) => { setBaseUrl(c.baseUrl); setUseMock(c.useMock); }); }, []);

  const save = async () => {
    try {
      await configure({ baseUrl, useMock });
      Alert.alert('Saved', 'Please log in again.');
    } catch (e) { Alert.alert('Connection settings', e instanceof Error ? e.message : 'Could not save settings.'); }
  };

  return (
    <Screen>
      <H>Backend</H>
      <Input placeholder="http://192.168.1.10:8000" value={baseUrl} onChangeText={setBaseUrl} />
      <View style={s.row}><Text>Use mock data (no server)</Text><Switch value={useMock} onValueChange={setUseMock} /></View>
      <Text style={s.muted}>Enter the API server address for testing. Mock data is for demos only. Server credentials belong in the backend environment file.</Text>
      <Button title="Save" onPress={save} />
    </Screen>
  );
}
