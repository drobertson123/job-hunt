"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  Artifact,
  Capability,
  Note,
  Opportunity,
  SettingsView,
  exportArtifact,
  fetchArtifacts,
  fetchCapabilities,
  fetchNotes,
  fetchOpportunities,
  getSettings,
  invokeCapability,
  streamChat,
  updateSettings,
} from "@/lib/api";

type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; text: string }
  | { kind: "error"; text: string };

const BADGE: Record<Artifact["review_status"], string> = {
  draft: "bg-slate-200 text-slate-700",
  needs_review: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
};

export default function Home() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [caps, setCaps] = useState<Capability[]>([]);
  const [opps, setOpps] = useState<Opportunity[]>([]);
  const [selectedOpp, setSelectedOpp] = useState("");
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshCanvas = useCallback(async () => {
    try {
      const [n, a, o] = await Promise.all([
        fetchNotes(),
        fetchArtifacts(),
        fetchOpportunities(),
      ]);
      setNotes(n);
      setArtifacts(a);
      setOpps(o);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => setSettings(null));
    fetchCapabilities().then(setCaps).catch(() => setCaps([]));
    refreshCanvas();
  }, [refreshCanvas]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [items]);

  const makeOnEvent = useCallback(() => {
    return (e: AgentEvent) => {
      setItems((prev) => {
        const next = [...prev];
        if (e.type === "token") {
          // append to the trailing assistant bubble
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].kind === "assistant") {
              next[i] = { kind: "assistant", text: next[i].text + e.content };
              break;
            }
          }
        } else if (e.type === "tool_use") {
          let name = e.content;
          try {
            name = JSON.parse(e.content).name ?? e.content;
          } catch {
            /* keep raw */
          }
          next.push({ kind: "tool", text: `🔧 ${name}` });
          next.push({ kind: "assistant", text: "" });
        } else if (e.type === "error") {
          next.push({ kind: "error", text: e.content });
        }
        return next;
      });
      if (e.type === "tool_result" || e.type === "result") refreshCanvas();
    };
  }, [refreshCanvas]);

  const runStream = useCallback(
    async (
      bubble: string,
      start: (onEvent: (e: AgentEvent) => void) => Promise<void>,
    ) => {
      if (running) return;
      setRunning(true);
      setItems((prev) => [
        ...prev,
        { kind: "user", text: bubble },
        { kind: "assistant", text: "" },
      ]);
      try {
        await start(makeOnEvent());
      } catch (err) {
        setItems((prev) => [...prev, { kind: "error", text: String(err) }]);
      } finally {
        setRunning(false);
        refreshCanvas();
      }
    },
    [running, makeOnEvent, refreshCanvas],
  );

  const send = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt) return;
    setInput("");
    await runStream(prompt, (onEvent) => streamChat(prompt, onEvent));
  }, [input, runStream]);

  const invoke = useCallback(
    async (cap: Capability) => {
      const text = input.trim();
      if (cap.requires_input && !text) {
        setItems((prev) => [
          ...prev,
          {
            kind: "error",
            text: `"${cap.label}" needs input — paste it into the message box first.`,
          },
        ]);
        return;
      }
      if (cap.requires_input) setInput("");
      await runStream(`▶ ${cap.label}`, (onEvent) =>
        invokeCapability(
          cap.name,
          { opportunity_id: selectedOpp || undefined, input: text },
          onEvent,
        ),
      );
    },
    [input, selectedOpp, runStream],
  );

  const doExport = useCallback(async (artifactId: number, format: "docx" | "pdf") => {
    try {
      const r = await exportArtifact(artifactId, format);
      window.location.assign(r.download_url);
    } catch (err) {
      setItems((prev) => [...prev, { kind: "error", text: String(err) }]);
    }
  }, []);

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b bg-white px-4 py-3">
        <h1 className="text-lg font-semibold">Opportunity Hunter</h1>
        <SettingsBadge settings={settings} onSaved={setSettings} />
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Chat pane */}
        <section className="flex min-h-0 flex-1 flex-col border-r">
          {/* Capability bar */}
          <div className="flex flex-wrap items-center gap-2 border-b bg-slate-50 px-3 py-2">
            <select
              className="rounded border px-2 py-1 text-xs"
              value={selectedOpp}
              onChange={(e) => setSelectedOpp(e.target.value)}
            >
              <option value="">— opportunity —</option>
              {opps.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.organization ? `${o.organization} — ${o.title}` : o.title}
                </option>
              ))}
            </select>
            {caps.map((c) => (
              <button
                key={c.name}
                title={c.description}
                className="rounded bg-slate-200 px-2 py-1 text-xs font-medium text-slate-800 hover:bg-slate-300 disabled:opacity-40"
                onClick={() => invoke(c)}
                disabled={running || (c.requires_opportunity && !selectedOpp)}
              >
                {c.label}
              </button>
            ))}
          </div>

          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {items.length === 0 && (
              <p className="text-sm text-slate-500">
                Message the agent, or pick an opportunity and press a capability
                button. &ldquo;Add by paste&rdquo; uses whatever you&rsquo;ve typed
                in the message box.
              </p>
            )}
            {items.map((it, i) => (
              <Bubble key={i} item={it} />
            ))}
          </div>
          <div className="flex gap-2 border-t bg-white p-3">
            <input
              className="flex-1 rounded border px-3 py-2 text-sm"
              placeholder="Message the agent…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              disabled={running}
            />
            <button
              className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={send}
              disabled={running || !input.trim()}
            >
              {running ? "…" : "Send"}
            </button>
          </div>
        </section>

        {/* Canvas pane */}
        <section className="flex min-h-0 flex-1 flex-col bg-white">
          <div className="border-b px-4 py-2 text-sm font-medium text-slate-600">
            Canvas — Artifacts ({artifacts.length}) · Notes ({notes.length})
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {artifacts.length === 0 && notes.length === 0 && (
              <p className="text-sm text-slate-400">
                Artifacts and notes the agent saves will appear here.
              </p>
            )}
            {artifacts.map((a) => (
              <article key={`a-${a.id}`} className="rounded border bg-slate-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{a.title}</h3>
                  <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                    {a.kind} v{a.version}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${BADGE[a.review_status]}`}
                  >
                    {a.review_status.replace("_", " ")}
                  </span>
                  {(["docx", "pdf"] as const).map((fmt) => (
                    <button
                      key={fmt}
                      className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-slate-600 hover:bg-slate-200"
                      onClick={() => doExport(a.id, fmt)}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
                {a.provenance && (
                  <p className="mt-0.5 text-[11px] text-slate-400">{a.provenance}</p>
                )}
                <p className="mt-1 max-h-40 overflow-hidden whitespace-pre-wrap text-sm text-slate-700">
                  {a.body}
                </p>
              </article>
            ))}
            {notes.map((n) => (
              <article key={`n-${n.id}`} className="rounded border bg-slate-50 p-3">
                <h3 className="text-sm font-semibold">{n.title}</h3>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{n.body}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function Bubble({ item }: { item: ChatItem }) {
  if (item.kind === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
        {item.text}
      </div>
    );
  }
  if (item.kind === "tool") {
    return <div className="text-xs font-medium text-amber-700">{item.text}</div>;
  }
  if (item.kind === "error") {
    return (
      <div className="max-w-[85%] rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {item.text}
      </div>
    );
  }
  if (!item.text) return null;
  return (
    <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-slate-100 px-3 py-2 text-sm">
      {item.text}
    </div>
  );
}

function SettingsBadge({
  settings,
  onSaved,
}: {
  settings: SettingsView | null;
  onSaved: (s: SettingsView) => void;
}) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const configured = settings?.anthropic_key_configured;

  const save = async () => {
    const body: Record<string, string> = {};
    if (key.trim()) body.anthropic_api_key = key.trim();
    if (model.trim()) body.agent_model = model.trim();
    const updated = await updateSettings(body);
    onSaved(updated);
    setKey("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        className={`rounded px-3 py-1 text-xs font-medium ${
          configured ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
        }`}
        onClick={() => setOpen((o) => !o)}
      >
        {configured ? `✓ ${settings?.agent_model}` : "⚠ Configure API key"}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-80 space-y-2 rounded border bg-white p-3 shadow">
          <label className="block text-xs font-medium text-slate-600">Anthropic API key</label>
          <input
            type="password"
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder={configured ? "••••• (set)" : "sk-ant-…"}
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <label className="block text-xs font-medium text-slate-600">Agent model</label>
          <input
            className="w-full rounded border px-2 py-1 text-sm"
            placeholder={settings?.agent_model ?? "claude-sonnet-4-6"}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <button
            className="w-full rounded bg-slate-900 py-1.5 text-sm font-medium text-white"
            onClick={save}
          >
            Save
          </button>
          <p className="text-[11px] text-slate-400">
            Stored locally. If left blank, the local Claude CLI&rsquo;s own auth is used.
          </p>
        </div>
      )}
    </div>
  );
}
