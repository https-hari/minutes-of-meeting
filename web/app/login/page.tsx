"use client";

import Link from "next/link";
import { useState } from "react";
import { Logo } from "@/components/Logo";
import { ErrorNote } from "@/components/ui";
import { authEnabled, supabase } from "@/lib/supabase";

export default function LoginPage() {
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  if (!authEnabled) {
    return (
      <Shell>
        <p className="text-sm text-muted">Login isn&apos;t configured, so the app runs in local mode.</p>
        <Link href="/" className="btn-primary mt-6 w-full">Open the app</Link>
      </Shell>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(""); setNotice("");
    const { data, error } = mode === "in"
      ? await supabase!.auth.signInWithPassword({ email, password })
      : await supabase!.auth.signUp({ email, password, options: { emailRedirectTo: `${location.origin}/auth/callback` } });
    setBusy(false);
    if (error) return setError(error.message);
    if (mode === "up" && !data.session) setNotice("Check your email to confirm your account, then sign in.");
  }

  async function google() {
    const next = new URLSearchParams(location.search).get("next") || "/";
    const { error } = await supabase!.auth.signInWithOAuth({
      provider: "google", options: { redirectTo: `${location.origin}/auth/callback?next=${encodeURIComponent(next)}` },
    });
    if (error) setError(error.message);
  }

  return (
    <Shell>
      <button onClick={google} className="btn-ghost w-full">Continue with Google</button>
      <div className="my-5 flex items-center gap-3 text-xs text-muted"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></div>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor="email" className="label">Email</label>
          <input id="email" type="email" required autoComplete="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label htmlFor="password" className="label">Password</label>
          <input id="password" type="password" required minLength={8} autoComplete={mode === "in" ? "current-password" : "new-password"}
            className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
          {mode === "up" && <p className="mt-1 text-xs text-muted">At least 8 characters.</p>}
        </div>
        {error && <ErrorNote message={error} />}
        {notice && <p className="rounded-lg bg-ok/10 px-3 py-2 text-sm text-ok">{notice}</p>}
        <button disabled={busy} className="btn-primary w-full">{busy ? "Please wait…" : mode === "in" ? "Sign in" : "Create account"}</button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        {mode === "in" ? "New here? " : "Already have an account? "}
        <button onClick={() => { setMode(mode === "in" ? "up" : "in"); setError(""); setNotice(""); }} className="font-medium text-accent underline-offset-2 hover:underline">
          {mode === "in" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <Logo className="h-9 w-9" />
          <h1 className="mt-5 text-[26px] font-semibold leading-tight tracking-tight">Meetings in.<br /><span className="mark">Decisions and tasks out.</span></h1>
          <p className="mt-2 text-sm text-muted">Record a call, paste a transcript or upload audio. Minutes pulls out who owes what, and answers questions about it later.</p>
        </div>
        <div className="card p-6">{children}</div>
      </div>
    </main>
  );
}
