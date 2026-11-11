import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api, ApiError, Plan, Subscription } from '../api';
import { useAuth } from './AuthContext';
import { offline } from '../offline';

type Ctx = {
  plan: Plan; source: Subscription['source']; isPremium: boolean;
  refresh: () => Promise<void>; change: (plan: Plan) => Promise<void>;
};
const FREE: Subscription = { plan: 'free', source: 'device' };
const SubCtx = createContext<Ctx>({ ...FREE, isPremium: false, refresh: async () => {}, change: async () => {} });
export const useSubscription = () => useContext(SubCtx);

// A failed request is not a downgrade. Only a server-confirmed plan replaces the
// bounded, account-scoped offline entitlement. Unknown accounts still default Free.
export function SubscriptionProvider({ children }: { children: React.ReactNode }) {
  const { user, online = true, cachePlan } = useAuth();
  const [stored, setStored] = useState<{ id?: string; sub: Subscription }>({ sub: FREE });
  const sub = stored.id === user?.id ? stored.sub : FREE;
  const setSub = (value: Subscription) => setStored({ id: user?.id, sub: value });
  const actor = useRef(user?.id);
  actor.current = user?.id;
  const revision = useRef(0);
  const refresh = useCallback(async (force = false) => {
    if (!user) return;
    const id = user.id, request = ++revision.current;
    let cached: Subscription = FREE;
    try { await offline.list(id); cached = { plan: 'premium', source: 'device' }; } catch {}
    if (actor.current !== id || revision.current !== request) return;
    setSub(cached);
    if (!online && !force) return;
    try {
      const result = await api.getSubscription();
      if (actor.current !== id || revision.current !== request) return;
      if (result.source === 'server') await cachePlan(result.plan).catch(() => {});
      if (actor.current === id && revision.current === request) setSub(result);
    } catch (e) {
      // Keep the verified cached plan during outages; AuthContext handles real revocation.
      if (actor.current === id && revision.current === request) {
        setSub(e instanceof ApiError && e.status === 401 ? FREE : cached);
      }
    }
  }, [user?.id, online, cachePlan]);
  // cachePlan is supplied by AuthContext each render; use a ref to avoid request loops.
  const refreshRef = useRef(refresh); refreshRef.current = refresh;
  useEffect(() => {
    if (user) void refreshRef.current();
    else { ++revision.current; setSub(FREE); }
    return () => { ++revision.current; };
  }, [user?.id, online]);
  const change = async (plan: Plan) => {
    const id = user?.id, request = ++revision.current;
    const result = await api.setSubscription(plan);
    if (actor.current !== id || revision.current !== request) return;
    if (result.source === 'server') await cachePlan(result.plan).catch(() => {});
    if (actor.current === id && revision.current === request) setSub(result);
  };
  return <SubCtx.Provider value={{ ...sub, isPremium: sub.plan === 'premium', refresh: () => refresh(true), change }}>{children}</SubCtx.Provider>;
}
