// Runs on the Minutes website. The "Connect extension" page posts the signed-in
// session here; we pass it to the background worker. Only same-origin messages
// with our exact shape are accepted.
window.addEventListener("message", (e) => {
  if (e.source !== window || e.origin !== location.origin) return;
  const m = e.data;
  if (!m || m.source !== "minutes-web" || m.type !== "connect" || !m.session) return;
  chrome.runtime.sendMessage({ type: "connect", session: m.session, apiUrl: m.apiUrl }, (r) => {
    window.postMessage({ source: "minutes-extension", type: "connected", ok: !!r?.ok, error: r?.error }, location.origin);
  });
});
// let the page know the extension is installed
window.postMessage({ source: "minutes-extension", type: "hello" }, location.origin);
// the page can also ask (React mounts after this script runs)
window.addEventListener("message", (e) => {
  if (e.source === window && e.origin === location.origin && e.data?.source === "minutes-web" && e.data.type === "ping") {
    window.postMessage({ source: "minutes-extension", type: "hello" }, location.origin);
  }
});
