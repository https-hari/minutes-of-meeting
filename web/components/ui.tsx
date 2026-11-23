"use client";

import type { Status } from "@/lib/api";

export function PageHeader({ title, sub, action }: { title: string; sub?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight md:text-[28px]">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return <p role="alert" className="rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-sm text-bad">{message}</p>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-accent" aria-hidden="true" />
      {label}
    </p>
  );
}

const STATUS_LABEL: Record<Status, string> = { open: "Open", in_progress: "In progress", done: "Done" };
const NEXT: Record<Status, Status> = { open: "in_progress", in_progress: "done", done: "open" };

/** Click to move a task along: Open -> In progress -> Done -> Open. */
export function StatusButton({ status, onChange, disabled }: { status: Status; onChange: (s: Status) => void; disabled?: boolean }) {
  const style = status === "done" ? "border-ok/40 text-ok" : status === "in_progress" ? "border-warn/40 text-warn" : "border-line text-muted";
  return (
    <button type="button" disabled={disabled} onClick={() => onChange(NEXT[status])}
      title={`Mark as ${STATUS_LABEL[NEXT[status]].toLowerCase()}`}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style} disabled:opacity-50`}>
      <span className={`h-1.5 w-1.5 rounded-full ${status === "done" ? "bg-ok" : status === "in_progress" ? "bg-warn" : "bg-muted"}`} aria-hidden="true" />
      {STATUS_LABEL[status]}
    </button>
  );
}
