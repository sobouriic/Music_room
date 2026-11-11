// Pure helpers for the Google PKCE flow (kept free of native modules so they can be unit-tested).
export const b64url = (b64: string) => b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

/** Reads code/state/error from a pasted callback address (or just its query string). */
export function parseCallback(input: string): Record<string, string> {
  const query = input.includes('?') ? input.slice(input.indexOf('?') + 1) : input;
  const out: Record<string, string> = {};
  for (const part of query.split('#')[0].split('&')) {
    const [k, ...v] = part.split('=');
    if (!k) continue;
    try { out[decodeURIComponent(k)] = decodeURIComponent(v.join('=').replace(/\+/g, ' ')); } catch {}
  }
  return out;
}
