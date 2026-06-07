"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AgentEvent,
  Note,
  SettingsView,
  fetchNotes,
  getSettings,
  streamChat,
  updateSettings,
} from "@/lib/api";

type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; text: string }
  | { kind: "error"; text: string };

export default function Home() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [settings, setSettings] = useState<SettingsView | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshNotes = useCallback(async () => {
    try {
      setNotes(await fetchNotes());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => setSettings(null));
    refreshNotes();
  }, [refreshNotes]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [items]);

  const send = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || running) return;
    setInput("");
    setRunning(true);
    setItems((prev) => [...prev, { kind: "user", text: prompt }, { kind: "assistant", text: "" }]);

    const onEvent = (e: AgentEvent) => {
      setItems((prev) => {
        const next = [...prev];
        const last = next.length - 1;
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
          if (typeof name === "string" && name.includes("save_note")) {
            refreshNotes();
          }
        } else if (e.type === "error") {
          next.push({ kind: "error", text: e.content });
        }
        void last;
        return next;
      });
      if (e.type === "tool_result" || e.type === "result") refreshNotes();
    };

    try {
      await streamChat(prompt, onEvent);
    } catch (err) {
      setItems((prev) => [...prev, { kind: "error", text: String(err) }]);
    } finally {
      setRunning(false);
      refreshNotes();
    }
  }, [input, running, refreshNotes]);

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b bg-white px-4 py-3">
        <h1 className="text-lg font-semibold">Opportunity Hunter</h1>
        <SettingsBadge settings={settings} onSaved={setSettings} />
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* Chat pane */}
        <section className="flex min-h-0 flex-1 flex-col border-r">
          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {items.length === 0 && (
              <p className="text-sm text-slate-500">
                Ask the agent something, e.g. &ldquo;Save a note titled
                &lsquo;Test&rsquo; with body &lsquo;hello from the agent&rsquo;.&rdquo;
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
            Canvas — Notes ({notes.length})
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {notes.length === 0 && (
              <p className="text-sm text-slate-400">
                Notes the agent saves will appear here.
              </p>
            )}
            {notes.map((n) => (
              <article key={n.id} className="rounded border bg-slate-50 p-3">
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
