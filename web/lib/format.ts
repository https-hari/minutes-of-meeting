export function formatDate(iso: string, withTime = false): string {
  const d = new Date(iso.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    day: "numeric", month: "short", year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function formatDuration(seconds: number | null): string | null {
  if (!seconds) return null;
  const m = Math.round(seconds / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export function isOverdue(deadline: string | null, status: string): boolean {
  if (!deadline || status === "done") return false;
  return new Date(deadline) < new Date(new Date().toDateString());
}
