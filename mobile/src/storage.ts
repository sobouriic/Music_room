import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

// Phone: encrypted SecureStore. Browser: localStorage (SecureStore does not exist on web).
export const storage = {
  async get(key: string): Promise<string | null> {
    if (Platform.OS !== 'web') return SecureStore.getItemAsync(key);
    try { return window.localStorage.getItem(key); } catch { return null; }
  },
  async set(key: string, value: string) {
    if (Platform.OS !== 'web') return SecureStore.setItemAsync(key, value);
    try { window.localStorage.setItem(key, value); } catch {}
  },
  async remove(key: string) {
    if (Platform.OS !== 'web') return SecureStore.deleteItemAsync(key);
    try { window.localStorage.removeItem(key); } catch {}
  },
};
