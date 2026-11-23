"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ErrorNote, PageHeader, Spinner, StatusButton } from "@/components/ui";
import { api, type ActionItem, type Status } from "@/lib/api";
import { formatDate, isOverdue } from "@/lib/format";

const FILTERS: { id: Status | "all"; label: string }[] = [
  { id: "open", label: "Open" }, { id: "in_progress", label: "In progress" }, { id: "done", label: "Done" }, { id: "all", label: "All" },
];

export default function TasksPage() {
  const [items, setItems] = useState<ActionItem[] | null>(null);
  const [filter, setFilter] = useState<Status | "all">("open");
  const [owner, setOwner] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { api.actionItems().then(setItems).catch((e) => setError(e.message)); }, []);

  const owners = useMemo(() => [...new Set((items ?? []).map((i) => i.owner).filter(Boolean) as string[])].sort(), [items]);
  const shown = (items ?? []).filter((i) => (filter === "all" || i.status === filter) && (!owner || i.owner === owner));
  const count = (s: Status | "all") => (items ?? []).filter((i) => s === "all" || i.status === s).length;

  async function setStatus(item: ActionItem, status: Status) {
    setItems((cur) => cur && cur.map((i) => (i.id === item.id ? { ...i, status } : i)));
    try { await api.setStatus(item.id, status); }
    catch (e) { setError((e as Error).message); setItems((cur) => cur && cur.map((i) => (i.id === item.id ? item : i))); }
  }

  return (
    <>
      <PageHeader title="Action items" sub="Everything people committed to, across all meetings." />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div role="tablist" className="inline-flex rounded-lg border border-line bg-surface p-1">
          {FILTERS.map((f) => (
            <button key={f.id} role="tab" aria-selected={filter === f.id} onClick={() => setFilter(f.id)}
              className={`rounded-md px-3 py-1.5 text-sm ${filter === f.id ? "bg-canvas font-medium" : "text-muted hover:text-ink"}`}>
              {f.label} <span className="tabular-nums text-muted">{items ? count(f.id) : ""}</span>
            </button>
          ))}
        </div>
        {owners.length > 0 && (
          <select aria-label="Filter by owner" value={owner} onChange={(e) => setOwner(e.target.value)} className="input w-auto py-1.5">
            <option value="">Everyone</option>
            {owners.map((o) => <option key={o}>{o}</option>)}
          </select>
        )}
      </div>
      {error && <div className="mb-4"><ErrorNote message={error} /></div>}
      {!items && !error && <Spinner />}
      {items && shown.length === 0 && <p className="card px-5 py-8 text-center text-sm text-muted">Nothing here.</p>}
      {shown.length > 0 && (
        <ul className="card divide-y divide-line">
          {shown.map((a) => (
            <li key={a.id} className="flex items-start gap-3 px-4 py-3">
              <StatusButton status={a.status} onChange={(s) => setStatus(a, s)} />
              <div className="min-w-0 flex-1">
                <p className={a.status === "done" ? "text-muted line-through decoration-line" : ""}>{a.description}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {a.owner ?? "No owner"}
                  {a.deadline && <span className={isOverdue(a.deadline, a.status) ? "font-medium text-bad" : ""}> · due {formatDate(a.deadline)}{isOverdue(a.deadline, a.status) ? " (overdue)" : ""}</span>}
                  {" · "}<Link href={`/meetings/${a.meeting_id}`} className="underline-offset-2 hover:text-ink hover:underline">{a.meeting}</Link>
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
