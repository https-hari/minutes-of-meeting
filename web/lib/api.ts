import { supabase } from "./supabase";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Status = "open" | "in_progress" | "done";
export type MeetingSummary = { id: number; title: string; date: string; summary: string | null; duration: number | null; open_items: number };
export type ActionItem = { id: number; description: string; status: Status; deadline: string | null; owner: string | null; meeting_id?: number; meeting?: string };
export type Decision = { id: number; description: string; context: string | null };
export type MeetingDetail = {
  id: number; title: string; date: string; summary: string | null; duration: number | null; transcript: string | null;
  participants: string[]; action_items: ActionItem[]; decisions: Decision[];
};
export type Source = { chunk_id: number; meeting_id: number; meeting_title: string; speaker: string | null; text: string; score: number; found_by: Record<string, number> };
export type QueryResult = { question: string; answer: string; mode: string; sources: Source[] };
export type AgentStep = { tool: string; arguments: string; ok: boolean; summary: string };
export type AgentReply = { answer: string; conversation_id: number; steps: AgentStep[]; memories_used: string[] };
export type MemoryFact = { id: number; fact: string; created_at: string };
export type IngestResult = { meeting_id: number; title: string; participants: number; action_items: number; decisions: number; chunks: number };

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function accessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(`Can't reach the server at ${API_URL}. Is the backend running?`, 0);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail
      : Array.isArray(body.detail) ? body.detail.map((d: { msg: string }) => d.msg).join("; ")
      : `Request failed (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return body.data as T;
}

const json = (data: unknown) => JSON.stringify(data);

export const api = {
  me: () => request<{ id: string; email: string | null }>("/me"),
  meetings: () => request<MeetingSummary[]>("/meetings"),
  meeting: (id: number) => request<MeetingDetail>(`/meetings/${id}`),
  deleteMeeting: (id: number) => request<{ id: number }>(`/meetings/${id}`, { method: "DELETE" }),
  addTranscript: (title: string, transcript: string) =>
    request<IngestResult>("/meetings/transcript", { method: "POST", body: json({ title, transcript }) }),
  addAudio: (title: string, file: File) => {
    const form = new FormData();
    form.set("title", title);
    form.set("file", file);
    return request<IngestResult>("/meetings/audio", { method: "POST", body: form });
  },
  actionItems: (status?: Status) => request<ActionItem[]>(`/action-items${status ? `?status=${status}` : ""}`),
  setStatus: (id: number, status: Status) =>
    request<{ id: number; status: Status }>(`/action-items/${id}/status?status=${status}`, { method: "PATCH" }),
  query: (question: string, mode: string, meeting_id?: number) =>
    request<QueryResult>("/query", { method: "POST", body: json({ question, mode, meeting_id }) }),
  chat: (message: string, conversation_id?: number | null) =>
    request<AgentReply>("/agent/chat", { method: "POST", body: json({ message, conversation_id }) }),
  memories: () => request<MemoryFact[]>("/agent/memories"),
  forget: (id: number) => request<{ id: number }>(`/agent/memories/${id}`, { method: "DELETE" }),
};
