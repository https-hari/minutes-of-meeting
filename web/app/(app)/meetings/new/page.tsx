"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { ErrorNote, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";

type Tab = "text" | "audio" | "live";
const TABS: { id: Tab; label: string }[] = [
  { id: "text", label: "Paste transcript" },
  { id: "audio", label: "Upload audio" },
  { id: "live", label: "Live meeting" },
];

export default function NewMeetingPage() {
  return <Suspense><NewMeeting /></Suspense>;
}

function NewMeeting() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "text");
  return (
    <>
      <PageHeader title="New meeting" sub="Action items, decisions and a searchable transcript in under a minute." />
      <div role="tablist" className="mb-6 inline-flex rounded-lg border border-line bg-surface p-1">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            className={`rounded-md px-3.5 py-1.5 text-sm ${tab === t.id ? "bg-canvas font-medium" : "text-muted hover:text-ink"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "text" && <TextForm />}
      {tab === "audio" && <AudioForm />}
      {tab === "live" && <LiveHelp />}
    </>
  );
}

function useSubmit() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(fn: () => Promise<{ meeting_id: number }>) {
    setBusy(true); setError("");
    try { router.push(`/meetings/${(await fn()).meeting_id}?new=1`); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  }
  return { busy, error, run };
}

function TextForm() {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const { busy, error, run } = useSubmit();
  return (
    <form className="card space-y-5 p-6" onSubmit={(e) => { e.preventDefault(); run(() => api.addTranscript(title, text)); }}>
      <div>
        <label htmlFor="title" className="label">Title</label>
        <input id="title" required maxLength={200} className="input" placeholder="Q3 budget review" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div>
        <label htmlFor="transcript" className="label">Transcript</label>
        <textarea id="transcript" required minLength={10} rows={12} className="input font-[inherit] leading-relaxed"
          placeholder={"Alice: Let's move the launch to August.\nBob: Agreed. I'll update the timeline by Friday."}
          value={text} onChange={(e) => setText(e.target.value)} />
        <p className="mt-1 text-xs text-muted">Start each line with the speaker&apos;s name and a colon for the best results.</p>
      </div>
      {error && <ErrorNote message={error} />}
      <button disabled={busy} className="btn-primary">{busy ? "Reading the meeting…" : "Process meeting"}</button>
    </form>
  );
}

function AudioForm() {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useSubmit();
  const tooBig = file && file.size > 25 * 1024 * 1024;

  return (
    <form className="card space-y-5 p-6" onSubmit={(e) => { e.preventDefault(); if (file) run(() => api.addAudio(title, file)); }}>
      <div>
        <label htmlFor="atitle" className="label">Title</label>
        <input id="atitle" required maxLength={200} className="input" placeholder="Weekly sync" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
        className={`rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${drag ? "border-accent bg-accent/5" : "border-line"}`}>
        {file ? (
          <p className="text-sm"><span className="font-medium">{file.name}</span> <span className="text-muted">· {(file.size / 1024 / 1024).toFixed(1)} MB</span></p>
        ) : (
          <p className="text-sm text-muted">Drop an audio file here</p>
        )}
        <button type="button" onClick={() => input.current?.click()} className="btn-ghost mt-3">{file ? "Choose another" : "Choose a file"}</button>
        <input ref={input} type="file" accept="audio/*,video/webm,.m4a,.mp3,.wav,.webm,.ogg" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <p className="mt-3 text-xs text-muted">MP3, M4A, WAV, WebM or OGG, up to 25 MB. Speakers are labelled Speaker 1 / 2.</p>
      </div>
      {tooBig && <ErrorNote message="That file is larger than 25 MB. Compress it, or split the recording." />}
      {error && <ErrorNote message={error} />}
      <button disabled={busy || !file || !!tooBig} className="btn-primary">{busy ? "Transcribing and reading…" : "Upload and process"}</button>
    </form>
  );
}

function LiveHelp() {
  const steps = [
    "Install the Minutes extension in Chrome (Load unpacked → the extension folder).",
    "Open the extension once and sign in with the same account.",
    "Join a Google Meet call and turn on captions (CC).",
    "Click Start in the extension. A red “Recording” badge stays visible while it captures.",
    "Click Stop when the meeting ends. It appears here, already processed.",
  ];
  return (
    <div className="card p-6">
      <h2 className="font-semibold">Capture a live Google Meet call</h2>
      <ol className="mt-4 space-y-3">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line text-xs font-semibold">{i + 1}</span>
            <span className="pt-0.5">{s}</span>
          </li>
        ))}
      </ol>
      <p className="mt-6 rounded-lg bg-canvas px-4 py-3 text-sm text-muted">
        Tell everyone in the call that you&apos;re taking notes with Minutes. In many places recording without consent isn&apos;t allowed.
      </p>
      <Link href="/" className="btn-ghost mt-6">Back to meetings</Link>
    </div>
  );
}
