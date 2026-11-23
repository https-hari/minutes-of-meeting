"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorNote, PageHeader } from "@/components/ui";
import { api, type AgentReply, type MemoryFact } from "@/lib/api";

type Turn = { role: "user"; text: string } | { role: "agent"; reply: AgentReply } | { role: "error"; text: string };

const EXAMPLES = ["What does Daniel still have open?", "Why did we move the launch?", "I'm Bob. Remember that I own the launch timeline.", "What are my open tasks?"];

const TOOL_LABEL: Record<string, string> = {
  search_meetings: "Searched transcripts", list_meetings: "Listed meetings", get_action_items: "Looked up action items",
  get_decisions: "Looked up decisions", update_action_item: "Updated a task", save_memory: "Saved to memory",
};

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversation, setConversation] = useState<number | null>(null);
  const [memories, setMemories] = useState<MemoryFact[]>([]);
  const end = useRef<HTMLDivElement>(null);

  const loadMemories = () => api.memories().then(setMemories).catch(() => {});
  useEffect(() => { loadMemories(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, busy]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text }]);
    setBusy(true);
    try {
      const reply = await api.chat(text, conversation);
      setConversation(reply.conversation_id);
      setTurns((t) => [...t, { role: "agent", reply }]);
      if (reply.steps.some((s) => s.tool === "save_memory")) loadMemories();
    } catch (e) {
      setTurns((t) => [...t, { role: "error", text: (e as Error).message }]);
    }
    setBusy(false);
  }

  async function forget(id: number) {
    setMemories((m) => m.filter((x) => x.id !== id));
    await api.forget(id).catch(loadMemories);
  }

  return (
    <>
      <PageHeader title="Assistant" sub="Ask about tasks, decisions or anything said. It looks things up and can update task status."
        action={turns.length > 0 ? <button onClick={() => { setTurns([]); setConversation(null); }} className="btn-ghost">New conversation</button> : undefined} />
      <div className="grid gap-8 lg:grid-cols-[1fr_260px]">
        <div className="flex min-h-[60vh] flex-col">
          <div className="flex-1 space-y-5" aria-live="polite">
            {turns.length === 0 && (
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((e) => <button key={e} onClick={() => send(e)} className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-muted hover:border-accent hover:text-ink">{e}</button>)}
              </div>
            )}
            {turns.map((t, i) =>
              t.role === "user" ? (
                <p key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-accent-ink">{t.text}</p>
              ) : t.role === "error" ? (
                <ErrorNote key={i} message={t.text} />
              ) : (
                <div key={i} className="max-w-[92%]">
                  {t.reply.steps.length > 0 && (
                    <ul className="mb-2 flex flex-wrap gap-1.5">
                      {t.reply.steps.map((s, j) => (
                        <li key={j} title={s.arguments} className={`rounded-md border px-2 py-0.5 text-xs ${s.ok ? "border-line text-muted" : "border-bad/40 text-bad"}`}>
                          {TOOL_LABEL[s.tool] ?? s.tool} · {s.summary}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="card whitespace-pre-wrap px-4 py-3 leading-relaxed">{t.reply.answer}</div>
                </div>
              ),
            )}
            {busy && <p className="text-sm text-muted">Looking it up…</p>}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="sticky bottom-4 mt-6 flex gap-2 rounded-xl border border-line bg-surface p-2 shadow-sm">
            <input aria-label="Message" className="flex-1 bg-transparent px-2 text-sm focus:outline-none" placeholder="Ask about your meetings…"
              value={input} onChange={(e) => setInput(e.target.value)} />
            <button disabled={busy || !input.trim()} className="btn-primary">Send</button>
          </form>
        </div>

        <aside className="lg:sticky lg:top-10 lg:self-start">
          <h2 className="text-sm font-semibold">What it remembers about you</h2>
          <p className="mt-1 text-xs text-muted">Saved when you tell it something lasting. Used in every conversation.</p>
          {memories.length === 0 ? <p className="mt-3 text-sm text-muted">Nothing yet.</p> : (
            <ul className="mt-3 space-y-2">
              {memories.map((m) => (
                <li key={m.id} className="group flex items-start justify-between gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm">
                  <span>{m.fact}</span>
                  <button onClick={() => forget(m.id)} aria-label={`Forget: ${m.fact}`} className="text-xs text-muted hover:text-bad">Forget</button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </>
  );
}
