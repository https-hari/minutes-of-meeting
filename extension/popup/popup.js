const $ = (id) => document.getElementById(id);
let tab = null, meet = null, bg = null, ticker = null;

const send = (msg) => chrome.runtime.sendMessage(msg);
const toTab = (msg) => chrome.tabs.sendMessage(tab.id, msg).catch(() => null);
function say(text, error = false) { $("message").textContent = text; $("message").className = error ? "error" : ""; }

async function refresh() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  bg = await send({ type: "status" });
  meet = tab?.url?.startsWith("https://meet.google.com/") ? await toTab({ type: "meet-status" }) : null;

  $("who").textContent = bg.email || "";
  $("apiUrl").value = bg.apiUrl; $("webUrl").value = bg.webUrl;
  $("approve").hidden = !bg.approve;
  if (bg.approve) { $("apOrigin").textContent = bg.approve.origin; $("apApi").textContent = bg.approve.apiUrl; }
  $("connect").hidden = bg.connected || !!bg.approve;
  $("notMeet").hidden = !bg.connected || !!meet;
  $("meet").hidden = !bg.connected || !meet;

  if (meet) {
    if (!$("title").value) $("title").value = meet.title;
    $("captionState").textContent = meet.captionsOn ? "Captions are on." : "Captions are off. Turn them on in Meet (CC, or press C).";
    $("startBtn").hidden = meet.recording;
    $("recRow").hidden = !meet.recording;
    $("recText").textContent = meet.recording ? `Taking notes · ${meet.lines} lines` : "";
  } else if (tab?.url?.startsWith("https://meet.google.com/")) {
    $("notMeet").hidden = false;
    $("notMeet").querySelector("p").textContent = "Reload this Meet tab once so the extension can read captions.";
  }

  $("pending").hidden = !bg.pending;
  if (bg.pending) $("pendingText").textContent = `“${bg.pending.title}” (${bg.pending.lines} lines) wasn't sent yet.`;
  if (bg.lastResult) {
    $("last").hidden = false;
    $("last").innerHTML = "";
    const a = Object.assign(document.createElement("a"), { href: bg.lastResult.url, target: "_blank", textContent: bg.lastResult.title });
    $("last").append("Last saved: ", a, ` · ${bg.lastResult.action_items} action items`);
  }
}

$("approveBtn").onclick = async () => {
  // the server may be on a host the extension can't reach yet; ask Chrome (needs this click)
  const api = new URL(bg.approve.apiUrl).origin + "/*";
  const granted = await chrome.permissions.request({ origins: [api] }).catch(() => false);
  if (!granted && !(await chrome.permissions.contains({ origins: [api] }))) return say("The extension needs access to the server to save meetings.", true);
  const r = await send({ type: "approve" });
  r?.ok ? say("Connected. Go back to the website.") : say(r?.error || "Couldn't connect.", true);
  refresh();
};

$("connectBtn").onclick = () => chrome.tabs.create({ url: `${bg.webUrl}/extension` });

$("startBtn").onclick = async () => {
  const r = await toTab({ type: "meet-start" });
  if (!r?.ok) return say(r?.error || "Couldn't start. Reload the Meet tab and try again.", true);
  say("Taking notes. You can close this popup.");
  refresh();
};

$("stopBtn").onclick = async () => {
  $("stopBtn").disabled = true;
  say("Saving the meeting…");
  const r = await toTab({ type: "meet-stop", title: $("title").value.trim() });
  $("stopBtn").disabled = false;
  if (r?.ok) say("Saved. The meeting is opening in a new tab.");
  else say(r?.error || "Couldn't save.", true);
  refresh();
};

$("retryBtn").onclick = async () => {
  say("Sending…");
  const r = await send({ type: "retry" });
  r?.ok ? say("Saved.") : say(r?.error || "Still failing.", true);
  refresh();
};

$("saveSettings").onclick = async () => {
  await send({ type: "settings", apiUrl: $("apiUrl").value.trim().replace(/\/$/, ""), webUrl: $("webUrl").value.trim().replace(/\/$/, "") });
  say("Settings saved."); refresh();
};
$("localMode").onclick = async () => {
  await chrome.storage.local.set({ session: { local: true } });
  say("Using the local backend without login."); refresh();
};
$("disconnect").onclick = async () => { await send({ type: "disconnect" }); say("Disconnected."); refresh(); };

refresh();
ticker = setInterval(() => { if (meet?.recording) refresh(); }, 2000);
