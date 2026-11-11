import * as Crypto from 'expo-crypto';
import { Config } from './config';
import { Tokens } from './api/types';
import { storage } from './storage';

export function validTokens(value: unknown): value is Tokens {
  const t = value as Tokens | null;
  return !!t && typeof t.accessToken === 'string' && !!t.accessToken
    && typeof t.refreshToken === 'string' && !!t.refreshToken;
}

export async function sessionStore(config: Config) {
  const server = `${config.useMock ? 'mock' : 'http'}:${config.baseUrl.replace(/\/$/, '')}`;
  const hash = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, server);
  const key = `tokens_${hash}`; // SecureStore keys allow alphanumerics, '.', '-' and '_'.
  return {
    async get(): Promise<Tokens | null> {
      try {
        const raw = await storage.get(key);
        if (!raw) return null;
        const saved = JSON.parse(raw);
        if (saved.server === server && validTokens(saved.tokens)) return saved.tokens;
      } catch {} // Corrupt/foreign credentials must never block app startup or be sent.
      await storage.remove(key).catch(() => {});
      return null;
    },
    set(tokens: Tokens) { return storage.set(key, JSON.stringify({ server, tokens })); },
    clear() { return storage.remove(key); },
  };
}
