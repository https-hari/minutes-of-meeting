"use client";

import { useEffect, useState } from "react";
import { ErrorNote, PageHeader } from "@/components/ui";
import { API_URL } from "@/lib/api";
import { authEnabled, supabase } from "@/lib/supabase";

type State = "checking" | "missing" | "ready" | "connected";

/** Hands the signed-in session to the Chrome extension (via its content script on this site),
 *  so meetings captured in Google Meet are saved to this account. */
export default function ConnectExtension() {
  const [state, setState] = useState<State>("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.source !== window || e.origin !== location.origin || e.data?.source !== "minutes-extension") return;
      if (e.data.type === "hello") setState((s) => (s === "checking" || s === "missing" ? "ready" : s));
      if (e.data.type === "connected") e.data.ok ? setState("connected") : setError(e.data.error || "The extension refused the connection.");
    };
    window.addEventListener("message", onMsg);
    window.postMessage({ source: "minutes-web", type: "ping" }, location.origin);
    const t = setTimeout(() => setState((s) => (s === "checking" ? "missing" : s)), 1200);
    return () => { window.removeEventListener("message", onMsg); clearTimeout(t); };
  }, []);

  async function connect() {
    setError("");
    let session: Record<string, unknown> = { local: true, email: "local mode" };
    if (authEnabled && supabase) {
      const { data } = await supabase.auth.getSession();
      const s = data.session;
      if (!s) return setError("You're signed out. Sign in again first.");
      session = {
        access_token: s.access_token, refresh_token: s.refresh_token, expires_at: s.expires_at,
        email: s.user.email, supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL, anonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      };
    }
    window.postMessage({ source: "minutes-web", type: "connect", session, apiUrl: API_URL }, location.origin);
  }

  return (
    <>
      <PageHeader title="Chrome extension" sub="Capture Google Meet calls straight into your meetings." />
      <div className="card max-w-xl p-6">
        {state === "checking" && <p className="text-sm text-muted">Looking for the extension…</p>}
        {state === "missing" && (
          <>
            <p className="font-medium">The extension isn&apos;t installed in this browser yet.</p>
            <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-muted">
              <li>Open <code className="rounded bg-canvas px-1">chrome://extensions</code> and turn on Developer mode.</li>
              <li>Click Load unpacked and choose the <code className="rounded bg-canvas px-1">extension</code> folder of this project.</li>
              <li>Reload this page.</li>
            </ol>
          </>
        )}
        {state === "ready" && (
          <>
            <p>Connect the extension to this account. It keeps you signed in and refreshes the session by itself.</p>
            <button onClick={connect} className="btn-primary mt-4">Connect extension</button>
          </>
        )}
        {state === "connected" && (
          <>
            <p className="font-medium text-ok">Connected.</p>
            <p className="mt-1 text-sm text-muted">Join a Google Meet call, turn on captions, and click Start in the extension. When you stop, the meeting opens here.</p>
          </>
        )}
        {error && <div className="mt-4"><ErrorNote message={error} /></div>}
      </div>
    </>
  );
}
