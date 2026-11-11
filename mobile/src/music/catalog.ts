// Demo-mode catalog: Apple's public iTunes Search API (no key). The real back-end searches Deezer itself.
import { TrackInput } from '../api/types';

export async function searchItunes(query: string): Promise<TrackInput[]> {
  const q = query.trim();
  if (!q) return [];
  const url = `https://itunes.apple.com/search?media=music&entity=song&limit=15&term=${encodeURIComponent(q)}`;
  let res: Response;
  try { res = await fetch(url); } catch { throw new Error('Music search is unreachable. Check your connection.'); }
  if (!res.ok) throw new Error(`Music search failed (${res.status}).`);
  const body = await res.json();
  return (body.results ?? [])
    .filter((r: any) => r.trackName && r.artistName)
    .map((r: any) => ({
      title: r.trackName,
      artist: r.artistName,
      artwork: r.artworkUrl100 ? String(r.artworkUrl100).replace('100x100', '300x300') : undefined,
      previewUrl: r.previewUrl,
    }));
}
