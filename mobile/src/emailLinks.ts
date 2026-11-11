import { Linking } from 'react-native';
// Tokens stay in email URL fragments; translate only internally for navigation.
export function emailAction(url: string | null): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    const path = u.protocol === 'musicroom:' ? u.host : u.pathname.replace(/^\//, '');
    if (!['verify-email', 'reset-password'].includes(path)) return null;
    const token = new URLSearchParams(u.hash.slice(1)).get('token');
    if (!token || token.length > 256) return null;
    return `musicroom://${path}?token=${encodeURIComponent(token)}`;
  } catch { return null; }
}
export const emailLinking = {
  prefixes: ['musicroom://'],
  config: { screens: { VerifyEmail: 'verify-email', ResetPassword: 'reset-password' } },
  getInitialURL: async () => emailAction(await Linking.getInitialURL()),
  subscribe(listener: (url: string) => void) {
    const sub = Linking.addEventListener('url', ({ url }) => { const action = emailAction(url); if (action) listener(action); });
    return () => sub.remove();
  },
};
