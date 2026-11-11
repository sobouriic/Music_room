import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { AppState, Platform } from 'react-native';
import { Alert } from '../alert';
import { recordAction, setActivityUser } from '../activity';
import { storage } from '../storage';
import { offline } from '../offline';
import { Config, loadConfig, saveConfig, validateConfig } from '../config';
import { sessionStore } from '../sessionStore';
import { api, ApiError, initApi, setTokensListener, setTokensResolver, setConnectivityListener, Plan, Tokens, User } from '../api';

type AuthCtx = {
  user: User | null; ready: boolean; online: boolean;
  start: (tokens: Tokens) => Promise<void>;
  setUser: (user: User) => void;
  logout: () => Promise<void>;
  configure: (config: Config) => Promise<void>;
  reloadUser: () => Promise<User>;
  cachePlan: (plan: Plan) => Promise<void>;
};
const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [online, setOnline] = useState(true);
  useEffect(() => { setActivityUser(user?.id ?? null); if (user) recordAction('screen_view'); return () => setActivityUser(null); }, [user?.id]);
  const store = useRef<Awaited<ReturnType<typeof sessionStore>> | null>(null);
  const epoch = useRef(0);
  const getStore = async () => {
    if (!store.current) store.current = await sessionStore(await loadConfig());
    return store.current;
  };
  const remember = async (profile: User) => {
    const attempt = epoch.current;
    const saved = await (await getStore()).get();
    if (saved && attempt === epoch.current) await offline.remember(profile, saved).catch(() => {});
  };
  const start = async (tokens: Tokens) => {
    const attempt = ++epoch.current;
    api.setTokens(tokens);
    await (await getStore()).set(tokens);
    const profile = await api.getMe();
    if (attempt !== epoch.current) return;
    setOnline(true); setUser(profile);
    // Optional offline persistence must not delay entering the authenticated app.
    void remember(profile).catch(() => {});
  };
  const reloadUser = async () => {
    const attempt = epoch.current;
    const profile = await api.getMe();
    if (attempt !== epoch.current) throw new Error('Session changed. Please try again.');
    setOnline(true); setUser(profile);
    // Optional offline persistence must not delay entering the authenticated app.
    void remember(profile).catch(() => {});
    return profile;
  };
  const cachePlan = async (plan: Plan) => {
    const attempt = epoch.current;
    const saved = await (await getStore()).get();
    if (user && saved && attempt === epoch.current) await offline.confirm(user, saved, plan);
  };
  useEffect(() => {
    if (!user) return;
    const reconnect = () => {
      if (AppState.currentState === 'active') void reloadUser().catch(() => {});
    };
    const subscription = AppState.addEventListener('change', state => { if (state === 'active') reconnect(); });
    const timer = !online ? setInterval(reconnect, 15000) : undefined;
    return () => { subscription.remove(); if (timer) clearInterval(timer); };
  }, [user?.id, online]);
  const logout = async () => {
    setActivityUser(null);
    ++epoch.current;
    const saved = await (await getStore()).get();
    try { if (saved) await api.logout(saved.refreshToken); } catch {}
    api.setTokens(null);
    await (await getStore()).clear();
    await offline.clear().catch(() => {});
    setOnline(true); setUser(null);
  };
  const configure = async (config: Config) => {
    const valid = validateConfig(config);
    // Revoke against the OLD client before changing either configuration or API.
    await logout();
    await saveConfig(valid);
    store.current = await sessionStore(valid);
    await initApi();
  };

  useEffect(() => {
    let active = true;
    let finishingBrowser = false;
    const finishBrowserCallback = async () => {
      if (!active || finishingBrowser || Platform.OS !== 'web' || !window.location.hash.startsWith('#google-callback=')) return;
      finishingBrowser = true;
      try {
        const fragment = window.location.hash.slice('#google-callback='.length);
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
        const saved = sessionStorage.getItem('music-room-google-attempt');
        sessionStorage.removeItem('music-room-google-attempt');
        if (!saved) throw new Error('Start Google sign-in again from this browser tab.');
        const attempt = JSON.parse(saved);
        const params = new URLSearchParams(decodeURIComponent(fragment));
        const age = Date.now() - attempt.createdAt;
        if (params.get('state') !== attempt.state || !Number.isFinite(age) || age < 0 || age > 600000) {
          throw new Error('Google sign-in expired. Please try again.');
        }
        if (params.get('error')) throw new Error('Google sign-in was cancelled or refused.');
        const code = params.get('code');
        if (!code) throw new Error('Google did not return a sign-in code.');
        if (attempt.intent === 'link') {
          await api.googleLink(attempt.state, code, attempt.verifier); await reloadUser();
        } else if (attempt.intent === 'login') {
          await start(await api.googleExchange(attempt.state, code, attempt.verifier));
        } else throw new Error('Invalid sign-in attempt.');
      } catch (e) { Alert.alert('Google sign-in', e instanceof Error ? e.message : 'Unable to finish sign-in.'); }
      finally { finishingBrowser = false; }
    };
    const onBrowserReturn = () => { void finishBrowserCallback(); };
    (async () => {
      try {
        store.current = await sessionStore(await loadConfig());
        setTokensResolver(async () => active ? (await getStore()).get() : null);
        setConnectivityListener(value => { if (active) setOnline(value); });
        setTokensListener(async tokens => {
          if (!active) return;
          if (tokens) {
            await (await getStore()).set(tokens);
            await offline.rotate(tokens).catch(() => {});
          } else {
            ++epoch.current;
            await (await getStore()).clear(); await offline.clear().catch(() => {});
            setUser(null);
          }
        });
        await initApi();
        // Legacy unscoped credentials cannot safely be assigned to a server.
        await storage.remove('tokens').catch(() => {});
        const saved = await store.current.get();
        if (saved) {
          api.setTokens(saved);
          try { await reloadUser(); }
          catch (e) {
            if (e instanceof ApiError && (e.status === 0 || e.status === 429 || e.status >= 500)) {
              // Refresh may have rotated the pair before a later request lost connectivity.
              const current = await store.current.get();
              const profile = current ? await offline.restore(current).catch(() => null) : null;
              if (active) { setUser(profile); setOnline(false); }
            } else {
              if (e instanceof ApiError && e.status === 401) {
                await store.current.clear(); await offline.clear().catch(() => {});
              }
              api.setTokens(null);
            }
          }
        }
        if (Platform.OS === 'web') {
          window.addEventListener('hashchange', onBrowserReturn);
          window.addEventListener('pageshow', onBrowserReturn);
        }
        await finishBrowserCallback();
      } catch (e) {
        api.setTokens(null);
        if (active) Alert.alert('Connection settings', e instanceof Error ? e.message : 'Unable to initialize the app.');
      } finally { if (active) setReady(true); }
    })();
    return () => {
      active = false; ++epoch.current;
      if (Platform.OS === 'web') {
        window.removeEventListener('hashchange', onBrowserReturn);
        window.removeEventListener('pageshow', onBrowserReturn);
      }
    };
  }, []);

  return <Ctx.Provider value={{ user, ready, online, start, setUser, logout, configure, reloadUser, cachePlan }}>{children}</Ctx.Provider>;
}
