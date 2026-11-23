// Holds the session and talks to the backend, so the popup and the Meet page don't need to.

const DEFAULTS = { apiUrl: "http://localhost:8000", webUrl: "http://localhost:3000" };

async function settings() {
  const s = await chrome.storage.local.get(["apiUrl", "webUrl", "session"]);
  return { apiUrl: s.apiUrl || DEFAULTS.apiUrl, webUrl: s.webUrl || DEFAULTS.webUrl, session: s.session || null };
}

// Supabase access tokens last about an hour; refresh with the stored refresh token.
async function accessToken() {
  const { session } = await settings();
  if (!session) return null;
  if (session.local) return null;                          // backend runs with AUTH_DISABLED=1
  if (Date.now() / 1000 < session.expires_at - 60) return session.access_token;
  const res = await fetch(`${session.supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: session.anonKey },
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  if (!res.ok) {
    await chrome.storage.local.remove("session");
    throw new Error("Your session ended. Open the extension and connect again.");
  }
  const t = await res.json();
  const next = { ...session, access_token: t.access_token, refresh_token: t.refresh_token,
                 expires_at: Math.floor(Date.now() / 1000) + (t.expires_in || 3600) };
  await chrome.storage.local.set({ session: next });
  return next.access_token;
}

async function sendMeeting({ title, captions }) {
  const { apiUrl, webUrl } = await settings();
  const token = await accessToken();
  let res;
  try {
    res = await fetch(`${apiUrl}/meetings/live`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ title, captions, source: "google-meet" }),
    });
  } catch {
    throw new Error(`Can't reach the server at ${apiUrl}.`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Server error (${res.status})`);
  const url = `${webUrl}/meetings/${body.data.meeting_id}?new=1`;
  await chrome.storage.local.set({ lastResult: { ...body.data, url, at: Date.now() }, pending: null });
  chrome.tabs.create({ url });
  return { ...body.data, url };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === "connect") {
      // From the website, relayed by content/bridge.js. A site we haven't approved could
      // otherwise point the extension at its own server, so a new site needs approval in the popup.
      const { webUrl } = await settings();
      const origin = new URL(sender.url).origin;
      const data = { session: msg.session, apiUrl: (msg.apiUrl || DEFAULTS.apiUrl).replace(/\/$/, "") };
      if (origin === webUrl) { await chrome.storage.local.set(data); return { ok: true }; }
      await chrome.storage.local.set({ pendingConnect: { origin, ...data } });
      return { ok: false, error: "Open the Minutes extension (toolbar icon) and approve this website." };
    }
    if (msg.type === "approve") {
      const { pendingConnect: p } = await chrome.storage.local.get("pendingConnect");
      if (!p) return { ok: false, error: "Nothing to approve." };
      await chrome.storage.local.set({ session: p.session, apiUrl: p.apiUrl, webUrl: p.origin });
      await chrome.storage.local.remove("pendingConnect");
      return { ok: true };
    }
    if (msg.type === "finish") {
      // save first, so nothing is lost if the upload fails
      await chrome.storage.local.set({ pending: { title: msg.title, captions: msg.captions, at: Date.now() } });
      return { ok: true, result: await sendMeeting(msg) };
    }
    if (msg.type === "retry") {
      const { pending } = await chrome.storage.local.get("pending");
      if (!pending) return { ok: false, error: "Nothing to resend." };
      return { ok: true, result: await sendMeeting(pending) };
    }
    if (msg.type === "status") {
      const s = await settings();
      const { lastResult, pending, pendingConnect } = await chrome.storage.local.get(["lastResult", "pending", "pendingConnect"]);
      return { ok: true, connected: !!s.session, email: s.session?.email || (s.session?.local ? "local mode" : null),
               apiUrl: s.apiUrl, webUrl: s.webUrl, lastResult,
               approve: pendingConnect ? { origin: pendingConnect.origin, apiUrl: pendingConnect.apiUrl } : null, pending: pending ? { title: pending.title, lines: pending.captions.length } : null };
    }
    if (msg.type === "disconnect") { await chrome.storage.local.remove("session"); return { ok: true }; }
    if (msg.type === "settings") { await chrome.storage.local.set({ apiUrl: msg.apiUrl, webUrl: msg.webUrl }); return { ok: true }; }
    return { ok: false, error: "unknown message" };
  })().then(reply, (e) => reply({ ok: false, error: e.message }));
  return true;
});
