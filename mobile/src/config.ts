import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'music-room-config';
export type Config = { baseUrl: string; useMock: boolean };

export function validateConfig(config: Config): Config {
  const url = new URL(config.baseUrl.trim());
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
      || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) {
    throw new Error('Enter the server root URL, without credentials, path, query or fragment.');
  }
  const host = url.hostname;
  const parts = host.split('.').map(Number);
  const ipv4 = parts.length === 4 && parts.every(n => Number.isInteger(n) && n >= 0 && n <= 255);
  const local = host === 'localhost' || host === '[::1]' || (ipv4 && parts[0] === 127);
  const lan = ipv4 && (parts[0] === 10 || (parts[0] === 192 && parts[1] === 168) || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31));
  if (url.protocol === 'http:' && !local && !(typeof __DEV__ !== 'undefined' && __DEV__ && lan)) {
    throw new Error('Use HTTPS for remote servers. HTTP is allowed for local development only.');
  }
  return { baseUrl: url.origin, useMock: config.useMock === true };
}

const defaults: Config = {
  baseUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8001',
  useMock: (process.env.EXPO_PUBLIC_USE_MOCK ?? 'false') === 'true',
};

export async function loadConfig(): Promise<Config> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return validateConfig(raw ? { ...defaults, ...JSON.parse(raw) } : defaults);
  } catch {
    return validateConfig(defaults);
  }
}

export async function saveConfig(c: Config) {
  await AsyncStorage.setItem(KEY, JSON.stringify(validateConfig(c)));
}
