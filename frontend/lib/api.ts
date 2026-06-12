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

export type Artifact = {
  id: number;
  title: string;
  body: string;
  kind: string;
  opportunity_id: string | null;
  provenance: string | null;
  version: number;
  review_status: "draft" | "needs_review" | "approved";
  created_at: string;
};

export type Opportunity = {
  id: string;
  title: string;
  organization: string | null;
  stage: string;
};

export type Capability = {
  name: string;
  label: string;
  description: string;
  requires_opportunity: boolean;
  requires_input: boolean;
};

export type SettingsView = {
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  agent_model: string;
  default_agent_model: string;
  deep_analysis_model: string;
};

/** POST JSON to an SSE endpoint and dispatch each agent event. */
async function streamSSE(
  url: string,
  body: unknown,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`${url} failed: ${res.status}`);
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

/** POST a prompt and stream agent events. */
export async function streamChat(
  prompt: string,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE("/api/chat", { prompt }, onEvent, signal);
}

/** Invoke a named capability (templated skill run) and stream its events. */
export async function invokeCapability(
  name: string,
  body: { opportunity_id?: string; input?: string },
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(
    `/api/capabilities/${encodeURIComponent(name)}`,
    body,
    onEvent,
    signal,
  );
}

export async function fetchCapabilities(): Promise<Capability[]> {
  const res = await fetch("/api/capabilities");
  if (!res.ok) throw new Error(`capabilities failed: ${res.status}`);
  return res.json();
}

export async function fetchOpportunities(): Promise<Opportunity[]> {
  const res = await fetch("/api/opportunities");
  if (!res.ok) throw new Error(`opportunities failed: ${res.status}`);
  return res.json();
}

export async function fetchArtifacts(): Promise<Artifact[]> {
  const res = await fetch("/api/artifacts");
  if (!res.ok) throw new Error(`artifacts failed: ${res.status}`);
  return res.json();
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
