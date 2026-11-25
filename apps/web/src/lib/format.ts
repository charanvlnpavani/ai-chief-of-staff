/** 90 -> "1h 30m", 45 -> "45m", 0 -> "0m". */
export function formatMinutes(total: number): string {
  const minutes = Math.max(0, Math.round(total));
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/** 0.667 -> "67%"; null -> "—". */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

/** Parses "YYYY-MM-DD" as a calendar date (no time-zone shift). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function toIsoDay(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function addDays(iso: string, days: number): string {
  const date = parseDay(iso);
  date.setDate(date.getDate() + days);
  return toIsoDay(date);
}

export function dayLabel(iso: string): string {
  return parseDay(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parseDay(to).getTime() - parseDay(from).getTime()) / 86_400_000);
}

/** Human due-date label relative to the user's "today" (as computed by the API). */
export function dueLabel(dueOn: string | null | undefined, today: string): string | null {
  if (!dueOn) return null;
  const diff = daysBetween(today, dueOn);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  if (diff < 0) return `${-diff} days overdue`;
  if (diff < 7) return parseDay(dueOn).toLocaleDateString(undefined, { weekday: "long" });
  return dayLabel(dueOn);
}

export function greeting(hour: number): string {
  if (hour < 5) return "Good night";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}
