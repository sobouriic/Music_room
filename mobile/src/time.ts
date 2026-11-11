/** ISO timestamp (with timezone, as the back-end requires) for today at the given local hour, 0 to 24. */
export function isoForHour(hour: number): string {
  const d = new Date();
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

/** "16:00" in the phone's local time. */
export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
