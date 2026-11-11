import AsyncStorage from '@react-native-async-storage/async-storage';
import { loadConfig } from '../config';
const listeners = new Set<() => void>();
async function key(userId: string) { return `music-room-player:${(await loadConfig()).baseUrl}:${userId}`; }
export async function getLocalDevice(userId: string) { return AsyncStorage.getItem(await key(userId)); }
export async function bindLocalDevice(userId: string, deviceId: string) {
  await AsyncStorage.setItem(await key(userId), deviceId);
  listeners.forEach(listener => listener());
}
export function onLocalDeviceChange(listener: () => void) {
  listeners.add(listener); return () => { listeners.delete(listener); };
}
