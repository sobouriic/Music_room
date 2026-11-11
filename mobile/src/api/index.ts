import { loadConfig } from '../config';
import { createHttpApi } from './httpApi';
import { mockApi } from './mockApi';
import { ApiClient, Tokens } from './types';

let impl: ApiClient = mockApi;
let configKey = '';
let resolveTokens: () => Promise<Tokens | null> = async () => null;
let connectionListener: (online: boolean) => void = () => {};
let listener: (t: Tokens | null) => void | Promise<void> = () => {};

/** Screens always import `api`; whether it is the mock or the real backend is decided by config. */
export const api: ApiClient = new Proxy({} as ApiClient, {
  get: (_t, key) => (impl as any)[key],
});

/** The auth context registers here to persist rotated tokens. Survives mock/real switches. */
export function setTokensListener(cb: (t: Tokens | null) => void | Promise<void>) {
  listener = cb;
}

export function setTokensResolver(cb: () => Promise<Tokens | null>) { resolveTokens = cb; }
export function setConnectivityListener(cb: (online: boolean) => void) { connectionListener = cb; }
export async function initApi() {
  const { useMock, baseUrl } = await loadConfig();
  const key = `${useMock}:${baseUrl}`;
  if (key === configKey) return; // Reinitializing the same server must not drop its session.
  const client = useMock ? mockApi : createHttpApi(baseUrl);
  impl = client; configKey = key;
  client.onTokensChange((t) => { if (impl === client) return listener(t); });
  client.onTokensNeeded?.(async () => impl === client ? resolveTokens() : null);
  client.onConnectionChange?.(online => { if (impl === client) connectionListener(online); });
}

export * from './types';
