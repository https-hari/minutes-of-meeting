"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ErrorNote, Spinner, StatusButton } from "@/components/ui";
import { api, type ActionItem, type MeetingDetail, type QueryResult, type Status } from "@/lib/api";
import { formatDate, formatDuration, isOverdue } from "@/lib/format";

export default function Page() {
  return <Suspense><MeetingPage /></Suspense>;
}

function MeetingPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = useSearchParams().get("new") === "1";
  const router = useRouter();
  const [m, setM] = useState<MeetingDetail | null>(null);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => { api.meeting(Number(id)).then(setM).catch((e) => setError(e.message)); }, [id]);

  async function setStatus(item: ActionItem, status: Status) {
    setM((cur) => cur && { ...cur, action_items: cur.action_items.map((a) => (a.id === item.id ? { ...a, status } : a)) });
    try { await api.setStatus(item.id, status); }
    catch (e) { setError((e as Error).message); setM((cur) => cur && { ...cur, action_items: cur.action_items.map((a) => (a.id === item.id ? item : a)) }); }
  }

  async function remove() {
    try { await api.deleteMeeting(Number(id)); router.replace("/"); }
    catch (e) { setError((e as Error).message); }
  }

  if (error && !m) return <><BackLink /><ErrorNote message={error} /></>;
  if (!m) return <Spinner />;

  return (
    <>
      <BackLink />
      {isNew && (
        <p className="mb-6 rounded-lg bg-ok/10 px-4 py-2.5 text-sm text-ok">
          Processed: {m.action_items.length} action item{m.action_items.length === 1 ? "" : "s"} and {m.decisions.length} decision{m.decisions.length === 1 ? "" : "s"} found.
        </p>
      )}
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight md:text-[28px]">{m.title}</h1>
        <p className="mt-1 text-sm text-muted">
          {formatDate(m.date, true)}{formatDuration(m.duration) ? ` · ${formatDuration(m.duration)}` : ""}
          {m.participants.length > 0 && ` · ${m.participants.join(", ")}`}
        </p>
      </header>
      {error && <div className="mb-4"><ErrorNote message={error} /></div>}

      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        <div className="space-y-10">
          {m.summary && (
            <section>
              <h2 className="mb-2 text-sm font-semibold text-muted">Summary</h2>
              <p className="max-w-prose leading-relaxed">{m.summary}</p>
            </section>
          )}

          <section>
            <h2 className="mb-3 text-sm font-semibold text-muted">Decisions</h2>
            {m.decisions.length === 0 ? <p className="text-sm text-muted">No decisions recorded.</p> : (
              <ul className="space-y-3">
                {m.decisions.map((d) => (
                  <li key={d.id}>
                    <p className="font-medium"><span className="mark">{d.description}</span></p>
                    {d.context && <p className="mt-0.5 text-sm text-muted">Why: {d.context}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold text-muted">Action items</h2>
            {m.action_items.length === 0 ? <p className="text-sm text-muted">No action items.</p> : (
              <ul className="card divide-y divide-line">
                {m.action_items.map((a) => (
                  <li key={a.id} className="flex items-start gap-3 px-4 py-3">
                    <StatusButton status={a.status} onChange={(s) => setStatus(a, s)} />
                    <div className="min-w-0">
                      <p className={a.status === "done" ? "text-muted line-through decoration-line" : ""}>{a.description}</p>
                      <p className="mt-0.5 text-xs text-muted">
                        {a.owner ?? "No owner"}
                        {a.deadline && <span className={isOverdue(a.deadline, a.status) ? "text-bad" : ""}> · due {formatDate(a.deadline)}</span>}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {m.transcript && (
            <details className="group">
              <summary className="cursor-pointer text-sm font-semibold text-muted hover:text-ink">Transcript</summary>
              <pre className="mt-3 max-h-[480px] overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-surface p-4 font-[inherit] text-sm leading-relaxed">{m.transcript}</pre>
            </details>
          )}

          <div className="border-t border-line pt-6">
            {confirmDelete ? (
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span>Delete this meeting, its tasks and transcript? This can&apos;t be undone.</span>
                <button onClick={remove} className="btn-danger">Delete</button>
                <button onClick={() => setConfirmDelete(false)} className="btn-ghost">Cancel</button>
              </div>
            ) : (
              <button onClick={() => setConfirmDelete(true)} className="text-sm text-muted underline-offset-2 hover:text-bad hover:underline">Delete meeting</button>
            )}
          </div>
        </div>

        <AskBox meetingId={m.id} />
      </div>
    </>
  );
}

function BackLink() {
  return <Link href="/" className="mb-6 inline-block text-sm text-muted hover:text-ink">← Meetings</Link>;
}

function AskBox({ meetingId }: { meetingId: number }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<QueryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true); setError("");
    try { setRes(await api.query(q, "hybrid_rerank", meetingId)); } catch (err) { setError((err as Error).message); }
    setBusy(false);
  }
  return (
    <aside className="lg:sticky lg:top-10 lg:self-start">
      <form onSubmit={ask} className="card p-4">
        <label htmlFor="ask" className="label">Ask about this meeting</label>
        <textarea id="ask" rows={2} className="input resize-none" placeholder="Why did we move the launch?"
          value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(e); } }} />
        <button disabled={busy || !q.trim()} className="btn-primary mt-2 w-full">{busy ? "Reading…" : "Ask"}</button>
        {error && <div className="mt-3"><ErrorNote message={error} /></div>}
        {res && (
          <div className="mt-4 border-t border-line pt-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{res.answer}</p>
            <ol className="mt-3 space-y-2">
              {res.sources.slice(0, 3).map((s, i) => (
                <li key={s.chunk_id} className="text-xs text-muted"><span className="font-medium text-ink">[{i + 1}] {s.speaker ?? "Unknown"}:</span> {s.text.length > 140 ? s.text.slice(0, 140) + "…" : s.text}</li>
              ))}
            </ol>
          </div>
        )}
      </form>
    </aside>
  );
}
