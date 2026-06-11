// Minimal API client. In dev, /api is proxied to FastAPI (:8000) via Next
// rewrites; in prod the app is served by FastAPI on the same origin.

export type AgentEvent = {
  run_id: string;
  seq: number;
  type: "status" | "token" | "tool_use" | "tool_result" | "result" | "error";
  content: string;
};

export type Note = {
  id: number;
  title: string;
  body: string;
  run_id: string | null;
  created_at: string;
};

export type SettingsView = {
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  agent_model: string;
  default_agent_model: string;
  deep_analysis_model: string;
};

/** POST a prompt and stream agent events (SSE over fetch). */
export async function streamChat(
  prompt: string,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`chat failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    // SSE frames are separated by a blank line.
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data:")) {
          const json = line.slice(5).trim();
          if (json) onEvent(JSON.parse(json) as AgentEvent);
        }
      }
    }
  }
}

export async function fetchNotes(runId?: string): Promise<Note[]> {
  const url = runId ? `/api/notes?run_id=${encodeURIComponent(runId)}` : "/api/notes";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`notes failed: ${res.status}`);
  return res.json();
}

export async function getSettings(): Promise<SettingsView> {
  const res = await fetch("/api/settings");
  if (!res.ok) throw new Error(`settings failed: ${res.status}`);
  return res.json();
}

export async function updateSettings(
  body: Partial<{ anthropic_api_key: string; openai_api_key: string; agent_model: string }>,
): Promise<SettingsView> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`settings update failed: ${res.status}`);
  return res.json();
}
