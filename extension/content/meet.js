// Google Meet: read the live captions while recording, with real speaker names.
//
// Meet's class names are generated and change often, so this relies on structure:
// the captions panel is a role="region" whose label mentions captions, and each
// caption block shows the speaker's name on its first line and the words after it.
// If Meet changes this, only findRegion() / readBlocks() need updating.

(() => {
  const STORE_KEY = "live:" + location.pathname;   // autosave per call
  let recording = false;
  let lines = [];                                  // [{speaker, text}]
  const indexOf = new WeakMap();                   // caption element -> index in lines
  let timer = null, saver = null, startedAt = null;
  let badge = null;

  const CAPTION_LABEL = /caption|subtit|untertitel|sous-titre|legenda|字幕|자막/i;

  function findRegion() {
    return [...document.querySelectorAll('[role="region"]')]
      .find((r) => CAPTION_LABEL.test(r.getAttribute("aria-label") || ""));
  }

  function readBlocks(region) {
    // a caption block = the element holding one avatar image plus name + text
    const blocks = [...region.querySelectorAll("img")].map((img) => {
      let el = img;
      while (el.parentElement && el.parentElement !== region && el.innerText.trim().split("\n").length < 2) el = el.parentElement;
      return el;
    });
    const unique = [...new Set(blocks)];
    const source = unique.length ? unique : [...region.children];
    return source.map((el) => {
      const parts = el.innerText.split("\n").map((s) => s.trim()).filter(Boolean);
      if (parts.length < 2) return null;
      return { el, speaker: parts[0].slice(0, 100), text: parts.slice(1).join(" ") };
    }).filter(Boolean);
  }

  function poll() {
    const region = findRegion();
    setHint(region ? "" : "Turn on captions (CC, or press C) so Minutes can hear the meeting.");
    if (!region) return;
    for (const b of readBlocks(region)) {
      const i = indexOf.get(b.el);
      if (i === undefined) {
        indexOf.set(b.el, lines.length);
        lines.push({ speaker: b.speaker, text: b.text });
      } else if (b.text !== lines[i].text) {
        // Meet keeps rewriting the current line as the person talks; keep the latest version.
        // If the start changed completely, the block was reused for something new.
        const old = lines[i].text;
        if (b.text.startsWith(old.slice(0, 15)) || old.length < 15) lines[i].text = b.text;
        else { indexOf.set(b.el, lines.length); lines.push({ speaker: b.speaker, text: b.text }); }
      }
    }
    updateBadge();
  }

  function meetingTitle() {
    const t = document.title.replace(/^Meet\s*[-–—:]\s*/i, "").trim();
    return t && !/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(t) ? t : `Google Meet · ${new Date().toLocaleDateString()}`;
  }

  // ── visible recording badge (always on screen while capturing) ──────
  function showBadge() {
    badge = document.createElement("div");
    badge.className = "minutes-badge";
    badge.setAttribute("role", "status");
    badge.innerHTML = '<span class="minutes-dot" aria-hidden="true"></span><span class="minutes-text"></span><button type="button">Stop</button><p class="minutes-hint"></p>';
    badge.querySelector("button").onclick = stop;
    document.body.appendChild(badge);
    updateBadge();
  }
  function updateBadge() {
    if (!badge) return;
    const mins = Math.floor((Date.now() - startedAt) / 60000);
    badge.querySelector(".minutes-text").textContent = `Minutes is taking notes · ${mins} min · ${lines.length} lines`;
  }
  function setHint(t) { if (badge) badge.querySelector(".minutes-hint").textContent = t; }

  // ── start / stop ─────────────────────────────────────────────────────
  async function start() {
    if (recording) return status();
    const saved = (await chrome.storage.local.get(STORE_KEY))[STORE_KEY];
    lines = saved?.lines || [];                     // resume after a page reload
    startedAt = saved?.startedAt || Date.now();
    recording = true;
    showBadge();
    poll();
    timer = setInterval(poll, 1000);
    saver = setInterval(() => chrome.storage.local.set({ [STORE_KEY]: { lines, startedAt } }), 5000);
    return status();
  }

  async function stop(title) {
    if (!recording) return { ok: false, error: "Not recording." };
    clearInterval(timer); clearInterval(saver);
    poll();
    recording = false;
    const captions = lines.filter((l) => l.text.trim());
    if (!captions.length) {
      setHint("No captions were captured. Were captions turned on?");
      setTimeout(() => badge?.remove(), 4000);
      return { ok: false, error: "No captions were captured. Turn on captions in Meet and try again." };
    }
    badge.querySelector(".minutes-text").textContent = "Sending to Minutes…";
    badge.querySelector("button").remove();
    const r = await chrome.runtime.sendMessage({ type: "finish", title: typeof title === "string" && title ? title : meetingTitle(), captions });
    if (r?.ok) {
      await chrome.storage.local.remove(STORE_KEY);
      badge.querySelector(".minutes-text").textContent = "Saved. Opening the meeting in Minutes.";
      setTimeout(() => badge?.remove(), 3000);
    } else {
      badge.querySelector(".minutes-text").textContent = "Couldn't send. Use Retry in the extension.";
      setHint(r?.error || "");
    }
    return r;
  }

  function status() {
    return { ok: true, onMeet: true, recording, lines: lines.length, startedAt, title: meetingTitle(), captionsOn: !!findRegion() };
  }

  chrome.runtime.onMessage.addListener((msg, _s, reply) => {
    (async () => {
      if (msg.type === "meet-status") return status();
      if (msg.type === "meet-start") return start();
      if (msg.type === "meet-stop") return stop(msg.title);
      return { ok: false };
    })().then(reply, (e) => reply({ ok: false, error: e.message }));
    return true;
  });
})();
