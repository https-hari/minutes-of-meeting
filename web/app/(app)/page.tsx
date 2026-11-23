"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { api, type MeetingSummary } from "@/lib/api";
import { formatDuration } from "@/lib/format";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<MeetingSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.meetings().then(setMeetings).catch((e) => setError(e.message)); }, []);

  const open = meetings?.reduce((n, m) => n + m.open_items, 0) ?? 0;

  return (
    <>
      <PageHeader title="Meetings"
        sub={meetings && meetings.length > 0 ? `${meetings.length} meeting${meetings.length === 1 ? "" : "s"} · ${open} open action item${open === 1 ? "" : "s"}` : undefined}
        action={meetings && meetings.length > 0 ? <Link href="/meetings/new" className="btn-primary hidden md:inline-flex">New meeting</Link> : undefined} />
      {error && <ErrorNote message={error} />}
      {!meetings && !error && <Spinner />}
      {meetings?.length === 0 && <FirstMeeting />}
      {meetings && meetings.length > 0 && (
        <ol className="card divide-y divide-line">
          {meetings.map((m) => <MeetingRow key={m.id} m={m} />)}
        </ol>
      )}
    </>
  );
}

function MeetingRow({ m }: { m: MeetingSummary }) {
  const d = new Date(m.date.replace(" ", "T"));
  return (
    <li>
      <Link href={`/meetings/${m.id}`} className="grid grid-cols-[52px_1fr] gap-4 px-5 py-4 transition-colors hover:bg-canvas/60 md:grid-cols-[64px_1fr_auto]">
        <div className="text-center leading-none">
          <div className="text-[22px] font-semibold tabular-nums">{d.getDate()}</div>
          <div className="mt-1 text-xs uppercase text-muted">{d.toLocaleDateString(undefined, { month: "short" })}</div>
        </div>
        <div className="min-w-0">
          <p className="truncate font-medium">{m.title}</p>
          {m.summary && <p className="mt-0.5 line-clamp-2 text-sm text-muted">{m.summary}</p>}
          <p className="mt-1 text-xs text-muted md:hidden">{m.open_items} open · {formatDuration(m.duration) ?? ""}</p>
        </div>
        <div className="hidden items-center gap-4 text-sm md:flex">
          {formatDuration(m.duration) && <span className="text-muted">{formatDuration(m.duration)}</span>}
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${m.open_items ? "bg-mark/70 text-ink" : "text-muted"}`}>
            {m.open_items ? `${m.open_items} open` : "All done"}
          </span>
        </div>
      </Link>
    </li>
  );
}

function FirstMeeting() {
  const ways = [
    { href: "/meetings/new?tab=live", title: "Record a live meeting", body: "Use the Chrome extension in Google Meet. Speaker names come from the captions." },
    { href: "/meetings/new?tab=audio", title: "Upload a recording", body: "MP3, M4A, WAV or WebM up to 25 MB. We transcribe it for you." },
    { href: "/meetings/new?tab=text", title: "Paste a transcript", body: "One line per speaker, like “Alice: let's ship on Friday”." },
  ];
  return (
    <div className="card px-6 py-10 md:px-10">
      <h2 className="text-lg font-semibold">Add your first meeting</h2>
      <p className="mt-1 max-w-prose text-sm text-muted">Minutes pulls out action items with owners and deadlines, the decisions made and why, and lets you ask questions about any meeting later.</p>
      <div className="mt-6 grid gap-3 md:grid-cols-3">
        {ways.map((w) => (
          <Link key={w.href} href={w.href} className="rounded-xl border border-line p-4 transition-colors hover:border-accent">
            <p className="font-medium">{w.title}</p>
            <p className="mt-1 text-sm text-muted">{w.body}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
