"use client";

import Link from "next/link";
import { useState } from "react";
import { ErrorNote, PageHeader } from "@/components/ui";
import { api, type QueryResult } from "@/lib/api";

const MODES = [
  { id: "hybrid_rerank", label: "Best (hybrid + re-rank)" },
  { id: "hybrid", label: "Hybrid" },
  { id: "vector", label: "Meaning only" },
  { id: "keyword", label: "Exact words only" },
];

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("hybrid_rerank");
  const [res, setRes] = useState<QueryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true); setError("");
    try { setRes(await api.query(q, mode)); } catch (err) { setError((err as Error).message); }
    setBusy(false);
  }

  return (
    <>
      <PageHeader title="Search" sub="Ask a question across every meeting. Answers cite the transcript lines they came from." />
      <form onSubmit={search} className="flex flex-col gap-2 sm:flex-row">
        <input aria-label="Question" className="input flex-1" placeholder="What caused the login outage?" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Search method" value={mode} onChange={(e) => setMode(e.target.value)} className="input sm:w-56">
          {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
        <button disabled={busy || !q.trim()} className="btn-primary">{busy ? "Searching…" : "Search"}</button>
      </form>
      {error && <div className="mt-4"><ErrorNote message={error} /></div>}
      {res && (
        <div className="mt-8 space-y-6">
          <div className="card px-5 py-4 leading-relaxed whitespace-pre-wrap">{res.answer}</div>
          <div>
            <h2 className="mb-3 text-sm font-semibold text-muted">Sources</h2>
            <ol className="space-y-3">
              {res.sources.map((s, i) => (
                <li key={s.chunk_id} className="card px-4 py-3">
                  <p className="text-xs text-muted">
                    [{i + 1}] <Link href={`/meetings/${s.meeting_id}`} className="font-medium text-ink hover:underline">{s.meeting_title}</Link>
                    {" · "}{s.speaker ?? "Unknown"}{" · found by "}{Object.keys(s.found_by).filter((k) => k !== "rrf_score").join(" + ")}
                  </p>
                  <p className="mt-1 text-sm">{s.text}</p>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </>
  );
}
